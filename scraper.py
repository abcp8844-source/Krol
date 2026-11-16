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
    suffix = f" - Comprehensive {keyword.capitalize()} Career Opportunities, Professional Requirements, Verification Details, and Direct Online Application Process in {city}, {country} ({year})"
    
    title = f"{base}{suffix}" if base else f"Complete Official Guide for Immediate {keyword.capitalize()} Opening in {city}, {country} ({year}) - Verified Direct Application Portal and Requirements"

    if len(title.split()) < 40:
        title = f"{title} - Detailed Eligibility Criteria, Salary Packages, Benefits, Documentation, and Step-by-Step Application Instructions for Interested Job Seekers"

    return title

def is_already_scraped(url):
    try:
        res = supabase.table("zunex").select("id").eq("link", url).execute()
        return len(res.data) > 0
    except Exception:
        return False

def search_and_insert_job_for_country(driver, target_country, current_year, blocked_url_terms):
    cities = COUNTRY_CITIES.get(target_country, [target_country])
    domains = COUNTRY_DOMAINS.get(target_country, [])
    country_kw_dict = COUNTRY_KEYWORDS.get(target_country, {"Jobs": ["apply now"]})
    
    if not domains:
        return False
        
    if isinstance(country_kw_dict, dict):
        keywords = list(country_kw_dict.get("Jobs", ["apply now"]))
    else:
        keywords = list(country_kw_dict)

    for target_city in cities:
        for target_domain in domains:
            for keyword in keywords:
                search_urls = [
                    f"https://{target_domain}/jobs?q={keyword}&l={target_city}",
                    f"https://{target_domain}/search?q={keyword}",
                    f"https://{target_domain}/jobs/{keyword}",
                    f"https://{target_domain}/vagas-{keyword}",
                    f"https://{target_domain}"
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
                                full_link = f"https://{target_domain}{href}"
                            elif href.startswith('http'):
                                full_link = href
                            else:
                                continue
                            if full_link.rstrip('/') == f"https://{target_domain}":
                                continue
                            title_text = a.get_text().strip()
                            if len(title_text) > 10:
                                candidate_links.append((full_link, title_text))

                        for j_link, j_title in candidate_links[:20]:
                            if is_already_scraped(j_link):
                                continue
                            
                            enriched_data = extract_strict_job_details(
                                driver, j_link, target_country, target_city, "Jobs"
                            )
                            if enriched_data:
                                if is_already_scraped(enriched_data['finalUrl']):
                                    continue
                                
                                raw_snippet = enriched_data.get("snippet", "")
                                if len(raw_snippet.split()) < 400:
                                    raw_snippet += f"\n\nComprehensive Job Overview: This official listing for a {keyword} position in {target_city}, {target_country} provides detailed professional insights, candidate eligibility benchmarks, necessary documentation, interview preparation guidelines, employer expectations, perks, allowances, and direct application links to ensure applicants have all required details before submitting their professional profiles."

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

                                final_snippet = raw_snippet + "\n\nComprehensive Details & Application Channels:\n" + "\n".join(cta_parts)

                                insert_data = {
                                    'title': final_title,
                                    'snippet': final_snippet,
                                    'link': enriched_data['finalUrl'],
                                    'country': f"{target_country} ({target_city})",
                                    'category': 'Jobs',
                                    'query_used': f"Query: {keyword} on {target_domain}",
                                    'status': 'pending',
                                    'audit_status': None
                                }
                                try:
                                    supabase.table("zunex").insert(insert_data).execute()
                                    time.sleep(5)
                                    return True
                                except Exception:
                                    pass
                    except Exception:
                        continue
    return False

def run_independent_crawler():
    if not supabase:
        return

    today = datetime.now().strftime("%A")
    current_year = datetime.now().year
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
        for country in day_countries:
            inserted = False
            while not inserted:
                inserted = search_and_insert_job_for_country(driver, country, current_year, blocked_url_terms)
                if not inserted:
                    time.sleep(5)

    except Exception:
        pass
    finally:
        driver.quit()

if __name__ == "__main__":
    run_independent_crawler()
