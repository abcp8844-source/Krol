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
    "UAE": ["Dubai", "Abu Dhabi", "Sharjah", "Ajman"],
    "Saudi Arabia": ["Riyadh", "Jeddah", "Mecca", "Medina"],
    "Qatar": ["Doha", "Al Rayyan", "Al Wakrah"],
    "Bahrain": ["Manama", "Muharraq", "Riffa"],
    "Kuwait": ["Kuwait City", "Hawalli", "Salmiya"],
    "Oman": ["Muscat", "Salalah", "Sohar"],
    "Japan": ["Tokyo", "Osaka", "Kyoto", "Yokohama"],
    "South Korea": ["Seoul", "Busan", "Incheon"],
    "China": ["Shanghai", "Beijing", "Shenzhen", "Guangzhou"],
    "Taiwan": ["Taipei", "Kaohsiung", "Taichung"],
    "Singapore": ["Singapore"],
    "Hong Kong": ["Hong Kong", "Kowloon"],
    "Thailand": ["Bangkok", "Phuket", "Chiang Mai"],
    "Vietnam": ["Ho Chi Minh City", "Hanoi", "Da Nang"],
    "Malaysia": ["Kuala Lumpur", "Penang", "Johor Bahru"],
    "Indonesia": ["Jakarta", "Surabaya", "Bandung"],
    "Philippines": ["Manila", "Cebu City", "Davao"],
    "Germany": ["Berlin", "Munich", "Frankfurt", "Hamburg"],
    "France": ["Paris", "Lyon", "Marseille", "Toulouse"],
    "Netherlands": ["Amsterdam", "Rotterdam", "The Hague"],
    "Belgium": ["Brussels", "Antwerp", "Ghent"],
    "Switzerland": ["Zurich", "Geneva", "Basel"],
    "Austria": ["Vienna", "Salzburg", "Graz"],
    "UK": ["London", "Manchester", "Birmingham", "Edinburgh"],
    "Ireland": ["Dublin", "Cork", "Galway"],
    "Sweden": ["Stockholm", "Gothenburg", "Malmo"],
    "Norway": ["Oslo", "Bergen", "Trondheim"],
    "Denmark": ["Copenhagen", "Aarhus", "Odense"],
    "Finland": ["Helsinki", "Espoo", "Tampere"],
    "Canada": ["Toronto", "Vancouver", "Montreal", "Calgary"],
    "USA": ["New York", "Los Angeles", "Chicago", "Houston"],
    "Mexico": ["Mexico City", "Guadalajara", "Monterrey"],
    "Panama": ["Panama City", "Colon"],
    "Brazil": ["São Paulo", "Rio de Janeiro", "Brasília"],
    "Argentina": ["Buenos Aires", "Córdoba", "Rosario"],
    "Italy": ["Rome", "Milan", "Naples", "Turin"],
    "Turkey": ["Istanbul", "Ankara", "Izmir"],
    "Azerbaijan": ["Baku", "Ganja"],
    "Georgia": ["Tbilisi", "Batumi"],
    "Spain": ["Madrid", "Barcelona", "Valencia", "Seville", "Bilbao", "Malaga"],
    "Greece": ["Athens", "Thessaloniki"]
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
    "UAE": ["job", "career", "vacancy", "position", "وظائف", "emploi", "hiring", "opportunities", "work", "apply"],
    "Saudi Arabia": ["job", "career", "vacancy", "position", "وظائف", "vancancy", "employment", "hiring", "opportunities", "apply"],
    "Qatar": ["job", "career", "vacancy", "position", "وظائف", "hiring", "employment", "opportunities", "work"],
    "Bahrain": ["job", "career", "vacancy", "position", "وظائف", "hiring", "employment", "opportunities"],
    "Kuwait": ["job", "career", "vacancy", "position", "وظائف", "hiring", "employment", "opportunities"],
    "Oman": ["job", "career", "vacancy", "position", "وظائف", "hiring", "employment", "opportunities"],
    "Japan": ["job", "career", "vacancy", "position", "求人", "採用", "仕事", "中途", "正社員", "hiring"],
    "South Korea": ["job", "career", "vacancy", "position", "채용", "구인", "일자리", "취업", "모집", "hiring"],
    "China": ["job", "career", "vacancy", "position", "招聘", "职位", "工作", "社会招聘", "全职", "hiring"],
    "Taiwan": ["job", "career", "vacancy", "position", "職缺", "工作", "招募", "求職", "兼職", "hiring"],
    "Singapore": ["job", "career", "vacancy", "position", "hiring", "employment", "opportunities", "sgjobs"],
    "Hong Kong": ["job", "career", "vacancy", "position", "招聘", "職位", "筍工", "hiring", "employment"],
    "Thailand": ["job", "career", "vacancy", "position", "งาน", "สมัครงาน", "จัดหางาน", "hiring", "employment"],
    "Vietnam": ["job", "career", "vacancy", "position", "việc làm", "tuyển dụng", "cơ hội việc làm", "hiring"],
    "Malaysia": ["job", "career", "vacancy", "position", "kerja", "jawatan", "kekosongan", "hiring", "employment"],
    "Indonesia": ["job", "career", "vacancy", "position", "lowongan", "kerja", "loker", "karir", "hiring"],
    "Philippines": ["job", "career", "vacancy", "position", "trabaho", "hiring", "empleyo", "opportunities"],
    "Germany": ["job", "career", "vacancy", "position", "stelle", "karriere", "ausbildung", "arbeit", "jobs", "stellenangebot"],
    "France": ["job", "career", "vacancy", "position", "emploi", "offre", "poste", "carrière", "alternance", "recrutement"],
    "Netherlands": ["job", "career", "vacancy", "position", "vacature", "baan", "werk", "carriere", "solliciteren"],
    "Belgium": ["job", "career", "vacancy", "position", "vacature", "emploi", "offres", "travail", "jobs"],
    "Switzerland": ["job", "career", "vacancy", "position", "stelle", "emploi", "lavoro", "jobs", "karriere"],
    "Austria": ["job", "career", "vacancy", "position", "stelle", "karriere", "jobbörse", "arbeiten", "jobs"],
    "UK": ["job", "career", "vacancy", "position", "employment", "opportunity", "roles", "hiring", "work"],
    "Ireland": ["job", "career", "vacancy", "position", "employment", "opportunities", "hiring", "work"],
    "Sweden": ["job", "career", "vacancy", "position", "jobb", "lediga", "tjänst", "arbete", "rekrytering"],
    "Norway": ["job", "career", "vacancy", "position", "stilling", "jobb", "karriere", "arbeid", "ledige"],
    "Denmark": ["job", "career", "vacancy", "position", "stilling", "ledige", "arbejde", "jobmuligheder"],
    "Finland": ["job", "career", "vacancy", "position", "työpaikat", "avoimet", "rekrytointi", "työ", "duuni"],
    "Canada": ["job", "career", "vacancy", "position", "employment", "hiring", "opportunities", "careers", "work"],
    "USA": ["job", "career", "vacancy", "position", "employment", "hiring", "opportunity", "careers", "opening"],
    "Mexico": ["job", "career", "vacancy", "position", "empleo", "trabajo", "vacantes", "bolsa de trabajo", "contratacion"],
    "Panama": ["job", "career", "vacancy", "position", "empleo", "trabajo", "vacantes", "oportunidades"],
    "Brazil": ["job", "career", "vacancy", "position", "vagas", "emprego", "trabalho", "oportunidades", "contratando"],
    "Argentina": ["job", "career", "vacancy", "position", "empleo", "trabajo", "busqueda", "ofertas", "empleos"],
    "Italy": ["job", "career", "vacancy", "position", "lavoro", "offerta", "impiego", "posizioni", "assunzioni", "lavora"],
    "Turkey": ["job", "career", "vacancy", "position", "iş", "ilan", "kariyer", "pozisyon", "eleman", "araniyor", "personel"],
    "Azerbaijan": ["job", "career", "vacancy", "position", "iş", "vakansiya", "kadr", "elanlar", "işə", "qəbul"],
    "Georgia": ["job", "career", "vacancy", "position", "vakansia", "samushao", "وظائف", "სამუშაო", "ვაკანსია"],
    "Spain": ["job", "career", "vacancy", "position", "empleo", "trabajo", "ofertas", "puesto", "bolsa de empleo", "trabaja"],
    "Greece": ["job", "career", "vacancy", "position", "douleia", "theseis", "karriera", "εργασία", "θέσεις", "δουλειά"]
}

def clean_text_content(text):
    if not text:
        return ""
    cleaned = re.sub(r"(?i)we use cookies.*?(accept|agree|decline|settings)", "", text)
    cleaned = re.sub(r"(?i)privacy policy.*?(rights reserved|cookies)", "", cleaned)
    return re.sub(r'\s+', ' ', cleaned).strip()

def extract_strict_job_details(page, target_url):
    try:
        print(f"-> Opening Target Job URL for Deep Scan: {target_url}")
        page.goto(target_url, timeout=30000, wait_until="domcontentloaded")
        time.sleep(5)  # تسلی سے لوڈ ہونے کا انتظار
        
        html_content = page.content()
        soup = BeautifulSoup(html_content, 'html.parser')
        
        for element in soup(["script", "style", "nav", "footer", "header", "aside", "form", "iframe", "button"]):
            element.decompose()
            
        page_text = soup.get_text(separator=" ")
        page_text = clean_text_content(page_text)

        # کوکیز، پرائیویسی یا فیل ہونے والے پیجز کو سخت انداز میں مسترد کرنا
        if any(term in page_text.lower() for term in ["cookie policy", "privacy policy", "legal notice", "page not found", "error 404", "job expired", "position filled", "sign in to view"]):
            print(f"[WARNING] Page skipped due to generic/cookie filter match on: {target_url}")
            return None

        # لازمی چیک: کیا یہ واقعی جاب پوسٹ ہے؟ اس میں ریکوائرمنٹ یا ڈیوٹیز کے الفاظ ہونے چاہئیں
        job_indicators = ["requirements", "experience", "qualification", "responsibilities", "duties", "salary", "apply", "puesto", "empleo", "vacante"]
        if not any(ind in page_text.lower() for ind in job_indicators):
            print(f"[WARNING] Page does not contain genuine job description indicators: {target_url}")
            return None

        salary = "Not Specified"
        salary_match = re.search(r'(?:salary|pay|wage|compensation|USD|EUR|AED|QAR|SAR|SGD|\$)\s*[:\-]?\s*[\d,]+\s*(?:-|to)?\s*[\d,]*', page_text, re.IGNORECASE)
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

        if len(combined_details.split()) < 40:
            print(f"[WARNING] Insufficient genuine text length extracted from: {target_url}")
            return None

        return {
            "finalUrl": page.url,
            "salary": salary,
            "location": location,
            "email": email,
            "phone": phone,
            "snippet": combined_details[:1800]
        }
    except Exception as e:
        print(f"[ERROR] Extraction Error on URL {target_url}: {e}")
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
    keywords = COUNTRY_KEYWORDS.get(target_country, ["job", "career", "vacancy", "position"])
    
    if not domains:
        print(f"[ERROR] No specific local domains configured for country: {target_country}")
        return

    print(f"-> Today: {today} | Target Country: {target_country} | Local Domains: {domains}")

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

            for target_city in shuffled_cities:
                if posts_found >= required_posts:
                    break

                for target_domain in domains:
                    if posts_found >= required_posts:
                        break

                    print(f"-> Searching Portal: {target_domain} for City: {target_city}")
                    
                    # اب ہم صرف ہوم پیج کے بجائے سرچ یا جاب سیکشن کا یو آر ایل بنائیں گے تاکہ فضول پیج نہ آئیں
                    direct_portal_url = f"https://www.{target_domain}"
                    
                    try:
                        page.goto(direct_portal_url, timeout=35000, wait_until="domcontentloaded")
                        time.sleep(6)  # تسلی سے پیج کو رینڈر ہونے دیں

                        html = page.content()
                        soup = BeautifulSoup(html, 'html.parser')

                        job_link = None
                        job_title = f"{target_country} - {target_city} Job Opening ({current_year})"

                        # ایسے لنکس تلاش کریں جو جابز یا سرچ سے متعلق ہوں اور کوکیز/پرائیویسی نہ ہوں
                        for a in soup.find_all('a', href=True):
                            href = a['href']
                            txt = a.get_text().lower()
                            
                            # کوکیز یا پرائیویسی کے لنکس کو سختی سے اگنور کریں
                            if any(bad in href.lower() or bad in txt for bad in ["cookie", "privacy", "legal", "terms", "login", "register", "faq"]):
                                continue

                            if any(k in href.lower() or k in txt for k in keywords):
                                if href.startswith('/'):
                                    job_link = f"https://www.{target_domain}{href}"
                                elif href.startswith('http'):
                                    job_link = href
                                
                                title_text = a.get_text().strip()
                                if len(title_text) > 12:
                                    job_title = title_text[:100]
                                    break
                        
                        if not job_link:
                            for a in soup.find_all('a', href=True):
                                href = a['href']
                                if target_domain in href and not any(bad in href.lower() for bad in ["cookie", "privacy", "terms", "login"]):
                                    if len(href) > len(f"https://www.{target_domain}") + 5:
                                        job_link = href if href.startswith('http') else f"https://www.{target_domain}{href}"
                                        break

                        if job_link:
                            print(f"-> Found Candidate Job Link: {job_link}")
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
                                    'query_used': f"Deep search on {target_domain} for {target_city}",
                                    'status': 'pending',
                                    'audit_status': None
                                }

                                try:
                                    supabase.table("zunex").insert(insert_data).execute()
                                    print(f">>> [SUCCESS] Genuine verified job post inserted for {target_country} ({target_city})!")
                                    posts_found += 1
                                    time.sleep(5)
                                except Exception as db_err:
                                    print(f"[ERROR] Supabase Insertion Failed: {db_err}")
                            else:
                                print(f"[INFO] Link rejected due to lack of genuine job content. Searching further...")
                        else:
                            print(f"[INFO] No valid job link matched on portal {target_domain}.")

                    except Exception as inner_e:
                        print(f"[ERROR] Iteration Exception in City [{target_city}] with Domain [{target_domain}]: {inner_e}")
                        continue

            browser.close()
    except Exception as e:
        print(f"[CRITICAL ERROR] Crawler Execution Exception: {e}")

if __name__ == "__main__":
    run_independent_crawler()
