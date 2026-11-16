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

def evaluate_and_clean_content(old_title, old_snippet, target_country="", target_category="Jobs"):
    prompt = f"""
    You are an elite, highly intelligent data quality gatekeeper and professional translator for international Job, Visa, and Travel portals.
    Do not rely blindly on rigid rules; use your own independent brain, advanced reasoning, and autonomous judgment to thoroughly inspect the provided content.
    
    Target Country: {target_country}
    Target Category: {target_category}
    Current Title: {old_title}
    Current Snippet: {old_snippet}

    AUTONOMOUS COGNITIVE EVALUATION & OPERATIONAL RULES:
    1. **Lenient & Balanced Assessment (60-70% Rule):** If the content has even 60% to 70% useful, substantive, or actionable value regarding the target category and country, DO NOT reject it. Preserve the core details. Aim to keep comprehensive and detailed descriptions rather than aggressively shortening it. 
    2. **Independent Category & Country Verification:** Use your own intelligence to verify if the content genuinely belongs to the target country and category. Look beyond mere keywords; understand the deep context.
    3. **Action Determination ("action"):**
       - Return "reject" ONLY if the post is pure junk, completely empty, or completely devoid of any utility (lacks even 60% useful info). In this case, title and snippet will be null.
       - Return "no_change" if the content is already pristine, perfectly rich, and requires zero cleaning or modification.
       - Return "update" if the content contains valid actionable data mixed with noise, requiring surgical cleaning and professional translation while preserving core facts.
    4. **Zero Fabrication:** Never invent fake data. Only clean, translate, and polish real facts present in the text.

    OUTPUT FORMAT: Return strictly a valid JSON object with three keys:
    - "action": "reject" | "no_change" | "update"
    - "title": cleaned/translated title (or null if rejected / string if no_change)
    - "snippet": cleaned/translated snippet (or null if rejected / string if no_change)
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
                return data.get("action"), data.get("title"), data.get("snippet")
        except Exception as e:
            print(f"[WARNING] Model {model_name} failed: {str(e)}. Trying fallback...")
            continue

    return "API_ERROR", None, None

def run_cleaner():
    if not supabase or not gemini_client:
        print("[CRITICAL ERROR] Supabase client or Gemini client is not initialized. Check environment variables.")
        return

    print("[INFO] Starting intelligent zunex cleaner & translator batch...")

    try:
        res = (
            supabase.table("zunex")
            .select("id, title, snippet, status, audit_status, country, category")
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
        target_country = post.get("country", "")
        target_category = post.get("category", "Jobs")
        current_timestamp = datetime.now(timezone.utc).isoformat()

        print(f"\n----------------------------------------")
        print(f"[INFO] Processing Zunex Post ID: {post_id} | Country: {target_country} | Category: {target_category}")
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

        action, new_title, new_snippet = evaluate_and_clean_content(old_title, old_snippet, target_country, target_category)

        if action == "API_ERROR":
            print(f"[WARNING] API error or quota exceeded for Post ID {post_id}. Skipping this post for now.")
            continue

        try:
            if action == "reject":
                update_payload = {
                    "snippet": None,
                    "status": "success",
                    "audit_status": "success",
                    "updated_at": current_timestamp
                }
                supabase.table("zunex").update(update_payload).eq("id", post_id).execute()
                print(f"[RESULT] REJECTED! Snippet/Title is useless. Set both status & audit_status to success.")

            elif action == "no_change":
                update_payload = {
                    "audit_status": "rejected",
                    "updated_at": current_timestamp
                }
                supabase.table("zunex").update(update_payload).eq("id", post_id).execute()
                print(f"[RESULT] NO CHANGE NEEDED (Already pristine)! Main status untouched, audit_status set to 'rejected'.")

            elif action == "update":
                final_title = new_title.strip() if new_title and str(new_title).strip() else old_title
                update_payload = {
                    "title": final_title,
                    "snippet": new_snippet,
                    "audit_status": "success",
                    "updated_at": current_timestamp
                }
                supabase.table("zunex").update(update_payload).eq("id", post_id).execute()
                print(f"[RESULT] SUCCESS! Cleaned, translated, main status untouched, and audit_status updated to success.")
                print(f"[NEW TITLE]: {final_title}")
            else:
                print(f"[WARNING] Unknown action returned for Post ID {post_id}: {action}")

        except Exception as db_err:
            print(f"[DB ERROR] Failed to update database for Post ID {post_id}: {str(db_err)}")

        processed_count += 1
        print(f"[INFO] Waiting 8 seconds before moving to the next post...")
        time.sleep(8)

    print(f"\n[INFO] Batch completed. Total posts processed in this run: {processed_count}. Exiting.")

if __name__ == "__main__":
    run_cleaner()
