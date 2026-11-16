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

def search_and_insert_post(page, target_country, category, current_year, blocked_url_terms):
    cities = COUNTRY_CITIES.get(target_country, [target_country])
    domains = COUNTRY_DOMAINS.get(target_country, [])
    country_kw_dict = COUNTRY_KEYWORDS.get(target_country, {"Jobs": ["apply now"], "Visa": ["visa apply"], "Travel": ["travel tour"]})
    
    if not domains:
        return False
        
    if isinstance(country_kw_dict, dict):
        keywords = list(country_kw_dict.get(category, ["apply now"]))
    else:
        keywords = list(country_kw_dict)

    shuffled_cities = list(cities)
    random.shuffle(shuffled_cities)
    shuffled_domains = list(domains)
    random.shuffle(shuffled_domains)
    shuffled_keywords = list(keywords)
    random.shuffle(shuffled_keywords)

    for target_city in shuffled_cities:
        for target_domain in shuffled_domains:
            for keyword in shuffled_keywords:
                search_urls = [
                    f"https://www.{target_domain}/jobs?q={keyword}&l={target_city}",
                    f"https://www.{target_domain}/search?q={keyword}",
                    f"https://www.{target_domain}/vagas-{keyword}",
                    f"https://www.{target_domain}"
                ]
                for s_url in search_urls:
                    try:
                        print(f"[TRACE-NAV] Navigating to: {s_url}")
                        page.goto(s_url, timeout=20000)
                        time.sleep(3)
                        
                        raw_links = page.eval_on_selector_all(
                            "a[href]",
                            """elements => elements.map(el => ({
                                href: el.href,
                                text: el.innerText ? el.innerText.trim() : ''
                            }))"""
                        )
                        
                        candidate_links = []
                        for item in raw_links:
                            href = item['href']
                            title_text = item['text']
                            txt = title_text.lower()
                            
                            if any(bad in href.lower() or bad in txt for bad in blocked_url_terms):
                                continue
                            if href.startswith('/'):
                                full_link = f"https://www.{target_domain}{href}"
                            elif href.startswith('http'):
                                full_link = href
                            else:
                                continue
                            if full_link.rstrip('/') == f"https://www.{target_domain}":
                                continue
                            if len(title_text) > 12:
                                candidate_links.append((full_link, title_text))

                        print(f"[TRACE-PARSE] Found {len(candidate_links)} candidate links.")

                        for j_link, j_title in candidate_links[:20]:
                            if is_already_scraped(j_link):
                                continue
                            
                            print(f"[TRACE-EXTRACT] Extracting details for: {j_link}")
                            enriched_data = extract_strict_job_details(
                                page, j_link, target_country, target_city, category
                            )
                            if enriched_data:
                                if is_already_scraped(enriched_data['finalUrl']):
                                    continue
                                final_title = format_strict_title(
                                    j_title, keyword, target_city, target_country, current_year
                                )
                                if target_country.lower() not in final_title.lower() and target_city.lower() not in final_title.lower():
                                    continue
                                
                                cta_parts = []
                                if enriched_data["salary"] != "Not Specified":
                                    cta_parts.append(f"Estimated Amount/Salary: {enriched_data['salary']}")
                                if enriched_data["location"]:
                                    cta_parts.append(f"Location/City: {enriched_data['location']}")
                                if enriched_data["phone"]:
                                    cta_parts.append(f"Contact/Phone: {enriched_data['phone']}")
                                if enriched_data["email"]:
                                    cta_parts.append(f"Email: {enriched_data['email']}")
                                cta_parts.append(f"Direct Apply Link: {enriched_data['finalUrl']}")

                                final_snippet = enriched_data["snippet"] + "\n\nDetails:\n" + "\n".join(cta_parts)

                                insert_data = {
                                    'title': final_title,
                                    'snippet': final_snippet,
                                    'link': enriched_data['finalUrl'],
                                    'country': f"{target_country} ({target_city})",
                                    'category': category,
                                    'query_used': f"Query: {keyword} on {target_domain}",
                                    'status': 'pending',
                                    'audit_status': None
                                }
                                try:
                                    supabase.table("zunex").insert(insert_data).execute()
                                    print(f"[TRACE-SUCCESS] Saved post: {final_title}")
                                    time.sleep(3)
                                    return True
                                except Exception as db_err:
                                    print(f"[TRACE-DB-ERROR] {db_err}")
                                    pass
                    except Exception as nav_err:
                        print(f"[TRACE-NAV-ERROR] {nav_err}")
                        continue
    return False

def run_independent_crawler():
    if not supabase:
        print("[TRACE-CRITICAL] Supabase client is not initialized.")
        return

    today = datetime.now().strftime("%A")
    current_year = datetime.now().year
    day_countries = SCHEDULE.get(today, [])
    
    print(f"\n==================================================")
    print(f"=== PLAYWRIGHT CRAWLER | Day: {today} | Year: {current_year} ===")
    print(f"=== Scheduled Countries: {day_countries} ===")
    print(f"==================================================")

    if not day_countries:
        return

    blocked_url_terms = [
        "cookie", "privacy", "legal", "terms", "login", "register", "faq", "sign-in", 
        "order", "sort", "filter", ", "help", "aviso", "ads", "forgot", "download",
        "/", "/career-advice", "/resume", "/blog", "", "/resources", "", "/about", "/contact"
    ]

    with sync_playwright() as p:
        print("[TRACE-INIT] Launching Playwright Chromium Headless Browser...")
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--ignore-certificate-errors",
                "--ignore-ssl-errors"
            ]
        )
        
        context = browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1366, "height": 768},
            bypass_csp=True,
            ignore_https_errors=True
        )
        
        page = context.new_page()
        page.set_default_timeout(20000)

        try:
            print(f"\n--- PHASE 1: COLLECTING JOBS ---")
            for country in day_countries:
                search_and_insert_post(page, country, "Jobs", current_year, blocked_url_terms)

            print(f"\n--- PHASE 2: COLLECTING VISA POSTS ---")
            visa_collected = 0
            while visa_collected < 2:
                shuffled_visa_countries = list(day_countries)
                random.shuffle(shuffled_visa_countries)
                for country in shuffled_visa_countries:
                    if visa_collected >= 2:
                        break
                    if search_and_insert_post(page, country, "Visa", current_year, blocked_url_terms):
                        visa_collected += 1

            print(f"\n--- PHASE 3: COLLECTING TRAVEL POSTS ---")
            travel_collected = 0
            while travel_collected < 2:
                shuffled_travel_countries = list(day_countries)
                random.shuffle(shuffled_travel_countries)
                for country in shuffled_travel_countries:
                    if travel_collected >= 2:
                        break
                    if search_and_insert_post(page, country, "Travel", current_year, blocked_url_terms):
                        travel_collected += 1

            print(f"\n=== CRAWLER FINISHED SUCCESSFULLY ===")

        except Exception as e:
            print(f"[TRACE-CRITICAL-ERROR] {e}")
        finally:
            browser.close()
            print("[TRACE-SHUTDOWN] Playwright browser closed.")

if __name__ == "__main__":
    run_independent_crawler()
