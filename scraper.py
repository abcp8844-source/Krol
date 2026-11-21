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

MAX_NEARBY_LINKS = 14
DANGEROUS_CLICK_TERMS = [
    "login", "log in", "sign in", "signin", "sign up", "signup", "register",
    "delete", "remove", "unsubscribe", "decline", "reject", "cookie settings",
]


def _base_domain_name(domain: str) -> str:
    d = (domain or "").strip().lower()
    if d.startswith(("http://", "https://")):
        d = urlparse(d).netloc
    d = d.strip("/")
    if d.startswith("www."):
        d = d[4:]
    return d


def _candidate_base_urls(domain: str) -> list:
    raw = (domain or "").strip()
    urls = []
    if raw.startswith(("http://", "https://")):
        urls.append(raw.rstrip("/"))
    core = _base_domain_name(domain)
    if core:
        for u in (f"https://{core}", f"https://www.{core}"):
            if u not in urls:
                urls.append(u)
    return urls


def format_strict_title(raw_title, keyword, city, country, year):
    base = re.sub(r"\s+", " ", raw_title).strip() if raw_title else ""
    suffix = f" - {keyword.capitalize()} Opportunity in {city}, {country} ({year}) | Direct Apply"

    if len(base) < 60:
        title = f"{base}{suffix}" if base else f"Immediate {keyword.capitalize()} Opening in {city}, {country} ({year}) - Direct Online Application"
    else:
        title = base

    if len(title) < 60:
        title = f"{title} - Verified Listing & Direct Application Details for {city}"

    if len(title) > 100:
        title = title[:97].rsplit(" ", 1)[0] + "..."
        if len(title) < 60:
            title = title[:100]

    return title


def is_already_scraped(url):
    try:
        res = supabase.table("zunex").select("id").eq("link", url).limit(1).execute()
        return len(res.data) > 0
    except Exception as e:
        print(f"[TRACE-DB-CHECK-ERROR] {e}")
        return False


def _build_search_urls(base_url: str, keyword: str, city: str, category: str) -> list:
    enc_kw = quote(keyword)
    enc_city = quote(city)
    cat_l = (category or "").lower()

    if cat_l == "jobs":
        return [
            f"{base_url}/jobs?q={enc_kw}&l={enc_city}",
            f"{base_url}/search?q={enc_kw}",
            f"{base_url}/vagas-{enc_kw}",
            base_url,
        ]
    if cat_l == "visa":
        return [
            f"{base_url}/search?q={enc_kw}+{enc_city}",
            f"{base_url}/?s={enc_kw}+visa+{enc_city}",
            f"{base_url}/?s={enc_kw}",
            base_url,
        ]
    return [
        f"{base_url}/search?q={enc_kw}+{enc_city}",
        f"{base_url}/?s={enc_kw}+{enc_city}",
        f"{base_url}/?s={enc_kw}",
        base_url,
    ]


def _is_not_found_page(html_lower: str) -> bool:
    markers = [
        "404 not found",
        "page not found",
        "not found",
        "no results found",
        "pagina nao encontrada",
        "página no encontrada",
        "introuvable",
        "seite nicht gefunden",
    ]
    return len(html_lower) < 4000 and any(m in html_lower for m in markers)


def _has_relevant_page_signal(page, category: str, keyword: str, city: str, country: str) -> bool:
    try:
        body_l = (page.inner_text("body") or "").lower()
    except Exception:
        body_l = (page.content() or "").lower()

    cat_signals = {
        "jobs": ["job", "jobs", "career", "careers", "salary", "apply", "vacancy", "vacancies", "hiring", "vagas", "empleo", "emploi"],
        "visa": ["visa", "visas", "immigration", "permit", "residence", "residency", "embassy", "consulate", "entry"],
        "travel": ["travel", "tour", "tours", "flight", "flights", "hotel", "hotels", "itinerary", "trip", "holiday"],
    }
    terms = list(cat_signals.get((category or "").lower(), cat_signals["jobs"]))
    if keyword:
        terms.append(keyword.lower())
    if city:
        terms.append(city.lower())
    if country:
        terms.append(country.lower())

    return any(t in body_l for t in terms if t)


def _sweep_and_scroll_page(page):
    try:
        total_h = page.evaluate("document.body.scrollHeight || 1200")
        steps = 4
        for s in range(1, steps + 1):
            y = int((total_h * s) / steps)
            page.evaluate(f"window.scrollTo(0, {y});")
            time.sleep(0.45)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.6)
    except Exception:
        pass


def _extract_links_from_page(page, active_base_url: str, blocked_url_terms: list) -> list:
    raw_links = page.eval_on_selector_all(
        "a[href]",
        """elements => elements.map(el => ({
            href: el.href,
            text: el.innerText ? el.innerText.trim() : ''
        }))""",
    )

    candidate_links = []
    seen = set()

    for item in raw_links or []:
        href = (item.get("href") or "").strip()
        title_text = re.sub(r"\s+", " ", item.get("text") or "").strip()
        txt = title_text.lower()

        if any(bad in href.lower() or bad in txt for bad in blocked_url_terms):
            continue
        if href.startswith("/"):
            full_link = f"{active_base_url}{href}"
        elif href.startswith("http"):
            full_link = href
        else:
            continue

        clean_link = full_link.rstrip("/")
        if clean_link == active_base_url or full_link in seen:
            continue
        if len(title_text) > 10:
            seen.add(full_link)
            candidate_links.append((full_link, title_text))

    return candidate_links


def _click_relevant_controls(page, category: str, target_city: str, target_country: str) -> bool:
    category_terms = {
        "Jobs": ["job", "jobs", "career", "careers", "hiring", "vacancy", "vacancies", "latest", "openings", "search", "load more", "show more", "more"],
        "Visa": ["visa", "visas", "immigration", "permit", "work permit", "residency", "entry", "latest", "search", "load more", "show more", "more"],
        "Travel": ["travel", "tour", "tours", "hotel", "hotels", "flight", "flights", "holiday", "package", "latest", "search", "load more", "show more", "more"],
    }
    terms = list(category_terms.get(category, category_terms["Jobs"]))
    city_l = (target_city or "").lower().strip()
    country_l = (target_country or "").lower().strip()

    clicked = False
    locators = page.locator("button, a[role='button'], input[type='submit'], a")
    total = min(locators.count(), 65)
    clicks_used = 0

    for i in range(total):
        if clicks_used >= 3:
            break
        el = locators.nth(i)
        try:
            if not el.is_visible():
                continue
            label = re.sub(r"\s+", " ", (el.inner_text(timeout=800) or "")).strip()
            label_l = label.lower()
            if not label_l or len(label_l) > 60:
                continue
            if any(bad in label_l for bad in DANGEROUS_CLICK_TERMS):
                continue

            matched = any(t in label_l for t in terms) or (
                (city_l and city_l in label_l) or (country_l and country_l in label_l)
            )
            if matched:
                el.scroll_into_view_if_needed(timeout=1500)
                el.click(timeout=2500)
                time.sleep(1.2)
                _sweep_and_scroll_page(page)
                clicks_used += 1
                clicked = True
                print(f"      [TRACE-CLICK] Clicked control: [{label}]")
        except Exception:
            continue

    return clicked


def _score_post_richness(enriched_data: dict, title_text: str, current_year: int) -> int:
    snippet = enriched_data.get("snippet") or ""
    score = min(len(snippet.split()), 1200)
    if enriched_data.get("salary") and enriched_data["salary"] != "Not Specified":
        score += 120
    if enriched_data.get("location"):
        score += 60
    if enriched_data.get("phone"):
        score += 80
    if enriched_data.get("email"):
        score += 80
    combined_l = f"{title_text} {snippet}".lower()
    if str(current_year) in combined_l or str(current_year - 1) in combined_l:
        score += 120
    return score


def _try_process_links(page, candidate_links, active_base_url, raw_domain, target_country, target_city, category, keyword, current_year):
    evaluated = []
    links_to_check = candidate_links[:MAX_NEARBY_LINKS]

    for j_link, j_title in links_to_check:
        if is_already_scraped(j_link):
            continue

        print(f"        [TRACE-EXTRACT] Checking nearby link: {j_link}")
        enriched_data = extract_strict_job_details(
            page,
            j_link,
            target_country,
            target_city,
            category=category,
            search_keyword=keyword,
        )
        if enriched_data and enriched_data.get("finalUrl"):
            if is_already_scraped(enriched_data["finalUrl"]):
                print(f"        [TRACE-REJECT] Final URL already scraped.")
                continue

            final_title = format_strict_title(
                j_title, keyword, target_city, target_country, current_year
            )
            if target_country.lower() not in final_title.lower() and target_city.lower() not in final_title.lower():
                continue

            score = _score_post_richness(enriched_data, j_title, current_year)
            evaluated.append((score, final_title, enriched_data))

            if len(evaluated) >= 3 and score >= 750:
                break

    if not evaluated:
        return False

    evaluated.sort(key=lambda x: x[0], reverse=True)
    best_score, final_title, best_data = evaluated[0]

    cta_parts = []
    if best_data.get("salary") and best_data["salary"] != "Not Specified":
        cta_parts.append(f"Estimated Amount/Salary: {best_data['salary']}")
    if best_data.get("location"):
        cta_parts.append(f"Location/City: {best_data['location']}")
    if best_data.get("phone"):
        cta_parts.append(f"Contact/Phone: {best_data['phone']}")
    if best_data.get("email"):
        cta_parts.append(f"Email: {best_data['email']}")
    cta_parts.append(f"Direct Apply Link: {best_data['finalUrl']}")

    final_snippet = best_data.get("snippet", "") + "\n\nDetails:\n" + "\n".join(cta_parts)

    insert_data = {
        "title": final_title,
        "snippet": final_snippet,
        "link": best_data["finalUrl"],
        "country": f"{target_country} ({target_city})",
        "category": category,
        "query_used": f"Query: {keyword} on {raw_domain}",
        "status": "pending",
        "audit_status": None,
    }
    try:
        supabase.table("zunex").insert(insert_data).execute()
        print(f"  [TRACE-SUCCESS] Saved post (score={best_score}) to DB: {final_title}")
        time.sleep(3)
        return True
    except Exception as db_err:
        print(f"  [TRACE-DB-ERROR] {db_err}")
        return False


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

    shuffled_cities = list(cities)
    random.shuffle(shuffled_cities)
    shuffled_domains = list(domains)
    random.shuffle(shuffled_domains)
    shuffled_keywords = list(keywords)
    random.shuffle(shuffled_keywords)

    print(f"[TRACE-INFO] Config -> Domains: {len(shuffled_domains)} | Keywords: {len(shuffled_keywords)} | Cities: {len(shuffled_cities)}")

    for target_domain in shuffled_domains:
        candidate_bases = _candidate_base_urls(target_domain)
        if not candidate_bases:
            continue

        active_base_url = None
        reachable = False
        last_err = None

        for cand_url in candidate_bases:
            print(f"\n  [TRACE-DOMAIN] Evaluating Domain -> [{cand_url}]")
            try:
                page.goto(cand_url, timeout=15000, wait_until="domcontentloaded")
                time.sleep(1.5)
                page_text = page.content().lower()
                if any(wall in page_text for wall in ["please sign in", "log in to continue", "sign in to view", "login required"]):
                    print(f"  [TRACE-WALL] Login/Sign-in wall detected on domain [{target_domain}].")
                    active_base_url = None
                    reachable = False
                    break
                active_base_url = page.url.rstrip("/") or cand_url
                reachable = True
                break
            except Exception as conn_err:
                last_err = conn_err
                continue

        if not reachable or not active_base_url:
            print(f"  [TRACE-DOMAIN-ERROR] Could not reach [{target_domain}]: {last_err}. Shifting to next domain.")
            continue

        dead_prefixes = set()
        consecutive_not_found = 0
        home_checked_once = False

        for target_city in shuffled_cities:
            for keyword in shuffled_keywords:
                encoded_kw = quote(keyword)
                encoded_city = quote(target_city)

                search_urls = _build_search_urls(active_base_url, encoded_kw, encoded_city, category)
                for s_url in search_urls:
                    if s_url.rstrip("/") == active_base_url:
                        if home_checked_once:
                            continue
                        home_checked_once = True

                    prefix = urlparse(s_url).path
                    if prefix in dead_prefixes:
                        continue

                    try:
                        print(f"    [TRACE-NAV] Navigating to: {s_url}")
                        resp = page.goto(s_url, timeout=15000, wait_until="domcontentloaded")
                        time.sleep(2)

                        current_content = page.content().lower()
                        if any(wall in current_content for wall in ["sign in to view", "log in to apply", "please login"]):
                            print(f"    [TRACE-WALL] Sign-in wall encountered on search URL. Moving on.")
                            break

                        if (resp and resp.status in (404, 410)) or _is_not_found_page(current_content):
                            consecutive_not_found += 1
                            if consecutive_not_found >= 4:
                                dead_prefixes.add(prefix)
                            continue

                        consecutive_not_found = 0
                        _sweep_and_scroll_page(page)

                        if _has_relevant_page_signal(page, category, keyword, target_city, target_country):
                            _click_relevant_controls(page, category, target_city, target_country)

                        candidate_links = _extract_links_from_page(page, active_base_url, blocked_url_terms)
                        if not candidate_links and _click_relevant_controls(page, category, target_city, target_country):
                            candidate_links = _extract_links_from_page(page, active_base_url, blocked_url_terms)

                        print(f"      [TRACE-PARSE] Found {len(candidate_links)} candidate links on {target_domain}")

                        if _try_process_links(
                            page, candidate_links, active_base_url, target_domain,
                            target_country, target_city, category, keyword, current_year
                        ):
                            return True

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
        "/salary", "/career-advice", "/resume", "/blog", "/article", "/resources", "/employers", "/about", "/contact"
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
