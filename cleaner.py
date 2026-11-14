import re
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

def extract_strict_job_details(driver, target_url):
    try:
        driver.get(target_url)
        driver.implicitly_wait(6)
        
        html_content = driver.page_source
        soup = BeautifulSoup(html_content, 'html.parser')
        
        for element in soup(["script", "style", "nav", "footer", "header", "aside", "form", "iframe", "button", "noscript"]):
            element.decompose()
            
        page_text = soup.get_text(separator=" ")
        page_text = clean_text_content(page_text)

        junk_indicators = [
            "ordenar por", "relevancia", "resultados de búsqueda", "¿te avisamos si hay nuevas ofertas?", 
            "filtrar por", "empleos y trabajo", "candidatos", "iniciar sesión", "cookies", 
            "aviso legal", "política de privacidad", "inicia sesión con tu cuenta"
        ]
        if any(j in page_text.lower() for j in junk_indicators):
            return None

        salary = "Not Specified"
        salary_match = re.search(r'(?:salary|pay|wage|compensation|USD|EUR|AED|QAR|SAR|SGD|\$|₺|€|B/\.)\s*[:\-]?\s*[\d,]+\s*(?:-|to)?\s*[\d,]*', page_text, re.IGNORECASE)
        if salary_match:
            sal_text = salary_match.group(0).strip()
            if "0.00" not in sal_text:
                salary = sal_text

        location = "On-site"
        loc_match = re.search(r'(?:Location|City|Address|Area|Ubicación):\s*([A-Za-z\s,]+)', page_text, re.IGNORECASE)
        if loc_match:
            location = loc_match.group(1).strip()[:50]

        email_match = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', page_text)
        email = email_match.group(0) if email_match else ""

        phone_match = re.search(r'\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{4}\b', page_text)
        phone = phone_match.group(0).strip() if phone_match else ""

        paragraphs = []
        for p in soup.find_all(['p', 'div', 'li']):
            txt = p.get_text().strip()
            if len(txt) > 35 and txt not in paragraphs:
                paragraphs.append(txt)

        intro_snippet = " ".join(page_text.split()[:250])
        combined_details = intro_snippet
        if paragraphs:
            combined_details += "\n\nJob Description & Details:\n" + "\n".join([f"- {pr}" for pr in paragraphs[:12]])

        if len(combined_details.split()) < 40:
            return None

        return {
            "finalUrl": driver.current_url,
            "salary": salary,
            "location": location,
            "email": email,
            "phone": phone,
            "snippet": combined_details[:2000]
        }
    except Exception as e:
        print(f"[CLEANER ERROR] {e}")
        return None
