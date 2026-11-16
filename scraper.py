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

def is_root_or_homepage(url, domain):
    if not url:
        return True
    clean_url = url.strip().rstrip('/')
    clean_domain = domain.strip().rstrip('/')
    
    if clean_url in [f"https://www.{clean_domain}", f"https://{clean_domain}", f"http://www.{clean_domain}", f"http://{clean_domain}"]:
        return True
    
    parsed_path = clean_url.replace(f"https://www.{clean_domain}", "").replace(f"https://{clean_domain}", "").replace(f"http://www.{clean_domain}", "").replace(f"http://{clean_domain}", "")
    if not parsed_path or parsed_path == "/":
        return True
        
    return False

def deep_scroll_page(driver):
    try:
        print(f"[TRACE-SCROLL] Initiating deep scroll...")
        for _ in range(3):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
    except Exception as e:
        pass

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
        keywords = ["apply now", "visa support", "travel package"]

    print(f"[TRACE-INFO] Total Domains: {len(domains)} | Keywords: {len(keywords)} | Cities: {len(cities)}")

    for target_domain in domains:
        print(f"\n  [TRACE-DOMAIN] Evaluating Domain -> [https://www.{target_domain}]")
        
        base_domain_url = f"https://www.{target_domain}"
        try:
            driver.get(base_domain_url)
            time.sleep(2.5)
            current_loaded_url = driver.current_url
            if not current_loaded_url or "error" in current_loaded_url.lower():
                print(f"  [TRACE-REJECT] Domain [{target_domain}] failed to connect. Skipping.")
                continue
        except Exception as conn_err:
            print(f"  [TRACE-ERROR] Connection failed for [{target_domain}]: {conn_err}. Moving to next.")
            continue

        domain_has_activity = False

        for keyword in keywords:
            encoded_kw = keyword.replace(" ", "%20")
            
            for target_city in cities:
                encoded_city = target_city.replace(" ", "%20")
                
                deep_paths = [
                    f"/jobs/search/?q={encoded_kw}&location={encoded_city}",
                    f"/search/?q={encoded_kw}&loc={encoded_city}",
                    f"/jobs?q={encoded_kw}&l={encoded_city}",
                    f"/search?q={encoded_kw}",
                    f"/jobs/{encoded_city.lower()}/?q={encoded_kw}",
                    f"/careers/search?query={encoded_kw}&city={encoded_city}",
                    f"/vacancies?keyword={encoded_kw}&city={encoded_city}",
                    f"/visa-services?q={encoded_kw}&location={encoded_city}",
                    f"/travel-packages?q={encoded_kw}&destination={encoded_city}",
                    f"/listings?q={encoded_kw}&l={encoded_city}"
                ]
                
                for path in deep_paths:
                    s_url = f"https://www.{target_domain}{path}"
                    try:
                        print(f"    [TRACE-NAV] Trying Deep Path -> Domain: {target_domain} | Keyword: '{keyword}' | City: '{target_city}' | Path: {path}")
                        driver.get(s_url)
                        time.sleep(2.5)
                        
                        deep_scroll_page(driver)
                        
                        soup = BeautifulSoup(driver.page_source, 'html.parser')
                        candidate_links = []
                        
                        deep_identifiers = [
                            "/job", "/vacancy", "/vagas", "/loker", "/emploi", "/career", 
                            "/hiring", "/position", "/listing", "/item", "/post", "/details",
                            "/visa", "/travel", "/tour", "/application", "/apply"
                        ]

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
                                
                            if is_root_or_homepage(full_link, target_domain):
                                continue
                            
                            is_valid_deep_link = any(ind in full_link.lower() for ind in deep_identifiers) or len(txt) > 8
                            
                            if is_valid_deep_link:
                                title_candidate = txt if len(txt) > 5 else f"{category} Opportunity for {keyword} in {target_city}"
                                candidate_links.append((full_link, title_candidate))

                        unique_candidates = list(dict(candidate_links).items())
                        print(f"      [TRACE-PARSE] Discovered {len(unique_candidates)} unique candidate links from deep path.")

                        if not unique_candidates:
                            continue

                        domain_has_activity = True

                        for j_link, j_title in unique_candidates[:10]:
                            if is_root_or_homepage(j_link, target_domain) or is_already_scraped(j_link):
                                continue
                            
                            print(f"        [TRACE-EXTRACT] Deep extracting details: {j_link}")
                            enriched_data = extract_strict_job_details(
                                driver, j_link, target_country, target_city, category
                            )
                            
                            if enriched_data and enriched_data.get('finalUrl'):
                                final_url = enriched_data['finalUrl']
                                
                                if is_root_or_homepage(final_url, target_domain) or is_already_scraped(final_url):
                                    print(f"        [TRACE-REJECT] Final URL is homepage or already scraped: {final_url}")
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
                                    'query_used': f"Query: {keyword} via path {path} on {target_domain}",
                                    'status': 'pending',
                                    'audit_status': None
                                }
                                
                                try:
                                    supabase.table("zunex").insert(insert_data).execute()
                                    print(f"  [TRACE-SUCCESS] VALID POST SECURED & INSERTED! Country: {target_country} ({target_city}) | Domain: {target_domain}")
                                    return True
                                except Exception as db_err:
                                    print(f"  [TRACE-DB-ERROR] Insertion failed: {db_err}")
                                    
                    except Exception as nav_err:
                        continue
        
        print(f"  [TRACE-DOMAIN-EXHAUST] Domain [{target_domain}] fully exhausted across deep paths. Shifting to next domain.")

    print(f"[TRACE-COUNTRY-EXHAUST] All domains exhausted for country [{target_country}] in category [{category}].")
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
    driver.set_page_load_timeout(30)

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
        while visa_collected < 2 and visa_attempts < 15:
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
        while travel_collected < 2 and travel_attempts < 15:
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
