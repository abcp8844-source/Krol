# cleaner.py
import re
from bs4 import BeautifulSoup

def clean_text_content(text):
    if not text:
        return ""
    # Remove boilerplate noise
    cleaned = re.sub(r"(?i)we use cookies.*?(accept|agree|decline|settings)", "", text)
    cleaned = re.sub(r"(?i)privacy policy.*?(rights reserved|cookies)", "", cleaned)
    cleaned = re.sub(r"(?i)about us.*?(contact us|our team)", "", cleaned)
    cleaned = re.sub(r"(?i)terms and conditions.*?(copyright|all rights)", "", cleaned)
    cleaned = re.sub(r"(?i)create your jobseeker profile.*?(upload cv|sign up)", "", cleaned)
    return re.sub(r'\s+', ' ', cleaned).strip()

def extract_strict_job_details(page, target_url):
    try:
        page.goto(target_url, timeout=45000, wait_until="domcontentloaded")
        import time
        time.sleep(4)
        
        html_content = page.content()
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove unwanted structural tags
        for element in soup(["script", "style", "nav", "footer", "header", "aside", "form", "iframe", "button", "noscript"]):
            element.decompose()
            
        page_text = soup.get_text(separator=" ")
        page_text = clean_text_content(page_text)

        # Negative keywords to reject trash pages
        bad_terms = [
            "cookie policy", "privacy policy", "legal notice", "page not found", 
            "error 404", "job expired", "position filled", "sign in to view", 
            "terms of use", "about our company", "copyright all rights reserved",
            "create your profile", "jobseeker login", "register to apply"
        ]
        if any(term in page_text.lower() for term in bad_terms):
            return None

        # Must contain legitimate job keywords
        job_indicators = ["requirements", "experience", "qualification", "responsibilities", "duties", "salary", "apply", "position", "candidate", "skills", "benefits", "employment type"]
        match_count = sum(1 for ind in job_indicators if ind in page_text.lower())
        if match_count < 3:
            return None

        # Extract Salary safely
        salary = "Not Specified"
        salary_match = re.search(r'(?:salary|pay|wage|compensation|USD|EUR|AED|QAR|SAR|SGD|\$|₺|€)\s*[:\-]?\s*[\d,]+\s*(?:-|to)?\s*[\d,]*', page_text, re.IGNORECASE)
        if salary_match:
            sal_text = salary_match.group(0).strip()
            if "0.00" not in sal_text:
                salary = sal_text

        # Extract Location safely
        location = "On-site"
        loc_match = re.search(r'(?:Location|City|Address|Area):\s*([A-Za-z\s,]+)', page_text, re.IGNORECASE)
        if loc_match:
            location = loc_match.group(1).strip()[:50]

        # Extract Email if present
        email_match = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', page_text)
        email = email_match.group(0) if email_match else ""

        # Strict phone extraction avoiding wage confusion
        phone_match = re.search(r'\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{4}\b', page_text)
        phone = phone_match.group(0).strip() if phone_match else ""

        paragraphs = []
        for p in soup.find_all(['p', 'div', 'li']):
            txt = p.get_text().strip()
            if len(txt) > 40 and any(k in txt.lower() for k in ["apply", "salary", "requirement", "experience", "qualification", "duty", "responsibility", "benefit", "position"]):
                if txt not in paragraphs and not any(bt in txt.lower() for bt in bad_terms):
                    paragraphs.append(txt)

        intro_snippet = " ".join(page_text.split()[:180])
        combined_details = intro_snippet
        if paragraphs:
            combined_details += "\n\nKey Job Description & Requirements:\n" + "\n".join([f"- {pr}" for pr in paragraphs[:8]])

        if len(combined_details.split()) < 50:
            return None

        return {
            "finalUrl": page.url,
            "salary": salary,
            "location": location,
            "email": email,
            "phone": phone,
            "snippet": combined_details[:2000]
        }
    except Exception as e:
        return None
print("-> [Cleaner] Strict text parser loaded.")
