import os
import json
import logging
import requests
import re
import time
from groq import Groq

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Master Dossier background context
MASTER_DOSSIER = """
Candidate: Wong Choong Leong Vincent (Vincent Wong)
Target Level: Senior Regional / Director / Head of Operations, Customer Experience (CX) & Client/Customer Care
Experience: 20+ years of leadership in Customer Service, Contact Centre, Client/Account Management, and Regional Operations across APAC markets (Invisalign / Align Technology, LifeScan / Johnson & Johnson Medical Asia Pacific, Singtel, Ogilvy / Teledirect, Iomega).
Core Domains: Contact Centre & Omnichannel Operations, Customer Experience (CX), Client Management & Customer Relationship, Service Delivery, Regional P&L & Budget Ownership (OPEX & COGS), Quality Governance & CAPA, SLA/KPI Management, Workforce Management (WFM & Erlang), Vendor/BPO Governance, Patient & Customer Engagement.
Technical & Digital Transformation: Salesforce CRM (SFDC), SAP, MS Dynamics CRM, Zendesk, Twilio Flex, Generative AI & Agentic AI for customer operations, SQL, Power BI, MarTech & campaign analytics.
Key Career Highlights:
- Invisalign Pte Ltd (APAC, Dec 2019–Apr 2024, Director – Regional Concierge and Customer Service Lead): Led customer service and concierge operations across 14 APAC markets (300,000+ annual inquiries; 650,000+ annual leads across 12 markets), set up 5 Invisalign Experience Centres in 6 months, deployed 24/7 follow-the-sun technical support, integrated Twilio Flex with Salesforce, and achieved a 30% reduction in OPEX/COGS.
- LifeScan, Johnson & Johnson Medical Asia Pacific (APAC, Dec 2005–Nov 2019, Asst. Director – Regional Customer Service): Led regional customer care and OneTouch digital ecosystem support across 12 APAC markets, reduced annual OPEX by 40% via call center consolidation and vendor renegotiation, and led Salesforce CRM rollout saving over US$500K annually.
- Singtel (May 2004–Dec 2005, Senior Manager - Customer Service): Managed a 120-seat in-house and outsourced contact center using WFM and Erlang capacity planning, reducing staff turnover by 35% in 2005.
- Ogilvy / Teledirect Pte Ltd (Oct 2001–Apr 2004, Senior / Account Manager - Customer Support): Managed multi-market outsourced contact center programs, account retention/renewals, B2B/enterprise client governance, and WFM/Erlang scheduling across APAC.
Location: Singapore (Singaporean; fluent in English, Mandarin/Chinese, and Cantonese)
"""

CACHE_FILE = "evaluator_progress.json"
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")


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
        return None


def call_groq_with_retry(client, prompt, max_retries=5, initial_delay=3):
    """Calls Groq API with exponential backoff retries for rate limits (429)."""
    delay = initial_delay
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=500,
            )
            return response.choices[0].message.content
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "rate_limit" in err_msg.lower():
                logging.warning(
                    f"[429 Rate Limit] Retrying in {delay} seconds... (Attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(delay)
                delay *= 2
            else:
                logging.error(f"Groq API Error: {err_msg}")
                raise e
    raise Exception("Max retries exceeded for Groq API due to Rate Limits.")


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
        raw_content = call_groq_with_retry(client, prompt)
        return clean_and_parse_json(raw_content)
    except Exception as e:
        logging.error(f"Error evaluating job '{title}' at '{company}': {e}")
        return None


def send_email_digest(matched_jobs):
    api_key = os.getenv("MAILGUN_API_KEY")
    domain = os.getenv("MAILGUN_DOMAIN")
    recipient = (
        os.getenv("RECIPIENT_EMAIL")
        or os.getenv("ALERT_RECIPIENT_EMAIL")
        or os.getenv("TARGET_EMAIL")
        or "callcentre.wong@gmail.com"
    )

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
            "html": html_content,
        },
        timeout=15,
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

        # ONLY add to cache if evaluation succeeds
        if eval_result is not None:
            cache.add(job_id)
            if eval_result.get("match_score", 0) >= 75:
                high_matches.append({"job": job, "eval": eval_result})
        else:
            logging.warning(f"Skipping cache entry for {job_id} due to processing failure.")

        time.sleep(5)

    save_cache(cache)
    logging.info(f"Processed {len(scraped_jobs)} roles. Found {len(high_matches)} matches >= 75%.")

    if high_matches:
        send_email_digest(high_matches)
    else:
        logging.info("No new high-scoring matches found today.")


if __name__ == "__main__":
    main()
