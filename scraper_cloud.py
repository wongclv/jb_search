import os
import pandas as pd
from jobspy import scrape_jobs
import config

def run_scraper():
    print("🚀 Executing Singapore Executive Job Scraper (LinkedIn, Indeed, Glassdoor, Google)...")
    
    # Expanded query to catch Resolution, Client Service, CX, and AP/SEA variations
    base_query = "(Operations OR 'Customer Experience' OR 'Customer Resolution' OR 'Client Service' OR 'Contact Center' OR Service OR Compliance) (Director OR Head OR Lead OR Manager OR VP OR Regional)"
    
    all_jobs = []
    
    # Build complete company target list across Tiers 1-6
    target_companies = []
    for tier, comps in config.TIER_COMPANIES.items():
        target_companies.extend(comps)
        
    print(f"📡 Sweeping target companies across 4 major job boards (including Google)...")
    
    # Process in targeted company chunks to maximize coverage
    chunk_size = 15
    for i in range(0, len(target_companies), chunk_size):
        chunk = target_companies[i:i + chunk_size]
        company_filter = " OR ".join([f"company:'{c}'" for c in chunk])
        google_query = f"{base_query} Singapore AND ({company_filter})"
        
        try:
            jobs = scrape_jobs(
                site_name=["linkedin", "indeed", "glassdoor", "google"],  # Explicitly included google
                search_term=base_query,
                google_search_term=google_query,
                location="Singapore",
                results_wanted=50,
                hours_old=168,
                country_indeed='singapore'
            )
            if not jobs.empty:
                all_jobs.append(jobs)
        except Exception as e:
            print(f"⚠️ Search batch note: {e}")

    if not all_jobs:
        print("📭 No new listings retrieved during this sweep.")
        return

    combined_df = pd.concat(all_jobs, ignore_index=True)
    combined_df.drop_duplicates(subset=['job_url'], inplace=True)

    # Clean non-executive roles using config definitions
    def is_executive_fit(title):
        t = str(title).lower()
        if any(ex in t for ex in ["intern", "junior", "trainee", "entry level"]):
            return False
        return any(kw in t for kw in config.ALL_VALID_KEYWORDS)

    if 'title' in combined_df.columns:
        combined_df = combined_df[combined_df['title'].apply(is_executive_fit)]

    csv_file = "scraped_jobs_v3.csv"
    if os.path.exists(csv_file):
        existing_df = pd.read_csv(csv_file)
        updated_df = pd.concat([existing_df, combined_df], ignore_index=True)
        updated_df.drop_duplicates(subset=['job_url'], inplace=True)
        updated_df.to_csv(csv_file, index=False)
    else:
        combined_df.to_csv(csv_file, index=False)

    print(f"💾 Database updated successfully: {csv_file}")

if __name__ == "__main__":
    run_scraper()
