import random
import re
import time
from datetime import datetime
from urllib.parse import quote
from cleaner import extract_strict_job_details
from config import COUNTRY_CITIES, SCHEDULE, SUPABASE_KEY, SUPABASE_URL, USER_AGENTS
from domains import COUNTRY_DOMAINS
from keywords import COUNTRY_KEYWORDS
from playwright.sync_api import sync_playwright
from supabase import Client, create_client

if not SUPABASE_URL or not SUPABASE_KEY:
  raise ValueError("Supabase environment variables missing")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

TARGET_JOBS_PER_COUNTRY = 5
MAX_SECONDS_PER_DOMAIN = 25
MAX_SECONDS_PER_COUNTRY = 380
MAX_TOTAL_RUN_SECONDS = 4500


def format_strict_title(raw_title, keyword, city, country, year):
  base = re.sub(r"\s+", " ", raw_title).strip() if raw_title else ""
  suffix = (
      f" - {keyword.capitalize()} Opportunity in {city}, {country} ({year}) |"
      " Direct Apply"
  )

  if len(base) < 60:
    title = (
        f"{base}{suffix}"
        if base
        else (
            f"Immediate {keyword.capitalize()} Opening in {city}, {country}"
            f" ({year}) - Direct Online Application"
        )
    )
  else:
    title = base

  if len(title) < 60:
    title = (
        f"{title} - Verified Listing & Direct Application Details for {city}"
    )

  if len(title) > 100:
    title = title[:97].rsplit(" ", 1)[0] + "..."
    if len(title) < 60:
      title = title[:100]

  return title


def is_already_scraped(url):
  if not url:
    return False
  try:
    res = supabase.table("zunex").select("id").eq("link", url).execute()
    return len(res.data) > 0
  except Exception as e:
    print(f"[TRACE-DB-CHECK-ERROR] {e}")
    return False


def is_domain_healthy(page, base_domain_url, dead_domains, norm_domain):
  if norm_domain in dead_domains:
    return False
  try:
    resp = page.goto(
        base_domain_url, timeout=9000, wait_until="domcontentloaded"
    )
    if resp and resp.status >= 400:
      print(
          f"  [TRACE-DOMAIN-BAD-STATUS] [{norm_domain}] returned status"
          f" {resp.status}. Shifting."
      )
      dead_domains.add(norm_domain)
      return False

    page.wait_for_timeout(800)
    body_text = (page.inner_text("body") or "").strip().lower()
    if len(body_text) < 40:
      print(
          f"  [TRACE-DOMAIN-EMPTY] [{norm_domain}] loaded empty/blocked"
          " content. Shifting."
      )
      dead_domains.add(norm_domain)
      return False

    walls = [
        "please sign in",
        "log in to continue",
        "sign in to view",
        "login required",
        "log in to apply",
        "please login",
        "access denied",
        "enable javascript and cookies",
    ]
    if any(w in body_text for w in walls):
      print(
          f"  [TRACE-WALL] Login/Block wall on [{norm_domain}]. Shifting to"
          " next domain."
      )
      dead_domains.add(norm_domain)
      return False

    return True
  except Exception as conn_err:
    print(
        f"  [TRACE-DOMAIN-ERROR] [{norm_domain}] failed health check:"
        f" {conn_err}. Shifting."
    )
    dead_domains.add(norm_domain)
    return False


def collect_jobs_for_country(
    page,
    target_country,
    current_year,
    blocked_url_terms,
    dead_domains,
    run_start,
):
  print(f"\n==================================================")
  print(
      f"[TRACE-COUNTRY] Country: [{target_country}] | Category: [Jobs] |"
      f" Target: {TARGET_JOBS_PER_COUNTRY}"
  )
  print(f"==================================================")

  cities = COUNTRY_CITIES.get(target_country, [target_country])
  domains = COUNTRY_DOMAINS.get(target_country, [])
  country_kw_dict = COUNTRY_KEYWORDS.get(target_country, {})

  if not domains:
    print(f"[TRACE-STOP] No domains configured for country: {target_country}")
    return 0

  if isinstance(country_kw_dict, dict):
    keywords = list(country_kw_dict.get("Jobs", []))
  else:
    keywords = list(country_kw_dict)

  if not keywords:
    print(f"[TRACE-STOP] No job keywords found for country [{target_country}]")
    return 0

  shuffled_cities = list(cities)
  random.shuffle(shuffled_cities)
  shuffled_domains = list(domains)
  random.shuffle(shuffled_domains)
  shuffled_keywords = list(keywords)
  random.shuffle(shuffled_keywords)

  saved_count = 0
  country_start = time.time()
  visited_links = set()

  for target_domain in shuffled_domains:
    if saved_count >= TARGET_JOBS_PER_COUNTRY:
      break
    if time.time() - country_start > MAX_SECONDS_PER_COUNTRY:
      print(
          f"[TRACE-COUNTRY-SHIFT] Time cap hit for [{target_country}]."
          " Shifting to next country."
      )
      break
    if time.time() - run_start > MAX_TOTAL_RUN_SECONDS:
      print("[TRACE-GLOBAL-STOP] Total runtime limit reached.")
      break

    norm_domain = target_domain.replace("www.", "").strip().lower()
    base_domain_url = f"https://www.{norm_domain}"
    domain_start = time.time()

    print(f"\n  [TRACE-DOMAIN] Checking -> [{base_domain_url}]")
    if not is_domain_healthy(page, base_domain_url, dead_domains, norm_domain):
      continue

    for target_city in shuffled_cities:
      if saved_count >= TARGET_JOBS_PER_COUNTRY:
        break
      if (
          time.time() - domain_start > MAX_SECONDS_PER_DOMAIN
          or time.time() - country_start > MAX_SECONDS_PER_COUNTRY
      ):
        break

      for keyword in shuffled_keywords:
        if saved_count >= TARGET_JOBS_PER_COUNTRY:
          break
        if (
            time.time() - domain_start > MAX_SECONDS_PER_DOMAIN
            or time.time() - country_start > MAX_SECONDS_PER_COUNTRY
        ):
          break

        encoded_kw = quote(keyword)
        encoded_city = quote(target_city)

        search_urls = [
            f"https://www.{norm_domain}/jobs?q={encoded_kw}&l={encoded_city}",
            f"https://www.{norm_domain}/search?q={encoded_kw}",
            f"https://www.{norm_domain}/vagas-{encoded_kw}",
            f"https://www.{norm_domain}",
        ]

        for s_url in search_urls:
          if saved_count >= TARGET_JOBS_PER_COUNTRY:
            break
          if (
              time.time() - domain_start > MAX_SECONDS_PER_DOMAIN
              or time.time() - country_start > MAX_SECONDS_PER_COUNTRY
          ):
            break

          try:
            print(f"    [TRACE-NAV] {s_url}")
            page.goto(s_url, timeout=9000, wait_until="domcontentloaded")
            page.wait_for_timeout(900)

            current_content = (page.inner_text("body") or "").lower()
            if any(
                wall in current_content
                for wall in [
                    "sign in to view",
                    "log in to apply",
                    "please login",
                ]
            ):
              print(f"    [TRACE-WALL] Login wall on search URL. Shifting.")
              break

            page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
            page.wait_for_timeout(500)

            raw_links = page.eval_on_selector_all(
                "a[href]",
                """elements => elements.map(el => ({
                                    href: el.href,
                                    text: el.innerText ? el.innerText.trim() : ''
                                }))""",
            )

            candidate_links = []
            for item in raw_links:
              href = item.get("href") or ""
              title_text = item.get("text") or ""
              txt = title_text.lower()

              if any(
                  bad in href.lower() or bad in txt for bad in blocked_url_terms
              ):
                continue
              if href.startswith("/"):
                full_link = f"https://www.{norm_domain}{href}"
              elif href.startswith("http"):
                full_link = href
              else:
                continue

              if full_link.rstrip("/") == base_domain_url:
                continue
              if len(title_text) > 12 and full_link not in visited_links:
                visited_links.add(full_link)
                candidate_links.append((full_link, title_text))

            print(
                f"      [TRACE-PARSE] {len(candidate_links)} candidate links on"
                f" {norm_domain}"
            )

            for j_link, j_title in candidate_links[:15]:
              if saved_count >= TARGET_JOBS_PER_COUNTRY:
                break
              if (
                  time.time() - domain_start > MAX_SECONDS_PER_DOMAIN
                  or time.time() - country_start > MAX_SECONDS_PER_COUNTRY
              ):
                break
              if is_already_scraped(j_link):
                continue

              print(f"        [TRACE-EXTRACT] {j_link}")
              enriched_data = extract_strict_job_details(
                  page, j_link, target_country, target_city, "Jobs"
              )
              if enriched_data and enriched_data.get("finalUrl"):
                final_url = enriched_data["finalUrl"]
                if is_already_scraped(final_url):
                  continue

                final_title = format_strict_title(
                    j_title,
                    keyword,
                    target_city,
                    target_country,
                    current_year,
                )
                if (
                    target_country.lower() not in final_title.lower()
                    and target_city.lower() not in final_title.lower()
                ):
                  continue

                cta_parts = []
                if enriched_data.get("salary") and enriched_data[
                    "salary"
                ] != "Not Specified":
                  cta_parts.append(
                      f"Estimated Amount/Salary: {enriched_data['salary']}"
                  )
                if enriched_data.get("location"):
                  cta_parts.append(
                      f"Location/City: {enriched_data['location']}"
                  )
                if enriched_data.get("phone"):
                  cta_parts.append(f"Contact/Phone: {enriched_data['phone']}")
                if enriched_data.get("email"):
                  cta_parts.append(f"Email: {enriched_data['email']}")
                cta_parts.append(f"Direct Apply Link: {final_url}")

                final_snippet = (
                    enriched_data.get("snippet", "")
                    + "\n\nDetails:\n"
                    + "\n".join(cta_parts)
                )

                insert_data = {
                    "title": final_title,
                    "snippet": final_snippet,
                    "link": final_url,
                    "country": f"{target_country} ({target_city})",
                    "category": "Jobs",
                    "query_used": f"Query: {keyword} on {norm_domain}",
                    "status": "pending",
                    "audit_status": None,
                }
                try:
                  supabase.table("zunex").insert(insert_data).execute()
                  saved_count += 1
                  print(
                      f"  [TRACE-SUCCESS] [{saved_count}/{TARGET_JOBS_PER_COUNTRY}]"
                      f" Saved: {final_title}"
                  )
                  time.sleep(1.5)
                except Exception as db_err:
                  print(f"  [TRACE-DB-ERROR] {db_err}")
                  continue

          except Exception as nav_err:
            print(f"    [TRACE-NAV-ERROR] {nav_err}")
            continue

    print(
        f"  [TRACE-DOMAIN-SHIFT] Done with [{norm_domain}] in"
        f" {int(time.time() - domain_start)}s."
    )

  print(
      f"[TRACE-COUNTRY-DONE] {target_country}: {saved_count} jobs saved in"
      f" {int(time.time() - country_start)}s."
  )
  return saved_count


def run_independent_crawler():
  if not supabase:
    print("[TRACE-CRITICAL] Supabase client is not initialized.")
    return

  run_start = time.time()
  today = datetime.now().strftime("%A")
  current_year = datetime.now().year
  day_countries = SCHEDULE.get(today, [])
  dead_domains = set()

  print(f"\n==================================================")
  print(
      f"=== JOBS PLAYWRIGHT CRAWLER | Day: {today} | Year: {current_year} ==="
  )
  print(f"=== Scheduled Countries: {day_countries} ===")
  print(f"==================================================")

  if not day_countries:
    print("[TRACE-INFO] No countries scheduled for today.")
    return

  blocked_url_terms = [
      "cookie",
      "privacy",
      "legal",
      "terms",
      "login",
      "register",
      "faq",
      "sign-in",
      "order",
      "sort",
      "filter",
      "search?",
      "help",
      "aviso",
      "ads",
      "forgot",
      "download",
      "/salary",
      "/career-advice",
      "/resume",
      "/blog",
      "/article",
      "/resources",
      "/employers",
      "/about",
      "/contact",
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
            "--ignore-ssl-errors",
        ],
    )

    context = browser.new_context(
        user_agent=random.choice(USER_AGENTS),
        viewport={"width": 1366, "height": 768},
        bypass_csp=True,
        ignore_https_errors=True,
    )

    page = context.new_page()
    page.set_default_timeout(9000)

    total_saved = 0
    try:
      for country in day_countries:
        if time.time() - run_start > MAX_TOTAL_RUN_SECONDS:
          print("[TRACE-GLOBAL-STOP] Reached global time limit.")
          break
        total_saved += collect_jobs_for_country(
            page,
            country,
            current_year,
            blocked_url_terms,
            dead_domains,
            run_start,
        )

      print(f"\n==================================================")
      print(
          f"=== JOBS CRAWLER FINISHED | Total Saved: {total_saved} |"
          f" Time: {int(time.time() - run_start)}s ==="
      )
      print(f"==================================================")

    except Exception as e:
      print(f"[TRACE-CRITICAL-ERROR] {e}")
    finally:
      browser.close()
      print("[TRACE-SHUTDOWN] Playwright browser closed cleanly.")


if __name__ == "__main__":
  run_independent_crawler()
