import os
import json
import time
import logging
import requests
from groq import Groq, RateLimitError, APIError

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# Initialize Groq Client
client = Groq()

# Model Configurations
PRIMARY_MODEL = "llama-3.3-70b-versatile"
FALLBACK_MODEL = "llama-3.1-8b-instant"

# Mailgun Environment Variables
MAILGUN_API_KEY = os.getenv("MAILGUN_API_KEY")
MAILGUN_DOMAIN = os.getenv("MAILGUN_DOMAIN")
ALERT_RECIPIENT_EMAIL = os.getenv("ALERT_RECIPIENT_EMAIL", "callcentre.wong@gmail.com")

# Updated Scoring Threshold
MINIMUM_SCORE_THRESHOLD = 80

# Roles and Keywords to Exclude locally
EXCLUDE_KEYWORDS = [
    "software engineer", "developer", "backend engineer", 
    "frontend engineer", "fullstack", "data engineer", "devops",
    "qa engineer", "systems engineer", "cloud architect"
]

def send_mailgun_email(subject: str, text_body: str):
    """Sends an email notification via Mailgun API."""
    if not MAILGUN_API_KEY or not MAILGUN_DOMAIN:
        logging.warning("Mailgun credentials not configured. Skipping email dispatch.")
        return False

    url = f"https://api.mailgun.net/v3/{MAILGUN_DOMAIN}/messages"
    try:
        response = requests.post(
            url,
            auth=("api", MAILGUN_API_KEY),
            data={
                "from": f"Job Pipeline Bot <mailgun@{MAILGUN_DOMAIN}>",
                "to": [ALERT_RECIPIENT_EMAIL],
                "subject": subject,
                "text": text_body
            },
            timeout=10
        )
        response.raise_for_status()
        logging.info(f"Mailgun email sent successfully: '{subject}'")
        return True
    except Exception as e:
        logging.error(f"Failed to send Mailgun email: {e}")
        return False

def is_title_in_target_scope(job_title: str) -> bool:
    """Pre-screens job titles locally to preserve LLM API quota."""
    title_lower = job_title.lower()
    for kw in EXCLUDE_KEYWORDS:
        if kw in title_lower:
            return False
    return True

def call_groq_with_backoff(prompt_messages, max_retries=5, base_delay=3.0):
    """
    Executes Groq API completion with exponential backoff for rate limits (429)
    and automatic model fallback.
    """
    models_to_try = [PRIMARY_MODEL, FALLBACK_MODEL]

    for model in models_to_try:
        logging.info(f"Attempting evaluation with model: {model}")
        for attempt in range(max_retries):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=prompt_messages,
                    temperature=0.1,
                    max_tokens=600
                )
                return response.choices[0].message.content

            except RateLimitError as e:
                delay = base_delay * (2 ** attempt)
                logging.warning(
                    f"Rate limit 429 on '{model}'. Retrying in {delay:.1f}s (Attempt {attempt + 1}/{max_retries})..."
                )
                time.sleep(delay)

            except APIError as e:
                if "429" in str(e):
                    delay = base_delay * (2 ** attempt)
                    logging.warning(
                        f"API Error 429 on '{model}'. Retrying in {delay:.1f}s (Attempt {attempt + 1}/{max_retries})..."
                    )
                    time.sleep(delay)
                else:
                    logging.error(f"Unrecoverable API Error on '{model}': {e}")
                    break

        logging.warning(f"Exceeded max retries for model '{model}'. Trying fallback if available...")

    raise RuntimeError("All models and retries failed due to API rate limits or errors.")

def evaluate_single_job(job_id: str, job_data: dict) -> dict:
    """Evaluates an individual job posting against the target candidate profile."""
    title = job_data.get("title", "")
    company = job_data.get("company", "")

    if not is_title_in_target_scope(title):
        logging.info(f"Skipping '{title}' at {company} (Title outside target scope).")
        return {
            "title": title,
            "company": company,
            "score": 0,
            "assessment": "Skipped: Title outside target scope.",
            "evaluated": True
        }

    system_prompt = (
        "You are an executive talent acquisition assistant evaluating jobs for a candidate with "
        "20+ years of experience in Customer Service, Contact Centre Management, Technical Support, "
        "Service Governance, CRM/ERP Operations, and Operational Excellence in APAC/Singapore.\n\n"
        "Evaluation Rules:\n"
        "1. Score from 0 to 100 based on alignment with Customer Service Leadership, Contact Centre Management, "
        "Operational Excellence, Regional Operations, or Service Delivery leadership roles.\n"
        "2. Only assign scores of 80 to 100 for strong regional leadership matches (Regional Manager, Head, Executive, or Director levels).\n"
        "3. Explicitly output the final score in the exact format: 'Score: [number]/100' on the first line."
    )
    user_prompt = f"Title: {title}\nCompany: {company}\nDetails: {json.dumps(job_data)}"

    prompt_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    try:
        assessment_text = call_groq_with_backoff(prompt_messages)
        
        score = 0
        if "Score:" in assessment_text:
            try:
                score_str = assessment_text.split("Score:")[1].split("/")[0].strip()
                score = int(score_str)
            except Exception:
                score = 0

        return {
            "title": title,
            "company": company,
            "score": score,
            "assessment": assessment_text,
            "evaluated": True
        }

    except Exception as e:
        logging.error(f"Failed to evaluate job {job_id}: {e}")
        return {
            "title": title,
            "company": company,
            "score": 0,
            "assessment": f"API Error: {str(e)}",
            "evaluated": False
        }

def run_evaluation_pipeline(input_jobs: dict, output_file_path: str = "evaluation_report.json"):
    """Runs the full evaluation pipeline and dispatches digest/alert emails."""
    results = {}
    total_jobs = len(input_jobs)
    failed_count = 0
    qualifying_jobs = []

    logging.info(f"Starting pipeline evaluation for {total_jobs} jobs...")

    for idx, (job_id, job_data) in enumerate(input_jobs.items(), 1):
        logging.info(f"Processing [{idx}/{total_jobs}]: {job_id}")
        
        eval_result = evaluate_single_job(job_id, job_data)
        results[job_id] = eval_result

        if not eval_result.get("evaluated", False):
            failed_count += 1

        if eval_result.get("score", 0) >= MINIMUM_SCORE_THRESHOLD:
            qualifying_jobs.append(eval_result)

        time.sleep(1.5)

    # Save final JSON output
    with open(output_file_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    # Alert Trigger 1: Send System Health Alert if error rate exceeds 20%
    failure_rate = (failed_count / total_jobs) if total_jobs > 0 else 0
    if failure_rate > 0.20:
        alert_msg = (
            f"WARNING: Executive Job Pipeline completed with high error rate!\n\n"
            f"Total Jobs Processed: {total_jobs}\n"
            f"Failed Evaluated Jobs: {failed_count}\n"
            f"Failure Rate: {failure_rate * 100:.1f}%\n\n"
            f"Please check your API quota or model status."
        )
        send_mailgun_email("⚠️ Pipeline Health Alert: High Evaluation Failure Rate", alert_msg)

    # Alert Trigger 2: Send Email Digest for high matches (80+)
    if qualifying_jobs:
        digest_body = f"Found {len(qualifying_jobs)} high-match job opportunities (Score >= {MINIMUM_SCORE_THRESHOLD}):\n\n"
        for job in qualifying_jobs:
            digest_body += f"• {job['title']} at {job['company']} (Score: {job['score']}/100)\n"
            digest_body += f"  Summary: {job['assessment'][:200]}...\n\n"
        
        send_mailgun_email(f"🎯 Daily Executive Job Match Digest ({len(qualifying_jobs)} Found)", digest_body)
    else:
        logging.info(f"No jobs met the minimum score threshold of {MINIMUM_SCORE_THRESHOLD}+ for digest dispatch.")

    logging.info(f"Evaluation pipeline completed. Output saved to {output_file_path}")
    return results

if __name__ == "__main__":
    input_file = "raw_jobs.json"
    if os.path.exists(input_file):
        with open(input_file, "r", encoding="utf-8") as f:
            raw_jobs = json.load(f)
        run_evaluation_pipeline(raw_jobs)
    else:
        logging.warning(f"No '{input_file}' found. Running dry run check...")
