import time
import random
from datetime import datetime
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY, SCHEDULE, COUNTRY_CITIES, COUNTRY_DUAL_DOMAINS, COUNTRY_KEYWORDS, USER_AGENTS
from cleaner import extract_strict_job_details

try:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("Supabase environment variables missing")
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("[INFO] Connected to Supabase successfully.")
except Exception as e:
    print(f"[CRITICAL] Supabase connection failed: {e}")
    supabase = None

def run_independent_crawler():
    if not supabase:
        print("[ERROR] Crawler stopped because Supabase client is missing.")
        return

    today = datetime.now().strftime("%A")
    current_year = datetime.now().year
    day_countries = SCHEDULE.get(today, ["Spain"])
    
    target_country = random.choice(day_countries)
    cities = COUNTRY_CITIES.get(target_country, [target_country])
    domains = COUNTRY_DUAL_DOMAINS.get(target_country, [])
    keywords = COUNTRY_KEYWORDS.get(target_country, ["developer", "manager", "engineer"])
    
    if not domains:
        print(f"[ERROR] No domains found for country: {target_country}")
        return

    print(f"[START] Robust Selenium Crawler Targeting Country: {target_country}")

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument(f"user-agent={random.choice(USER_AGENTS)}")

    driver = webdriver.Chrome(options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    driver.set_window_size(1366, 768)

    posts_found = 0
    required_posts = 8

    try:
        shuffled_cities = list(cities)
        random.shuffle(shuffled_cities)
        random.shuffle(domains)
        random.shuffle(keywords)

        for target_city in shuffled_cities:
            if posts_found >= required_posts:
                break

            for target_domain in domains:
                if posts_found >= required_posts:
                    break

                for keyword in keywords:
                    if posts_found >= required_posts:
                        break
                    
                    search_urls = [
                        f"https://www.{target_domain}/jobs?q={keyword}&l={target_city}",
                        f"https://www.{target_domain}/search?q={keyword}",
                        f"https://www.{target_domain}/vagas-{keyword}",
                        f"https://www.{target_domain}"
                    ]

                    for s_url in search_urls:
                        if posts_found >= required_posts:
                            break
                        try:
                            print(f"[NAVIGATING] Visiting search URL: {s_url}")
                            driver.get(s_url)
                            time.sleep(6)

                            soup = BeautifulSoup(driver.page_source, 'html.parser')
                            default_title = f"{keyword.capitalize()} Job in {target_city}, {target_country} ({current_year})"
                            candidate_links = []
                            
                            for a in soup.find_all('a', href=True):
                                href = a['href']
                                txt = a.get_text().lower()
                                
                                if any(bad in href.lower() or bad in txt for bad in ["cookie", "privacy", "legal", "terms", "login", "register", "faq", "sign-in", "order", "sort", "filter", "search?", "help", "aviso", "ads","forgot", "download"]):
                                    continue

                                if href.startswith('/'):
                                    full_link = f"https://www.{target_domain}{href}"
                                elif href.startswith('http'):
                                    full_link = href
                                else:
                                    continue
                                
                                title_text = a.get_text().strip()
                                if len(title_text) > 100:
                                    candidate_links.append((full_link, title_text[:500]))

                            print(f"[FOUND] {len(candidate_links)} flexible candidate links on {target_domain}")

                            for j_link, j_title in candidate_links[:100]:
                                if posts_found >= required_posts:
                                    break

                                print(f"[EXTRACTING] Validating inner job post: {j_link}")
                                enriched_data = extract_strict_job_details(driver, j_link)
                                
                                if enriched_data:
                                    print(f"[SUCCESS] Verified job post found: {enriched_data['finalUrl']}")
                                    job_title = j_title if j_title and len(j_title) > 60 else default_title
                                    cta_parts = []
                                    if enriched_data["salary"] != "Not Specified":
                                        cta_parts.append(f"Estimated Salary: {enriched_data['salary']}")
                                    if enriched_data["location"]:
                                        cta_parts.append(f"Location/City: {enriched_data['location']}")
                                    if enriched_data["phone"]:
                                        cta_parts.append(f"Contact/Phone: {enriched_data['phone']}")
                                    if enriched_data["email"]:
                                        cta_parts.append(f"Email: {enriched_data['email']}")
                                    
                                    cta_parts.append(f"Direct Job Link: {enriched_data['finalUrl']}")
                                    
                                    final_snippet = enriched_data["snippet"] + "\n\nDetails:\n" + "\n".join(cta_parts)

                                    insert_data = {
                                        'title': job_title,
                                        'snippet': final_snippet,
                                        'link': enriched_data['finalUrl'],
                                        'country': f"{target_country} ({target_city})",
                                        'category': "Jobs",
                                        'query_used': f"Query: {keyword} on {target_domain}",
                                        'status': 'pending',
                                        'audit_status': None
                                    }

                                    try:
                                        print(f"[SUPABASE] Inserting record into 'zunex'...")
                                        supabase.table("zunex").insert(insert_data).execute()
                                        print(f"[INSERTED] Successfully saved valid job to database!")
                                        posts_found += 8
                                        break
                                    except Exception as db_err:
                                        print(f"[SUPABASE ERROR] Failed to insert data: {db_err}")
                                else:
                                    print(f"[REJECTED] Cleaner discarded this link as non-job or listing page.")
                            
                            if posts_found >= required_posts:
                                break

                        except Exception as nav_err:
                            print(f"[WARNING] Navigation error on {s_url}: {nav_err}")
                            continue

    except Exception as main_err:
        print(f"[CRITICAL ERROR] Crawler crashed: {main_err}")
    finally:
        driver.quit()
        print("[INFO] Browser closed successfully.")

if __name__ == "__main__":
    run_independent_crawler()
