import re
from bs4 import BeautifulSoup
from config import SCHEDULE
try:
    from keywords import KEYWORDS
except ImportError:
    KEYWORDS = {}

ALL_COUNTRIES = [c for country_list in SCHEDULE.values() for c in country_list]

def clean_text_content(text):
    if not text:
        return ""
    cleaned = re.sub(r"(?i)we use cookies.*?(accept|agree|decline|settings)", "", text)
    cleaned = re.sub(r"(?i)privacy policy.*?(rights reserved|cookies)", "", cleaned)
    cleaned = re.sub(r"(?i)terms and conditions.*?(copyright|all rights)", "", cleaned)
    cleaned = re.sub(r"(?i)create your jobseeker profile.*?(upload cv|sign up)", "", cleaned)
    cleaned = re.sub(r"(?i)cookie policy.*?(consent|preferences)", "", cleaned)
    return re.sub(r'\s+', ' ', cleaned).strip()

def extract_strict_job_details(driver, target_url, target_country, target_city, category="Jobs", search_keyword=""):
    try:
        driver.get(target_url)
        driver.implicitly_wait(6)
        
        current_url_lower = driver.current_url.lower()
        if any(p in current_url_lower for p in ["/login", "/signin", "/register", "/signup", "/auth/"]):
            return None

        html_content = driver.page_source
        soup = BeautifulSoup(html_content, 'html.parser')
        
        for element in soup(["script", "style", "nav", "footer", "header", "aside", "form", "iframe", "button", "noscript"]):
            element.decompose()
            
        page_text = soup.get_text(separator=" ")
        page_text = clean_text_content(page_text)
        page_text_lower = page_text.lower()

        is_truly_blocked = (
            len(page_text_lower) < 300 and 
            any(b in page_text_lower for b in ["access denied", "additional verification required", "ray id:", "checking your browser before accessing"])
        )
        if is_truly_blocked:
            return None

        if any(j in page_text_lower for j in ["this job listing is no longer available", "expired job posting", "job has expired"]):
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

        salary = "Not Specified"
        salary_match = re.search(r'(?:salary|pay|wage|compensation|fee|price|USD|EUR|AED|QAR|SAR|SGD|GBP|CAD|AUD|\$|₺|€|£|¥|฿)\s*[:\-]?\s*[\d,]+\s*(?:-|to)?\s*[\d,]*', page_text, re.IGNORECASE)
        if salary_match:
            sal_text = salary_match.group(0).strip()
            if "0.00" not in sal_text:
                salary = sal_text

        location = target_city
        loc_match = re.search(r'(?:Location|City|Address|Area|Ubicación):\s*([A-Za-z\s,]+)', page_text, re.IGNORECASE)
        if loc_match:
            location = loc_match.group(1).strip()[:50]

        email_match = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', page_text)
        email = email_match.group(0) if email_match else ""

        phone_match = re.search(r'\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{4}\b', page_text)
        phone = phone_match.group(0).strip() if phone_match else ""

        paragraphs = []
        for p in soup.find_all(['p', 'div', 'li', 'section']):
            txt = p.get_text().strip()
            if len(txt) > 40 and txt not in paragraphs:
                paragraphs.append(txt)

        intro_snippet = " ".join(page_text.split()[:350])
        combined_details = intro_snippet
        if paragraphs:
            combined_details += "\n\nJob Description & Details:\n" + "\n".join([f"- {pr}" for pr in paragraphs[:30]])

        words = combined_details.split()
        if len(words) < 400:
            return None

        final_snippet = " ".join(words[:800])

        return {
            "finalUrl": driver.current_url,
            "salary": salary,
            "location": location,
            "email": email,
            "phone": phone,
            "snippet": final_snippet
        }
    except Exception:
        return None
