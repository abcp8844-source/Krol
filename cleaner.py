import re
from config import SCHEDULE
try:
    from keywords import KEYWORDS
except ImportError:
    KEYWORDS = {}

ALL_COUNTRIES = [c for country_list in SCHEDULE.values() for c in country_list]

APPLY_SIGNALS = [
    "how to apply", "apply now", "apply here", "apply online", "submit application",
    "send your cv", "send cv", "send resume", "upload resume", "upload cv",
    "application process", "application steps", "hiring process", "contact hr",
    "whatsapp", "apply via", "career portal", "job portal", "interview", "vacancy"
]

VISA_TRAVEL_SIGNALS = [
    "requirements", "documents required", "eligibility", "application fee", "visa fee",
    "processing time", "how to apply", "steps", "itinerary", "booking", "validity",
    "embassy", "consulate", "passport", "permit", "rules", "regulations"
]


def clean_text_content(text):
    if not text:
        return ""
    cleaned = re.sub(r"(?is)we use cookies.*?(accept|agree|decline|settings)", " ", text)
    cleaned = re.sub(r"(?is)privacy policy.*?(rights reserved|cookies)", " ", cleaned)
    cleaned = re.sub(r"(?is)terms and conditions.*?(copyright|all rights)", " ", cleaned)
    cleaned = re.sub(r"(?is)create your jobseeker profile.*?(upload cv|sign up)", " ", cleaned)
    cleaned = re.sub(r"(?is)cookie policy.*?(consent|preferences)", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def has_actionable_substance(text_lower, email, phone, apply_links, category):
    cat = (category or "Jobs").lower()
    has_contact = bool(email or phone or apply_links)

    if cat == "jobs":
        has_apply_phrase = any(sig in text_lower for sig in APPLY_SIGNALS)
        return has_apply_phrase or (has_contact and ("apply" in text_lower or "resume" in text_lower or "cv" in text_lower or "job" in text_lower))

    if cat in ("visa", "travel"):
        signal_hits = sum(1 for sig in VISA_TRAVEL_SIGNALS if sig in text_lower)
        return signal_hits >= 2 or (signal_hits >= 1 and has_contact)

    return any(sig in text_lower for sig in APPLY_SIGNALS) or sum(1 for sig in VISA_TRAVEL_SIGNALS if sig in text_lower) >= 2


def extract_strict_job_details(page, target_url, target_country, target_city, category="Jobs", search_keyword=""):
    try:
        page.goto(target_url, wait_until="domcontentloaded", timeout=25000)
        page.wait_for_timeout(2000)

        current_url_lower = page.url.lower()
        if any(p in current_url_lower for p in ["/login", "/signin", "/register", "/signup", "/auth/"]):
            return None

        extracted_data = page.evaluate("""() => {
            const unwanted = document.querySelectorAll('script, style, nav, footer, header, aside, form, iframe, button, noscript');
            unwanted.forEach(el => el.remove());

            const pageText = document.body ? document.body.innerText : '';

            const textBlocks = [];
            const elements = document.querySelectorAll('p, div, li, section, article');
            elements.forEach(el => {
                const txt = el.innerText ? el.innerText.replace(/\\s+/g, ' ').trim() : '';
                if (txt.length > 40 && !textBlocks.includes(txt)) {
                    textBlocks.push(txt);
                }
            });

            const links = [];
            const anchors = document.querySelectorAll('a[href]');
            anchors.forEach(a => {
                const href = (a.href || '').trim();
                const label = (a.innerText || '').trim().toLowerCase();
                if (href.startsWith('http') && (
                    href.toLowerCase().includes('apply') ||
                    href.toLowerCase().includes('career') ||
                    href.toLowerCase().includes('job') ||
                    label.includes('apply')
                )) {
                    if (!links.includes(href)) links.push(href);
                }
            });

            return {
                pageText: pageText,
                paragraphs: textBlocks,
                applyLinks: links.slice(0, 5)
            };
        }""")

        page_text = clean_text_content(extracted_data.get("pageText", ""))
        page_text_lower = page_text.lower()

        is_truly_blocked = (
            len(page_text_lower) < 300
            and any(
                b in page_text_lower
                for b in [
                    "access denied",
                    "additional verification required",
                    "ray id:",
                    "checking your browser before accessing",
                ]
            )
        )
        if is_truly_blocked:
            return None

        if any(
            j in page_text_lower
            for j in [
                "this job listing is no longer available",
                "expired job posting",
                "job has expired",
            ]
        ):
            return None

        if target_country.lower() not in page_text_lower and target_city.lower() not in page_text_lower:
            return None

        for other_country in ALL_COUNTRIES:
            if other_country.lower() != target_country.lower():
                if other_country.lower() in page_text_lower[:400]:
                    return None

        category_keywords = KEYWORDS.get(category, [])
        if category_keywords and not any(kw.lower() in page_text_lower for kw in category_keywords):
            if search_keyword and search_keyword.lower() not in page_text_lower:
                return None

        email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", page_text)
        email = email_match.group(0) if email_match else ""

        phone_match = re.search(
            r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{4}\b",
            page_text,
        )
        phone = phone_match.group(0).strip() if phone_match else ""

        apply_links = extracted_data.get("applyLinks", [])

        if not has_actionable_substance(page_text_lower, email, phone, apply_links, category):
            return None

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

        location = target_city
        loc_match = re.search(
            r"(?:Location|City|Address|Area|Ubicación):\s*([A-Za-z\s,]+)",
            page_text,
            re.IGNORECASE,
        )
        if loc_match:
            location = loc_match.group(1).strip()[:50]

        paragraphs = [clean_text_content(p) for p in extracted_data.get("paragraphs", [])]
        paragraphs = [p for p in paragraphs if len(p) > 40]

        intro_snippet = " ".join(page_text.split()[:350])
        combined_details = intro_snippet
        if paragraphs:
            combined_details += "\n\nDetails:\n" + "\n".join([f"- {pr}" for pr in paragraphs[:30]])
        if apply_links:
            combined_details += "\n\nApplication Links:\n" + "\n".join([f"- {lnk}" for lnk in apply_links])

        words = combined_details.split()
        if len(words) < 400:
            return None

        final_snippet = " ".join(words[:800])

        return {
            "finalUrl": page.url,
            "salary": salary,
            "location": location,
            "email": email,
            "phone": phone,
            "applyLinks": apply_links,
            "snippet": final_snippet,
        }
    except Exception:
        return None
