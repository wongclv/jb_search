import os
import pandas as pd
from jobspy import scrape_jobs
import config

def run_scraper():
    print("🚀 Executing Industry-Agnostic Wide Net Singapore Executive Job Scraper...")
    
    # Wide Boolean Matrix optimized to catch all variations of CX, Operations, Service & Resolution Leadership
    search_queries = [
        "('Customer Resolution' OR 'Client Service' OR 'Customer Experience' OR CX OR 'Customer Service' OR Customer) (Director OR Head OR VP OR Regional OR Lead OR Senior OR Manager)",
        "(Operations OR 'Operational Excellence' OR 'Service Delivery' OR Service OR 'Contact Center') (Director OR Head OR VP OR Manager OR Regional OR Senior)",
        "(Compliance OR Quality OR CAPA OR Governance OR Resolution) (Director OR Head OR VP OR Regional OR Manager OR Senior)"
    ]
    
    all_jobs = []
    
    for idx, query in enumerate(search_queries, 1):
        print(f"🔍 [Query {idx}/{len(search_queries)}] Sweeping Singapore market: {query}")
        try:
            jobs = scrape_jobs(
                site_name=["linkedin", "indeed", "glassdoor", "google"],
                search_term=f"{query} Singapore",
                google_search_term=f"{query} Singapore",
                location="Singapore",
                results_wanted=100,
                hours_old=168,
                country_indeed='singapore'
            )
            if not jobs.empty:
                print(f"   --> Found {len(jobs)} raw listings")
                all_jobs.append(jobs)
        except Exception as e:
            print(f"⚠️ Search note for query {idx}: {e}")

    if not all_jobs:
        print("📭 No new listings retrieved during this sweep.")
        return

    # Combine results and remove exact duplicate job URLs across platforms
    combined_df = pd.concat(all_jobs, ignore_index=True)
    combined_df.drop_duplicates(subset=['job_url'], inplace=True)

    # Filter out junior/entry level titles while retaining executive leadership roles
    def is_executive_fit(title):
        t = str(title).lower()
        if any(ex in t for ex in ["intern", "junior", "trainee", "entry level", "associate manager"]):
            return False
        return any(kw in t for kw in config.ALL_VALID_KEYWORDS)

    if 'title' in combined_df.columns:
        combined_df = combined_df[combined_df['title'].apply(is_executive_fit)]

    # Append to master dataset and ensure persistent deduplication
    csv_file = "scraped_jobs_v3.csv"
    if os.path.exists(csv_file):
        existing_df = pd.read_csv(csv_file)
        updated_df = pd.concat([existing_df, combined_df], ignore_index=True)
        updated_df.drop_duplicates(subset=['job_url'], inplace=True)
        updated_df.to_csv(csv_file, index=False)
        print(f"💾 Master database updated. Total unique jobs stored: {len(updated_df)}")
    else:
        combined_df.to_csv(csv_file, index=False)
        print(f"💾 Master database created with {len(combined_df)} executive jobs.")

if __name__ == "__main__":
    run_scraper()
