import re
from config import SCHEDULE

try:
    from keywords import KEYWORDS
except ImportError:
    KEYWORDS = {}

try:
    from keywords import COUNTRY_KEYWORDS
except ImportError:
    COUNTRY_KEYWORDS = {}

ALL_COUNTRIES = [c for country_list in SCHEDULE.values() for c in country_list]


def clean_text_content(text):
    if not text:
        return ""
    cleaned = re.sub(r"(?i)we use cookies.*?(accept|agree|decline|settings)", "", text)
    cleaned = re.sub(r"(?i)privacy policy.*?(rights reserved|cookies)", "", cleaned)
    cleaned = re.sub(r"(?i)terms and conditions.*?(copyright|all rights)", "", cleaned)
    cleaned = re.sub(r"(?i)create your jobseeker profile.*?(upload cv|sign up)", "", cleaned)
    cleaned = re.sub(r"(?i)cookie policy.*?(consent|preferences)", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _get_category_keywords(target_country, category):
    combined = []
    if isinstance(KEYWORDS, dict) and category in KEYWORDS:
        combined.extend(KEYWORDS.get(category) or [])
    if isinstance(COUNTRY_KEYWORDS, dict) and target_country in COUNTRY_KEYWORDS:
        country_map = COUNTRY_KEYWORDS.get(target_country) or {}
        combined.extend(country_map.get(category) or [])
    return combined


def _extract_single_page(page, url, target_country, target_city, category, search_keyword):
    page.goto(url, wait_until="domcontentloaded", timeout=25000)
    page.wait_for_timeout(2000)

    current_url_lower = page.url.lower()
    if any(p in current_url_lower for p in ["/login", "/signin", "/register", "/signup", "/auth/"]):
        return None, "auth_wall"

    extracted_data = page.evaluate(
        """() => {
            const unwanted = document.querySelectorAll('script, style, nav, footer, header, aside, form, iframe, button, noscript');
            unwanted.forEach(el => el.remove());

            const pageText = document.body ? document.body.innerText : '';

            const textBlocks = [];
            const elements = document.querySelectorAll('p, div, li, section, article');
            elements.forEach(el => {
                const txt = el.innerText ? el.innerText.trim() : '';
                if (txt.length > 40 && !textBlocks.includes(txt)) {
                    textBlocks.push(txt);
                }
            });

            return {
                pageText: pageText,
                paragraphs: textBlocks
            };
        }"""
    )

    page_text = clean_text_content(extracted_data.get("pageText", ""))
    page_text_lower = page_text.lower()

    is_truly_blocked = len(page_text_lower) < 300 and any(
        b in page_text_lower
        for b in [
            "access denied",
            "additional verification required",
            "ray id:",
            "checking your browser before accessing",
        ]
    )
    if is_truly_blocked:
        return None, "blocked"

    if any(
        j in page_text_lower
        for j in ["this job listing is no longer available", "expired job posting", "job has expired"]
    ):
        return None, "expired"

    country_match = target_country.lower() in page_text_lower if target_country else True
    city_match = target_city.lower() in page_text_lower if target_city else True
    if not country_match and not city_match:
        return None, "location_mismatch"

    for other_country in ALL_COUNTRIES:
        if target_country and other_country.lower() != target_country.lower():
            if other_country.lower() in page_text_lower[:400]:
                return None, "other_country_lead"

    category_keywords = _get_category_keywords(target_country, category)
    if category_keywords and not any(kw.lower() in page_text_lower for kw in category_keywords):
        if not search_keyword or search_keyword.lower() not in page_text_lower:
            return None, "topic_mismatch"

    salary = "Not Specified"
    salary_match = re.search(
        r"(?:salary|pay|wage|compensation|fee|price|USD|EUR|AED|QAR|SAR|SGD|GBP|CAD|AUD|\$|₺|€|£|¥|฿)\s*[:\-]?\s*[\d,]+\s*(?:-|to)?\s*[\d,]*",
        page_text,
        re.IGNORECASE,
    )
    if salary_match:
        sal_text = salary_match.group(0).strip()
        if "0.00" not in sal_text:
            salary = sal_text

    location = target_city or target_country or "Not Specified"
    loc_match = re.search(r"(?:Location|City|Address|Area|Ubicación):\s*([A-Za-z\s,]+)", page_text, re.IGNORECASE)
    if loc_match:
        location = loc_match.group(1).strip()[:50]

    email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", page_text)
    email = email_match.group(0) if email_match else ""

    phone_match = re.search(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{4}\b", page_text)
    phone = phone_match.group(0).strip() if phone_match else ""

    paragraphs = extracted_data.get("paragraphs", [])

    intro_snippet = " ".join(page_text.split()[:450])
    combined_details = intro_snippet
    if paragraphs:
        combined_details += "\n\nDetails:\n" + "\n".join([f"- {pr}" for pr in paragraphs[:40]])

    words = combined_details.split()
    if len(words) < 300:
        return None, "thin_content"

    final_snippet = " ".join(words[:1200])

    meta_lines = []
    if salary != "Not Specified" and salary.lower() not in final_snippet.lower():
        meta_lines.append(f"Salary/Fee: {salary}")
    if location and location.lower() not in final_snippet.lower():
        meta_lines.append(f"Location: {location}")
    if email and email.lower() not in final_snippet.lower():
        meta_lines.append(f"Contact Email: {email}")
    if phone and phone.lower() not in final_snippet.lower():
        meta_lines.append(f"Contact Phone: {phone}")

    if meta_lines:
        final_snippet = final_snippet + "\n\nKey Contact & Details:\n" + "\n".join(meta_lines)

    return (
        {
            "accepted": True,
            "retry_needed": False,
            "reason": "ok",
            "finalUrl": page.url,
            "salary": salary,
            "location": location,
            "email": email,
            "phone": phone,
            "snippet": final_snippet,
        },
        "ok",
    )


def extract_strict_job_details(
    page,
    target_url,
    target_country,
    target_city,
    category="Jobs",
    search_keyword="",
    fallback_urls=None,
):
    candidate_urls = []
    if target_url:
        candidate_urls.append(target_url)
    if fallback_urls:
        for u in fallback_urls:
            if u and u not in candidate_urls:
                candidate_urls.append(u)

    reasons_seen = []

    for url in candidate_urls:
        try:
            result, reason = _extract_single_page(
                page, url, target_country, target_city, category, search_keyword
            )
            if result:
                return result
            reasons_seen.append(f"{url}: {reason}")
        except Exception as exc:
            reasons_seen.append(f"{url}: error({str(exc)[:80]})")
            continue

    return {
        "accepted": False,
        "retry_needed": True,
        "reason": " | ".join(reasons_seen) if reasons_seen else "no_valid_url",
        "tried_urls": candidate_urls,
        "snippet": None,
    }
