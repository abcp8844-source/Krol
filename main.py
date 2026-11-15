import logging
from datetime import datetime
from scraper import run_independent_crawler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

def main():
    logging.info("[START] Crawler process initiated. Running until success...")
    try:
        run_independent_crawler()
        logging.info("[SUCCESS] Target post successfully found and inserted into database.")
    except Exception as e:
        logging.error(f"[CRITICAL ERROR] Crawler encountered an issue: {e}")
        raise e

if __name__ == "__main__":
    main()
