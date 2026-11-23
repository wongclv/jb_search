import json
import logging
import time
from functools import wraps
import pandas as pd
from jobspy import scrape_jobs

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

SEARCH_QUERIES = [
    "Director Customer Experience",
    "Regional Director Customer Service",
    "Head of Customer Service",
    "Head of Customer Care",
    "Director Client Management",
    "Senior Director Client Management",
    "Director Customer Relationship",
    "Director Contact Center",
    "Head of Service Delivery",
    "Director Customer Success",
    "Director Customer Advocacy",
    "Operations Director",
    "Regional Operations Director",
    "Head of Operations",
    "Director Quality Compliance",
    "Head of Quality Governance",
    "APAC Customer Operations",
    "Global Head Customer Care",
]


def retry_on_exception(retries=3, delay=2, backoff=2):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            for attempt in range(retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    logging.warning(f"Attempt {attempt + 1} failed for {func.__name__}: {e}")
                    if attempt == retries - 1:
                        raise e
                    time.sleep(current_delay)
                    current_delay *= backoff
        return wrapper
    return decorator


@retry_on_exception(retries=3, delay=3, backoff=2)
def execute_scrape(query: str):
    return scrape_jobs(
        site_name=["linkedin", "indeed", "glassdoor", "google"],
        search_term=query,
        google_search_term=f"{query} jobs in Singapore",
        location="Singapore",
        results_wanted=25,
        hours_old=168,  # Past 7 days
        country_indeed="Singapore",
    )


def run_scraper():
    all_jobs = []

    logging.info(f"Prepared {len(SEARCH_QUERIES)} clean search queries for Singapore.")
    for query in SEARCH_QUERIES:
        logging.info(f"Executing Query: {query}")
        try:
            jobs = execute_scrape(query)
            if jobs is not None and not jobs.empty:
                all_jobs.append(jobs)
                logging.info(f"Retrieved {len(jobs)} raw listings for query '{query}'.")
            else:
                logging.info(f"0 listings returned for query '{query}'.")
        except Exception as e:
            logging.error(f"Error scraping query '{query}' after retries: {e}")
        time.sleep(3)

    if not all_jobs:
        logging.warning("No jobs retrieved across any query.")
        with open("scraped_jobs.json", "w", encoding="utf-8") as f:
            json.dump([], f)
        return

    combined_df = pd.concat(all_jobs, ignore_index=True)
    if "job_url" in combined_df.columns:
        combined_df.drop_duplicates(subset=["job_url"], inplace=True)
    combined_df = combined_df.fillna("")

    records = combined_df.to_dict(orient="records")
    logging.info(f"Total unique roles extracted after deduplication: {len(records)}")

    with open("scraped_jobs.json", "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, default=str)


if __name__ == "__main__":
    run_scraper()
