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

def clean_snippet_with_gemini(old_title, old_snippet):
    prompt = f"""
    You are an elite data cleaner, quality gatekeeper, and professional translator for Job, Visa, and Travel portals.
    
    Current Title: {old_title}
    Current Snippet: {old_snippet}

    STRICT OPERATIONAL RULES:
    1. If the content is a general newspaper article, news report, political commentary, irrelevant war story, trade war report, economic overview, fabricated story, or non-informative text without direct, actionable job vacancies, official visa application guides, or travel/tour booking details, return `null` for the snippet.
    2. If it is pure cookie notices, privacy policies, terms of use, login pages, banners, or unidentifiable gibberish, return `null`.
    3. If the post contains valid job, travel, or visa-related information mixed with extraneous elements, surgically remove all clutter.
    4. Translate all remaining valid informative content into pure, fluent, professional English and present it clearly. Never leave foreign text in the output.
    5. Keep core details intact: job descriptions, responsibilities, requirements, salaries, contact emails/phones, application links, official visa requirements, and travel itineraries. Never invent fake data.

    OUTPUT FORMAT: Return strictly a valid JSON object with a single key: "snippet". If the post is useless, a newspaper article, or an irrelevant story, return {{"snippet": null}}.
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
                return data.get("snippet")
        except Exception as e:
            continue

    return "API_ERROR"

def run_cleaner():
    if not supabase or not gemini_client:
        return

    try:
        res = (
            supabase.table("zunex")
            .select("id, title, snippet, status")
            .eq("status", "pending")
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
                "updated_at": current_timestamp
            }
            supabase.table("zunex").update(update_payload).eq("id", post_id).execute()
            continue

        new_snippet = clean_snippet_with_gemini(old_title, old_snippet)

        if new_snippet == "API_ERROR":
            continue

        if new_snippet is None or str(new_snippet).strip() == "":
            update_payload = {
                "snippet": None,
                "status": "success",
                "updated_at": current_timestamp
            }
            supabase.table("zunex").update(update_payload).eq("id", post_id).execute()
        else:
            update_payload = {
                "snippet": new_snippet,
                "status": "success",
                "updated_at": current_timestamp
            }
            supabase.table("zunex").update(update_payload).eq("id", post_id).execute()

        time.sleep(5)

if __name__ == "__main__":
    run_cleaner()
