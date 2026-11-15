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
        category = post.get("category", "Jobs")

        prompt = f"""
        You are an expert human-like inspection system for job, visa, and travel listings. 
        Analyze the following scraped text comprehensively from start to finish.
        
        Evaluate if this contains substantive, legitimate offers with details like company, requirements, and application procedures. 
        Discard cookies policies, generic site banners, login pages, ads, or incomplete/vague snippets.
        
        If valid, extract and return a JSON object with:
        - "is_valid": true/false
        - "title": string
        - "category": string (mandatory, e.g., Jobs, Visa, Travel)
        - "country": string (mandatory)
        - "city": string (optional, or "Not Specified")
        - "salary": string
        - "email": string
        - "phone": string
        - "snippet": a comprehensive summary including requirements and direct call to action for applying.

        Scraped Text:
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
