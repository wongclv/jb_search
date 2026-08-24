import os
import json
import csv
import time
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Configuration & Paths ---
CSV_FILE_PATH = "scraped_jobs_v3.csv"
PROGRESS_FILE_PATH = "evaluator_progress.json"
OUTPUT_REPORT_PATH = "evaluation_report.json"

MAX_JOBS_PER_RUN = 40
MAX_WORKERS = 4

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
MAILGUN_API_KEY = os.environ.get("MAILGUN_API_KEY")
MAILGUN_DOMAIN = os.environ.get("MAILGUN_DOMAIN")
RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL", "callcentre.wong@gmail.com")

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL_NAME = "llama-3.3-70b-versatile"

CANDIDATE_PROFILE = """
[CANDIDATE DOSSIER]: Wong Choong Leong Vincent (Singaporean National)
- Seniority: 20+ Years Senior APAC Executive Leadership (Director, Head, VP, GM).
- Core Expertise: APAC Regional Operations, Customer Experience (CX) Leadership, Large-Scale Contact Center Management, Service Governance, P&L & COGS/OPEX Reduction.
- Domain & Compliance: Medical Devices, Healthcare Operations, QA/QC/CAPA Compliance (Align Technology, Johnson & Johnson), COPC Coordinator, 6 Sigma Green Belt.
- Technology & Systems: Omnichannel Architecture, CRM/ERP Modernization (Salesforce SFDC, Twilio, Genesys).
- Strict Exclusion: Entry/Mid-level roles, pure IT Software Development/Engineering, non-leadership individual contributor roles.
"""

SYSTEM_PROMPT = f"""
You are an expert AI Executive Recruiter scoring vacancies for an elite operations leader.

{CANDIDATE_PROFILE}

Analyze the job title, company, and description. Provide:
1. A Score (0 to 100) based on alignment with Vincent's executive regional operations, contact center, and compliance profile.
2. A concise 2-3 sentence assessment explaining why it matches or lacks fit.

Return output strictly in JSON:
{{
  "score": <integer 0-100>,
  "assessment": "<string>"
}}
"""

def load_progress():
    if Path(PROGRESS_FILE_PATH).exists():
        with open(PROGRESS_FILE_PATH, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_progress(progress_data):
    with open(PROGRESS_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(progress_data, f, indent=2, ensure_ascii=False)

def evaluate_single_job(job, job_id):
    title = job.get("title", "Unknown Title")
    company = job.get("company", "Unknown Company")
    job_url = job.get("job_url") or job.get("url") or "#"
    description = job.get("description", "")

    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is not set in secrets.")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    user_content = f"Job Title: {title}\nCompany: {company}\nDescription:\n{description[:2000]}"
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"}
    }

    for attempt in range(3):
        try:
            response = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=20)
            if response.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            response.raise_for_status()
            res_data = response.json()
            parsed = json.loads(res_data["choices"][0]["message"]["content"])
            return job_id, {
                "title": title,
                "company": company,
                "url": job_url,
                "score": parsed.get("score", 0),
                "assessment": parsed.get("assessment", "No assessment provided."),
                "evaluated": True
            }
        except Exception as e:
            if attempt == 2:
                return job_id, {
                    "title": title,
                    "company": company,
                    "url": job_url,
                    "score": 0,
                    "assessment": f"Failed evaluation: {str(e)}",
                    "evaluated": True
                }
            time.sleep(2)

def send_mailgun_digest(top_jobs):
    if not MAILGUN_API_KEY or not MAILGUN_DOMAIN:
        print("⚠️ Mailgun API key or Domain missing. Skipping email dispatch.")
        return

    print(f"📧 Sending daily email digest to {RECIPIENT_EMAIL}...")
    
    body = "🚀 Daily AI Job Match Digest\n"
    body += "Here are your top-scoring executive opportunities evaluated today:\n"
    body += "=" * 50 + "\n\n"

    for idx, job in enumerate(top_jobs, 1):
        body += f"{idx}. {job['title']}\n"
        body += f"Company: {job['company']}\n"
        body += f"Match Score: {job['score']} / 100\n"
        body += f"AI Analysis:\n{job['assessment']}\n"
        body += f"🔗 Direct Application Link:\n{job['url']}\n"
        body += "=" * 50 + "\n\n"

    try:
        res = requests.post(
            f"https://api.mailgun.net/v3/{MAILGUN_DOMAIN}/messages",
            auth=("api", MAILGUN_API_KEY),
            data={
                "from": f"AI Job Hunter <mailgun@{MAILGUN_DOMAIN}>",
                "to": [RECIPIENT_EMAIL],
                "subject": f"🚀 Daily Executive AI Job Digest ({len(top_jobs)} High Fit Roles)",
                "text": body
            },
            timeout=15
        )
        if res.status_code == 200:
            print("✅ Email digest successfully delivered via Mailgun!")
        else:
            print(f"❌ Mailgun error: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"⚠️ Failed to send email via Mailgun: {e}")

def run_evaluation():
    progress = load_progress()
    if not Path(CSV_FILE_PATH).exists():
        print(f"Error: {CSV_FILE_PATH} not found.")
        return

    with open(CSV_FILE_PATH, "r", encoding="utf-8") as f:
        jobs = list(csv.DictReader(f))

    pending_jobs = []
    for idx, job in enumerate(jobs):
        job_id = job.get("job_id") or f"job_{idx}"
        existing = progress.get(job_id)
        if not (existing and existing.get("evaluated")):
            pending_jobs.append((job_id, job))

    jobs_to_process = pending_jobs[:MAX_JOBS_PER_RUN]
    
    if jobs_to_process:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(evaluate_single_job, job, job_id): job_id for job_id, job in jobs_to_process}
            for future in as_completed(futures):
                try:
                    job_id, result = future.result()
                    progress[job_id] = result
                    save_progress(progress)
                except Exception as e:
                    print(f"Error evaluating job: {e}")

    with open(OUTPUT_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(progress, f, indent=2, ensure_ascii=False)

    # Filter top scores (>= 75) for email alert
    top_matches = [j for j in progress.values() if j.get("score", 0) >= 75]
    top_matches = sorted(top_matches, key=lambda x: x["score"], reverse=True)[:10]

    if top_matches:
        send_mailgun_digest(top_matches)
    else:
        print("ℹ️ No new roles scored 75+ today. Skipping email alert.")

if __name__ == "__main__":
    run_evaluation()
