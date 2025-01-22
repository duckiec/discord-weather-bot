from dotenv import load_dotenv
from functools import lru_cache
import os
from requests.adapters import HTTPAdapter
from requests.sessions import Session
from urllib3.util import Retry

load_dotenv()
geoapikey = os.getenv('GEOCODINGAPIKEY')

# Create a global session with connection pooling
session = Session()
retries = Retry(total=3, backoff_factor=0.1)
adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10, max_retries=retries)
session.mount('http://', adapter)
session.mount('https://', adapter)

# Cache city coordinates to avoid repeated API calls to OpenWeatherMap
@lru_cache(maxsize=1000)
def getcods(city):
    global geoapikey, session
    url = f'http://api.openweathermap.org/geo/1.0/direct?q={city}&limit=1&appid={geoapikey}'
    
    try:
        response = session.get(url, timeout=5)
        if response.status_code == 200 and (data := response.json()):
            location = data[0]
            return {
                'name': location['name'],
                'lat': location['lat'],
                'lon': location['lon']
            }
    except Exception:
        pass
    return None












