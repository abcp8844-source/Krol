import time
import random
import re
from datetime import datetime
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY, SCHEDULE, COUNTRY_CITIES, USER_AGENTS
from domains import COUNTRY_DOMAINS
from keywords import COUNTRY_KEYWORDS
from cleaner import extract_strict_job_details

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Supabase environment variables missing")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def format_strict_title(raw_title, keyword, city, country, year):
    base = re.sub(r'\s+', ' ', raw_title).strip() if raw_title else ""
    suffix = f" - {keyword.capitalize()} Opportunity in {city}, {country} ({year}) | Direct Apply"
    
    if len(base) < 60:
        title = f"{base}{suffix}" if base else f"Immediate {keyword.capitalize()} Opening in {city}, {country} ({year}) - Direct Online Application"
    else:
        title = base

    if len(title) < 60:
        title = f"{title} - Verified Listing & Direct Application Details for {city}"

    if len(title) > 100:
        title = title[:97].rsplit(' ', 1)[0] + "..."
        if len(title) < 60:
            title = title[:100]

    return title

def is_already_scraped(url):
    try:
        res = supabase.table("zunex").select("id").eq("link", url).execute()
        return len(res.data) > 0
    except Exception:
        return False

def deep_scroll_page(driver):
    try:
        print(f"[TRACE-SCROLL] Initiating deep scroll to load dynamic elements...")
        last_height = driver.execute_script("return document.body.scrollHeight")
        for _ in range(3):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
        print(f"[TRACE-SCROLL] Deep scroll completed successfully.")
    except Exception as e:
        print(f"[TRACE-SCROLL-WARN] Scroll encountered an issue: {e}")

def search_and_insert_post(driver, target_country, category, current_year, blocked_url_terms):
    print(f"\n==================================================")
    print(f"[TRACE-COUNTRY] Starting process for Country: [{target_country}] | Category: [{category}]")
    print(f"==================================================")
    
    cities = COUNTRY_CITIES.get(target_country, [target_country])
    domains = COUNTRY_DOMAINS.get(target_country, [])
    country_kw_dict = COUNTRY_KEYWORDS.get(target_country, {})
    
    if not domains:
        print(f"[TRACE-STOP] No domains configured for country: {target_country}")
        return False
        
    if isinstance(country_kw_dict, dict):
        keywords = list(country_kw_dict.get(category, []))
    else:
        keywords = list(country_kw_dict)

    if not keywords:
        keywords = ["apply now"]

    print(f"[TRACE-INFO] Total Domains to check: {len(domains)}")
    print(f"[TRACE-INFO] Total Keywords to check: {len(keywords)}")
    print(f"[TRACE-INFO] Total Cities to check: {len(cities)}")

    for target_domain in domains:
        print(f"\n  [TRACE-DOMAIN] Shifting to Domain -> [https://www.{target_domain}]")
        
        for keyword in keywords:
            print(f"    [TRACE-QUERY] Testing Keyword/Query -> [{keyword}] on Domain -> [{target_domain}]")
            
            for target_city in cities:
                print(f"      [TRACE-CITY] Targeting City -> [{target_city}] with Keyword -> [{keyword}]")
                search_urls = [
                    f"https://www.{target_domain}/jobs?q={keyword}&l={target_city}",
                    f"https://www.{target_domain}/search?q={keyword}+{target_city}",
                    f"https://www.{target_domain}/search?q={keyword}",
                    f"https://www.{target_domain}"
                ]
                
                for s_url in search_urls:
                    try:
                        print(f"        [TRACE-NAV] Opening URL: {s_url}")
                        driver.get(s_url)
                        time.sleep(3)
                        
                        deep_scroll_page(driver)
                        
                        soup = BeautifulSoup(driver.page_source, 'html.parser')
                        candidate_links = []
                        
                        for a in soup.find_all('a', href=True):
                            href = a['href']
                            txt = a.get_text().strip()
                            
                            if any(bad in href.lower() or bad in txt.lower() for bad in blocked_url_terms):
                                continue
                                
                            if href.startswith('/'):
                                full_link = f"https://www.{target_domain}{href}"
                            elif href.startswith('http'):
                                full_link = href
                            else:
                                continue
                                
                            if full_link.rstrip('/') == f"https://www.{target_domain}":
                                continue
                                
                            if len(txt) > 10:
                                candidate_links.append((full_link, txt))

                        unique_candidates = list(dict(candidate_links).items())
                        print(f"        [TRACE-PARSE] Discovered {len(unique_candidates)} unique candidate links from URL.")

                        if not unique_candidates:
                            print(f"        [TRACE-EMPTY] No candidate links found on URL: {s_url}. Moving to next check...")

                        for j_link, j_title in unique_candidates[:12]:
                            if is_already_scraped(j_link):
                                print(f"          [TRACE-DB-SKIP] Link already exists in database: {j_link}")
                                continue
                            
                            print(f"          [TRACE-EXTRACT] Deep extracting details from link: {j_link}")
                            enriched_data = extract_strict_job_details(
                                driver, j_link, target_country, target_city, category
                            )
                            
                            if enriched_data and enriched_data.get('finalUrl'):
                                final_url = enriched_data['finalUrl']
                                if is_already_scraped(final_url):
                                    print(f"          [TRACE-DB-SKIP] Final URL already exists in database: {final_url}")
                                    continue
                                    
                                final_title = format_strict_title(
                                    j_title, keyword, target_city, target_country, current_year
                                )
                                
                                cta_parts = []
                                if enriched_data.get("salary") and enriched_data["salary"] != "Not Specified":
                                    cta_parts.append(f"Estimated Amount/Salary: {enriched_data['salary']}")
                                if enriched_data.get("location"):
                                    cta_parts.append(f"Location/City: {enriched_data['location']}")
                                if enriched_data.get("phone"):
                                    cta_parts.append(f"Contact/Phone: {enriched_data['phone']}")
                                if enriched_data.get("email"):
                                    cta_parts.append(f"Email: {enriched_data['email']}")
                                cta_parts.append(f"Direct Apply Link: {final_url}")

                                final_snippet = enriched_data.get("snippet", "") + "\n\nDetails:\n" + "\n".join(cta_parts)

                                insert_data = {
                                    'title': final_title,
                                    'snippet': final_snippet,
                                    'link': final_url,
                                    'country': f"{target_country} ({target_city})",
                                    'category': category,
                                    'query_used': f"Query: {keyword} on {target_domain}",
                                    'status': 'pending',
                                    'audit_status': None
                                }
                                
                                try:
                                    print(f"          [TRACE-DB-INSERT] Attempting insertion into Supabase...")
                                    supabase.table("zunex").insert(insert_data).execute()
                                    print(f"  [TRACE-SUCCESS] POST SECURED & INSERTED! Country: {target_country} ({target_city}) | Domain: {target_domain} | Keyword: '{keyword}'")
                                    return True
                                except Exception as db_err:
                                    print(f"  [TRACE-DB-ERROR] Insertion failed: {db_err}")
                            else:
                                print(f"          [TRACE-REJECT] Extracted data was invalid or empty for link: {j_link}")
                                    
                    except Exception as nav_err:
                        print(f"        [TRACE-NAV-ERROR] Error browsing URL {s_url}: {nav_err}")
                        continue
        
        print(f"  [TRACE-DOMAIN-EXHAUST] Domain [{target_domain}] fully exhausted across all queries and cities. Shifting to next domain...")

    print(f"[TRACE-COUNTRY-EXHAUST] All domains, queries, and cities exhausted for country [{target_country}] in category [{category}] without a match.")
    return False

def run_independent_crawler():
    if not supabase:
        print("[TRACE-CRITICAL] Supabase client is not initialized.")
        return

    today = datetime.now().strftime("%A")
    current_year = datetime.now().year
    day_countries = SCHEDULE.get(today, [])
    
    print(f"\n==================================================")
    print(f"=== CRAWLER INITIATED | Day: {today} | Year: {current_year} ===")
    print(f"=== Scheduled Countries for Today: {day_countries} ===")
    print(f"==================================================")

    if not day_countries:
        print("[TRACE-INFO] No countries scheduled for today.")
        return

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
    driver.set_page_load_timeout(35)

    blocked_url_terms = [
        "cookie", "privacy", "legal", "terms", "login", "register", "faq", "sign-in", 
        "order", "sort", "filter", "search?", "help", "aviso", "ads", "forgot", "download",
        "/salary", "/career-advice", "/resume", "/blog", "/article", "/resources", "/employers", "/about", "/contact"
    ]

    try:
        print(f"\n--------------------------------------------------")
        print(f"--- PHASE 1: STARTING JOB POSTS COLLECTION ------")
        print(f"--------------------------------------------------")
        for country in day_countries:
            print(f"\n[PHASE-1-COUNTRY] Processing Country: {country}")
            search_and_insert_post(driver, country, "Jobs", current_year, blocked_url_terms)

        print(f"\n--------------------------------------------------")
        print(f"--- PHASE 2: STARTING VISA POSTS COLLECTION -----")
        print(f"--------------------------------------------------")
        visa_collected = 0
        visa_attempts = 0
        while visa_collected < 2 and visa_attempts < 20:
            visa_countries = list(day_countries)
            random.shuffle(visa_countries)
            for country in visa_countries:
                if visa_collected >= 2:
                    break
                visa_attempts += 1
                print(f"\n[PHASE-2-VISA-ATTEMPT {visa_attempts}] Shuffled country picked: [{country}]")
                if search_and_insert_post(driver, country, "Visa", current_year, blocked_url_terms):
                    visa_collected += 1
                    print(f"[PHASE-2-VISA-PROGRESS] Total Visa Posts Collected: {visa_collected}/2")

        print(f"\n--------------------------------------------------")
        print(f"--- PHASE 3: STARTING TRAVEL POSTS COLLECTION ---")
        print(f"--------------------------------------------------")
        travel_collected = 0
        travel_attempts = 0
        while travel_collected < 2 and travel_attempts < 20:
            travel_countries = list(day_countries)
            random.shuffle(travel_countries)
            for country in travel_countries:
                if travel_collected >= 2:
                    break
                travel_attempts += 1
                print(f"\n[PHASE-3-TRAVEL-ATTEMPT {travel_attempts}] Shuffled country picked: [{country}]")
                if search_and_insert_post(driver, country, "Travel", current_year, blocked_url_terms):
                    travel_collected += 1
                    print(f"[PHASE-3-TRAVEL-PROGRESS] Total Travel Posts Collected: {travel_collected}/2")

        print(f"\n==================================================")
        print("=== CRAWLER EXECUTION COMPLETED SUCCESSFULLY ===")
        print(f"==================================================")

    except Exception as e:
        print(f"[TRACE-CRITICAL-ERROR] Crawler aborted due to exception: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    run_independent_crawler()
