import time
import random
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY, SCHEDULE, COUNTRY_CITIES, COUNTRY_DUAL_DOMAINS, COUNTRY_KEYWORDS, USER_AGENTS
from cleaner import extract_strict_job_details

try:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("Supabase environment variables missing")
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception:
    supabase = None

def run_independent_crawler():
    if not supabase:
        return

    today = datetime.now().strftime("%A")
    current_year = datetime.now().year
    day_countries = SCHEDULE.get(today, ["Spain"])
    
    target_country = random.choice(day_countries)
    cities = COUNTRY_CITIES.get(target_country, [target_country])
    domains = COUNTRY_DUAL_DOMAINS.get(target_country, [])
    keywords = COUNTRY_KEYWORDS.get(target_country, ["developer", "manager", "engineer"])
    
    if not domains:
        return

    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--ignore-certificate-errors",
                        "--disable-gpu",
                        "--no-sandbox",
                        "--disable-dev-shm-usage"
                    ]
                )
            except Exception:
                return

            context = browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": 1366, "height": 768},
                ignore_https_errors=True
            )
            page = context.new_page()

            posts_found = 0
            required_posts = 1
            
            shuffled_cities = list(cities)
            random.shuffle(shuffled_cities)
            random.shuffle(domains)
            random.shuffle(keywords)

            for target_city in shuffled_cities:
                if posts_found >= required_posts:
                    break

                for target_domain in domains:
                    if posts_found >= required_posts:
                        break

                    for keyword in keywords:
                        if posts_found >= required_posts:
                            break
                        
                        search_urls = [
                            f"https://www.{target_domain}/jobs?q={keyword}&l={target_city}",
                            f"https://www.{target_domain}/search?q={keyword}",
                            f"https://www.{target_domain}"
                        ]

                        for s_url in search_urls:
                            if posts_found >= required_posts:
                                break
                            try:
                                page.goto(s_url, timeout=35000, wait_until="domcontentloaded")
                                time.sleep(3)

                                html = page.content()
                                soup = BeautifulSoup(html, 'html.parser')

                                default_title = f"{keyword.capitalize()} Job in {target_city}, {target_country} ({current_year})"
                                candidate_links = []
                                
                                for a in soup.find_all('a', href=True):
                                    href = a['href']
                                    txt = a.get_text().lower()
                                    
                                    if any(bad in href.lower() or bad in txt for bad in ["cookie", "privacy", "legal", "terms", "login", "register", "faq", "sign-in"]):
                                        continue

                                    if any(term in href.lower() or term in txt for term in [keyword.lower(), "job", "career", "vacancy", "position", "ilan"]):
                                        if href.startswith('/'):
                                            full_link = f"https://www.{target_domain}{href}"
                                        elif href.startswith('http'):
                                            full_link = href
                                        else:
                                            continue
                                        
                                        title_text = a.get_text().strip()
                                        if len(title_text) > 5:
                                            candidate_links.append((full_link, title_text[:100]))

                                for j_link, j_title in candidate_links[:5]:
                                    enriched_data = extract_strict_job_details(page, j_link)
                                    
                                    if enriched_data:
                                        job_title = j_title if j_title and len(j_title) > 5 else default_title
                                        cta_parts = []
                                        if enriched_data["salary"] != "Not Specified":
                                            cta_parts.append(f"Estimated Salary: {enriched_data['salary']}")
                                        if enriched_data["location"]:
                                            cta_parts.append(f"Location/City: {enriched_data['location']}")
                                        if enriched_data["phone"]:
                                            cta_parts.append(f"Contact/Phone: {enriched_data['phone']}")
                                        if enriched_data["email"]:
                                            cta_parts.append(f"Email: {enriched_data['email']}")
                                        
                                        cta_parts.append(f"Direct Job Link: {enriched_data['finalUrl']}")
                                        
                                        final_snippet = enriched_data["snippet"] + "\n\nDetails:\n" + "\n".join(cta_parts)

                                        insert_data = {
                                            'title': job_title,
                                            'snippet': final_snippet,
                                            'link': enriched_data['finalUrl'],
                                            'country': f"{target_country} ({target_city})",
                                            'category': "Jobs",
                                            'query_used': f"Query: {keyword} on {target_domain}",
                                            'status': 'pending',
                                            'audit_status': None
                                        }

                                        try:
                                            supabase.table("zunex").insert(insert_data).execute()
                                            posts_found += 1
                                            break
                                        except Exception:
                                            pass
                                    
                                    if posts_found >= required_posts:
                                        break
                                
                                if posts_found >= required_posts:
                                    break

                            except Exception:
                                continue

            browser.close()
    except Exception:
        pass
