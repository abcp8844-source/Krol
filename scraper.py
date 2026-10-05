# scraper.py
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
        raise ValueError("Supabase environment variables are missing!")
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("-> [Supabase] Connected successfully.")
except Exception as e:
    print(f"[ERROR] Supabase Connection Error: {e}")
    supabase = None

def run_independent_crawler():
    if not supabase:
        print("[ERROR] Aborting crawler run: Supabase client is missing.")
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

    print(f"-> Today: {today} | Target Country: {target_country} | Domains: {domains}")

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
            except Exception as b_err:
                print(f"[CRITICAL ERROR] Failed to launch browser: {b_err}")
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
            random.shuffle(keywords)
            random.shuffle(domains)

            for target_city in shuffled_cities:
                if posts_found >= required_posts:
                    break

                for target_domain in domains:
                    if posts_found >= required_posts:
                        break

                    for keyword in keywords: 
                        if posts_found >= required_posts:
                            break

                        print(f"\n[DEEP SEARCH] Domain: {target_domain} | City: {target_city} | Keyword: {keyword}")
                        
                        # Secure HTTPS Search URLs construction
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
                                time.sleep(4)

                                html = page.content()
                                soup = BeautifulSoup(html, 'html.parser')

                                default_title = f"{keyword.capitalize()} Job in {target_city}, {target_country} ({current_year})"
                                candidate_links = []
                                
                                for a in soup.find_all('a', href=True):
                                    href = a['href']
                                    txt = a.get_text().lower()
                                    
                                    # Skip garbage / footer links
                                    if any(bad in href.lower() or bad in txt for bad in ["cookie", "privacy", "legal", "terms", "login", "register", "faq", "sign-in", "about", "contact", "profile"]):
                                        continue

                                    if any(term in href.lower() or term in txt for term in [keyword.lower(), "job", "career", "vacancy", "position", "ilan"]):
                                        if href.startswith('/'):
                                            full_link = f"https://www.{target_domain}{href}"
                                        elif href.startswith('http'):
                                            full_link = href
                                        else:
                                            continue
                                        
                                        title_text = a.get_text().strip()
                                        if len(title_text) > 10:
                                            candidate_links.append((full_link, title_text[:100]))

                                for j_link, j_title in candidate_links[:4]:
                                    enriched_data = extract_strict_job_details(page, j_link)
                                    
                                    if enriched_data:
                                        job_title = j_title if j_title and len(j_title) > 10 else default_title
                                        cta_parts = []
                                        if enriched_data["salary"] != "Not Specified":
                                            cta_parts.append(f"Estimated Salary: {enriched_data['salary']}")
                                        if enriched_data["location"]:
                                            cta_parts.append(f"Location/City: {enriched_data['location']}")
                                        if enriched_data["phone"]:
                                            cta_parts.append(f"Contact/Phone: {enriched_data['phone']}")
                                        if enriched_data["email"]:
                                            cta_parts.append(f"Email: {enriched_data['email']}")
                                        
                                        cta_parts.append(f"Apply / Direct Job Link: {enriched_data['finalUrl']}")
                                        
                                        final_snippet = enriched_data["snippet"] + "\n\nCall to Action & Direct Details:\n" + "\n".join(cta_parts)

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
                                            print(f">>> [SUCCESS] 100% Clean Verified Job Inserted for {target_country} ({target_city})!")
                                            posts_found += 1
                                            break
                                        except Exception as db_err:
                                            print(f"[ERROR] Supabase Insertion Failed: {db_err}")
                                    
                                    if posts_found >= required_posts:
                                        break
                                
                                if posts_found >= required_posts:
                                    break

                            except Exception as ex:
                                continue

            browser.close()
    except Exception as e:
        print(f"[CRITICAL ERROR] Crawler Exception: {e}")
print("-> [Scraper Engine] Secure crawler module loaded.")
