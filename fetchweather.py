import openmeteo_requests
import requests_cache
import pandas as pd
import numpy as np  # Add numpy import
from retry_requests import retry
from datetime import datetime, timedelta
from functools import lru_cache

def convert_to_list(value):
    """Helper function to safely convert values to lists."""
    if isinstance(value, (np.ndarray, list)):
        return list(value)
    return [value]

# cache responses
cache_session = requests_cache.CachedSession(
    '.cache',
    expire_after=3600,  # 1 hour
    stale_if_error=True,
    backend='sqlite'  
)
retry_session = retry(cache_session, retries=2, backoff_factor=0.1)
openmeteo = openmeteo_requests.Client(session=retry_session)

# Pre-compile the date format for better performance
DATE_FORMAT = '%Y-%m-%d %H:%M %Z'

# Cache weather data for specific lat/lon combinations
@lru_cache(maxsize=128)
def getweather(lat, lon, forecast_days):
    url = "https://api.open-meteo.com/v1/forecast"
    
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": [
            "temperature_2m", "relative_humidity_2m", "apparent_temperature",
            "precipitation", "rain", "weather_code", "cloud_cover",
            "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m"
        ],
        "daily": [
            "weather_code",            # index 0
            "temperature_2m_max",      # index 1
            "temperature_2m_min",      # index 2
            "apparent_temperature_max",# index 3
            "apparent_temperature_min",# index 4
            "sunrise",                # index 5
            "sunset",                 # index 6
            "precipitation_probability_max", # index 7
            "wind_speed_10m_max",     # index 8
            "rain_sum"                # index 9
        ],
        "forecast_days": int(forecast_days),
        "timezone": "auto"
    }
    
    try:
        response = openmeteo.weather_api(url, params=params)[0]
        
        # Get current weather
        current = response.Current()
        current_weather = {
            "temperature": current.Variables(0).Value(),
            "humidity": current.Variables(1).Value(),
            "feels_like": current.Variables(2).Value(),
            "precipitation": current.Variables(3).Value(),
            "rain": current.Variables(4).Value(),
            "weather_code": current.Variables(5).Value(),
            "cloud_cover": current.Variables(6).Value(),
            "wind_speed": current.Variables(7).Value(),
            "wind_direction": current.Variables(8).Value(),
            "wind_gusts": current.Variables(9).Value(),
            "time": current.Time()
        }
        
        # Get daily forecast
        daily = response.Daily()
        
        try:
            daily_weather = {
                "dates": pd.date_range(
                    start=pd.to_datetime(daily.Time(), unit="s", utc=True),
                    end=pd.to_datetime(daily.TimeEnd(), unit="s", utc=True),
                    freq=pd.Timedelta(seconds=daily.Interval()),
                    inclusive="left"
                ),
                # Match the indices with the params order above
                "weather_codes": np.array(daily.Variables(0).ValuesAsNumpy(), dtype=np.int32),  # weather_code
                "max_temp": np.array(daily.Variables(1).ValuesAsNumpy(), dtype=np.float32),      # temperature_2m_max
                "min_temp": np.array(daily.Variables(2).ValuesAsNumpy(), dtype=np.float32),      # temperature_2m_min
                "feels_like_max": convert_to_list(daily.Variables(3).ValuesAsNumpy()), # apparent_temperature_max
                "feels_like_min": convert_to_list(daily.Variables(4).ValuesAsNumpy()), # apparent_temperature_min
                "sunrise_timestamp": convert_to_list(daily.Variables(5).ValuesAsNumpy()), # sunrise
                "sunset_timestamp": convert_to_list(daily.Variables(6).ValuesAsNumpy()),  # sunset
                "precip_prob": convert_to_list(daily.Variables(7).ValuesAsNumpy()),    # precipitation_probability_max
                "wind_speed": convert_to_list(daily.Variables(8).ValuesAsNumpy()),     # wind_speed_10m_max
                "rain_sum": convert_to_list(daily.Variables(9).ValuesAsNumpy())       # rain_sum
            }
        except Exception:
            raise

        return {
            "location": {
                "latitude": response.Latitude(),
                "longitude": response.Longitude(),
                "elevation": response.Elevation(),
                "timezone": response.Timezone(),
                "timezone_abbreviation": response.TimezoneAbbreviation(),
                "utc_offset": response.UtcOffsetSeconds()
            },
            "current": current_weather,
            "daily": daily_weather
        }
        
    except Exception:
        return None


