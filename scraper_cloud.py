import json
import logging
from jobspy import scrape_jobs
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Wide-Net Executive Boolean Query Matrix
SEARCH_QUERIES = [
    '(Director OR Head OR VP OR Regional OR Lead OR Manager OR Senior) AND ("Customer Experience" OR CX OR "Client Service" OR "Customer Service")',
    '(Director OR Head OR VP OR Regional OR Lead OR Manager OR Senior) AND ("Contact Center" OR "Call Center" OR "Service Delivery" OR "Customer Resolution")',
    '(Director OR Head OR VP OR Regional OR Lead OR Manager OR Senior) AND (Operations OR Quality OR Compliance OR Governance OR CAPA)'
]

def run_scraper():
    all_jobs = []
    
    for query in SEARCH_QUERIES:
        logging.info(f"Executing Query: {query}")
        try:
            jobs = scrape_jobs(
                site_name=["linkedin", "indeed", "glassdoor", "google"],
                search_term=query,
                location="Singapore",
                results_wanted=100,
                hours_old=168,  # Posts from past 7 days
                country_code_indeed='singapore'
            )
            if not jobs.empty:
                all_jobs.append(jobs)
                logging.info(f"Retrieved {len(jobs)} raw listings.")
        except Exception as e:
            logging.error(f"Error scraping query '{query}': {e}")

    if not all_jobs:
        logging.warning("No jobs retrieved across any query.")
        with open("scraped_jobs.json", "w") as f:
            json.dump([], f)
        return

    # Combine and deduplicate listings
    combined_df = pd.concat(all_jobs, ignore_index=True)
    combined_df.drop_duplicates(subset=["job_url"], inplace=True)
    combined_df = combined_df.fillna("")
    
    records = combined_df.to_dict(orient="records")
    logging.info(f"Total unique roles extracted after deduplication: {len(records)}")

    with open("scraped_jobs.json", "w") as f:
        json.dump(records, f, indent=2, default=str)

if __name__ == "__main__":
    run_scraper()
