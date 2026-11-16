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
        except Exception:
            continue

    return "API_ERROR", "API_ERROR"

def run_cleaner():
    if not supabase or not gemini_client:
        return

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
    except Exception:
        return

    if not posts:
        return

    for post in posts:
        post_id = post.get("id")
        old_title = post.get("title", "")
        old_snippet = post.get("snippet", "")
        current_timestamp = datetime.now(timezone.utc).isoformat()

        if not old_snippet:
            update_payload = {
                "snippet": None,
                "status": "success",
                "audit_status": "success",
                "updated_at": current_timestamp
            }
            supabase.table("zunex").update(update_payload).eq("id", post_id).execute()
            continue

        new_title, new_snippet = clean_and_translate_content(old_title, old_snippet)

        if new_title == "API_ERROR" or new_snippet == "API_ERROR":
            continue

        if new_snippet is None or str(new_snippet).strip() == "":
            update_payload = {
                "snippet": None,
                "status": "success",
                "audit_status": "success",
                "updated_at": current_timestamp
            }
            supabase.table("zunex").update(update_payload).eq("id", post_id).execute()
        else:
            update_payload = {
                "title": new_title if new_title else old_title,
                "snippet": new_snippet,
                "audit_status": "success",
                "updated_at": current_timestamp
            }
            supabase.table("zunex").update(update_payload).eq("id", post_id).execute()

        time.sleep(10)

if __name__ == "__main__":
    run_cleaner()
