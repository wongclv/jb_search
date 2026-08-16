import os
import json
import csv
import time
import requests
from pathlib import Path

# --- Configuration & Paths ---
CSV_FILE_PATH = "scraped_jobs_v3.csv"
PROGRESS_FILE_PATH = "evaluator_progress.json"
OUTPUT_REPORT_PATH = "evaluation_report.json"

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# Official active Groq replacement model with optimal rate limits
MODEL_NAME = "llama-3.3-70b-versatile"

# Target job titles / keywords allowed for evaluation
TARGET_JOB_TITLES = [
    "director", "head", "lead", "vp", "vice president", 
    "chief", "manager", "senior manager", "general manager",
    "operations", "product", "software engineer"
]

# Whitelist filter: If a title contains any of these, bypass strict title filtering
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

# --- Helper Functions ---

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
    
    # Check whitelist override first
    if any(keyword in title_lower for keyword in SKIP_CHECK_TITLE_FILTER):
        return True
        
    # Check standard target titles
    return any(target in title_lower for target in TARGET_JOB_TITLES)

def evaluate_job_with_retry(title, company, description, max_retries=3, initial_backoff=3):
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY environment variable is not set.")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    user_content = f"Job Title: {title}\nCompany: {company}\nJob Description:\n{description[:2000]}"
    
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"}
    }

    backoff = initial_backoff
    for attempt in range(max_retries):
        try:
            response = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=20)
            
            # Handle Rate Limits (HTTP 429) explicitly
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                wait_time = int(retry_after) if retry_after and retry_after.isdigit() else min(backoff, 10)
                print(f"  [429 Rate Limit] Backing off for {wait_time}s (Attempt {attempt + 1}/{max_retries})...")
                time.sleep(wait_time)
                backoff *= 2
                continue

            response.raise_for_status()
            res_data = response.json()
            content = res_data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            
            return {
                "score": parsed.get("score", 0),
                "assessment": parsed.get("assessment", "No assessment provided."),
                "evaluated": True
            }

        except requests.exceptions.HTTPError as http_err:
            if response.status_code != 429:
                print(f"  [HTTP Error {response.status_code}]: {http_err}")
                return {
                    "score": 0,
                    "assessment": f"API Error: Status {response.status_code}, Msg: {response.text[:100]}",
                    "evaluated": True
                }
        except Exception as e:
            print(f"  [Error]: {e}")
            if attempt == max_retries - 1:
                return {
                    "score": 0,
                    "assessment": f"Failed after {max_retries} attempts: {str(e)}",
                    "evaluated": True
                }
        
        time.sleep(backoff)
        backoff *= 2

    return {
        "score": 0,
        "assessment": "API Error: Max rate limit retries exceeded.",
        "evaluated": True
    }

# --- Main Pipeline ---

def run_evaluation():
    progress = load_progress()
    
    if not Path(CSV_FILE_PATH).exists():
        print(f"Error: {CSV_FILE_PATH} not found.")
        return

    with open(CSV_FILE_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        jobs = list(reader)

    print(f"Loaded {len(jobs)} total jobs from CSV.")

    for idx, job in enumerate(jobs):
        job_id = job.get("job_id") or f"job_{idx}"
        title = job.get("title", "Unknown Title")
        company = job.get("company", "Unknown Company")
        description = job.get("description", "")

        # Skip if already evaluated successfully (and not rate limited previously)
        existing = progress.get(job_id)
        if existing and existing.get("evaluated") and "Rate limit reached" not in existing.get("assessment", ""):
            continue

        print(f"Processing ({idx + 1}/{len(jobs)}): {title} @ {company}")

        # Check title filter with Whitelist Override
        if not is_title_allowed(title):
            print("  Skipped: Title outside target scope.")
            progress[job_id] = {
                "title": title,
                "company": company,
                "score": 0,
                "assessment": "Skipped: Title outside target scope.",
                "evaluated": True
            }
            save_progress(progress)
            continue

        # Evaluate via API
        eval_result = evaluate_job_with_retry(title, company, description)
        
        progress[job_id] = {
            "title": title,
            "company": company,
            "score": eval_result["score"],
            "assessment": eval_result["assessment"],
            "evaluated": eval_result["evaluated"]
        }
        
        save_progress(progress)
        time.sleep(0.2) # Fast pacing between jobs

    # Save final report summary
    with open(OUTPUT_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(progress, f, indent=2, ensure_ascii=False)

    print(f"\nEvaluation complete. Full report written to {OUTPUT_REPORT_PATH}")

if __name__ == "__main__":
    run_evaluation()
