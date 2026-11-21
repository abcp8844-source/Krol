import random
import re
import signal
import sys
import time
from datetime import datetime, timezone
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

MAX_CANDIDATE_LINKS = 16
MAX_BUTTON_CLICKS_PER_PAGE = 4
MAX_ZERO_POST_RETRIES = 3

DANGEROUS_CLICK_TERMS = [
    "login", "log in", "sign in", "signin", "sign up", "signup", "register",
    "delete", "remove", "unsubscribe", "decline", "reject", "cookie settings",
]

INSERTED_POSTS_LOG = []
SUMMARY_PRINTED = False


def _normalize_domain(domain: str) -> str:
    d = (domain or "").strip().lower()
    if d.startswith("http://") or d.startswith("https://"):
        d = urlparse(d).netloc
    return d.strip("/")


def _candidate_base_urls(domain: str) -> list:
    raw = (domain or "").strip()
    urls = []
    if raw.startswith(("http://", "https://")):
        urls.append(raw.rstrip("/"))
    core = _normalize_domain(domain)
    if core:
        bare = core[4:] if core.startswith("www.") else core
        for u in (f"https://{core}", f"https://{bare}", f"https://www.{bare}"):
            if u not in urls:
                urls.append(u)
    return urls


def print_final_run_summary(reason: str = "Normal Exit"):
    global SUMMARY_PRINTED
    if SUMMARY_PRINTED:
        return
    SUMMARY_PRINTED = True

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    now_local = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("\n==================================================")
    print(f"=== FINAL RUN REPORT ({reason}) | UTC: {now_utc} | Local: {now_local} ===")
    print(f"=== Total Posts Inserted This Run: {len(INSERTED_POSTS_LOG)} ===")
    if INSERTED_POSTS_LOG:
        ids_only = [str(item.get("id")) for item in INSERTED_POSTS_LOG if item.get("id") is not None]
        print(f"=== Inserted IDs: [{', '.join(ids_only) if ids_only else 'N/A'}] ===")
        for idx, item in enumerate(INSERTED_POSTS_LOG, start=1):
            print(
                f"  {idx}. ID: {item.get('id', 'N/A')} | "
                f"[{item.get('category', '-')}] {item.get('country', '-')} | "
                f"{item.get('query_used', '-')} | {item.get('title', '-')}"
            )
    else:
        print("=== Inserted IDs: [] (0 posts inserted in this run) ===")
    print("==================================================\n")


def _handle_termination(signum, frame):
    print_final_run_summary(f"Signal {signum}")
    sys.exit(0)


signal.signal(signal.SIGTERM, _handle_termination)
signal.signal(signal.SIGINT, _handle_termination)


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


def _safe_goto(page, url: str, timeout: int = 20000):
    try:
        page.wait_for_load_state("domcontentloaded", timeout=3000)
    except Exception:
        pass

    last_err = None
    for attempt in range(2):
        try:
            resp = page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=4000)
            except Exception:
                pass
            return resp
        except Exception as err:
            last_err = err
            msg = str(err).lower()
            if "interrupted by another navigation" in msg and attempt == 0:
                time.sleep(0.8)
                continue
            raise last_err


def _build_search_urls(base_url: str, keyword: str, city: str, category: str) -> list:
    clean_base = base_url.rstrip("/")
    enc_kw = quote(keyword)
    enc_city = quote(city)
    cat_l = (category or "").lower()

    if cat_l == "jobs":
        return [
            f"{clean_base}/jobs?q={enc_kw}&l={enc_city}",
            f"{clean_base}/search?q={enc_kw}",
            f"{clean_base}/?s={enc_kw}+{enc_city}",
            clean_base,
        ]
    if cat_l == "visa":
        return [
            f"{clean_base}/search?q={enc_kw}+{enc_city}+visa",
            f"{clean_base}/?s={enc_kw}+visa+{enc_city}",
            f"{clean_base}/?s={enc_kw}",
            clean_base,
        ]
    return [
        f"{clean_base}/search?q={enc_kw}+{enc_city}",
        f"{clean_base}/?s={enc_kw}+{enc_city}",
        f"{clean_base}/?s={enc_kw}",
        clean_base,
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


def _collect_filtered_links(page, active_base_url: str, blocked_url_terms: list) -> list:
    try:
        raw_links = page.eval_on_selector_all(
            "a[href]",
            """elements => elements.map(el => ({
                href: el.href,
                text: el.innerText ? el.innerText.trim() : ''
            }))""",
        )
    except Exception:
        return []

    candidate_links = []
    seen_hrefs = set()
    clean_base = active_base_url.rstrip("/")

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
        if href.rstrip("/") == clean_base:
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
    try:
        locators = page.locator("button, a[role='button'], input[type='submit'], a")
        count = min(locators.count(), 60)
    except Exception:
        return False

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
    word_count = len(snippet.split())
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

    print(
        f"[TRACE-INFO] [{target_country}] -> Domains: {len(domains)} | "
        f"Cities: {len(cities)} | Keywords: {len(keywords)}"
    )

    for target_domain in domains:
        active_base_url = None
        reachable = False
        last_err = None

        for cand_url in _candidate_base_urls(target_domain):
            print(f"\n  [TRACE-DOMAIN] Trying [{cand_url}]")
            try:
                _safe_goto(page, cand_url, timeout=20000)
                page.wait_for_timeout(1200)
                home_html = (page.content() or "").lower()
                if any(w in home_html for w in ["please sign in", "log in to continue", "sign in to view", "login required"]):
                    print(f"  [TRACE-WALL] Auth wall on [{cand_url}].")
                    active_base_url = None
                    reachable = False
                    break
                active_base_url = (page.url or cand_url).rstrip("/")
                reachable = True
                break
            except Exception as conn_err:
                last_err = conn_err
                continue

        if not reachable or not active_base_url:
            print(f"  [TRACE-DOMAIN-ERROR] [{target_domain}] failed: {last_err}. Skipping domain.")
            continue

        domain_done = False

        for target_city in cities:
            if domain_done:
                break

            for keyword in keywords:
                if domain_done:
                    break

                search_urls = _build_search_urls(active_base_url, keyword, target_city, category)

                for s_url in search_urls:
                    if domain_done:
                        break

                    try:
                        print(f"    [TRACE-NAV] {s_url}")
                        _safe_goto(page, s_url, timeout=20000)
                        page.wait_for_timeout(1300)

                        page_html = (page.content() or "").lower()
                        if any(w in page_html for w in ["sign in to view", "log in to apply", "please login"]):
                            print(f"    [TRACE-WALL] Login wall on search URL. Next keyword/city.")
                            break

                        try:
                            page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                        except Exception:
                            pass
                        page.wait_for_timeout(700)

                        candidate_links = _collect_filtered_links(page, active_base_url, blocked_url_terms)

                        if len(candidate_links) < 4:
                            clicked = _click_relevant_page_buttons(page, category, target_city, target_country)
                            if clicked:
                                try:
                                    page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                                except Exception:
                                    pass
                                page.wait_for_timeout(800)
                                candidate_links = _collect_filtered_links(page, active_base_url, blocked_url_terms)

                        print(f"      [TRACE-PARSE] {len(candidate_links)} links found on {active_base_url}")

                        evaluated_posts = []
                        links_slice = candidate_links[:MAX_CANDIDATE_LINKS]

                        for idx, (j_link, j_title) in enumerate(links_slice):
                            if is_already_scraped(j_link):
                                continue

                            fallback_pool = [
                                u for u, _ in links_slice[idx + 1 : idx + 3] if not is_already_scraped(u)
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

                                post_score = _score_rich_and_fresh_post(enriched_data, j_title, current_year)
                                evaluated_posts.append((post_score, j_title, enriched_data))

                                if len(evaluated_posts) >= 5 and post_score >= 950:
                                    break

                        if evaluated_posts:
                            evaluated_posts.sort(key=lambda x: x[0], reverse=True)
                            best_score, best_title, best_data = evaluated_posts[0]
                            final_url = best_data["finalUrl"]
                            final_title = format_strict_title(
                                best_title, keyword, target_city, target_country, current_year
                            )

                            cta_parts = []
                            if best_data.get("salary") and best_data["salary"] != "Not Specified":
                                cta_parts.append(f"Salary/Fee: {best_data['salary']}")
                            if best_data.get("location"):
                                cta_parts.append(f"Location/City: {best_data['location']}")
                            if best_data.get("phone"):
                                cta_parts.append(f"Contact/Phone: {best_data['phone']}")
                            if best_data.get("email"):
                                cta_parts.append(f"Email: {best_data['email']}")
                            cta_parts.append(f"Source Link: {final_url}")

                            base_snippet = best_data.get("snippet") or ""
                            final_snippet = f"{base_snippet}\n\nDetails:\n" + "\n".join(cta_parts)

                            query_label = f"Query: {keyword} on {target_domain}"
                            country_label = f"{target_country} ({target_city})"

                            insert_data = {
                                "title": final_title,
                                "snippet": final_snippet,
                                "link": final_url,
                                "country": country_label,
                                "category": category,
                                "query_used": query_label,
                                "status": "pending",
                                "audit_status": None,
                            }

                            try:
                                res = supabase.table("zunex").insert(insert_data).execute()
                                inserted_id = None
                                if getattr(res, "data", None) and isinstance(res.data, list) and len(res.data) > 0:
                                    inserted_id = res.data[0].get("id")

                                INSERTED_POSTS_LOG.append({
                                    "id": inserted_id,
                                    "title": final_title,
                                    "country": country_label,
                                    "category": category,
                                    "query_used": query_label,
                                })
                                print(
                                    f"  [TRACE-DONE] Saved post ID={inserted_id} (score={best_score}) "
                                    f"for [{target_country}]: {final_title}"
                                )
                                page.wait_for_timeout(1200)
                                domain_done = True
                                return True
                            except Exception as db_err:
                                print(f"  [TRACE-DB-ERROR] {db_err}")
                                continue

                    except Exception as nav_err:
                        print(f"    [TRACE-NAV-ERROR] {nav_err}")
                        continue

        print(f"  [TRACE-DOMAIN-NEXT] Moving past [{target_domain}].")

    print(f"[TRACE-COUNTRY-NEXT] Finished all checks for [{target_country}] ({category}). Moving to next country.")
    return False


def _execute_full_cycle(p, day_countries, current_year, blocked_url_terms):
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

    cycle_inserted = 0
    try:
        print(f"\n--------------------------------------------------")
        print(f"--- PHASE 1: 1 POST PER COUNTRY (JOBS) -----------")
        print(f"--------------------------------------------------")
        jobs_saved = 0
        for country in day_countries:
            if search_and_insert_post(page, country, "Jobs", current_year, blocked_url_terms):
                jobs_saved += 1
                cycle_inserted += 1
        print(f"[TRACE-PHASE1] Jobs saved this cycle: {jobs_saved}/{len(day_countries)}")

        print(f"\n--------------------------------------------------")
        print(f"--- PHASE 2: VISA POSTS ------------------------")
        print(f"--------------------------------------------------")
        visa_saved = 0
        for country in day_countries:
            if visa_saved >= 2:
                break
            if search_and_insert_post(page, country, "Visa", current_year, blocked_url_terms):
                visa_saved += 1
                cycle_inserted += 1
        print(f"[TRACE-PHASE2] Visa saved this cycle: {visa_saved}/2")

        print(f"\n--------------------------------------------------")
        print(f"--- PHASE 3: TRAVEL POSTS ----------------------")
        print(f"--------------------------------------------------")
        travel_saved = 0
        for country in day_countries:
            if travel_saved >= 2:
                break
            if search_and_insert_post(page, country, "Travel", current_year, blocked_url_terms):
                travel_saved += 1
                cycle_inserted += 1
        print(f"[TRACE-PHASE3] Travel saved this cycle: {travel_saved}/2")
    finally:
        try:
            context.close()
        except Exception:
            pass
        try:
            browser.close()
        except Exception:
            pass
        print("[TRACE-SHUTDOWN] Browser closed.")

    return cycle_inserted


def run_independent_crawler():
    if not supabase:
        print("[TRACE-CRITICAL] Supabase client is not initialized.")
        print_final_run_summary("Supabase Init Failed")
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
        print_final_run_summary("No Scheduled Countries")
        return

    blocked_url_terms = [
        "cookie", "privacy", "legal", "terms", "login", "register", "faq", "sign-in",
        "order", "sort", "filter", "search?", "help", "aviso", "ads", "forgot", "download",
        "/salary", "/career-advice", "/resume", "/blog", "/article", "/resources",
        "/employers", "/about", "/contact",
    ]

    exit_reason = "Completed"
    with sync_playwright() as p:
        try:
            for attempt in range(1, MAX_ZERO_POST_RETRIES + 1):
                print(f"\n[TRACE-CYCLE] Starting full cycle attempt {attempt}/{MAX_ZERO_POST_RETRIES}...")
                inserted_in_cycle = _execute_full_cycle(p, day_countries, current_year, blocked_url_terms)
                if inserted_in_cycle > 0:
                    exit_reason = f"Completed (Attempt {attempt}, Inserted: {inserted_in_cycle})"
                    break
                if attempt < MAX_ZERO_POST_RETRIES:
                    print(f"[TRACE-RETRY] 0 posts inserted in attempt {attempt}. Restarting full cycle...")
                    time.sleep(2)
                else:
                    exit_reason = f"Completed with 0 posts after {MAX_ZERO_POST_RETRIES} full cycles"
        except Exception as e:
            exit_reason = f"Error: {e}"
            print(f"[TRACE-CRITICAL-ERROR] {e}")
        finally:
            print_final_run_summary(exit_reason)


if __name__ == "__main__":
    run_independent_crawler()
