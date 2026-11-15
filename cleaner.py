import re
from bs4 import BeautifulSoup
from config import SCHEDULE

ALL_COUNTRIES = [c for country_list in SCHEDULE.values() for c in country_list]

def clean_text_content(text):
    if not text:
        return ""
    cleaned = re.sub(r"(?i)we use cookies.*?(accept|agree|decline|settings)", "", text)
    cleaned = re.sub(r"(?i)privacy policy.*?(rights reserved|cookies)", "", cleaned)
    cleaned = re.sub(r"(?i)about us.*?(contact us|our team)", "", cleaned)
    cleaned = re.sub(r"(?i)terms and conditions.*?(copyright|all rights)", "", cleaned)
    cleaned = re.sub(r"(?i)create your jobseeker profile.*?(upload cv|sign up)", "", cleaned)
    cleaned = re.sub(r"(?i)cookie policy.*?(consent|preferences)", "", cleaned)
    return re.sub(r'\s+', ' ', cleaned).strip()

def extract_strict_job_details(driver, target_url, target_country, target_city, category="Jobs"):
    try:
        driver.get(target_url)
        driver.implicitly_wait(6)
        
        current_url_lower = driver.current_url.lower()
        blocked_paths = ["/salary", "/career-advice", "/resume", "/blog", "/article", "/resources", "/employers", "/about", "/contact", "/privacy", "/terms", "/cookie"]
        if any(bp in current_url_lower for bp in blocked_paths):
            return None

        html_content = driver.page_source
        soup = BeautifulSoup(html_content, 'html.parser')
        
        for element in soup(["script", "style", "nav", "footer", "header", "aside", "form", "iframe", "button", "noscript"]):
            element.decompose()
            
        page_text = soup.get_text(separator=" ")
        page_text = clean_text_content(page_text)
        page_text_lower = page_text.lower()

        bot_block_indicators = [
            "cloudflare", "additional verification required", "ray id", "access denied", 
            "checking your browser", "enable javascript and cookies", "security check", 
            "automated access", "captcha", "robot", "return home"
        ]
        if any(b in page_text_lower for b in bot_block_indicators):
            return None

        junk_indicators = [
            "ordenar por", "relevancia", "resultados de búsqueda", "¿te avisamos si hay nuevas ofertas?", 
            "filtrar por", "empleos y trabajo", "candidatos", "iniciar sesión", "cookies", 
            "aviso legal", "política de privacidad", "inicia sesión con tu cuenta",
            "salary calculator", "salary comparison", "check your earning potential", "no longer available", "expired"
        ]
        if any(j in page_text_lower for j in junk_indicators):
            return None

        if target_country.lower() not in page_text_lower and target_city.
