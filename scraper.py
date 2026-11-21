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
MAX_BUTTON_CLICKS_PER_PAGE = 4
MAX_TIME_PER_DOMAIN_SEC = 150
MAX_TIME_PER_COUNTRY_SEC = 1800

DANGEROUS_CLICK_TERMS = [
    "login", "log in", "sign in", "signin", "sign up", "signup", "register",
    "delete", "remove", "unsubscribe", "decline", "reject", "cookie settings",
]


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


def _collect_filtered_links(page, base_domain_url: str, blocked_url_terms: list) -> list:
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

    return candidate_links


def _click_relevant_page_buttons(page, category: str, target_city: str, target_country: str) -> bool:
    category_terms = {
        "Jobs": ["job", "jobs", "career", "careers", "hiring", "vacancy", "vacancies", "latest", "openings", "apply", "search", "load more", "show more", "more"],
        "Visa": ["visa", "visas", "immigration", "permit", "work permit", "residency", "entry", "latest", "search", "load more", "show more", "more"],
        "Travel": ["travel", "tour", "tours", "hotel", "hotels", "flight", "flights", "holiday", "package", "latest", "search", "load more", "show more", "more"],
    }
    terms = list(category_terms.get(category, category_terms["Jobs"]))
    city_l = (target_city or "").lower().strip()
    country_l = (target_country or "").lower().strip()

    clicked_any = False
    locators = page.locator("button, a[role='button'], input[type='submit'], a")
    count = min(locators.count(), 60)
    clicks_done = 0

    for i in range(count):
        if clicks_done >= MAX_BUTTON_CLICKS_PER_PAGE:
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

            has_term = any(t in label_l for t in terms)
            has_loc_combo = (
                (city_l and city_l in label_l and any(k in label_l for k in ["job", "visa", "tour", "travel", "work", "hire"]))
                or (country_l and country_l in label_l and any(k in label_l for k in ["job", "visa", "tour", "travel", "work", "hire"]))
            )

            if has_term or has_loc_combo:
                el.scroll_into_view_if_needed(timeout=1500)
                el.click(timeout=2500)
                page.wait_for_timeout(1200)
                clicks_done += 1
                clicked_any = True
                print(f"      [TRACE-BTN-CLICK] Clicked [{label}]")
        except Exception:
            continue

    return clicked_any


def _score_rich_and_fresh_post(enriched_data: dict, title_text: str, current_year: int) -> int:
    snippet = enriched_data.get("snippet") or ""
    words = snippet.split()
    word_count = len(words)

    score = min(word_count, 1200)

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
        score += 150
    if any(f in combined_l for f in ["latest", "new", "urgent", "immediate", "today", "2026", "2025"]):
        score += 90

    return score


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
        if (time.monotonic() - country_start) > MAX_TIME_PER_COUNTRY_SEC:
            print(f"[TRACE-COUNTRY-CAP] 30-min cap reached for [{target_country}]. Moving to next country.")
            break

        clean_dom = _normalize_domain(target_domain)
        base_domain_url = f"https://{clean_dom}"
        domain_start = time.monotonic()

        print(f"\n  [TRACE-DOMAIN] Trying [{base_domain_url}] (Up to 2.5 mins)")

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
            if domain_done or (time.monotonic() - domain_start) > MAX_TIME_PER_DOMAIN_SEC or (time.monotonic() - country_start) > MAX_TIME_PER_COUNTRY_SEC:
                break

            for keyword in keywords:
                if domain_done or (time.monotonic() - domain_start) > MAX_TIME_PER_DOMAIN_SEC or (time.monotonic() - country_start) > MAX_TIME_PER_COUNTRY_SEC:
                    break

                search_urls = _build_search_urls(clean_dom, keyword, target_city, category)

                for s_url in search_urls:
                    if domain_done or (time.monotonic() - domain_start) > MAX_TIME_PER_DOMAIN_SEC or (time.monotonic() - country_start) > MAX_TIME_PER_COUNTRY_SEC:
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

                        candidate_links = _collect_filtered_links(page, base_domain_url, blocked_url_terms)

                        if len(candidate_links) < 4:
                            clicked = _click_relevant_page_buttons(page, category, target_city, target_country)
                            if clicked:
                                page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                                page.wait_for_timeout(800)
                                candidate_links = _collect_filtered_links(page, base_domain_url, blocked_url_terms)

                        print(f"      [TRACE-PARSE] {len(candidate_links)} links found on {clean_dom}")

                        evaluated_posts = []
                        links_slice = candidate_links[:MAX_CANDIDATE_LINKS]

                        for idx, (j_link, j_title) in enumerate(links_slice):
                            if (time.monotonic() - domain_start) > MAX_TIME_PER_DOMAIN_SEC or (time.monotonic() - country_start) > MAX_TIME_PER_COUNTRY_SEC:
                                break
                            if is_already_scraped(j_link):
                                continue

                            fallback_pool = [
                                u for u, _ in links_slice[idx
