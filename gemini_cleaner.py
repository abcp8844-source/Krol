import json
import os
import time
from datetime import datetime, timezone
from google import genai
from google.genai import types
from supabase import create_client

supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
supabase = create_client(supabase_url, supabase_key) if supabase_url and supabase_key else None

raw_api_key = os.environ.get("GEMINI_API_KEY")
gemini_api_key = raw_api_key.strip() if raw_api_key else None
gemini_client = genai.Client(api_key=gemini_api_key) if gemini_api_key else None

def clean_and_translate_content(old_title, old_snippet):
    prompt = f"""
    You are an elite data cleaner, meticulous quality gatekeeper, and professional translator for international Job, Visa, and Travel portals.
    
    Current Title: {old_title}
    Current Snippet: {old_snippet}

    STRICT EVALUATION & OPERATIONAL RULES:
    1. Do not do any unnecessary rewriting or fabrication. Surgically remove clutter, ads, irrelevant news, cookie notices, privacy policies, terms of use, login banners, political commentaries, or unrelated war/trade stories.
    2. Check strictly for essential, actionable information and Call-to-Action (CTA) details:
       - For JOBS: Must contain clear job vacancies, requirements, roles, salaries, location, and how to apply or contact. Reject general employment news or articles lacking actionable job details.
       - For VISAS: Must contain official visa application steps, work permit requirements, or legal procedures. Reject opinion blogs.
       - For TRAVEL: Must contain tour packages, holiday deals, hotel/flight booking details, or itineraries. Reject general travel stories.
    3. If the post completely lacks actionable details, important requirements, or is purely junk/news/banners, return null for both title and snippet.
    4. If the post contains valid core info mixed with noise, strip out the noise precisely while keeping the original core facts intact. Translate and professionalize both the title and snippet into fluent English without changing their meaning or adding made-up details.

    OUTPUT FORMAT: Return strictly a valid JSON object with two keys: "title" and "snippet". If the post is useless or lacks actionable details, return {{"title": null, "snippet": null}}.
    """

    models_to_try = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]

    for model_name in models_to_try:
        try:
            response = gemini_client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.0,
                ),
            )
            if response and response.text:
                data = json.loads(response.text.strip())
                return data.get("title"), data.get("snippet")
        except Exception as e:
            print(f"[WARNING] Model {model_name} failed: {str(e)}. Trying fallback...")
            continue

    return "API_ERROR", "API_ERROR"

def run_cleaner():
    if not supabase or not gemini_client:
        print("[CRITICAL ERROR] Supabase client or Gemini client is not initialized. Check environment variables.")
        return

    print("[INFO] Starting zunex cleaner & translator batch...")

    try:
        res = (
            supabase.table("zunex")
            .select("id, title, snippet, status, audit_status")
            .eq("status", "pending")
            .is_("audit_status", "null")
            .limit(10)
            .execute()
        )
        posts = res.data if res else []
    except Exception as e:
        print(f"[DATABASE ERROR] Failed to fetch posts from zunex table: {str(e)}")
        return

    if not posts:
        print("[INFO] No pending posts found with null audit_status in zunex. Exiting.")
        return

    print(f"[INFO] Found {len(posts)} posts to process in zunex.")
    processed_count = 0

    for post in posts:
        post_id = post.get("id")
        old_title = post.get("title", "")
        old_snippet = post.get("snippet", "")
        current_timestamp = datetime.now(timezone.utc).isoformat()

        print(f"\n----------------------------------------")
        print(f"[INFO] Processing Zunex Post ID: {post_id}")
        print(f"[OLD TITLE]: {old_title}")

        if not old_snippet:
            try:
                update_payload = {
                    "snippet": None,
                    "status": "success",
                    "audit_status": "success",
                    "updated_at": current_timestamp
                }
                supabase.table("zunex").update(update_payload).eq("id", post_id).execute()
                print(f"[RESULT] Snippet was empty. Main status & audit_status set to success.")
            except Exception as db_err:
                print(f"[DB ERROR] Failed to update empty Post ID {post_id}: {str(db_err)}")
            
            processed_count += 1
            continue

        new_title, new_snippet = clean_and_translate_content(old_title, old_snippet)

        if new_title == "API_ERROR" or new_snippet == "API_ERROR":
            print(f"[WARNING] API error or quota exceeded for Post ID {post_id}. Skipping this post for now.")
            continue

        if new_snippet is None or str(new_snippet).strip() == "" or new_title is None or str(new_title).strip() == "":
            try:
                update_payload = {
                    "snippet": None,
                    "status": "success",
                    "audit_status": "success",
                    "updated_at": current_timestamp
                }
                supabase.table("zunex").update(update_payload).eq("id", post_id).execute()
                print(f"[RESULT] REJECTED! Snippet/Title is useless. Set both status & audit_status to success.")
            except Exception as db_err:
                print(f"[DB ERROR] Failed to update rejected Post ID {post_id}: {str(db_err)}")
        else:
            try:
                update_payload = {
                    "title": new_title,
                    "snippet": new_snippet,
                    "audit_status": "success",
                    "updated_at": current_timestamp
                }
                supabase.table("zunex").update(update_payload).eq("id", post_id).execute()
                print(f"[RESULT] SUCCESS! Cleaned, translated, and audit_status updated to success.")
                print(f"[NEW TITLE]: {new_title}")
            except Exception as db_err:
                print(f"[DB ERROR] Failed to update successful Post ID {post_id}: {str(db_err)}")

        processed_count += 1
        print(f"[INFO] Waiting 8 seconds before moving to the next post...")
        time.sleep(8)

    print(f"\n[INFO] Batch completed. Total posts processed in this run: {processed_count}. Exiting.")

if __name__ == "__main__":
    run_cleaner()
