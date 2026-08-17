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

# Process up to 40 un-evaluated jobs per run to ensure fast execution (< 5 mins)
MAX_JOBS_PER_RUN = 40
MAX_WORKERS = 4  # Parallel requests to Groq API

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

MODEL_NAME = "llama-3.3-70b-versatile"

TARGET_JOB_TITLES = [
    "director", "head", "lead", "vp", "vice president", 
    "chief", "manager", "senior manager", "general manager",
    "operations", "product", "software engineer"
]

SKIP_CHECK_TITLE_FILTER = [
    "director", "head", "lead", "vp", "vice president", 
    "chief", "general manager", "cpto", "coo"
]

CANDIDATE_PROFILE = """
Candidate Profile:
- Target Seniority: Senior Management / Executive Leadership (Director, VP, Head, GM, Chief).
- Expertise: Operations Management, Strategic Planning, Business Process Optimization, Team Leadership, Product Strategy.
- Background: Extensive leadership experience managing teams, driving operational efficiency, and scalable execution.
"""

SYSTEM_PROMPT = f"""
You are an expert AI Executive Recruiter. Your task is to evaluate whether a job posting is a good fit for the candidate provided.

{CANDIDATE_PROFILE}

Analyze the job title, company, and description. Provide:
1. A Score (0 to 100) on how well the job aligns with the candidate's senior leadership/operations profile.
2. A brief 2-3 sentence assessment explaining the rationale.

Return output strictly in valid JSON format with the following keys:
- "score": (integer 0-100)
- "assessment": (string)
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

def is_title_allowed(title):
    title_lower = title.lower()
    if any(keyword in title_lower for keyword in SKIP_CHECK_TITLE_FILTER):
        return True
    return any(target in title_lower for target in TARGET_JOB_TITLES)

def evaluate_single_job(job, job_id):
    title = job.get("title", "Unknown Title")
    company = job.get("company", "Unknown Company")
    job_url = job.get("job_url") or job.get("url") or "#"
    description = job.get("description", "")

    if not is_title_allowed(title):
        return job_id, {
            "title": title,
            "company": company,
            "url": job_url,
            "score": 0,
            "assessment": "Skipped: Title outside target scope.",
            "evaluated": True
        }

    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY environment variable is not set.")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    user_content = f"Job Title: {title}\nCompany: {company}\nJob Description:\n{description[:1500]}"
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
            response = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=15)
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
                    "assessment": f"Failed API evaluation: {str(e)}",
                    "evaluated": True
                }
            time.sleep(2)

def run_evaluation():
    progress = load_progress()
    if not Path(CSV_FILE_PATH).exists():
        print(f"Error: {CSV_FILE_PATH} not found.")
        return

    with open(CSV_FILE_PATH, "r", encoding="utf-8") as f:
        jobs = list(csv.DictReader(f))

    print(f"Loaded {len(jobs)} total jobs from CSV.")

    # Filter for un-evaluated jobs
    pending_jobs = []
    for idx, job in enumerate(jobs):
        job_id = job.get("job_id") or f"job_{idx}"
        existing = progress.get(job_id)
        if not (existing and existing.get("evaluated")):
            pending_jobs.append((job_id, job))

    jobs_to_process = pending_jobs[:MAX_JOBS_PER_RUN]
    print(f"Processing {len(jobs_to_process)} jobs in this run using {MAX_WORKERS} parallel threads...")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(evaluate_single_job, job, job_id): job_id for job_id, job in jobs_to_process}
        for future in as_completed(futures):
            try:
                job_id, result = future.result()
                progress[job_id] = result
                save_progress(progress)
                print(f"Completed: {result['title']} @ {result['company']} (Score: {result['score']})")
            except Exception as e:
                print(f"Error evaluating job: {e}")

    with open(OUTPUT_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(progress, f, indent=2, ensure_ascii=False)

    print(f"\nBatch complete. Saved to {OUTPUT_REPORT_PATH}")

if __name__ == "__main__":
    run_evaluation()
