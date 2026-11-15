import os
import json
import logging
from google import genai
from supabase import create_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not SUPABASE_URL or not SUPABASE_KEY or not GEMINI_API_KEY:
    logging.error("Missing environment variables: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, or GEMINI_API_KEY.")
    exit(1)

try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    client = genai.Client(api_key=GEMINI_API_KEY)
except Exception as e:
    logging.critical(f"Failed to initialize Supabase or Gemini clients: {e}")
    exit(1)

def process_raw_posts():
    logging.info("Starting Gemini Cleaner job inspection from 'zunex' to 'raw_jobs'...")
    
    try:
        # Source table is 'zunex'
        response = supabase.table("zunex").select("*").eq("status", "pending_inspection").execute()
        posts = response.data
    except Exception as e:
        logging.error(f"Database error while fetching pending posts from 'zunex': {e}")
        return

    if not posts:
        logging.info("No pending inspection posts found in 'zunex' table.")
        return

    logging.info(f"Found {len(posts)} posts to inspect.")

    success_count = 0
    rejected_count = 0
    error_count = 0

    for post in posts:
        post_id = post.get("id")
        url = post.get("finalUrl", "Unknown URL")
        raw_text = post.get("snippet", "")
        
        logging.info(f"Processing post ID: {post_id} | URL: {url}")

        if not raw_text:
            logging.warning(f"Post ID {post_id} has empty snippet. Purging from 'zunex'.")
            try:
                supabase.table("zunex").delete().eq("id", post_id).execute()
            except Exception as db_err:
                logging.error(f"Failed to delete empty post ID {post_id}: {db_err}")
            error_count += 1
            continue

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
            gemini_response = client.models.generate_content(
                model='gemini-3.1-flash',
                contents=prompt,
                config={
                    "response_mime_type": "application/json"
                }
            )
            
            result = json.loads(gemini_response.text)

            is_valid = result.get("is_valid")
            country = result.get("country")
            category = result.get("category")

            if is_valid and country and category:
                cleaned_data = {
                    "title": result.get("title"),
                    "category": category,
                    "country": country,
                    "city": result.get("city", "Not Specified"),
                    "salary": result.get("salary", "Not Specified"),
                    "email": result.get("email", ""),
                    "phone": result.get("phone", ""),
                    "snippet": result.get("snippet"),
                    "finalUrl": url,
                    "status": "pending"
                }
                
                try:
                    # Destination table is 'raw_jobs'
                    supabase.table("raw_jobs").insert(cleaned_data).execute()
                    logging.info(f"SUCCESS: Valid post inserted into 'raw_jobs' | Title: {result.get('title')} | Country: {country} | Category: {category}")
                    success_count += 1
                except Exception as db_ins_err:
                    logging.error(f"DATABASE ERROR inserting post ID {post_id} into 'raw_jobs': {db_ins_err}")
                    error_count += 1
            else:
                logging.info(f"REJECTED: Post ID {post_id} marked invalid or missing mandatory fields by Gemini. Response: {result}")
                rejected_count += 1

            try:
                # Cleanup from source 'zunex' table
                supabase.table("zunex").delete().eq("id", post_id).execute()
                logging.info(f"CLEANUP: Post ID {post_id} successfully deleted from 'zunex' table.")
            except Exception as db_del_err:
                logging.error(f"DATABASE ERROR deleting post ID {post_id} from 'zunex': {db_del_err}")

        except json.JSONDecodeError as json_err:
            logging.error(f"JSON PARSE ERROR for post ID {post_id} ({url}): {json_err}. Gemini output was not valid JSON.")
            error_count += 1
            try:
                supabase.table("zunex").delete().eq("id", post_id).execute()
                logging.info(f"CLEANUP: Malformed post ID {post_id} purged from 'zunex' after parse error.")
            except Exception:
                pass
        except Exception as e:
            logging.error(f"CRITICAL ERROR processing post ID {post_id} ({url}): {e}")
            error_count += 1

    logging.info(f"Execution Summary -> Total Processed: {len(posts)} | Successful: {success_count} | Rejected: {rejected_count} | Errors: {error_count}")

if __name__ == "__main__":
    process_raw_posts()
