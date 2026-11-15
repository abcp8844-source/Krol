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

def run_independent_crawler():
    if not supabase:
        return

    today = datetime.now().strftime("%A")
    current_year = datetime.now().year
    
    # Fully relies on config.py schedule, no hardcoded fake countries
    day_countries = SCHEDULE.get(today, [])
    if not day_countries:
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

    blocked_url_terms = [
        "cookie", "privacy", "legal", "terms", "login", "register", "faq", "sign-in", 
        "order", "sort", "filter", "search?", "help", "aviso", "ads", "forgot", "download",
        "/salary", "/career-advice", "/resume", "/blog", "/article", "/resources", "/employers", "/about", "/contact"
    ]

    try:
        shuffled_countries = list(day_countries)
        random.shuffle(shuffled_countries)

        for target_country in shuffled_countries:
            cities = COUNTRY_CITIES.get(target_country, [target_country])
            domains = COUNTRY_DOMAINS.get(target_country, [])
            country_kw_dict = COUNTRY_KEYWORDS.get(target_country, {"Jobs": ["apply now"]})

            if not domains:
                continue

            shuffled_cities = list(cities)
            random.shuffle(shuffled_cities)

            for target_city in shuffled_cities:
                shuffled_domains = list(domains)

                for target_domain in shuffled_domains:
                    categories = ["Jobs", "Visa", "Travel"]
                    random.shuffle(categories)

                    for category in categories:
                        if isinstance(country_kw_dict, dict):
                            keywords = list(country_kw_dict.get(category, ["apply now"]))
                        else:
                            keywords = list(country_kw_dict)

                        for keyword in keywords:
                            search_urls = [
                                f"https://www.{target_domain}/jobs?q={keyword}&l={target_city}",
                                f"https://www.{target_domain}/search?q={keyword}",
                                f"https://www.{target_domain}/vagas-{keyword}",
                                f"https://www.{target_domain}"
                            ]

                            for s_url in search_urls:
                                try:
                                    driver.get(s_url)
                                    time.sleep(5)

                                    soup = BeautifulSoup(driver.page_source, 'html.parser')
                                    candidate_links = []

                                    for a in soup.find_all('a', href=True):
                                        href = a['href']
                                        txt = a.get_text().lower()

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

                                        title_text = a.get_text().strip()
                                        if len(title_text) > 12:
                                            candidate_links.append((full_link, title_text))

                                    for j_link, j_title in candidate_links[:30]:
                                        if is_already_scraped(j_link):
                                            continue

                                        enriched_data = extract_strict_job_details(
                                            driver, j_link, target_country, target_city, category
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
                                                # Insert one post immediately
                                                supabase.table("zunex").insert(insert_data).execute()
                                                
                                                # Take a 5 seconds break after inserting one post as requested
                                                time.sleep(5)
                                                
                                                # Return/Break to process next systematically one by one
                                                return 
                                            except Exception:
                                                pass

                                except Exception:
                                    continue

    except Exception:
        pass
    finally:
        driver.quit()

if __name__ == "__main__":
    run_independent_crawler()
