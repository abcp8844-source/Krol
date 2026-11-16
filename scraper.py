import time
import random
import re
from datetime import datetime
from playwright.sync_api import sync_playwright
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
    except Exception as e:
        print(f"[TRACE-DB-CHECK-ERROR] {e}")
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

def deep_scroll_page(page):
    try:
        print(f"[TRACE-SCROLL] Initiating Playwright smooth deep scroll for dynamic content loading...")
        for _ in range(3):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.8)
    except Exception as e:
        print(f"[TRACE-SCROLL-ERROR] {e}")

def search_and_insert_post(page, target_country, category, current_year, blocked_url_terms):
    print(f"\n==================================================")
    print(f"[TRACE-COUNTRY] Starting flexible process for Country: [{target_country}] | Category: [{category}]")
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

    # لچکدار اور رینڈم طریقے سے شفل کرنا تاکہ ہر بار نئے کمبینیشنز چیک ہوں
    random.shuffle(domains)
    random.shuffle(keywords)
    random.shuffle(cities)

    print(f"[TRACE-INFO] Flexible Config -> Domains: {len(domains)} | Keywords: {len(keywords)} | Cities: {len(cities)}")

    for target_domain in domains:
        print(f"\n  [TRACE-DOMAIN] Evaluating Domain -> [https://www.{target_domain}]")
        
        base_domain_url = f"https://www.{target_domain}"
        try:
            page.goto(base_domain_url, wait_until="domcontentloaded", timeout=25000)
            time.sleep(2)
            current_loaded_url = page.url
            if not current_loaded_url or "error" in current_loaded_url.lower():
                print(f"  [TRACE-REJECT] Domain [{target_domain}] failed to connect. Skipping.")
                continue
        except Exception as conn_err:
            print(f"  [TRACE-ERROR] Connection failed for [{target_domain}]: {conn_err}. Moving to next.")
            continue

        for keyword in keywords:
            encoded_kw = keyword.replace(" ", "%20")
            
            for target_city in cities:
                encoded_city = target_city.replace(" ", "%20")
                
                # لچکدار اور تفصیلی سرچ پاتھز جو مختلف ویب سائٹس کے ڈھانچے کو کور کرتے ہیں
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
                        print(f"    [TRACE-NAV] Testing Path -> Domain: {target_domain} | Keyword: '{keyword}' | City: '{target_city}'")
                        page.goto(s_url, wait_until="domcontentloaded", timeout=20000)
                        time.sleep(2)
                        
                        deep_scroll_page(page)
                        
                        raw_links = page.eval_on_selector_all(
                            "a[href]",
                            """elements => elements.map(el => ({
                                href: el.href,
                                text: el.innerText ? el.innerText.trim() : ''
                            }))"""
                        )
                        
                        candidate_links = []
                        deep_identifiers = [
                            "/job", "/vacancy", "/vagas", "/loker", "/emploi", "/career", 
                            "/hiring", "/position", "/listing", "/item", "/post", "/details",
                            "/visa", "/travel", "/tour", "/application", "/apply"
                        ]

                        for item in raw_links:
                            href = item['href']
                            txt = item['text']
                            
                            # فلٹرنگ: اشتہارات، لاگ ان، پالیسی یا فضول لنکس کو فوراً باہر کرنا
                            if any(bad in href.lower() or bad in txt.lower() for bad in blocked_url_terms):
                                continue
                                
                            if is_root_or_homepage(href, target_domain):
                                continue
                            
                            is_valid_deep_link = any(ind in href.lower() for ind in deep_identifiers) or len(txt) > 10
                            if is_valid_deep_link:
                                title_candidate = txt if len(txt) > 5 else f"{category} Opportunity for {keyword} in {target_city}"
                                candidate_links.append((href, title_candidate))

                        unique_candidates = list(dict(candidate_links).items())
                        print(f"      [TRACE-PARSE] Found {len(unique_candidates)} filtered action-oriented links.")

                        if not unique_candidates:
                            continue

                        for j_link, j_title in unique_candidates[:8]:
                            if is_root_or_homepage(j_link, target_domain) or is_already_scraped(j_link):
                                continue
                            
                            print(f"        [TRACE-EXTRACT] Deep verifying and extracting: {j_link}")
                            enriched_data = extract_strict_job_details(
                                page, j_link, target_country, target_city, category, keyword
                            )
                            
                            # اگر کلینر نے ڈیٹا کو پاس کر دیا (یعنی یہ فالتو ایڈ یا پالیسی پیج نہیں ہے)
                            if enriched_data and enriched_data.get('finalUrl'):
                                final_url = enriched_data['finalUrl']
                                
                                if is_root_or_homepage(final_url, target_domain) or is_already_scraped(final_url):
                                    print(f"        [TRACE-REJECT] Final URL is homepage or already scraped.")
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
                                    print(f"  [TRACE-SUCCESS] ACTIONABLE POST SECURED & SAVED! Country: {target_country} ({target_city})")
                                    return True
                                except Exception as db_err:
                                    print(f"  [TRACE-DB-ERROR] Insertion failed: {db_err}")
                                    
                    except Exception as nav_err:
                        continue
        
        print(f"  [TRACE-DOMAIN-EXHAUST] Domain [{target_domain}] fully checked. Shifting to next.")

    print(f"[TRACE-COUNTRY-EXHAUST] All domains exhausted for country [{target_country}] in [{category}].")
    return False

def run_independent_crawler():
    if not supabase:
        print("[TRACE-CRITICAL] Supabase client is not initialized.")
        return

    today = datetime.now().strftime("%A")
    current_year = datetime.now().year
    day_countries = SCHEDULE.get(today, [])
    
    print(f"\n==================================================")
    print(f"=== FLEXIBLE PLAYWRIGHT CRAWLER | Day: {today} | Year: {current_year} ===")
    print(f"=== Scheduled Countries: {day_countries} ===")
    print(f"==================================================")

    if not day_countries:
        print("[TRACE-INFO] No countries scheduled for today.")
        return

    blocked_url_terms = [
        "cookie", "privacy", "legal", "terms", "login", "register", "faq", "sign-in", 
        "order", "sort", "filter", "search?", "help", "aviso", "ads", "forgot", "download",
        "/salary", "/career-advice", "/resume", "/blog", "/article", "/resources", "/employers", "/about", "/contact",
        "climate", "strategy", "policy", "news", "press", "events"
    ]

    with sync_playwright() as p:
        print("[TRACE-INIT] Launching Playwright Chromium Headless Browser...")
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled"
            ]
        )
        
        context = browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1366, "height": 768},
            bypass_csp=True
        )
        
        page = context.new_page()
        page.set_default_timeout(30000)

        try:
            print(f"\n--------------------------------------------------")
            print(f"--- PHASE 1: COLLECTING ACTIONABLE JOB POSTS ----")
            print(f"--------------------------------------------------")
            for country in day_countries:
                search_and_insert_post(page, country, "Jobs", current_year, blocked_url_terms)

            print(f"\n--------------------------------------------------")
            print(f"--- PHASE 2: COLLECTING ACTIONABLE VISA POSTS ---")
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
                    if search_and_insert_post(page, country, "Visa", current_year, blocked_url_terms):
                        visa_collected += 1

            print(f"\n--------------------------------------------------")
            print(f"--- PHASE 3: COLLECTING ACTIONABLE TRAVEL POSTS -")
            print(f"--------------------------------------------------")
            travel_collected = 0
            travel_attempts = 0
            while travel_collected < 2 and travel_attempts < 15:
                travel_countries = list(day_countries)
                random.shuffle(travel_countries)
                for country in visa_countries:
                    if travel_collected >= 2:
                        break
                    travel_attempts += 1
                    if search_and_insert_post(page, country, "Travel", current_year, blocked_url_terms):
                        travel_collected += 1

            print(f"\n==================================================")
            print("=== CRAWLER EXECUTION COMPLETED SUCCESSFULLY ===")
            print(f"==================================================")

        except Exception as e:
            print(f"[TRACE-CRITICAL-ERROR] Crawler aborted due to exception: {e}")
        finally:
            browser.close()
            print("[TRACE-SHUTDOWN] Playwright browser closed cleanly.")

if __name__ == "__main__":
    run_independent_crawler()
