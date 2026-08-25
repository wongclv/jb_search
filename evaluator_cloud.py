import os
import re
import json
import logging
import requests
from groq import Groq

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Updated Executive Dossier & Exclusion Safeguards
MASTER_DOSSIER = """
Candidate: Vincent Wong Choong Leong
Target Seniority: Senior Regional Leadership (Director, Head, VP, Regional Lead, Senior Operations Manager).
Core Domain: 20+ years of APAC regional leadership in Customer Experience (CX), Contact Center Operations, Service Delivery, Quality Governance, BPO Management, SLA & CAPA.
Target Sectors: Enterprise Tech, MNCs, FinTech, Logistics, Healthcare, Aerospace, Luxury, Public Sector.

CRITICAL EXCLUSIONS & DISQUALIFIERS:
- REJECT Mid-level/Junior roles (e.g., Deputy Manager, Assistant Manager, Specialist, Junior Product Manager).
- REJECT Pure Software Engineering / Network / SRE Infrastructure / IT Support roles.
- REJECT Physical Product Development / FMCG / F&B R&D roles (e.g., Tea/Beverage Product Development).
- Roles MUST be centered on CX, Operations Leadership, or Contact Center / Service Delivery.
"""

CACHE_FILE = "evaluator_progress.json"

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(list(cache), f, indent=2)

def clean_and_parse_json(raw_text: str) -> dict:
    """Safely extracts JSON from LLM outputs."""
    try:
        return json.loads(raw_text)
    except Exception:
        json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except Exception:
                pass
        return {
            "match_score": 0,
            "fit_summary": "Failed JSON validation.",
            "key_alignments": []
        }

def evaluate_job(client, job):
    prompt = f"""
You are an executive talent evaluator evaluating job opportunities against the candidate profile.

Candidate Profile & Constraints:
{MASTER_DOSSIER}

Job Posting Details:
- Title: {job.get('title')}
- Company: {job.get('company')}
- Location: {job.get('location')}
- Description: {str(job.get('description'))[:3000]}

SCORING RULES:
1. If the job title is below Senior Management level (e.g. "Deputy Manager", "Assistant Manager", "Specialist"), CAP the match_score at 30.
2. If the role is pure IT/Software/SRE engineering or physical product R&D (e.g. Tea/F&B product development), CAP the match_score at 30.
3. Assign match_score >= 75 ONLY if the role aligns directly with Customer Experience (CX), Contact Center Operations, Regional Service Delivery, or Operational Leadership.

Respond strictly in valid JSON with no markdown formatting:
{{
  "match_score": <integer 0 to 100>,
  "fit_summary": "<2-3 sentence strict evaluation of executive fit>",
  "key_alignments": ["<alignment 1>", "<alignment 2>", "<alignment 3>"]
}}
"""
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=500
        )
        content = response.choices[0].message.content.strip()
        if content.startswith("```"):
            content = content.split("```")[1].strip()
            if content.startswith("json"):
                content = content[4:].strip()
        return clean_and_parse_json(content)
    except Exception as e:
        logging.error(f"Error evaluating job {job.get('job_url')}: {e}")
        return None

def send_email_digest(matched_jobs):
    api_key = os.getenv("MAILGUN_API_KEY")
    domain = os.getenv("MAILGUN_DOMAIN")
    recipient = os.getenv("RECIPIENT_EMAIL")

    if not all([api_key, domain, recipient]):
        logging.error("Mailgun environment variables missing. Skipping email dispatch.")
        return

    cards_html = ""
    for item in matched_jobs:
        job = item['job']
        eval_data = item['eval']
        
        alignments_list = "".join([f"<li>{align}</li>" for align in eval_data.get('key_alignments', [])])
        
        cards_html += f"""
        <div style="border: 1px solid #e2e8f0; border-radius: 8px; padding: 18px; margin-bottom: 20px; background-color: #ffffff;">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px;">
                <div>
                    <h2 style="font-size: 16px; font-weight: 700; color: #0f172a; margin: 0 0 4px 0;">{job.get('title')}</h2>
                    <p style="font-size: 14px; font-weight: 500; color: #64748b; margin: 0;">{job.get('company')} • {job.get('location')}</p>
                </div>
                <div style="background: #dcfce7; color: #166534; font-weight: 700; font-size: 13px; padding: 4px 10px; border-radius: 9999px;">
                    {eval_data.get('match_score')}% Match
                </div>
            </div>
            <p style="font-size: 13.5px; line-height: 1.5; color: #334155; margin-bottom: 12px;">
                <strong>Fit Summary:</strong> {eval_data.get('fit_summary')}
            </p>
            <ul style="margin: 0 0 16px 0; padding-left: 20px; color: #475569; font-size: 13px;">
                {alignments_list}
            </ul>
            <a href="{job.get('job_url')}" style="display: inline-block; background-color: #2563eb; color: #ffffff; text-decoration: none; font-size: 13px; font-weight: 600; padding: 8px 16px; border-radius: 4px;" target="_blank">View Listing Position</a>
        </div>
        """

    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f4f6f9; color: #333333; margin: 0; padding: 20px;">
        <div style="max-width: 680px; margin: 0 auto; background: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 10px rgba(0,0,0,0.05);">
            <div style="background: #0f172a; color: #ffffff; padding: 24px; text-align: left;">
                <h1 style="margin: 0; font-size: 20px; font-weight: 600;">🎯 Executive AI Job Digest ({len(matched_jobs)} High Fit Roles)</h1>
                <p style="margin: 4px 0 0 0; color: #94a3b8; font-size: 13px;">Singapore Executive Search Pipeline | Autonomous Daily Sweep</p>
            </div>
            <div style="padding: 24px;">
                {cards_html}
            </div>
            <div style="background: #f8fafc; padding: 16px 24px; font-size: 11px; color: #94a3b8; text-align: center; border-top: 1px solid #e2e8f0;">
                Automated pipeline execution via GitHub Actions | Powered by Groq AI & Mailgun API
            </div>
        </div>
    </body>
    </html>
    """

    response = requests.post(
        f"https://api.mailgun.net/v3/{domain}/messages",
        auth=("api", api_key),
        data={
            "from": f"AI Job Hunter <mailgun@{domain}>",
            "to": [recipient],
            "subject": f"🎯 Executive AI Job Digest: {len(matched_jobs)} Strategic Matches Found",
            "html": full_html
        }
    )
    logging.info(f"Mailgun dispatch status: {response.status_code}")

def main():
    if not os.path.exists("scraped_jobs.json"):
        logging.info("No scraped_jobs.json file found.")
        return

    with open("scraped_jobs.json", "r") as f:
        scraped_jobs = json.load(f)

    if not scraped_jobs:
        logging.info("No scraped jobs to process.")
        return

    cache = load_cache()
    groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    high_matches = []

    for job in scraped_jobs:
        job_id = job.get("job_url") or f"{job.get('title')}_{job.get('company')}"
        if job_id in cache:
            continue

        eval_result = evaluate_job(groq_client, job)
        cache.add(job_id)

        if eval_result and eval_result.get("match_score", 0) >= 75:
            high_matches.append({"job": job, "eval": eval_result})

    save_cache(cache)
    logging.info(f"Evaluated {len(scraped_jobs)} roles. Found {len(high_matches)} high-match roles (>= 75%).")

    if high_matches:
        send_email_digest(high_matches)

if __name__ == "__main__":
    main()
