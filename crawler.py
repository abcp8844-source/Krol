import os
import time
import random
import re
from datetime import datetime
from bs4 import BeautifulSoup
from supabase import create_client, Client
from playwright.sync_api import sync_playwright

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")

try:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("Supabase environment variables (SUPABASE_URL or SUPABASE_KEY) are missing!")
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("-> Supabase connection established successfully.")
except Exception as e:
    print(f"[ERROR] Supabase Connection Error: {e}")
    supabase = None

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
]

SCHEDULE = {
    "Monday": ["UAE", "Saudi Arabia", "Qatar", "Bahrain", "Kuwait", "Oman"],
    "Tuesday": ["Japan", "South Korea", "China", "Taiwan", "Singapore", "Hong Kong"],
    "Wednesday": ["Thailand", "Vietnam", "Malaysia", "Indonesia", "Philippines", "Singapore"],
    "Thursday": ["Germany", "France", "Netherlands", "Belgium", "Switzerland", "Austria"],
    "Friday": ["UK", "Ireland", "Sweden", "Norway", "Denmark", "Finland"],
    "Saturday": ["Canada", "USA", "Mexico", "Panama", "Brazil", "Argentina"],
    "Sunday": ["Italy", "Turkey", "Azerbaijan", "Georgia", "Spain", "Greece"]
}

COUNTRY_CITIES = {
    "UAE": ["Dubai", "Abu Dhabi", "Sharjah"],
    "Saudi Arabia": ["Riyadh", "Jeddah"],
    "Qatar": ["Doha"],
    "Bahrain": ["Manama"],
    "Kuwait": ["Kuwait City"],
    "Oman": ["Muscat"],
    "Japan": ["Tokyo", "Osaka"],
    "South Korea": ["Seoul"],
    "China": ["Shanghai", "Beijing"],
    "Taiwan": ["Taipei"],
    "Singapore": ["Singapore"],
    "Hong Kong": ["Hong Kong"],
    "Thailand": ["Bangkok", "Phuket"],
    "Vietnam": ["Ho Chi Minh City", "Hanoi"],
    "Malaysia": ["Kuala Lumpur"],
    "Indonesia": ["Jakarta"],
    "Philippines": ["Manila"],
    "Germany": ["Berlin", "Munich", "Frankfurt"],
    "France": ["Paris", "Lyon"],
    "Netherlands": ["Amsterdam"],
    "Belgium": ["Brussels"],
    "Switzerland": ["Zurich"],
    "Austria": ["Vienna"],
    "UK": ["London", "Manchester", "Birmingham"],
    "Ireland": ["Dublin"],
    "Sweden": ["Stockholm"],
    "Norway": ["Oslo"],
    "Denmark": ["Copenhagen"],
    "Finland": ["Helsinki"],
    "Canada": ["Toronto", "Vancouver"],
    "USA": ["New York", "Los Angeles", "Chicago"],
    "Mexico": ["Mexico City"],
    "Panama": ["Panama City"],
    "Brazil": ["São Paulo", "Rio de Janeiro"],
    "Argentina": ["Buenos Aires"],
    "Italy": ["Rome", "Milan"],
    "Turkey": ["Istanbul", "Ankara", "Izmir"],
    "Azerbaijan": ["Baku"],
    "Georgia": ["Tbilisi"],
    "Spain": ["Madrid", "Barcelona", "Valencia"],
    "Greece": ["Athens"]
}

COUNTRY_DUAL_DOMAINS = {
    "UAE": ["naukrigulf.com", "dubizzle.ae"],
    "Saudi Arabia": ["bayt.com", "saudi.tanqeeb.com"],
    "Qatar": ["qatarliving.com", "bayt.com"],
    "Bahrain": ["bayt.com", "bahrain.tanqeeb.com"],
    "Kuwait": ["bayt.com", "kuwait.tanqeeb.com"],
    "Oman": ["bayt.com", "oman.tanqeeb.com"],
    "Japan": ["daijob.com", "tokyodev.com"],
    "South Korea": ["worknet.go.kr", "saramin.co.kr"],
    "China": ["zhaopin.com", "51job.com"],
    "Taiwan": ["104.com.tw", "1111.com.tw"],
    "Singapore": ["jobstreet.com.sg", "jobsbank.gov.sg"],
    "Hong Kong": ["jobsdb.com.hk", "ctgoodjobs.hk"],
    "Thailand": ["jobthai.com", "jobsdb.com/th"],
    "Vietnam": ["vietnamworks.com", "topcv.vn"],
    "Malaysia": ["jobstreet.com.my", "jobsdb.com.my"],
    "Indonesia": ["jobstreet.co.id", "glints.com/id"],
    "Philippines": ["jobstreet.com.ph", "jobstreet.com.ph"],
    "Germany": ["stepstone.de", "arbeitsagentur.de"],
    "France": ["apec.fr", "welcometothejungle.com"],
    "Netherlands": ["nationalevacaturebank.nl", "stepstone.nl"],
    "Belgium": ["stepstone.be", "vdab.be"],
    "Switzerland": ["jobs.ch", "jobup.ch"],
    "Austria": ["karriere.at", "stepstone.at"],
    "UK": ["reed.co.uk", "cv-library.co.uk"],
    "Ireland": ["irishjobs.ie", "jobs.ie"],
    "Sweden": ["arbetsformedlingen.se", "blocket.se"],
    "Norway": ["finn.no", "nav.no"],
    "Denmark": ["jobindex.dk", "ofir.dk"],
    "Finland": ["duunitori.fi", "te-palvelut.fi"],
    "Canada": ["jobbank.gc.ca", "eluta.ca"],
    "USA": ["ziprecruiter.com", "monster.com"],
    "Mexico": ["occ.com.mx", "computrabajo.com.mx"],
    "Panama": ["computrabajo.com.pa", "encuentra24.com"],
    "Brazil": ["catho.com.br", "infojobs.com.br"],
    "Argentina": ["computrabajo.com.ar", "zonajobs.com.ar"],
    "Italy": ["infojobs.it", "monster.it"],
    "Turkey": ["kariyer.net", "yenibiris.com"],
    "Azerbaijan": ["boss.az", "jobsearch.az"],
    "Georgia": ["hr.ge", "jobs.ge"],
    "Spain": ["infojobs.net", "empleo.gob.es"],
    "Greece": ["kariera.gr", "xe.gr"]
}

COUNTRY_KEYWORDS = {
    "UAE": ["engineer", "manager", "developer", "sales", "accountant", "nurse", "driver", "technician", "hr", "admin"],
    "Saudi Arabia": ["engineer", "manager", "developer", "sales", "accountant", "nurse", "driver", "technician", "supervisor"],
    "Qatar": ["engineer", "manager", "developer", "sales", "accountant", "hospitality", "admin"],
    "Bahrain": ["engineer", "manager", "sales", "accountant", "admin"],
    "Kuwait": ["engineer", "manager", "sales", "accountant", "nurse"],
    "Oman": ["engineer", "manager", "sales", "accountant"],
    "Japan": ["engineer", "developer", "sales", "manager", "marketing"],
    "South Korea": ["engineer", "developer", "manager", "sales"],
    "China": ["engineer", "developer", "manager", "sales", "analyst"],
    "Taiwan": ["engineer", "developer", "manager", "sales"],
    "Singapore": ["engineer", "manager", "developer", "analyst", "sales"],
    "Hong Kong": ["manager", "developer", "analyst", "sales", "accountant"],
    "Thailand": ["manager", "engineer", "sales", "admin", "hotel"],
    "Vietnam": ["developer", "engineer", "manager", "sales"],
    "Malaysia": ["engineer", "manager", "developer", "sales", "accountant"],
    "Indonesia": ["engineer", "manager", "sales", "developer"],
    "Philippines": ["agent", "nurse", "manager", "developer", "engineer"],
    "Germany": ["developer", "engineer", "manager", "consultant", "analyst"],
    "France": ["développeur", "ingénieur", "manager", "commercial"],
    "Netherlands": ["developer", "engineer", "manager", "analyst"],
    "Belgium": ["developer", "engineer", "manager"],
    "Switzerland": ["engineer", "developer", "manager", "consultant"],
    "Austria": ["developer", "engineer", "manager"],
    "UK": ["developer", "manager", "engineer", "analyst", "consultant", "admin"],
    "Ireland": ["developer", "manager", "engineer", "sales"],
    "Sweden": ["developer", "engineer", "manager"],
    "Norway": ["developer", "engineer", "manager"],
    "Denmark": ["developer", "engineer", "manager"],
    "Finland": ["developer", "engineer", "manager"],
    "Canada": ["developer", "manager", "engineer", "analyst", "representative"],
    "USA": ["developer", "manager", "engineer", "analyst", "representative", "specialist"],
    "Mexico": ["gerente", "ingeniero", "desarrollador", "ventas", "analista"],
    "Panama": ["gerente", "ingeniero", "ventas", "asistente"],
    "Brazil": ["gerente", "engenheiro", "desenvolvedor", "vendas"],
    "Argentina": ["gerente", "ingeniero", "analista", "ventas"],
    "Italy": ["sviluppatore", "ingegnere", "manager", "commerciale"],
    "Turkey": ["mühendis", "uzman", "yönetici", "müdür", "developer", "satış"],
    "Azerbaijan": ["mühəndis", "menecer", "mütəxəssis", "satış"],
    "Georgia": ["manager", "developer", "engineer", "sales"],
    "Spain": ["ingeniero", "desarrollador", "gerente", "comercial", "analista"],
    "Greece": ["developer", "manager", "engineer", "sales"]
}

def clean_text_content(text):
    if not text:
        return ""
    cleaned = re.sub(r"(?i)we use cookies.*?(accept|agree|decline|settings)", "", text)
    cleaned = re.sub(r"(?i)privacy policy.*?(rights reserved|cookies)", "", cleaned)
    return re.sub(r'\s+', ' ', cleaned).strip()

def extract_strict_job_details(page, target_url):
    try:
        page.goto(target_url, timeout=25000, wait_until="domcontentloaded")
        time.sleep(3)
        
        html_content = page.content()
        soup = BeautifulSoup(html_content, 'html.parser')
        
        for element in soup(["script", "style", "nav", "footer", "header", "aside", "form", "iframe", "button"]):
            element.decompose()
            
        page_text = soup.get_text(separator=" ")
        page_text = clean_text_content(page_text)

        if any(term in page_text.lower() for term in ["cookie policy", "privacy policy", "legal notice", "page not found", "error 404", "job expired", "position filled", "sign in to view"]):
            return None

        job_indicators = ["requirements", "experience", "qualification", "responsibilities", "duties", "salary", "apply", "puesto", "empleo", "vacante", "iş ilanı", "mühendis"]
        if not any(ind in page_text.lower() for ind in job_indicators):
            return None

        salary = "Not Specified"
        salary_match = re.search(r'(?:salary|pay|wage|compensation|USD|EUR|AED|QAR|SAR|SGD|\$|₺)\s*[:\-]?\s*[\d,]+\s*(?:-|to)?\s*[\d,]*', page_text, re.IGNORECASE)
        if salary_match:
            salary = salary_match.group(0).strip()

        location = "Local / On-site"
        loc_match = re.search(r'(?:Location|City|Address|Area):\s*([A-Za-z\s,]+)', page_text, re.IGNORECASE)
        if loc_match:
            location = loc_match.group(1).strip()[:50]

        email_match = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', page_text)
        email = email_match.group(0) if email_match else ""

        phone_match = re.search(r'\+?\d{1,4}?[-.\s]?\(?\d{1,3}?\)?[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}', page_text)
        phone = phone_match.group(0).strip() if phone_match else ""

        paragraphs = []
        for p in soup.find_all(['p', 'div', 'li']):
            txt = p.get_text().strip()
            if len(txt) > 30 and any(k in txt.lower() for k in ["apply", "salary", "requirement", "experience", "qualification", "duty", "responsibility", "benefit", "position"]):
                if txt not in paragraphs:
                    paragraphs.append(txt)

        intro_snippet = " ".join(page_text.split()[:120])
        combined_details = intro_snippet
        if paragraphs:
            combined_details += "\n\nKey Job Description & Requirements:\n" + "\n".join([f"- {pr}" for pr in paragraphs[:8]])

        if len(combined_details.split()) < 30:
            return None

        return {
            "finalUrl": page.url,
            "salary": salary,
            "location": location,
            "email": email,
            "phone": phone,
            "snippet": combined_details[:1800]
        }
    except Exception:
        return None

def run_independent_crawler():
    if not supabase:
        print("[ERROR] Aborting crawler run because Supabase client failed to initialize.")
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
                browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
            except Exception as b_err:
                print(f"[CRITICAL ERROR] Failed to launch Playwright browser: {b_err}")
                return

            context = browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": 1280, "height": 800}
            )
            page = context.new_page()

            posts_found = 0
            required_posts = 1
            
            shuffled_cities = list(cities)
            random.shuffle(shuffled_cities)
            random.shuffle(keywords)

            for target_city in shuffled_cities:
                if posts_found >= required_posts:
                    break

                for target_domain in domains:
                    if posts_found >= required_posts:
                        break

                    for keyword in keywords[:3]: # ہر ڈومین پر کم از کم 3 مختلف کیوریز ٹرائی کرے گا
                        if posts_found >= required_posts:
                            break

                        print(f"-> Searching Domain: {target_domain} | City: {target_city} | Keyword: {keyword}")
                        
                        # کیوری بیسڈ یو آر ایل جنریٹ کرنا تاکہ یہ سیدھا سرچ رزلٹ پر جائے
                        search_urls = [
                            f"https://www.{target_domain}/jobs?q={keyword}&l={target_city}",
                            f"https://www.{target_domain}/search?q={keyword}",
                            f"https://www.{target_domain}"
                        ]

                        for s_url in search_urls:
                            if posts_found >= required_posts:
                                break
                            try:
                                page.goto(s_url, timeout=25000, wait_until="domcontentloaded")
                                time.sleep(4)

                                html = page.content()
                                soup = BeautifulSoup(html, 'html.parser')

                                job_link = None
                                job_title = f"{keyword.capitalize()} Job in {target_city}, {target_country} ({current_year})"

                                for a in soup.find_all('a', href=True):
                                    href = a['href']
                                    txt = a.get_text().lower()
                                    
                                    if any(bad in href.lower() or bad in txt for bad in ["cookie", "privacy", "legal", "terms", "login", "register", "faq", "sign-in"]):
                                        continue

                                    if keyword.lower() in href.lower() or keyword.lower() in txt or "job" in href.lower() or "ilan" in href.lower() or "position" in href.lower():
                                        if href.startswith('/'):
                                            job_link = f"https://www.{target_domain}{href}"
                                        elif href.startswith('http'):
                                            job_link = href
                                        
                                        title_text = a.get_text().strip()
                                        if len(title_text) > 10:
                                            job_title = title_text[:100]
                                            break

                                if job_link:
                                    print(f"-> Found Job Link: {job_link}")
                                    enriched_data = extract_strict_job_details(page, job_link)
                                    
                                    if enriched_data:
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
                                            print(f">>> [SUCCESS] Verified job post inserted for {target_country} ({target_city}) using query '{keyword}'!")
                                            posts_found += 1
                                            break
                                        except Exception as db_err:
                                            print(f"[ERROR] Supabase Insertion Failed: {db_err}")
                            except Exception:
                                continue

            browser.close()
    except Exception as e:
        print(f"[CRITICAL ERROR] Crawler Execution Exception: {e}")

if __name__ == "__main__":
    run_independent_crawler()
