import re
from datetime import datetime
from config import SCHEDULE, COUNTRY_CITIES
from keywords import COUNTRY_KEYWORDS

try:
    from config import SEARCH_COUNTRY_NAMES, SEARCH_CITY_NAMES
except ImportError:
    SEARCH_COUNTRY_NAMES = {}
    SEARCH_CITY_NAMES = {}

try:
    from scraper import CATEGORY_TRANSLATIONS
except ImportError:
    CATEGORY_TRANSLATIONS = {}


def clean_text_content(text):
    if not text:
        return ""
    cleaned = re.sub(r"(?is)we use cookies.*?(accept|agree|decline|settings)", " ", text)
    cleaned = re.sub(r"(?is)privacy policy.*?(rights reserved|cookies)", " ", cleaned)
    cleaned = re.sub(r"(?is)terms and conditions.*?(copyright|all rights)", " ", cleaned)
    cleaned = re.sub(r"(?is)create your jobseeker profile.*?(upload cv|sign up)", " ", cleaned)
    cleaned = re.sub(r"(?is)cookie policy.*?(consent|preferences)", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def extract_strict_job_details(page, target_url, target_country, target_city, category="Jobs", search_keyword=""):
    try:
        today_name = datetime.now().strftime("%A")
        scheduled_countries = SCHEDULE.get(today_name, [])
        if scheduled_countries and target_country not in scheduled_countries:
            return None

        valid_cities = COUNTRY_CITIES.get(target_country, [])
        if valid_cities and target_city not in valid_cities:
            return None

        page.goto(target_url, wait_until="domcontentloaded", timeout=25000)
        page.wait_for_timeout(2000)

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

        country_variants = [target_country, SEARCH_COUNTRY_NAMES.get(target_country, "")]
        city_variants = [target_city, SEARCH_CITY_NAMES.get(target_city, "")]

        country_matched = any(c.strip().lower() in page_text_lower for c in country_variants if c and c.strip())
        city_matched = any(ct.strip().lower() in page_text_lower for ct in city_variants if ct and ct.strip())

        if not (country_matched and city_matched):
            return None

        translated_cat = CATEGORY_TRANSLATIONS.get(target_country, {}).get(category, "")
        category_keywords = COUNTRY_KEYWORDS.get(target_country, {}).get(category, [])
        cat_terms = [category, translated_cat, search_keyword] + list(category_keywords)

        category_matched = any(t.strip().lower() in page_text_lower for t in cat_terms if t and t.strip())
        if not category_matched:
            return None

        email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", page_text)
        email = email_match.group(0) if email_match else ""

        phone_match = re.search(
            r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{4}\b",
            page_text,
        )
        phone = phone_match.group(0).strip() if phone_match else ""

        apply_links = extracted_data.get("applyLinks", [])

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

        location = SEARCH_CITY_NAMES.get(target_city) or target_city
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
