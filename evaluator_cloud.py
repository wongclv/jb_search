import os
import json
import time
import logging
from groq import Groq, RateLimitError, APIError

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# Initialize Groq Client
client = Groq()

# Model Fallback Configuration
PRIMARY_MODEL = "llama-3.3-70b-versatile"
FALLBACK_MODEL = "llama-3.1-8b-instant"

# Keywords for local pre-filtering to prevent wasting LLM quota
EXCLUDE_KEYWORDS = [
    "software engineer", "developer", "backend engineer", 
    "frontend engineer", "fullstack", "data engineer", "devops"
]

def is_title_in_target_scope(job_title: str) -> bool:
    """Pre-screen job titles locally to avoid unnecessary API calls."""
    title_lower = job_title.lower()
    for kw in EXCLUDE_KEYWORDS:
        if kw in title_lower:
            return False
    return True

def call_groq_with_backoff(prompt_messages, max_retries=5, base_delay=3.0):
    """
    Executes Groq API completion with exponential backoff for rate limits (429)
    and automatic fallback to a secondary model if retries expire.
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
                    f"Rate limit 429 encountered on model '{model}'. "
                    f"Retrying in {delay:.1f}s (Attempt {attempt + 1}/{max_retries})..."
                )
                time.sleep(delay)

            except APIError as e:
                if "429" in str(e):
                    delay = base_delay * (2 ** attempt)
                    logging.warning(
                        f"API Error 429 encountered on model '{model}'. "
                        f"Retrying in {delay:.1f}s (Attempt {attempt + 1}/{max_retries})..."
                    )
                    time.sleep(delay)
                else:
                    logging.error(f"Unrecoverable API Error on model '{model}': {e}")
                    break  # Try fallback model if available

        logging.warning(f"Exceeded max retries for model '{model}'. Trying fallback if available...")

    raise RuntimeError("All models and retries failed due to API rate limits or errors.")


def evaluate_single_job(job_id: str, job_data: dict) -> dict:
    """
    Evaluates an individual job posting safely with rate-limit handling and pre-screening.
    """
    title = job_data.get("title", "")
    company = job_data.get("company", "")

    # Local Pre-screening Check
    if not is_title_in_target_scope(title):
        logging.info(f"Skipping '{title}' at {company} (Title outside target scope).")
        return {
            "title": title,
            "company": company,
            "score": 0,
            "assessment": "Skipped: Title outside target scope.",
            "evaluated": True
        }

    # Prepare LLM Prompt
    system_prompt = (
        "You are an executive job matching assistant. Evaluate the job posting "
        "and return a suitability score from 0 to 100 alongside a brief assessment."
    )
    user_prompt = f"Title: {title}\nCompany: {company}\nDetails: {json.dumps(job_data)}"

    prompt_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    try:
        assessment_text = call_groq_with_backoff(prompt_messages)
        
        # Placeholder score parsing (adjust according to your output parsing logic)
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
    """
    Runs the full evaluation pipeline across all raw job listings.
    """
    results = {}
    total_jobs = len(input_jobs)
    logging.info(f"Starting pipeline evaluation for {total_jobs} jobs...")

    for idx, (job_id, job_data) in enumerate(input_jobs.items(), 1):
        logging.info(f"Processing [{idx}/{total_jobs}]: {job_id}")
        
        eval_result = evaluate_single_job(job_id, job_data)
        results[job_id] = eval_result

        # Inter-request pacing delay to prevent hitting RPM limits
        time.sleep(1.5)

    # Save final report to JSON
    with open(output_file_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    logging.info(f"Evaluation finished! Results saved to {output_file_path}")
    return results


if __name__ == "__main__":
    # Example execution entry point
    input_file = "raw_jobs.json"
    if os.path.exists(input_file):
        with open(input_file, "r", encoding="utf-8") as f:
            raw_jobs = json.load(f)
        run_evaluation_pipeline(raw_jobs)
    else:
        logging.warning(f"No '{input_file}' found. Script ready for cloud execution.")
