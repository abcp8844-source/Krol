from datetime import datetime
import os
import random
import time
from bs4 import BeautifulSoup
from cleaner import extract_strict_job_details
from config import (
    COUNTRY_CITIES,
    COUNTRY_DUAL_DOMAINS,
    COUNTRY_KEYWORDS,
    SCHEDULE,
    SUPABASE_KEY,
    SUPABASE_URL,
    USER_AGENTS,
)
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from supabase import Client, create_client

if not SUPABASE_URL or not SUPABASE_KEY:
  raise ValueError("Supabase environment variables missing")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def run_independent_crawler():
  if not supabase:
    return

  today = datetime.now().strftime("%A")
  current_year = datetime.now().year
  day_countries = SCHEDULE.get(today, ["Spain"])

  target_country = random.choice(day_countries)
  cities = COUNTRY_CITIES.get(target_country, [target_country])
  domains = COUNTRY_DUAL_DOMAINS.get(target_country, [])
  keywords = COUNTRY_KEYWORDS.get(
      target_country, ["developer", "manager", "engineer"]
  )

  if not domains:
    return

  options = Options()
  options.add_argument("--headless=new")
  options.add_argument("--disable-gpu")
  options.add_argument("--no-sandbox")
  options.add_argument("--disable-dev-shm-usage")
  options.add_argument("--disable-blink-features=AutomationControlled")
  options.add_experimental_option("excludeSwitches", ["enable-automation"])
  options.add_experimental_option("useAutomationExtension", False)
  options.add_argument(f"user-agent={random.choice(USER_AGENTS)}")

  driver = webdriver.Chrome(options=options)
  driver.execute_script(
      "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
  )
  driver.set_window_size(1366, 768)

  posts_found = 0
  required_posts = 8

  try:
    shuffled_cities = list(cities)
    random.shuffle(shuffled_cities)
    shuffled_domains = list(domains)
    random.shuffle(shuffled_domains)

    for target_city in shuffled_cities:
      if posts_found >= required_posts:
        break

      for target_domain in shuffled_domains:
        if posts_found >= required_posts:
          break

        shuffled_keywords = list(keywords)
        random.shuffle(shuffled_keywords)

        for keyword in shuffled_keywords:
          if posts_found >= required_posts:
            break

          search_urls = [
              f"https://www.{target_domain}/jobs?q={keyword}&l={target_city}",
              f"https://www.{target_domain}/search?q={keyword}",
              f"https://www.{target_domain}/vagas-{keyword}",
              f"https://www.{target_domain}",
          ]

          for s_url in search_urls:
            if posts_found >= required_posts:
              break
            try:
              driver.get(s_url)
              time.sleep(5)

              soup = BeautifulSoup(driver.page_source, "html.parser")
              default_title = (
                  f"{keyword.capitalize()} Job in {target_city},"
                  f" {target_country} ({current_year})"
              )
              candidate_links = []

              for a in soup.find_all("a", href=True):
                href = a["href"]
                txt = a.get_text().lower()

                if any(
                    bad in href.lower() or bad in txt
                    for bad in [
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
                    ]
                ):
                  continue

                if href.startswith("/"):
                  full_link = f"https://www.{target_domain}{href}"
                elif href.startswith("http"):
                  full_link = href
                else:
                  continue

                title_text = a.get_text().strip()
                if len(title_text) > 10:
                  candidate_links.append((full_link, title_text[:500]))

              for j_link, j_title in candidate_links[:50]:
                if posts_found >= required_posts:
                  break

                enriched_data = extract_strict_job_details(driver, j_link)

                if enriched_data:
                  job_title = (
                      j_title
                      if j_title and len(j_title) > 10 and len(j_title) < 150
                      else default_title
                  )
                  cta_parts = []
                  if enriched_data["salary"] != "Not Specified":
                    cta_parts.append(
                        f"Estimated Salary: {enriched_data['salary']}"
                    )
                  if enriched_data["location"]:
                    cta_parts.append(f"Location/City: {enriched_data['location']}")
                  if enriched_data["phone"]:
                    cta_parts.append(f"Contact/Phone: {enriched_data['phone']}")
                  if enriched_data["email"]:
                    cta_parts.append(f"Email: {enriched_data['email']}")

                  cta_parts.append(f"Direct Job Link: {enriched_data['finalUrl']}")

                  final_snippet = (
                      enriched_data["snippet"]
                      + "\n\nDetails:\n"
                      + "\n".join(cta_parts)
                  )

                  insert_data = {
                      "title": job_title,
                      "snippet": final_snippet,
                      "link": enriched_data["finalUrl"],
                      "country": f"{target_country} ({target_city})",
                      "category": "Jobs",
                      "query_used": f"Query: {keyword} on {target_domain}",
                      "status": "pending",
                      "audit_status": None,
                  }

                  try:
                    supabase.table("zunex").insert(insert_data).execute()
                    posts_found += 1
                    break
                  except Exception:
                    pass

              if posts_found >= required_posts:
                break

            except Exception:
              continue

  except Exception:
    pass
  finally:
    driver.quit()


if __name__ == "__main__":
  run_independent_crawler()
