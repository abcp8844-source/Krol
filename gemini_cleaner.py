import os
import json
from google import genai
from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
client = genai.Client(api_key=GEMINI_API_KEY)

def process_raw_posts():
    response = supabase.table("raw_jobs").select("*").eq("status", "pending_inspection").execute()
    posts = response.data

    if not posts:
        return

    for post in posts:
        raw_text = post.get("snippet", "")
        url = post.get("finalUrl", "")
        original_category = post.get("category", "Jobs")

        prompt = f"""
        You are an expert human-like senior data inspector and quality auditor specializing in global Job listings, Visa application portals, and Travel/Tourism packages. 

        Your task is to thoroughly analyze the scraped text below from start to finish. You must evaluate whether the content represents a genuine, high-quality, and substantive offer rather than generic site navigation, login pages, ads, cookie banners, or vague text.

        The system handles THREE distinct categories: "Jobs", "Visa", and "Travel". Carefully determine and assign the correct category based on the actual content.

        Inspection Guidelines:
        1. STRICT VALIDATION: If the text lacks concrete, actionable information (e.g., missing essential requirements, application steps, or clear subject matter), mark "is_valid": false. Do NOT manufacture or hallucinate details. Do not turn bad text into good text artificially.
        2. RESPECT ORIGINAL DATA: If a post is legitimate and contains solid information, accurately extract what is present. Do not distort factual details.
        3. MANDATORY FIELDS: Valid posts MUST contain a clear title, a definitive category ("Jobs", "Visa", or "Travel"), and a valid country. City and salary are optional/descriptive (use "Not Specified" if absent).
        4. CONTENT EXTRACTION: Provide a clean, comprehensive summary for the snippet that preserves exact instructions, requirements, and direct calls to action (such as application links, official procedures, or contact methods).

        Return a JSON object with the following keys strictly:
        - "is_valid": true or false
        - "title": string (The main title of the posting)
        - "category": string (Must be strictly "Jobs", "Visa", or "Travel")
        - "country": string (Mandatory target country)
        - "city": string (Target city if available, otherwise "Not Specified")
        - "salary": string (Salary/fee/pricing details if applicable, otherwise "Not Specified")
        - "email": string (Contact email if found, otherwise empty string)
        - "phone": string (Contact phone if found, otherwise empty string)
        - "snippet": string (Cleaned, high-quality, comprehensive text outlining full details and application steps)

        Scraped Text to Inspect:
        {raw_text}
        """

        try:
            response = client.models.generate_content(
                model='gemini-3.1-flash',
                contents=prompt,
                config={
                    "response_mime_type": "application/json"
                }
            )
            
            result = json.loads(response.text)

            if result.get("is_valid") and result.get("country") and result.get("category"):
                cleaned_data = {
                    "title": result.get("title"),
                    "category": result.get("category"),
                    "country": result.get("country"),
                    "city": result.get("city", "Not Specified"),
                    "salary": result.get("salary", "Not Specified"),
                    "email": result.get("email", ""),
                    "phone": result.get("phone", ""),
                    "snippet": result.get("snippet"),
                    "finalUrl": url,
                    "status": "pending"
                }
                
                supabase.table("raw_jobs_score").insert(cleaned_data).execute()

            supabase.table("raw_jobs").delete().eq("id", post["id"]).execute()

        except Exception as e:
            print(f"Error processing post {url}: {e}")

if __name__ == "__main__":
    process_raw_posts()
