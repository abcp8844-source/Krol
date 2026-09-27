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
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"Supabase Connection Error: {e}")
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
    "UAE": ["Dubai", "Abu Dhabi", "Sharjah", "Ajman", "Al Ain", "Ras Al Khaimah", "Fujairah", "Umm Al Quwain"],
    "Saudi Arabia": ["Riyadh", "Jeddah", "Mecca", "Medina", "Dammam", "Khobar", "Tabuk", "Abha", "Jubail", "Taif"],
    "Qatar": ["Doha", "Al Rayyan", "Al Wakrah", "Al Khor", "Umm Salal", "Mesaieed"],
    "Bahrain": ["Manama", "Muharraq", "Riffa", "Hamad Town", "Aali", "Sitra"],
    "Kuwait": ["Kuwait City", "Hawalli", "Salmiya", "Farwaniya", "Jahra", "Ahmadi"],
    "Oman": ["Muscat", "Salalah", "Sohar", "Nizwa", "Sur", "Barka"],
    "Japan": ["Tokyo", "Osaka", "Kyoto", "Yokohama", "Nagoya", "Fukuoka", "Sapporo", "Kobe", "Kawasaki", "Hiroshima"],
    "South Korea": ["Seoul", "Busan", "Incheon", "Daegu", "Daejeon", "Gwangju", "Suwon", "Ulsan"],
    "China": ["Shanghai", "Beijing", "Shenzhen", "Guangzhou", "Chengdu", "Hangzhou", "Wuhan", "Xi'an", "Nanjing", "Chongqing"],
    "Taiwan": ["Taipei", "Kaohsiung", "Taichung", "Tainan", "Hsinchu", "Keelung", "Pingtung"],
    "Singapore": ["Singapore"],
    "Hong Kong": ["Hong Kong", "Kowloon", "Sha Tin", "Tuen Mun", "Tsuen Wan"],
    "Thailand": ["Bangkok", "Phuket", "Chiang Mai", "Pattaya", "Hat Yai", "Nonthaburi", "Udon Thani"],
    "Vietnam": ["Ho Chi Minh City", "Hanoi", "Da Nang", "Hai Phong", "Nha Trang", "Can Tho", "Bien Hoa"],
    "Malaysia": ["Kuala Lumpur", "Penang", "Johor Bahru", "Ipoh", "Malacca", "Kota Kinabalu", "Shah Alam", "Petaling Jaya"],
    "Indonesia": ["Jakarta", "Surabaya", "Bandung", "Medan", "Bali", "Semarang", "Palembang", "Makassar"],
    "Philippines": ["Manila", "Cebu City", "Davao", "Quezon City", "Makati", "Taguig", "Pasig", "Cagayan de Oro"],
    "Germany": ["Berlin", "Munich", "Frankfurt", "Hamburg", "Cologne", "Stuttgart", "Dusseldorf", "Dortmund", "Essen", "Leipzig"],
    "France": ["Paris", "Lyon", "Marseille", "Toulouse", "Nice", "Nantes", "Strasbourg", "Montpellier", "Bordeaux", "Lille"],
    "Netherlands": ["Amsterdam", "Rotterdam", "The Hague", "Utrecht", "Eindhoven", "Tilburg", "Groningen", "Almere"],
    "Belgium": ["Brussels", "Antwerp", "Ghent", "Bruges", "Liege", "Namur", "Leuven", "Mons"],
    "Switzerland": ["Zurich", "Geneva", "Basel", "Lausanne", "Bern", "Winterthur", "Lucerne", "St. Gallen"],
    "Austria": ["Vienna", "Salzburg", "Graz", "Linz", "Innsbruck", "Klagenfurt", "Villach", "Wels"],
    "UK": ["London", "Manchester", "Birmingham", "Edinburgh", "Glasgow", "Liverpool", "Bristol", "Leeds", "Sheffield", "Cardiff"],
    "Ireland": ["Dublin", "Cork", "Galway", "Limerick", "Waterford", "Drogheda"],
    "Sweden": ["Stockholm", "Gothenburg", "Malmo", "Uppsala", "Vasteras", "Orebro", "Linkoping"],
    "Norway": ["Oslo", "Bergen", "Trondheim", "Stavanger", "Drammen", "Fredrikstad"],
    "Denmark": ["Copenhagen", "Aarhus", "Odense", "Aalborg", "Esbjerg", "Randers"],
    "Finland": ["Helsinki", "Espoo", "Tampere", "Vantaa", "Oulu", "Turku", "Jyvaskyla"],
    "Canada": ["Toronto", "Vancouver", "Montreal", "Calgary", "Edmonton", "Ottawa", "Quebec City", "Winnipeg", "Halifax", "Victoria"],
    "USA": ["New York", "Los Angeles", "Chicago", "Houston", "Miami", "San Francisco", "Seattle", "Boston", "Dallas", "Atlanta", "Denver", "Phoenix", "San Diego"],
    "Mexico": ["Mexico City", "Guadalajara", "Monterrey", "Puebla", "Cancun", "Tijuana", "Leon", "Juarez"],
    "Panama": ["Panama City", "Colon", "David", "Santiago de Veraguas"],
    "Brazil": ["São Paulo", "Rio de Janeiro", "Brasília", "Salvador", "Fortaleza", "Curitiba", "Belo Horizonte", "Manaus", "Recife"],
    "Argentina": ["Buenos Aires", "Córdoba", "Rosario", "Mendoza", "La Plata", "Mar del Plata", "Tucuman"],
    "Italy": ["Rome", "Milan", "Naples", "Turin", "Florence", "Bologna", "Venice", "Palermo", "Genoa", "Bari"],
    "Turkey": ["Istanbul", "Ankara", "Izmir", "Bursa", "Antalya", "Adana", "Konya", "Gaziantep", "Mersin"],
    "Azerbaijan": ["Baku", "Ganja", "Sumqayit", "Shusha", "Mingachevir", "Lankaran"],
    "Georgia": ["Tbilisi", "Batumi", "Kutaisi", "Rustavi", "Zugdidi", "Gori"],
    "Spain": ["Madrid", "Barcelona", "Valencia", "Seville", "Bilbao", "Malaga", "Zaragoza", "Palma", "Alicante"],
    "Greece": ["Athens", "Thessaloniki", "Patras", "Heraklion", "Larissa", "Volos", "Rhodes"]
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
    "Philippines": ["jobstreet.com.ph", "indeed.com.ph"],
    "Germany": ["stepstone.de", "arbeitsagentur.de"],
    "France": ["apec.fr", "welcometothejungle.com"],
    "Netherlands": ["indeed.nl", "nationalevacaturebank.nl"],
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
    "USA": ["indeed.com", "ziprecruiter.com"],
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

def clean_text_content(text):
    if not text:
        return ""
    cleaned = re.sub(r"(?i)we use cookies.*?(accept|agree|decline|settings)", "", text)
    cleaned = re.sub(r"(?i)privacy policy.*?(rights reserved|cookies)", "", cleaned)
    return re.sub(r'\s+', ' ', cleaned).strip()

def extract_strict_job_details(page, target_url):
    try:
        print(f"Checking URL content: {target_url}")
        page.goto(target_url, timeout=25000, wait_until="domcontentloaded")
        time.sleep(3)
        
        html_content = page.content()
        soup = BeautifulSoup(html_content, 'html.parser')
        
        for element in soup(["script", "style", "nav", "footer", "header", "aside", "form", "iframe", "button"]):
            element.decompose()
            
        page_text = soup.get_text(separator=" ")
        page_text = clean_text_content(page_text)

        if any(term in page_text.lower() for term in ["cookie policy", "privacy notice", "page not found", "error 404", "job expired", "position filled"]):
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

        if not email and not phone:
            return None

        paragraphs = []
        for p in soup.find_all(['p', 'div', 'li']):
            txt = p.get_text().strip()
            if len(txt) > 35 and any(k in txt.lower() for k in ["apply", "salary", "requirement", "experience", "qualification", "duty", "responsibility", "benefit", "position"]):
                if txt not in paragraphs:
                    paragraphs.append(txt)

        intro_snippet = " ".join(page_text.split()[:90])
        combined_details = intro_snippet
        if paragraphs:
            combined_details += "\n\nKey Job Description & Requirements:\n" + "\n".join([f"- {pr}" for pr in paragraphs[:5]])

        if len(combined_details.split()) < 40:
            return None

        return {
            "finalUrl": page.url,
            "salary": salary,
            "location": location,
            "email": email,
            "phone": phone,
            "snippet": combined_details[:1200]
        }
    except Exception as e:
        print(f"Extraction Error: {e}")
        return None

def run_independent_crawler():
    if not supabase:
        print("Supabase client is not available.")
        return

    today = datetime.now().strftime("%A")
    current_year = datetime.now().year
    day_countries = SCHEDULE.get(today, [])
    
    if not day_countries:
        print("No countries scheduled for today.")
        return

    target_country = random.choice(day_countries)
    cities = COUNTRY_CITIES.get(target_country, [target_country])
    domains = COUNTRY_DUAL_DOMAINS.get(target_country, ["indeed.com", "linkedin.com"])
    
    print(f"Today: {today} | Target Country: {target_country}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=random.choice(USER_AGENTS))
            page = context.new_page()

            posts_found = 0
            required_posts = 2
            
            shuffled_cities = list(cities)
            random.shuffle(shuffled_cities)

            for target_city in shuffled_cities:
                if posts_found >= required_posts:
                    break

                for target_domain in domains:
                    if posts_found >= required_posts:
                        break

                    print(f"Searching city: {target_city} | Domain: {target_domain}")
                    search_keywords = f"job vacancy hiring {target_city} {target_country} {current_year}"
                    search_url = f"https://www.google.com/search?q=site:{target_domain}+{search_keywords.replace(' ', '+')}&tbs=qdr:w"
                    
                    try:
                        page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
                        time.sleep(3)

                        html = page.content()
                        soup = BeautifulSoup(html, 'html.parser')

                        job_link = None
                        job_title = f"{target_country} - {target_city} Job Opening ({current_year})"

                        for a in soup.find_all('a', href=True):
                            href = a['href']
                            if target_domain in href and "http" in href and "google" not in href:
                                job_link = href
                                title_tag = a.find('h3')
                                if title_tag:
                                    job_title = title_tag.get_text()
                                break

                        if job_link:
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
                                    'query_used': f"site:{target_domain} {search_keywords}",
                                    'status': 'pending',
                                    'created_at': 'now()'
                                }

                                supabase.table("zunex").insert(insert_data).execute()
                                print(f"Successfully inserted job post #{posts_found + 1} for {target_country} ({target_city}) using {target_domain}!")
                                posts_found += 1
                                time.sleep(2)
                    except Exception as inner_e:
                        print(f"Iteration Error: {inner_e}")
                        continue

            browser.close()
    except Exception as e:
        print(f"Crawler Execution Error: {e}")

if __name__ == "__main__":
    run_independent_crawler()
