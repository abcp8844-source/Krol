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
    except Exception as e:
        print(f"[DB-CHECK-ERROR] {e}")
        return False

def search_and_generate_job_via_gemini(country, city, query_template, year):
    formatted_query = query_template.format(city=city, c=country, y=year)
    prompt = f"Search and find the single best, latest real-time job in {city}, {country} using this query: '{formatted_query}'. Rules: 1. Provide the direct job application URL (never a root homepage). 2. Extract comprehensive details (role description, salary, contact email/phone, company name, requirements) to form a clean snippet of at least 400 words. 3. Return ONLY a valid JSON with keys: 'found' (true/false), 'title', 'link', 'snippet'."

    models_to_try = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
    
    for model_name in models_to_try:
        try:
            print(f"[MODEL] Trying {model_name} for {city}, {country}...")
            response = gemini_client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    response_mime_type="application/json",
                    temperature=0.0,
                ),
            )
            if response and response.text:
                raw_text = response.text.strip()
                if raw_text.startswith("```"):
                    raw_text = raw_text.split("```")[1]
                    if raw_text.startswith("json"):
                        raw_text = raw_text[4:].strip()
                
                data = json.loads(raw_text)
                
                grounded_url = None
                try:
                    chunks = response.candidates[0].grounding_metadata.grounding_chunks
                    if chunks:
                        for ch in chunks:
                            if ch.web and ch.web.uri and len(ch.web.uri) > 25:
                                grounded_url = ch.web.uri
                                break
                except Exception:
                    pass

                final_link = data.get("link") or grounded_url
                if data.get("found") and final_link and data.get("title") and data.get("snippet"):
                    data["link"] = final_link
                    print(f"[SUCCESS] Valid job found via {model_name}!")
                    return data
            else:
                print(f"[WARNING] Empty response from {model_name}")
        except Exception as e:
            err_str = str(e)
            print(f"[ERROR] Model {model_name} failed: {err_str}")
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                print(f"[QUOTA] Rate limit hit. Sleeping 10s before fallback...")
                time.sleep(10)
            continue
            
    return None

def run_search():
    if not supabase or not gemini_client:
        print("[CRITICAL] Supabase or Gemini client missing.")
        return

    today = datetime.now().strftime("%A")
    current_year = datetime.now().year
    countries = SCHEDULE.get(today, [])

    if not countries:
        print(f"[INFO] No countries scheduled for {today}.")
        return

    print(f"\n==========================================")
    print(f"=== ZUNEX SEARCH STARTED | {today} | {current_year} ===")
    print(f"=== Countries: {countries} ===")
    print(f"==========================================")

    for country in countries:
        cities = COUNTRY_CITIES.get(country, [country])
        random.shuffle(cities)
        
        country_secured = False
        attempts = 0
        
        shuffled_queries = list(QUERIES)
        random.shuffle(shuffled_queries)
        
        print(f"\n--- Processing Country: {country} ---")
        for query_template in shuffled_queries:
            if country_secured or attempts >= 2:
                break
                
            attempts += 1
            selected_city = random.choice(cities)
            
            print(f"Attempt {attempts} | City: {selected_city}")
            job_data = search_and_generate_job_via_gemini(country, selected_city, query_template, current_year)
            
            if job_data:
                link = job_data.get("link")
                title = job_data.get("title")
                snippet = job_data.get("snippet")
                
                if is_already_scraped(link):
                    print(f"[SKIP] Link already exists in DB: {link}")
                    continue
                
                current_timestamp = datetime.now(timezone.utc).isoformat()
                
                insert_data = {
                    "title": title,
                    "snippet": snippet,
                    "link": link,
                    "country": f"{country} ({selected_city})",
                    "category": "Jobs",
                    "query_used": query_template.format(city=selected_city, c=country, y=current_year),
                    "status": "pending",
                    "audit_status": None,
                    "created_at": current_timestamp
                }
                
                try:
                    supabase.table("zunex").insert(insert_data).execute()
                    print(f"[SAVED] Job successfully inserted into Supabase for {country} ({selected_city})")
                    country_secured = True
                except Exception as db_err:
                    print(f"[DB-ERROR] Failed to insert: {db_err}")
            else:
                print(f"[INFO] No valid job returned for this attempt.")
            
            if not country_secured:
                print(f"Waiting 15 seconds before next query...")
                time.sleep(15)

        print(f"Finished {country}. Taking a strict 1-minute break before next country...")
        time.sleep(60)

    print(f"\n==========================================")
    print(f"=== ZUNEX SEARCH COMPLETED SUCCESSFULLY ===")
    print(f"==========================================")

if __name__ == "__main__":
    run_search()
