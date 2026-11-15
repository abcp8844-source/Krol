import os
import json
import logging
from google import genai
from google.genai import types
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
    logging.info("Starting Gemini Cleaner: processing 'zunex' table in-place using gemini-3.5-flash-lite...")
    
    try:
        response = supabase.table("zunex").select("*").eq("status", "pending").execute()
        posts = response.data
    except Exception as e:
        logging.error(f"Database error while fetching pending posts from 'zunex': {e}")
        return

    if not posts:
        logging.info("No pending posts found in 'zunex' table.")
        return

    logging.info(f"Found {len(posts)} pending posts to inspect and process.")

    success_count = 0
    rejected_count = 0
    error_count = 0

    for post in posts:
        post_id = post.get("id")
        url = post.get("finalUrl", "Unknown URL")
        raw_text = post.get("snippet", "")
        
        logging.info(f"Processing post ID: {post_id} | URL: {url}")

        if not raw_text:
            logging.warning(f"Post ID {post_id} has empty snippet. Marking as 'rejected'.")
            try:
                supabase.table("zunex").update({"status": "rejected"}).eq("id", post_id).execute()
            except Exception as db_err:
                logging.error(f"Failed to update empty post ID {post_id}: {db_err}")
            error_count += 1
            continue

        prompt = f"""
        You are a strict data cleaner, translator, and structured extractor. Your task is to process the raw scraped text below.

        CRITICAL RULES - NO REWRITING OR HALLUCINATION:
        1. Do NOT invent, rewrite, or add any information from your own imagination. 
        2. Strictly use ONLY the facts, details, numbers, and text present in the source snippet below. 
        3. Translate the existing content accurately into professional, clean ENGLISH. 
        4. Remove only site navigation noise, repeated menu fragments, cookie notices, or ads, but preserve all original job/visa/travel details faithfully.

        The system handles THREE categories: "Jobs", "Visa", and "Travel". Determine the correct category based strictly on the text.

        If the text contains multiple distinct listings, extract each one separately into the "listings" array. If the text is completely vague or junk, set "is_valid": false.

        Return a JSON object strictly with these keys:
        - "is_valid": true or false
        - "listings": array of objects (if valid), where each object contains:
            - "title": string (Translated title from the text)
            - "category": string (Strictly "Jobs", "Visa", or "Travel")
            - "country": string (Target country found in text, in English)
            - "city": string (Target city if available, otherwise "Not Specified")
            - "salary": string (Salary/fee details if available, otherwise "Not Specified")
            - "email": string (Contact email if found, otherwise empty string)
            - "phone": string (Contact phone if found, otherwise empty string)
            - "snippet": string (Cleaned, strictly faithful English translation of the original text details without any added fluff)

        Raw Scraped Text to Clean and Translate:
        {raw_text}
        """

        try:
            gemini_response = client.models.generate_content(
                model='gemini-3.5-flash-lite',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response
