import os
import json
import logging
import requests
import re
from groq import Groq

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Master Dossier background context
MASTER_DOSSIER = """
Candidate: Vincent Wong Choong Leong
Target Level: Senior Regional / Director / Head of Operations & CX
Experience: 20+ years executive leadership across APAC markets (Align Technology, LifeScan/J&J, Singtel).
Core Domains: Contact Center Operations, Customer Experience (CX), Service Delivery, Regional P&L, Quality Governance, CAPA, SLA Management.
Technical & Transformation: Salesforce, SAP, Generative AI implementation, Digital Transformation, Vendor Management.
Location: Singapore
"""

CACHE_FILE = "evaluator_progress.json"
GROQ_MODEL = "llama-3.1-8b-instant"

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception as e:
            logging.error(f"Error loading cache file: {e}")
            return set()
    return set()

def save_cache(cache):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(list(cache), f, indent=2, ensure_ascii=False)
    except Exception as e:
        logging.error(f"Error saving cache file: {e}")

def clean_and_parse_json(raw_text: str) -> dict:
    """Extracts and parses valid JSON objects from raw LLM text responses."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        return {
            "match_score": 0,
            "fit_summary": "Parsing Error: LLM response failed JSON validation.",
            "key_alignments": []
        }

def evaluate_job(client, job):
    title = job.get("title", "Unknown Title")
    company = job.get("company", "Unknown Company")
    location = job.get("location", "Singapore")
    description = str(job.get("description", ""))[:3000]

    prompt = f"""
You are an executive career recruiter. Evaluate the following job posting against the candidate dossier.

Candidate Dossier:
{MASTER_DOSSIER}

Job Title: {title}
Company: {company}
Location: {location}
Description: {description}

Respond ONLY in valid JSON with no markdown block wrappers, adhering strictly to this schema:
{{
  "match_score": <integer between 0 and 100>,
  "fit_summary": "<2-3 sentence overview of why this matches or fails>",
  "key_alignments": ["<alignment 1>", "<alignment 2>", "<alignment 3>"]
}}
"""
    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=500
        )
        raw_content = response.choices[0].message.content
        return clean_and_parse_json(raw_content)
    except Exception as e:
        logging.error(f"Error evaluating job '{title}' at '{company}': {e}")
        return None

def send_email_digest(matched_jobs):
    api_key = os.getenv("MAILGUN_API_KEY")
    domain = os.getenv("MAILGUN_DOMAIN")
    recipient = os.getenv("RECIPIENT_EMAIL") or os.getenv("TARGET_EMAIL") or "callcentre.wong@gmail.com"

    if not api_key or not domain:
        logging.error("Mailgun environment variables missing. Skipping email dispatch.")
        return

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f4f6f9; color: #333; margin: 0; padding: 20px; }}
            .container {{ max-width: 680px; margin: 0 auto; background: #ffffff; border-radius: 8px; overflow: hidden; border: 1px solid #e2e8f0; }}
            .header {{ background: #0f172a; color: #ffffff; padding: 20px 24px; }}
            .header h1 {{ margin: 0; font-size: 20px; }}
            .content {{ padding: 24px; }}
            .card {{ border: 1px solid #e2e8f0; border-radius: 6px; padding: 18px; margin-bottom: 20px; background-color: #ffffff; }}
            .job-title {{ font-size: 16px; font-weight: 700; color: #0f172a; margin: 0 0 4px 0; }}
            .company-name {{ font-size: 14px; color: #64748b; margin: 0 0 12px 0; }}
            .badge {{ background: #dcfce7; color: #166534; font-weight: 700; font-size: 13px; padding: 4px 10px; border-radius: 9999px; display: inline-block; margin-bottom: 12px; }}
            .summary {{ font-size: 13.5px; line-height: 1.5; color: #334155; margin-bottom: 12px; }}
            .alignments {{ margin: 0 0 16px 0; padding-left: 20px; color: #475569; font-size: 13px; }}
            .btn {{ display: inline-block; background-color: #2563eb; color: #ffffff !important; text-decoration: none; font-size: 13px; font-weight: 600; padding: 8px 16px; border-radius: 4px; }}
            .footer {{ background: #f8fafc; padding: 16px 24px; font-size: 11px; color: #94a3b8; text-align: center; border-top: 1px solid #e2e8f0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎯 Executive AI Job Digest ({len(matched_jobs)} Strategic Matches)</h1>
            </div>
            <div class="content">
    """

    for item in matched_jobs:
        job = item["job"]
        eval_data = item["eval"]
        job_url = job.get("job_url") or job.get("url") or job.get("link") or "#"

        html_content += f"""
        <div class="card">
            <h2 class="job-title">{job.get('title', 'N/A')}</h2>
            <p class="company-name">{job.get('company', 'N/A')} • {job.get('location', 'Singapore')}</p>
            <div class="badge">Match Score: {eval_data.get('match_score', 0)}%</div>
            <p class="summary"><strong>Fit Summary:</strong> {eval_data.get('fit_summary', '')}</p>
            <ul class="alignments">
        """
        for align in eval_data.get("key_alignments", []):
            html_content += f"<li>{align}</li>"

        html_content += f"""
            </ul>
            <p><a href="{job_url}" class="btn" target="_blank">View Listing Position</a></p>
        </div>
        """

    html_content += """
            </div>
            <div class="footer">
                Automated pipeline execution via GitHub Actions | Powered by Groq AI & Mailgun API
            </div>
        </div>
    </body>
    </html>
    """

    url = f"[https://api.mailgun.net/v3/](https://api.mailgun.net/v3/){domain}/messages"
    response = requests.post(
        url,
        auth=("api", api_key),
        data={
            "from": f"AI Job Hunter <mailgun@{domain}>",
            "to": [recipient],
            "subject": f"🎯 Daily Executive AI Job Digest ({len(matched_jobs)} Strategic Matches)",
            "html": html_content
        },
        timeout=15
    )

    if response.status_code == 200:
        logging.info(f"Mailgun email dispatched successfully to {recipient}")
    else:
        logging.error(f"Mailgun dispatch failed [{response.status_code}]: {response.text}")

def main():
    if not os.path.exists("scraped_jobs.json"):
        logging.info("No scraped_jobs.json file found. Exiting execution.")
        return

    try:
        with open("scraped_jobs.json", "r", encoding="utf-8") as f:
            scraped_jobs = json.load(f)
    except Exception as e:
        logging.error(f"Failed to read scraped_jobs.json: {e}")
        return

    if not scraped_jobs:
        logging.info("scraped_jobs.json is empty. Nothing to process.")
        return

    cache = load_cache()
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        logging.error("GROQ_API_KEY environment variable missing.")
        return

    groq_client = Groq(api_key=groq_api_key)
    high_matches = []

    for job in scraped_jobs:
        job_url = job.get("job_url") or job.get("url") or job.get("link")
        job_id = job_url if job_url else f"{job.get('title')}_{job.get('company')}"

        if job_id in cache:
            continue

        eval_result = evaluate_job(groq_client, job)
        cache.add(job_id)

        if eval_result and eval_result.get("match_score", 0) >= 75:
            high_matches.append({"job": job, "eval": eval_result})

    save_cache(cache)
    logging.info(f"Processed {len(scraped_jobs)} roles. Found {len(high_matches)} matches >= 75%.")

    if high_matches:
        send_email_digest(high_matches)
    else:
        logging.info("No new high-scoring matches found today.")

if __name__ == "__main__":
    main()
