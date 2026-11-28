import os
import json
import logging
import requests
import re
import time
from groq import Groq

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

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
MAX_EVALS_PER_RUN = int(os.getenv("MAX_EVALS_PER_RUN", "15"))

RELEVANT_TITLE_KEYWORDS = [
    "operation", "cx", "customer experience", "service delivery",
    "contact center", "call center", "client service", "quality",
    "compliance", "governance", "capa", "customer resolution",
    "customer success", "customer advocacy", "client success", "concierge"
]

EXCLUDE_TITLE_KEYWORDS = [
    "junior", "intern", "associate", "analyst", "executive assistant",
    "technician", "food & beverage", "clinic", "retail"
]


def is_relevant_title(title: str) -> bool:
    t = (title or "").lower()
    if any(neg in t for neg in EXCLUDE_TITLE_KEYWORDS):
        return False
    return any(kw in t for kw in RELEVANT_TITLE_KEYWORDS)


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
    cleaned = (raw_text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return None


def evaluate_job(client, job):
    title = job.get("title", "Unknown Title")
    company = job.get("company", "Unknown Company")
    location = job.get("location", "Singapore")
    description = str(job.get("description", ""))[:1200]

    prompt = f"""Evaluate this job against the candidate dossier. Respond ONLY in valid JSON.

Candidate:
{MASTER_DOSSIER}

Title: {title}
Company: {company}
Location: {location}
Description: {description}

JSON schema:
{{"match_score": <0-100>, "fit_summary": "<2 sentences>", "key_alignments": ["<point 1>", "<point 2>"]}}"""

    for attempt in range(2):
        try:
            resp = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=300,
            )
            return clean_and_parse_json(resp.choices[0].message.content)
        except Exception as e:
            if "429" in str(e) and attempt == 0:
                logging.warning("[429 Rate Limit] Waiting 15s before 1 retry...")
                time.sleep(15)
            else:
                logging.error(f"Error evaluating '{title}' at '{company}': {e}")
                return None
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

    cards = []
    for item in matched_jobs:
        job = item["job"]
        ev = item["eval"]
        url = job.get("job_url") or job.get("url") or job.get("link") or "#"
        points = "".join(f"<li>{p}</li>" for p in ev.get("key_alignments", []))
        cards.append(
            f'<div style="border:1px solid #e2e8f0;border-radius:6px;padding:16px;margin-bottom:16px;">'
            f'<h2 style="margin:0 0 4px 0;font-size:16px;">{job.get("title", "N/A")}</h2>'
            f'<p style="margin:0 0 10px 0;color:#64748b;font-size:13px;">{job.get("company", "N/A")} • {job.get("location", "Singapore")}</p>'
            f'<div style="background:#dcfce7;color:#166534;font-weight:700;font-size:13px;padding:3px 10px;border-radius:9999px;display:inline-block;margin-bottom:10px;">Match Score: {ev.get("match_score", 0)}%</div>'
            f'<p style="margin:0 0 10px 0;font-size:13.5px;"><strong>Fit Summary:</strong> {ev.get("fit_summary", "")}</p>'
            f'<ul style="margin:0 0 12px 0;padding-left:20px;font-size:13px;">{points}</ul>'
            f'<a href="{url}" target="_blank" style="display:inline-block;background:#2563eb;color:#ffffff;text-decoration:none;font-size:13px;font-weight:600;padding:7px 14px;border-radius:4px;">View Listing Position</a>'
            f'</div>'
        )

    html_content = (
        f'<!DOCTYPE html><html><body style="font-family:sans-serif;background:#f4f6f9;padding:20px;">'
        f'<div style="max-width:680px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden;border:1px solid #e2e8f0;">'
        f'<div style="background:#0f172a;color:#fff;padding:20px 24px;"><h1 style="margin:0;font-size:20px;">🎯 Executive AI Job Digest ({len(matched_jobs)} Strategic Matches)</h1></div>'
        f'<div style="padding:24px;">{"".join(cards)}</div>'
        f'</div></body></html>'
    )

    resp = requests.post(
        f"[https://api.mailgun.net/v3/](https://api.mailgun.net/v3/){domain}/messages",
        auth=("api", api_key),
        data={
            "from": f"JB Search Digest <mailgun@{domain}>",
            "to": [recipient],
            "subject": f"🎯 Daily Executive AI Job Digest ({len(matched_jobs)} Strategic Matches)",
            "html": html_content,
        },
        timeout=15,
    )

    if resp.status_code == 200:
        logging.info(f"Mailgun email dispatched successfully to {recipient}")
    else:
        logging.error(f"Mailgun dispatch failed [{resp.status_code}]: {resp.text}")


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

    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        logging.error("GROQ_API_KEY environment variable missing.")
        return

    cache = load_cache()
    client = Groq(api_key=groq_api_key)
    high_matches = []
    evaluated_count = 0
    skipped_filter_count = 0

    for job in scraped_jobs:
        if evaluated_count >= MAX_EVALS_PER_RUN:
            logging.info(f"Reached batch cap of {MAX_EVALS_PER_RUN} evaluations. Saving progress.")
            break

        title = job.get("title", "")
        job_url = job.get("job_url") or job.get("url") or job.get("link")
        job_id = job_url if job_url else f"{title}_{job.get('company')}"

        if job_id in cache:
            continue

        if not is_relevant_title(title):
            cache.add(job_id)
            skipped_filter_count += 1
            continue

        result = evaluate_job(client, job)
        evaluated_count += 1

        if result is not None:
            cache.add(job_id)
            if result.get("match_score", 0) >= 75:
                high_matches.append({"job": job, "eval": result})
        else:
            logging.warning(f"Skipping cache entry for {job_id} due to processing failure.")

        time.sleep(2)

    save_cache(cache)
    logging.info(
        f"Evaluated {evaluated_count} relevant roles (filtered out {skipped_filter_count} non-matching titles). "
        f"Found {len(high_matches)} matches >= 75%."
    )

    if high_matches:
        send_email_digest(high_matches)
    else:
        logging.info("No new high-scoring matches found in this batch.")


if __name__ == "__main__":
    main()
