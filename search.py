import json
import os
import random
import time
from datetime import datetime, timezone
from google import genai
from google.genai import types
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
gemini_client = genai.Client(api_key=GEMINI_API_KEY.strip()) if GEMINI_API_KEY else None

SCHEDULE = {
    "Monday": ["UAE", "Saudi Arabia", "Qatar", "Bahrain", "Kuwait", "Oman"],
    "Tuesday": ["Japan", "South Korea", "China", "Taiwan", "Singapore", "Hong Kong"],
    "Wednesday": ["Thailand", "Vietnam", "Malaysia", "Indonesia", "Philippines", "Singapore"],
    "Thursday": ["Germany", "France", "Netherlands", "Belgium", "Switzerland", "Austria"],
    "Friday": ["UK", "Ireland", "Sweden", "Norway", "Denmark", "Finland"],
    "Saturday": ["Canada", "USA", "Mexico", "Panama", "Brazil", "Argentina"],
    "Sunday": ["Italy", "Turkey", "Azerbaijan", "Georgia", "Spain", "Greece"],
}

COUNTRY_CITIES = {
    "UAE": ["Dubai", "Abu Dhabi", "Sharjah", "Ajman", "Al Ain", "Ras Al Khaimah"],
    "Saudi Arabia": ["Riyadh", "Jeddah", "Mecca", "Medina", "Dammam", "Khobar"],
    "Qatar": ["Doha", "Al Rayyan", "Al Wakrah", "Al Khor"],
    "Bahrain": ["Manama", "Muharraq", "Riffa", "Hamad Town"],
    "Kuwait": ["Kuwait City", "Hawalli", "Salmiya", "Farwaniya"],
    "Oman": ["Muscat", "Salalah", "Sohar", "Nizwa"],
    "Japan": ["Tokyo", "Osaka", "Kyoto", "Yokohama", "Nagoya"],
    "South Korea": ["Seoul", "Busan", "Incheon", "Daegu"],
    "China": ["Shanghai", "Beijing", "Shenzhen", "Guangzhou", "Chengdu"],
    "Taiwan": ["Taipei", "Kaohsiung", "Taichung", "Tainan"],
    "Singapore": ["Singapore", "Woodlands", "Jurong", "Tampines"],
    "Hong Kong": ["Hong Kong", "Kowloon", "Sha Tin", "Tuen Mun"],
    "Thailand": ["Bangkok", "Phuket", "Chiang Mai", "Pattaya", "Hat Yai"],
    "Vietnam": ["Ho Chi Minh City", "Hanoi", "Da Nang", "Hai Phong"],
    "Malaysia": ["Kuala Lumpur", "Penang", "Johor Bahru", "Ipoh"],
    "Indonesia": ["Jakarta", "Surabaya", "Bandung", "Medan", "Bali"],
    "Philippines": ["Manila", "Cebu City", "Davao", "Quezon City"],
    "Germany": ["Berlin", "Munich", "Frankfurt", "Hamburg", "Cologne"],
    "France": ["Paris", "Lyon", "Marseille", "Toulouse", "Nice"],
    "Netherlands": ["Amsterdam", "Rotterdam", "The Hague", "Utrecht"],
    "Belgium": ["Brussels", "Antwerp", "Ghent", "Bruges"],
    "Switzerland": ["Zurich", "Geneva", "Basel", "Lausanne"],
    "Austria": ["Vienna", "Salzburg", "Graz", "Linz"],
    "UK": ["London", "Manchester", "Birmingham", "Edinburgh", "Glasgow"],
    "Ireland": ["Dublin", "Cork", "Galway", "Limerick"],
    "Sweden": ["Stockholm", "Gothenburg", "Malmo", "Uppsala"],
    "Norway": ["Oslo", "Bergen", "Trondheim", "Stavanger"],
    "Denmark": ["Copenhagen", "Aarhus", "Odense", "Aalborg"],
    "Finland": ["Helsinki", "Espoo", "Tampere", "Vantaa"],
    "Canada": ["Toronto", "Vancouver", "Montreal", "Calgary"],
    "USA": ["New York", "Los Angeles", "Chicago", "Houston", "Miami", "San Francisco"],
    "Mexico": ["Mexico City", "Guadalajara", "Monterrey", "Puebla"],
    "Panama": ["Panama City", "Colon", "David"],
    "Brazil": ["São Paulo", "Rio de Janeiro", "Brasília", "Salvador"],
    "Argentina": ["Buenos Aires", "Córdoba", "Rosario", "Mendoza"],
    "Italy": ["Rome", "Milan", "Naples", "Turin", "Florence"],
    "Turkey": ["Istanbul", "Ankara", "Izmir", "Bursa"],
    "Azerbaijan": ["Baku", "Ganja", "Sumqayit"],
    "Georgia": ["Tbilisi", "Batumi", "Kutaisi"],
    "Spain": ["Madrid", "Barcelona", "Valencia", "Seville"],
    "Greece": ["Athens", "Thessaloniki", "Patras"],
}

QUERIES = [
    "online job vacancy {city} {c} {y} apply link",
    "latest job {city} {c} {y} apply now",
    "urgent employer hiring job {city} {c} {y} apply",
    "employment position requirements {city} {c} {y} apply online",
    "latest job openings {city} {c} {y} apply now",
    "hiring now staff vacancy {city} {c} {y} apply",
    "direct online application form job {city} {c} {y} apply",
    "opening career position {city} {c} {y} apply",
    "job and hotels {city} {c} {y} apply",
    "opening restaurant {city} {c} {y} apply",
    "opening company job {city} {c} {y} apply",
    "job visa sponsors {city} {c} {y} apply",
    "opening government job {city} {c} {y} apply",
    "job in {city} {c} {y} apply",
]

def is_already_scraped(url):
    if not supabase or not url:
        return False
    try:
        res = supabase.table("zunex").select("id").eq("link", url).execute()
        return len(res.data) > 0
    except Exception:
        return False

def search_and_generate_job_via_gemini(country, city, query_template, year):
    formatted_query = query_template.format(city=city, c=country, y=year)
    
    prompt = f"""
    You are an elite, highly precise automated global job hunter and researcher. 
    Target Country: {country}
    Target City: {city}
    Search Query to execute via live Google Search Grounding: "{formatted_query}"

    STRICT INSTRUCTIONS:
    1. Use Google Search Grounding to execute the exact search query and find the absolute top, best, latest, and most authentic real-time job opening specifically located in {city}, {country}.
    2. Extract the DIRECT online application link or authoritative job page link. DO NOT provide root homepages, generic search result pages, or blocked sites. The link must point directly to the specific job listing page.
    3. COMPREHENSIVE SNIPPET REQUIREMENT: The snippet must be detailed and rich, containing at least 300 to 400 words (or maximum available authentic facts). Include complete job description, requirements, responsibilities, exact company name, salary range (if available), exact location/city, and contact email/phone numbers if found on that page.
    4. ZERO FABRICATION: Do not invent or make up any data. Only report real facts fetched directly from the search results. If the text is in a local language, translate and present it cleanly while keeping all core facts intact.
    5. Return your findings STRICTLY as a valid JSON object with these exact keys:
       - "found": true or false
       - "title": Clean, professional job title including company and city
       - "link": Direct application URL found during search
       - "snippet": Rich, comprehensive text of at least 400 words equivalent detailing the job description, requirements, salary, location, contact, and direct apply instructions.
    """

    models_to_try = ["gemini-2.5-flash", "gemini-2.5-pro"]
    
    for model_name in models_to_try:
        try:
            response = gemini_client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
            if response and response.text:
                data = json.loads(response.text.strip())
                if data.get("found") and data.get("link") and data.get("title") and data.get("snippet"):
                    return data
        except Exception as e:
            print(f"[WARNING] Gemini model {model_name} search failed: {str(e)}")
            continue
            
    return None

def run_gemini_grounded_crawler():
    if not supabase or not gemini_client:
        print("[CRITICAL ERROR] Supabase or Gemini client not initialized. Check environment variables.")
        return

    today = datetime.now().strftime("%A")
    current_year = datetime.now().year
    countries = SCHEDULE.get(today, [])

    if not countries:
        print(f"[INFO] No countries scheduled for today ({today}).")
        return

    print(f"\n==================================================")
    print(f"=== GEMINI GROUNDED HUNTER INITIATED | Day: {today} | Year: {current_year} ===")
    print(f"=== Scheduled Countries: {countries} ===")
    print(f"==================================================")

    for country in countries:
        cities = COUNTRY_CITIES.get(country, [country])
        random.shuffle(cities)
        
        country_secured = False
        attempts = 0
        
        while not country_secured and attempts < 3:
            attempts += 1
            selected_city = random.choice(cities)
            selected_query_template = random.choice(QUERIES)
            
            print(f"\n[COUNTRY: {country}] Attempt {attempts} | City: {selected_city}")
            print(f"[QUERY] Running Gemini grounded search...")

            job_data = search_and_generate_job_via_gemini(country, selected_city, selected_query_template, current_year)
            
            if job_data:
                link = job_data.get("link")
                title = job_data.get("title")
                snippet = job_data.get("snippet")
                
                if is_already_scraped(link):
                    print(f"[DB-SKIP] Link already exists in database: {link}")
                    continue
                
                current_timestamp = datetime.now(timezone.utc).isoformat()
                
                insert_data = {
                    "title": title,
                    "snippet": snippet,
                    "link": link,
                    "country": f"{country} ({selected_city})",
                    "category": "Jobs",
                    "query_used": selected_query_template.format(city=selected_city, c=country, y=current_year),
                    "status": "pending",
                    "audit_status": None,
                    "created_at": current_timestamp
                }
                
                try:
                    supabase.table("zunex").insert(insert_data).execute()
                    print(f"[SUCCESS] TOP JOB SECURED & INSERTED for {country} ({selected_city})!")
                    print(f"   - Title: {title}")
                    print(f"   - Link: {link}")
                    country_secured = True
                except Exception as db_err:
                    print(f"[DB-ERROR] Failed to insert job into Supabase: {str(db_err)}")
            else:
                print(f"[INFO] No valid job found for {country} in this attempt. Retrying...")
            
            if not country_secured:
                print(f"[INFO] Waiting 5 seconds before next attempt...")
                time.sleep(5)

        print(f"\n[PAUSE] Country transition break: Sleeping for 10 seconds before moving to next country...")
        time.sleep(10)

    print(f"\n==================================================")
    print(f"=== GEMINI GROUNDED HUNTER RUN COMPLETED SUCCESSFULLY ===")
    print(f"==================================================")

if __name__ == "__main__":
    run_gemini_grounded_crawler()
