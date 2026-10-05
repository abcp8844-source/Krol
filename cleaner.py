import re
import time
from bs4 import BeautifulSoup

def clean_text_content(text):
    if not text:
        return ""
    cleaned = re.sub(r"(?i)we use cookies.*?(accept|agree|decline|settings)", "", text)
    cleaned = re.sub(r"(?i)privacy policy.*?(rights reserved|cookies)", "", cleaned)
    cleaned = re.sub(r"(?i)about us.*?(contact us|our team)", "", cleaned)
    cleaned = re.sub(r"(?i)terms and conditions.*?(copyright|all rights)", "", cleaned)
    cleaned = re.sub(r"(?i)create your jobseeker profile.*?(upload cv|sign up)", "", cleaned)
    return re.sub(r'\s+', ' ', cleaned).strip()

def extract_strict_job_details(page, target_url):
    try:
        page.goto(target_url, timeout=45000, wait_until="domcontentloaded")
        time.sleep(3)
        
        html_content = page.content()
        soup = BeautifulSoup(html_content, 'html.parser')
        
        for element in soup(["script", "style", "nav", "footer", "header", "aside", "form", "iframe", "button", "noscript"]):
            element.decompose()
            
        page_text = soup.get_text(separator=" ")
        page_text = clean_text_content(page_text)

        salary = "Not Specified"
        salary_match = re.search(r'(?:salary|pay|wage|compensation|USD|EUR|AED|QAR|SAR|SGD|\$|₺|€)\s*[:\-]?\s*[\d,]+\s*(?:-|to)?\s*[\d,]*', page_text, re.IGNORECASE)
        if salary_match:
            sal_text = salary_match.group(0).strip()
            if "0.00" not in sal_text:
                salary = sal_text

        location = "On-site"
        loc_match = re.search(r'(?:Location|City|Address|Area):\s*([A-Za-z\s,]+)', page_text, re.IGNORECASE)
        if loc_match:
            location = loc_match.group(1).strip()[:50]

        email_match = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', page_text)
        email = email_match.group(0) if email_match else ""

        phone_match = re.search(r'\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{4}\b', page_text)
        phone = phone_match.group(0).strip() if phone_match else ""

        paragraphs = []
        for p in soup.find_all(['p', 'div', 'li']):
            txt = p.get_text().strip()
            if len(txt) > 20:
                if txt not in paragraphs:
                    paragraphs.append(txt)

        intro_snippet = " ".join(page_text.split()[:200])
        combined_details = intro_snippet
        if paragraphs:
            combined_details += "\n\nJob Description & Details:\n" + "\n".join([f"- {pr}" for pr in paragraphs[:10]])

        if len(combined_details.split()) < 15:
            return None

        return {
            "finalUrl": page.url,
            "salary": salary,
            "location": location,
            "email": email,
            "phone": phone,
            "snippet": combined_details[:2000]
        }
    except Exception:
        return None
