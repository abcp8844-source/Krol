import os
import time
import random
import re
from bs4 import BeautifulSoup
from supabase import create_client, Client
from playwright.sync_api import sync_playwright

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"Supabase Connection Error: {e}")
    supabase = None

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
]

def resolve_deep_target_url(page, initial_url, job_title):
    current_url = initial_url
    hops = 0
    max_hops = 5

    while hops < max_hops:
        try:
            print(f"Navigating to URL: {current_url}")
            page.goto(current_url, timeout=20000, wait_until="domcontentloaded")
            time.sleep(2)
            current_url = page.url
            html_content = page.content()
            soup = BeautifulSoup(html_content, 'html.parser')
            page_text = soup.get_text().lower()

            if any(domain in current_url for domain in ['facebook.com', 't.co', 'redirect', 'l.facebook.com', 'lnkd.in']):
                best_link = None
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    if href.startswith('http') and not any(d in href for d in ['facebook.com', 'google.com', 'twitter.com', 'linkedin.com']):
                        if job_title and job_title.lower() in page_text:
                            best_link = href
                            break
                        elif not best_link:
                            best_link = href

                if best_link:
                    current_url = best_link
                    hops += 1
                    continue
            break
        except Exception as e:
            print(f"URL Resolution Error at hop {hops}: {e}")
            break
    return current_url, page

def extract_job_details(page, target_url):
    try:
        print(f"Extracting details from: {target_url}")
        page.goto(target_url, timeout=20000, wait_until="domcontentloaded")
        time.sleep(2)
        html_content = page.content()
        soup = BeautifulSoup(html_content, 'html.parser')
        page_text = soup.get_text()

        salary = "Not Specified"
        salary_match = re.search(r'(\$|€|£|Rs\.?|PKR|USD)\s*[\d,]+(\.\d+)?(\s*-\s*[\d,]+)?', page_text, re.IGNORECASE)
        if salary_match:
            salary = salary_match.group(0)

        location = "Remote / On-site"
        loc_match = re.search(r'(Location|City|Address):\s*([A-Za-z\s,]+)', page_text, re.IGNORECASE)
        if loc_match:
            location = loc_match.group(2).strip()[:50]

        email_match = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', page_text)
        email = email_match.group(0) if email_match else ""

        phone_match = re.search(r'(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', page_text)
        phone = phone_match.group(0) if phone_match else ""

        return {
            "finalUrl": page.url,
            "salary": salary,
            "location": location,
            "email": email,
            "phone": phone,
            "snippet": page_text[:400].strip()
        }
    except Exception as e:
        print(f"Extraction Error: {e}")
        return None

def run_crawler():
    if not supabase:
        print("Supabase client is not available.")
        return

    try:
        print("Fetching pending jobs...")
        response = supabase.table("raw_jobs").select("*").eq("status", "pending").limit(5).execute()
        raw_jobs = response.data
    except Exception as e:
        print(f"Database Fetch Error: {e}")
        return

    if not raw_jobs:
        print("No pending jobs found.")
        return

    print(f"Found {len(raw_jobs)} jobs to process.")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=random.choice(USER_AGENTS))
            page = context.new_page()

            for job in raw_jobs:
                job_id = job.get("id")
                source_link = job.get("link")
                job_title = job.get("query_used")

                if not source_link:
                    print(f"Skipping ID {job_id}: Missing link.")
                    continue

                print(f"Processing ID: {job_id}")
                
                try:
                    resolved_url, page = resolve_deep_target_url(page, source_link, job_title)
                    enriched_data = extract_job_details(page, resolved_url)

                    if enriched_data and (
                        enriched_data["salary"] != "Not Specified" or 
                        enriched_data["email"] != "" or 
                        enriched_data["phone"] != "" or 
                        len(enriched_data["snippet"]) > 100
                    ):
                        supabase.table("raw_jobs").update({
                            "link": enriched_data["finalUrl"],
                            "snippet": f"Salary: {enriched_data['salary']} | Location: {enriched_data['location']} | Email: {enriched_data['email']} | Phone: {enriched_data['phone']} | {enriched_data['snippet']}",
                            "status": "pendings"
                        }).eq("id", job_id).execute()
                        print(f"Successfully updated ID {job_id} to 'pendings'.")
                    else:
                        print(f"Insufficient data found for ID {job_id}. Status remains pending.")
                except Exception as inner_e:
                    print(f"Error processing record ID {job_id}: {inner_e}")

                time.sleep(2)

            browser.close()
    except Exception as browser_e:
        print(f"Playwright Execution Error: {browser_e}")

if __name__ == "__main__":
    run_crawler()
