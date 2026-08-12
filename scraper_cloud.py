import os
import pandas as pd
from jobspy import scrape_jobs

def run_scraper():
    print("🔍 Executing Singapore Job Scraper Module...")
    search_terms = [
        "Customer Service Operations",
        "Operations Director",
        "Operations Manager",
        "Head of Operations",
        "Service Delivery Manager",
        "Service Delivery Director",
        "Shared Services Leader",
        "Shared Services Manager",
        "Contact Center Manager",
        "Call Center Manager",
        "Business Transformation Manager",
        "Customer Experience Manager",
        "Customer Journey Manager",
        "Technical Support Manager",
        "Helpdesk Operations"
    ]
    all_jobs = []
    for term in search_terms:
        print(f"🔎 Querying roles for term: '{term}' in Singapore...")
        try:
            jobs = scrape_jobs(
                site_name=["linkedin", "indeed", "glassdoor"],
                search_term=term,
                location="Singapore",
                results_wanted=25,
                hours_old=168,
                country_indeed='Singapore'
            )
            if not jobs.empty:
                all_jobs.append(jobs)
                print(f"   ↳ Retrieved {len(jobs)} listings for '{term}'.")
        except Exception as e:
            print(f"⚠️ Error scraping term '{term}': {e}")

    if not all_jobs:
        print("📭 No job listings retrieved during this execution cycle.")
        return

    combined_df = pd.concat(all_jobs, ignore_index=True)
    combined_df.drop_duplicates(subset=['job_url'], inplace=True)

    csv_file = "scraped_jobs_v3.csv"
    if os.path.exists(csv_file):
        existing_df = pd.read_csv(csv_file)
        updated_df = pd.concat([existing_df, combined_df], ignore_index=True)
        updated_df.drop_duplicates(subset=['job_url'], inplace=True)
        updated_df.to_csv(csv_file, index=False)
    else:
        combined_df.to_csv(csv_file, index=False)
    print(f"💾 Master database updated successfully: {csv_file}")

if __name__ == "__main__":
    run_scraper()
