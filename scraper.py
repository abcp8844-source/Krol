import time
import random
import re
from datetime import datetime
from urllib.parse import quote
from playwright.sync_api import sync_playwright
from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY, SCHEDULE, COUNTRY_CITIES, USER_AGENTS
from domains import COUNTRY_DOMAINS
from keywords import COUNTRY_KEYWORDS
from cleaner import extract_strict_job_details

try:
    from config import SEARCH_COUNTRY_NAMES, SEARCH_CITY_NAMES
except ImportError:
    SEARCH_COUNTRY_NAMES = {}
    SEARCH_CITY_NAMES = {}

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Supabase environment variables missing")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def get_search_country(country):
    return SEARCH_COUNTRY_NAMES.get(country, country)


def get_search_city(city):
    return SEARCH_CITY_NAMES.get(city, city)


def format_strict_title(raw_title, keyword, local_city, local_country, year):
    base = re.sub(r'\s+', ' ', raw_title).strip() if raw_title else ""
    suffix = f" - {keyword} | {local_city}, {local_country} ({year})"

    if len(base) < 60:
        title = f"{base}{suffix}" if base else f"{keyword} - {local_city}, {local_country} ({year})"
    else:
        title = base

    if len(title) < 60:
        title = f"{title} - {local_city} {local_country}"

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


def build_search_urls(domain, keyword, search_city, category):
    encoded_kw = quote(keyword)
    encoded_city = quote(search_city)
    cat_lower = (category or "Jobs").lower()

    urls = [
        f"https://www.{domain}/search?q={encoded_kw}+{encoded_city}",
        f"https://www.{domain}/search?q={encoded_kw}",
    ]

    if cat_lower == "jobs":
        urls.extend([
            f"https://www.{domain}/jobs?q={encoded_kw}&l={encoded_city}",
            f"https://www.{domain}/jobs?q={encoded_kw}",
            f"https://www.{domain}/vagas-{encoded_kw}",
        ])
    elif cat_lower == "visa":
        urls.extend([
            f"https://www.{domain}/visa?q={encoded_kw}",
            f"https://www.{domain}/search?q=visa+{encoded_kw}+{encoded_city}",
        ])
    elif cat_lower == "travel":
        urls.extend([
            f"https://www.{domain}/travel?q={encoded_kw}",
            f"https://www.{domain}/search?q=travel+{encoded_kw}+{encoded_city}",
        ])

    urls.append(f"https://www.{domain}")
    return urls


def is_relevant_candidate(href, title_text, category, blocked_url_terms):
    href_l = href.lower()
    txt_l = title_text.lower()

    if any(bad in href_l or bad in txt_l for bad in blocked_url_terms):
        return False

    if len(title_text.strip()) < 12:
        return False

    cat_lower = (category or "Jobs").lower()
    if cat_lower == "jobs":
        job_hints = [
            "job", "career", "vacancy", "opening", "hiring", "apply",
            "position", "work", "emploi", "trabajo", "vaga", "stellen", "offre",
            "وظائف", "توظيف", "求人", "採用", "채용", "招聘", "職缺",
            "สมัครงาน", "việc làm", "kerja", "lowongan", "vacantes", "lavoro", "iş"
        ]
        if not any(h in href_l or h in txt_l for h in job_hints):
            return False

    return True


def safe_goto(page, url, timeout=25000):
    page.goto(url, timeout=timeout, wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=6000)
    except Exception:
        pass
    time.sleep(2)


def search_and_insert_post(page, target_country, category, current_year, blocked_url_terms):
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
        print(f"[TRACE-STOP] No keywords found for category [{category}] in country [{target_country}]")
        return False

    search_country = get_search_country(target_country)

    shuffled_cities = list(cities)
    random.shuffle(shuffled_cities)
    shuffled_domains = list(domains)
    random.shuffle(shuffled_domains)
    shuffled_keywords = list(keywords)
    random.shuffle(shuffled_keywords)

    print(
        f"[TRACE-INFO] Config -> Domains: {len(shuffled_domains)} | "
        f"Keywords: {len(shuffled_keywords)} | Cities: {len(shuffled_cities)}"
    )

    for target_domain in shuffled_domains:
        print(f"\n  [TRACE-DOMAIN] Evaluating Domain -> [https://www.{target_domain}]")
        base_domain_url = f"https://www.{target_domain}"

        try:
            safe_goto(page, base_domain_url, timeout=25000)
            page_text = page.content().lower()
            if any(wall in page_text for wall in ["please sign in", "log in to continue", "sign in to view", "login required"]):
                print(f"  [TRACE-WALL] Login/Sign-in wall detected on domain [{target_domain}]. Shifting to next domain.")
                continue
        except Exception as conn_err:
            print(f"  [TRACE-DOMAIN-ERROR] Connection failed or timed out for [{target_domain}]: {conn_err}. Shifting to next domain.")
            continue

        for target_city in shuffled_cities:
            search_city = get_search_city(target_city)

            for keyword in shuffled_keywords:
                search_urls = build_search_urls(target_domain, keyword, search_city, category)

                for s_url in search_urls:
                    try:
                        print(f"    [TRACE-NAV] Navigating to: {s_url}")
                        safe_goto(page, s_url, timeout=25000)

                        current_content = page.content().lower()
                        if any(wall in current_content for wall in ["sign in to view", "log in to apply", "please login"]):
                            print(f"    [TRACE-WALL] Sign-in wall encountered on search URL. Moving on.")
                            break

                        for _ in range(2):
                            page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                            time.sleep(1.2)

                        raw_links = page.eval_on_selector_all(
                            "a[href]",
                            """elements => elements.map(el => ({
                                href: el.href,
                                text: el.innerText ? el.innerText.replace(/\\s+/g, ' ').trim() : ''
                            }))"""
                        )

                        candidate_links = []
                        seen_hrefs = set()

                        for item in raw_links:
                            href = (item.get('href') or '').strip()
                            title_text = (item.get('text') or '').strip()

                            if href.startswith('/'):
                                full_link = f"https://www.{target_domain}{href}"
                            elif href.startswith('http'):
                                full_link = href
                            else:
                                continue

                            if full_link.rstrip('/') == f"https://www.{target_domain}":
                                continue

                            if full_link in seen_hrefs:
                                continue

                            if not is_relevant_candidate(full_link, title_text, category, blocked_url_terms):
                                continue

                            seen_hrefs.add(full_link)
                            candidate_links.append((full_link, title_text))

                        print(f"      [TRACE-PARSE] Found {len(candidate_links)} filtered candidate links on {target_domain}")

                        for j_link, j_title in candidate_links[:25]:
                            if is_already_scraped(j_link):
                                continue

                            print(f"        [TRACE-EXTRACT] Extracting details for: {j_link}")
                            enriched_data = extract_strict_job_details(
                                page, j_link, target_country, target_city, category, keyword
                            )

                            if enriched_data and enriched_data.get('finalUrl'):
                                snippet_body = (enriched_data.get("snippet") or "").strip()
                                if len(snippet_body) < 80:
                                    print(f"        [TRACE-REJECT] Extracted snippet too short/thin ({len(snippet_body)} chars).")
                                    continue

                                if is_already_scraped(enriched_data['finalUrl']):
                                    print(f"        [TRACE-REJECT] Final URL already scraped.")
                                    continue

                                final_title = format_strict_title(
                                    j_title, keyword, search_city, search_country, current_year
                                )

                                location_tokens = [
                                    target_country.lower(),
                                    target_city.lower(),
                                    search_country.lower(),
                                    search_city.lower(),
                                ]
                                combined_check = (final_title + " " + snippet_body).lower()
                                if not any(tok and tok in combined_check for tok in location_tokens):
                                    continue

                                cta_parts = []
                                if enriched_data.get("salary") and enriched_data["salary"] != "Not Specified":
                                    cta_parts.append(f"Estimated Amount/Salary: {enriched_data['salary']}")
                                if enriched_data.get("location"):
                                    cta_parts.append(f"Location/City: {enriched_data['location']}")
                                if enriched_data.get("phone"):
                                    cta_parts.append(f"Contact/Phone: {enriched_data['phone']}")
                                if enriched_data.get("email"):
                                    cta_parts.append(f"Email: {enriched_data['email']}")
                                cta_parts.append(f"Direct Apply Link: {enriched_data['finalUrl']}")

                                final_snippet = snippet_body + "\n\nDetails:\n" + "\n".join(cta_parts)

                                db_country = (
                                    f"{target_country} ({search_country}) - {target_city} ({search_city})"
                                    if (search_country != target_country or search_city != target_city)
                                    else f"{target_country} ({target_city})"
                                )

                                insert_data = {
                                    'title': final_title,
                                    'snippet': final_snippet,
                                    'link': enriched_data['finalUrl'],
                                    'country': db_country,
                                    'category': category,
                                    'query_used': f"Query: {keyword} | City: {search_city} | Domain: {target_domain}",
                                    'status': 'pending',
                                    'audit_status': None
                                }
                                try:
                                    supabase.table("zunex").insert(insert_data).execute()
                                    print(f"  [TRACE-SUCCESS] Saved post to DB: {final_title}")
                                    time.sleep(3)
                                    return True
                                except Exception as db_err:
                                    print(f"  [TRACE-DB-ERROR] {db_err}")
                                    pass
                    except Exception as nav_err:
                        print(f"    [TRACE-NAV-ERROR] {nav_err}")
                        continue

        print(f"  [TRACE-DOMAIN-EXHAUST] Domain [{target_domain}] checked. Shifting to next domain.")

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
    print(f"=== PLAYWRIGHT CRAWLER | Day: {today} | Year: {current_year} ===")
    print(f"=== Scheduled Countries: {day_countries} ===")
    print(f"==================================================")

    if not day_countries:
        print("[TRACE-INFO] No countries scheduled for today.")
        return

    blocked_url_terms = [
        "cookie", "privacy", "legal", "terms", "login", "register", "faq", "sign-in",
        "order", "sort", "filter", "search?", "help", "aviso", "ads", "forgot", "download",
        "/salary", "/career-advice", "/resume", "/blog", "/article", "/resources",
        "/employers", "/about", "/contact", "facebook.com", "twitter.com", "x.com",
        "linkedin.com", "instagram.com", "youtube.com", "mailto:", "tel:"
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
        page.set_default_timeout(25000)

        try:
            print(f"\n--------------------------------------------------")
            print(f"--- PHASE 1: COLLECTING JOBS ---------------------")
            print(f"--------------------------------------------------")
            for country in day_countries:
                search_and_insert_post(page, country, "Jobs", current_year, blocked_url_terms)

            print(f"\n--------------------------------------------------")
            print(f"--- PHASE 2: COLLECTING VISA POSTS ---------------")
            print(f"--------------------------------------------------")
            visa_collected = 0
            while visa_collected < 2:
                shuffled_visa_countries = list(day_countries)
                random.shuffle(shuffled_visa_countries)
                for country in shuffled_visa_countries:
                    if visa_collected >= 2:
                        break
                    if search_and_insert_post(page, country, "Visa", current_year, blocked_url_terms):
                        visa_collected += 1

            print(f"\n--------------------------------------------------")
            print(f"--- PHASE 3: COLLECTING TRAVEL POSTS -------------")
            print(f"--------------------------------------------------")
            travel_collected = 0
            while travel_collected < 2:
                shuffled_travel_countries = list(day_countries)
                random.shuffle(shuffled_travel_countries)
                for country in shuffled_travel_countries:
                    if travel_collected >= 2:
                        break
                    if search_and_insert_post(page, country, "Travel", current_year, blocked_url_terms):
                        travel_collected += 1

            print(f"\n==================================================")
            print("=== ALL TARGETS ACHIEVED. CRAWLER FINISHED SUCCESSFULLY ===")
            print(f"==================================================")

        except Exception as e:
            print(f"[TRACE-CRITICAL-ERROR] {e}")
        finally:
            browser.close()
            print("[TRACE-SHUTDOWN] Playwright browser closed cleanly.")


if __name__ == "__main__":
    run_independent_crawler()
