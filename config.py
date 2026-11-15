import os
from domains import COUNTRY_DOMAINS
from keywords import COUNTRY_KEYWORDS

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0"
]

SCHEDULE = {
    "Monday": ["UAE", "Saudi Arabia", "Qatar", "Bahrain", "Kuwait", "Oman"],
    "Tuesday": ["Japan", "South Korea", "China", "Taiwan", "Singapore", "Hong Kong"],
    "Wednesday": ["Thailand", "Vietnam", "Malaysia", "Indonesia", "Philippines", "Singapore"],
    "Thursday": ["Germany", "France", "Netherlands", "Belgium", "Switzerland", "Austria"],
    "Friday": ["UK", "Ireland", "Sweden", "Norway", "Denmark", "Finland"],
    "Saturday": ["Canada", "USA", "Mexico", "Panama", "Brazil", "Argentina"],
    "Sunday": ["Italy", "Turkey", "Azerbaijan", "Georgia", "Spain", "Greece"]
}

COUNTRY_CITIES = {
    "UAE": ["Dubai", "Abu Dhabi", "Sharjah", "Ajman"],
    "Saudi Arabia": ["Riyadh", "Jeddah", "Dammam", "Khobar"],
    "Qatar": ["Doha", "Al Rayyan", "Lusail"],
    "Bahrain": ["Manama", "Riffa"],
    "Kuwait": ["Kuwait City", "Salmiya"],
    "Oman": ["Muscat", "Salalah"],
    "Japan": ["Tokyo", "Osaka", "Yokohama", "Nagoya"],
    "South Korea": ["Seoul", "Busan", "Incheon"],
    "China": ["Shanghai", "Beijing", "Shenzhen", "Guangzhou"],
    "Taiwan": ["Taipei", "Kaohsiung", "Taichung"],
    "Singapore": ["Singapore"],
    "Hong Kong": ["Hong Kong", "Kowloon"],
    "Thailand": ["Bangkok", "Phuket", "Chiang Mai", "Pattaya"],
    "Vietnam": ["Ho Chi Minh City", "Hanoi", "Da Nang"],
    "Malaysia": ["Kuala Lumpur", "Penang", "Johor Bahru"],
    "Indonesia": ["Jakarta", "Surabaya", "Bali", "Bandung"],
    "Philippines": ["Manila", "Cebu City", "Makati"],
    "Germany": ["Berlin", "Munich", "Frankfurt", "Hamburg"],
    "France": ["Paris", "Lyon", "Marseille"],
    "Netherlands": ["Amsterdam", "Rotterdam", "Utrecht"],
    "Belgium": ["Brussels", "Antwerp", "Ghent"],
    "Switzerland": ["Zurich", "Geneva", "Basel"],
    "Austria": ["Vienna", "Salzburg", "Graz"],
    "UK": ["London", "Manchester", "Birmingham", "Edinburgh"],
    "Ireland": ["Dublin", "Cork", "Galway"],
    "Sweden": ["Stockholm", "Gothenburg", "Malmo"],
    "Norway": ["Oslo", "Bergen", "Stavanger"],
    "Denmark": ["Copenhagen", "Aarhus"],
    "Finland": ["Helsinki", "Espoo", "Tampere"],
    "Canada": ["Toronto", "Vancouver", "Montreal", "Calgary"],
    "USA": ["New York", "Los Angeles", "Chicago", "Houston", "Miami"],
    "Mexico": ["Mexico City", "Guadalajara", "Monterrey", "Cancun"],
    "Panama": ["Panama City", "David"],
    "Brazil": ["São Paulo", "Rio de Janeiro", "Curitiba"],
    "Argentina": ["Buenos Aires", "Córdoba", "Rosario"],
    "Italy": ["Rome", "Milan", "Naples", "Turin"],
    "Turkey": ["Istanbul", "Ankara", "Izmir", "Antalya"],
    "Azerbaijan": ["Baku", "Ganja"],
    "Georgia": ["Tbilisi", "Batumi"],
    "Spain": ["Madrid", "Barcelona", "Valencia", "Seville"],
    "Greece": ["Athens", "Thessaloniki"]
}
