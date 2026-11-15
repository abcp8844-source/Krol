import time
import logging
from datetime import datetime
from scraper import run_independent_crawler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)

def main():
    logging.info("[START] Main entry point initiated.")
    
    attempt = 0
    while True:
        try:
            attempt += 1
            logging.info(f"[RUN] Starting crawler cycle # {attempt} at {datetime.now()}")
            
            run_independent_crawler()
            
            logging.info("[SUCCESS] Crawler cycle completed successfully.")
            
            time.sleep(15)
            attempt = 0
            
        except KeyboardInterrupt:
            logging.warning("[STOP] User interrupted the crawler.")
            break
            
        except Exception as e:
            logging.error(f"[CRITICAL ERROR] Crawler crashed during cycle #{attempt}: {e}")
            
            sleep_time = min(1 * attempt, 30)
            logging.info(f"[RECOVERY] Waiting for {sleep_time} seconds before restarting...")
            time.sleep(sleep_time)

if __name__ == "__main__":
    main()
