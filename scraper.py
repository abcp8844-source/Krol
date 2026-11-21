import random
import re
import time
from datetime import datetime
from urllib.parse import quote, urlparse
from playwright.sync_api import sync_playwright
from supabase import Client, create_client
from config import COUNTRY_CITIES, SCHEDULE, SUPABASE_KEY, SUPABASE_URL, USER_AGENTS
from domains import COUNTRY_DOMAINS
from keywords import COUNTRY_KEYWORDS
from cleaner import extract_strict_job_details

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Supabase environment variables missing")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

MAX_CANDIDATE_LINKS = 15
MAX_TIME_PER_DOMAIN_SEC = 35
MAX_TIME_PER_COUNTRY_SEC = 180


def _normalize_domain(domain: str) -> str:
    d = (domain or "").strip().lower()
    if d.startswith("http://") or d.startswith("https://"):
        d = urlparse(d).netloc
    return d.lstrip("/")


def format_strict_title(raw_title, keyword, city, country, year):
    base = re.sub(r"\s+", " ", raw_title or "").strip()
    kw_clean = re.sub(r"\s+", " ", keyword or "").strip()
    suffix = f" - {kw_clean} in {city}, {country} ({year}) | Direct Details"

    if len(base) < 60:
        title = f"{base}{suffix}" if base else f"{kw_clean} Opportunity in {city}, {country} ({year}) - Direct Details"
    else:
        title = base

    if len(title) < 60:
        title = f"{title} - Verified Listing & Guide for {city}, {country}"

    if len(title) > 100:
        title = title[:97].rsplit(" ", 1)[0] + "..."
        if len(title) < 60:
            title = title[:100]

    return title


def is_already_scraped(url):
    if not url:
        return False
    try:
        res = supabase.table("zunex").select("id").eq("link", url).limit(1).execute()
        return bool(res.data)
    except Exception as e:
        print(f"[TRACE-DB-CHECK-ERROR] {e}")
        return False


def _route_heavy_assets(route):
    if route.request.resource_type in {"image", "media", "font"}:
        route.abort()
    else:
        route.continue_()


def _build_search_urls(domain: str, keyword: str, city: str, category: str) -> list:
    clean_dom = _normalize_domain(domain)
    base_url = f"https://{clean_dom}"
    enc_kw = quote(keyword)
    enc_city = quote(city)

    if category == "Jobs":
        return [
            f"{base_url}/jobs?q={enc_kw}&l={enc_city}",
            f"{base_url}/search?q={enc_kw}",
            base_url,
        ]
    return [
        f"{base_url}/search?q={enc_kw}+{enc_city}",
        f"{base_url}/?s={enc_kw}",
        base_url,
    ]


def _get_keywords_for_country_category(target_country: str, category: str) -> list:
    country_kw_dict = COUNTRY_KEYWORDS.get(target_country, {})
    if isinstance(country_kw_dict, dict):
        kw_list = list(country_kw_dict.get(category) or [])
        if kw_list:
            return kw_list
        for fallback_cat in ("Jobs", "Visa", "Travel"):
            if country_kw_dict.get(fallback_cat):
                return list(country_kw_dict[fallback_cat])
    elif isinstance(country_kw_dict, (list, tuple)):
        return list(country_kw_dict)
    return []


def search_and_insert_post(page, target_country, category, current_year, blocked_url_terms):
    print(f"\n==================================================")
    print(f"[TRACE-COUNTRY] Country: [{target_country}] | Category: [{category}]")
    print(f"==================================================")

    cities = list(COUNTRY_CITIES.get(target_country, [target_country]))
    domains = list(COUNTRY_DOMAINS.get(target_country, []))
    keywords = _get_keywords_for_country_category(target_country, category)

    if not domains:
        print(f"[TRACE-STOP] No domains for [{target_country}]. Moving to next country.")
        return False

    if not keywords:
        print(f"[TRACE-STOP] No keywords for [{target_country}] / [{category}]. Moving to next country.")
        return False

    random.shuffle(cities)
    random.shuffle(domains)
    random.shuffle(keywords)

    country_start = time.monotonic()
    print(
        f"[TRACE-INFO] [{target_country}] -> Domains: {len(domains)} | "
        f"Cities: {len(cities)} | Keywords: {len(keywords)}"
    )

    for target_domain in domains:
        if time.monotonic() - country_start > MAX_TIME_PER_COUNTRY_SEC:
            print(f"[TRACE-COUNTRY-CAP] Time cap reached for [{target_country}]. Moving to next country.")
            break

        clean_dom = _normalize_domain(target_domain)
        base_domain_url = f"https://{clean_dom}"
        domain_start = time.monotonic()

        print(f"\n  [TRACE-DOMAIN] Trying [{base_domain_url}]")

        try:
            page.goto(base_domain_url, timeout=15000, wait_until="domcontentloaded")
            page.wait_for_timeout(1200)
            home_html = (page.content() or "").lower()
            if any(w in home_html for w in ["please sign in", "log in to continue", "sign in to view", "login required"]):
                print(f"  [TRACE-WALL] Auth wall on [{clean_dom}]. Skipping domain.")
                continue
        except Exception as conn_err:
            print(f"  [TRACE-DOMAIN-ERROR] [{clean_dom}] failed: {conn_err}. Skipping domain.")
            continue

        domain_done = False

        for target_city in cities:
            if domain_done or time.monotonic() - domain_start > MAX_TIME_PER_DOMAIN_SEC:
                break

            for keyword in keywords:
                if domain_done or time.monotonic() - domain_start > MAX_TIME_PER_DOMAIN_SEC:
                    break

                search_urls = _build_search_urls(clean_dom, keyword, target_city, category)

                for s_url in search_urls:
                    if domain_done or time.monotonic() - domain_start > MAX_TIME_PER_DOMAIN_SEC:
                        break

                    try:
                        print(f"    [TRACE-NAV] {s_url}")
                        page.goto(s_url, timeout=15000, wait_until="domcontentloaded")
                        page.wait_for_timeout(1400)

                        page_html = (page.content() or "").lower()
                        if any(w in page_html for w in ["sign in to view", "log in to apply", "please login"]):
                            print(f"    [TRACE-WALL] Login wall on search URL. Next keyword/city.")
                            break

                        page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                        page.wait_for_timeout(700)

                        raw_links = page.eval_on_selector_all(
                            "a[href]",
                            """elements => elements.map(el => ({
                                href: el.href,
                                text: el.innerText ? el.innerText.trim() : ''
                            }))""",
                        )

                        candidate_links = []
                        seen_hrefs = set()

                        for item in raw_links or []:
                            href = (item.get("href") or "").strip()
                            title_text = re.sub(r"\s+", " ", item.get("text") or "").strip()
                            txt_lower = title_text.lower()
                            href_lower = href.lower()

                            if not href.startswith(("http://", "https://")):
                                continue
                            if href in seen_hrefs:
                                continue
                            if any(bad in href_lower or bad in txt_lower for bad in blocked_url_terms):
                                continue
                            if href.rstrip("/") == base_domain_url:
                                continue
                            if len(title_text) > 10:
                                seen_hrefs.add(href)
                                candidate_links.append((href, title_text))

                        print(f"      [TRACE-PARSE] {len(candidate_links)} links found on {clean_dom}")

                        for idx, (j_link, j_title) in enumerate(candidate_links[:MAX_CANDIDATE_LINKS]):
                            if is_already_scraped(j_link):
                                continue

                            fallback_pool = [
                                u for u, _ in candidate_links[idx + 1 : idx + 3] if not is_already_scraped(u)
                            ]

                            print(f"        [TRACE-EXTRACT] {j_link}")
                            enriched_data = extract_strict_job_details(
                                page,
                                j_link,
                                target_country,
                                target_city,
                                category=category,
                                search_keyword=keyword,
                                fallback_urls=fallback_pool,
                            )

                            if (
                                isinstance(enriched_data, dict)
                                and enriched_data.get("accepted")
                                and enriched_data.get("finalUrl")
                            ):
                                final_url = enriched_data["finalUrl"]
                                if is_already_scraped(final_url):
                                    print(f"        [TRACE-DUP] Already in DB: {final_url}")
                                    continue

                                final_title = format_strict_title(
                                    j_title, keyword, target_city, target_country, current_year
                                )

                                cta_parts = []
                                if enriched_data.get("salary") and enriched_data["salary"] != "Not Specified":
                                    cta_parts.append(f"Salary/Fee: {enriched_data['salary']}")
                                if enriched_data.get("location"):
                                    cta_parts.append(f"Location/City: {enriched_data['location']}")
                                if enriched_data.get("phone"):
                                    cta_parts.append(f"Contact/Phone: {enriched_data['phone']}")
                                if enriched_data.get("email"):
                                    cta_parts.append(f"Email: {enriched_data['email']}")
                                cta_parts.append(f"Source Link: {final_url}")

                                base_snippet = enriched_data.get("snippet") or ""
                                final_snippet = f"{base_snippet}\n\nDetails:\n" + "\n".join(cta_parts)

                                insert_data = {
                                    "title": final_title,
                                    "snippet": final_snippet,
                                    "link": final_url,
                                    "country": f"{target_country} ({target_city})",
                                    "category": category,
                                    "query_used": f"Query: {keyword} on {clean_dom}",
                                    "status": "pending",
                                    "audit_status": None,
                                }

                                try:
                                    supabase.table("zunex").insert(insert_data).execute()
                                    print(f"  [TRACE-DONE] Saved for [{target_country}]: {final_title}")
                                    page.wait_for_timeout(1200)
                                    domain_done = True
                                    return True
                                except Exception as db_err:
                                    print(f"  [TRACE-DB-ERROR] {db_err}")
                                    continue

                    except Exception as nav_err:
                        print(f"    [TRACE-NAV-ERROR] {nav_err}")
                        continue

        print(f"  [TRACE-DOMAIN-NEXT] Moving past [{clean_dom}].")

    print(f"[TRACE-COUNTRY-NEXT] Finished all checks for [{target_country}] ({category}). Moving to next country.")
    return False


def run_independent_crawler():
    if not supabase:
        print("[TRACE-CRITICAL] Supabase client is not initialized.")
        return

    today = datetime.now().strftime("%A")
    current_year = datetime.now().year
    day_countries = list(dict.fromkeys(SCHEDULE.get(today, [])))

    print(f"\n==================================================")
    print(f"=== PLAYWRIGHT CRAWLER | Day: {today} | Year: {current_year} ===")
    print(f"=== Scheduled Countries ({len(day_countries)}): {day_countries} ===")
    print(f"==================================================")

    if not day_countries:
        print("[TRACE-INFO] No countries scheduled for today.")
        return

    blocked_url_terms = [
        "cookie", "privacy", "legal", "terms", "login", "register", "faq", "sign-in",
        "order", "sort", "filter", "search?", "help", "aviso", "ads", "forgot", "download",
        "/salary", "/career-advice", "/resume", "/blog", "/article", "/resources",
        "/employers", "/about", "/contact",
    ]

    with sync_playwright() as p:
        print("[TRACE-INIT] Launching Chromium...")
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--ignore-certificate-errors",
                "--ignore-ssl-errors",
            ],
        )

        context = browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1366, "height": 768},
            bypass_csp=True,
            ignore_https_errors=True,
        )
        context.route("**/*", _route_heavy_assets)

        page = context.new_page()
        page.set_default_timeout(20000)

        try:
            print(f"\n--------------------------------------------------")
            print(f"--- PHASE 1: 1 POST PER COUNTRY (JOBS) -----------")
            print(f"--------------------------------------------------")
            jobs_saved = 0
            for country in day_countries:
                if search_and_insert_post(page, country, "Jobs", current_year, blocked_url_terms):
                    jobs_saved += 1
            print(f"[TRACE-PHASE1] Jobs saved today: {jobs_saved}/{len(day_countries)}")

            print(f"\n--------------------------------------------------")
            print(f"--- PHASE 2: VISA POSTS ------------------------")
            print(f"--------------------------------------------------")
            visa_saved = 0
            for country in day_countries:
                if visa_saved >= 2:
                    break
                if search_and_insert_post(page, country, "Visa", current_year, blocked_url_terms):
                    visa_saved += 1
            print(f"[TRACE-PHASE2] Visa saved today: {visa_saved}/2")

            print(f"\n--------------------------------------------------")
            print(f"--- PHASE 3: TRAVEL POSTS ----------------------")
            print(f"--------------------------------------------------")
            travel_saved = 0
            for country in day_countries:
                if travel_saved >= 2:
                    break
                if search_and_insert_post(page, country, "Travel", current_year, blocked_url_terms):
                    travel_saved += 1
            print(f"[TRACE-PHASE3] Travel saved today: {travel_saved}/2")

            print(f"\n==================================================")
            print("=== CRAWLER FINISHED ===")
            print(f"==================================================")

        except Exception as e:
            print(f"[TRACE-CRITICAL-ERROR] {e}")
        finally:
            try:
                context.close()
            except Exception:
                pass
            browser.close()
            print("[TRACE-SHUTDOWN] Browser closed.")


if __name__ == "__main__":
    run_independent_crawler()
