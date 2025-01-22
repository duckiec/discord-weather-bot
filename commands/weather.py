import discord
from discord import app_commands
from discord.ext import commands
from geocoding import *
from fetchweather import getweather
from datetime import datetime, timezone, timedelta
from typing import Optional
from functools import lru_cache, partial
from concurrent.futures import ThreadPoolExecutor
from utils.database import DEFAULT_SETTINGS
import logging
import traceback
import asyncio
from time import time

logger = logging.getLogger('weatherbot')

# Pre-compile weather code ranges for faster lookup
WEATHER_CODE_RANGES = {
    (0, 1): "☀️",
    (1, 4): "🌤️",
    (4, 10): "☁️",
    (10, 20): "🌫️",
    (20, 30): "🌧️",
    (30, 40): "🌧️",
    (40, 50): "🌧️",
    (50, 60): "❄️",
    (60, 70): "🌨️",
    (70, 80): "🌨️",
    (80, 90): "🌦️",
    (90, 100): "⛈️",
}

# Cache emoji lookups to avoid repeated dictionary searches
@lru_cache(maxsize=100)
def get_weather_emoji(weather_code):
    for (start, end), emoji in WEATHER_CODE_RANGES.items():
        if start <= weather_code < end:
            return emoji
    return "❓"

def create_weather_embed(city_info, weather_data, rnd, forecast_days, settings=None):
    if settings is None:
        settings = DEFAULT_SETTINGS

    def format_temp(temp, feels_like=None):
        if settings['units'] == 'imperial':
            temp = (temp * 9/5) + 32
            unit = '°F'
            if feels_like is not None:
                feels_like = (feels_like * 9/5) + 32
        else:
            unit = '°C'
            
        if feels_like is not None:
            return f"{temp:.{rnd}f}{unit} (Feels like: {feels_like:.{rnd}f}{unit})"
        return f"{temp:.{rnd}f}{unit}"

    def format_speed(speed):
        if settings['units'] == 'imperial':
            return f"{speed * 0.621371:.{rnd}f}mph"
        return f"{speed:.{rnd}f}km/h"

    def format_precip(amount):
        if settings['units'] == 'imperial':
            return f"{amount * 0.0393701:.{rnd}f}in"
        return f"{amount:.{rnd}f}mm"

    location = weather_data['location']
    utc_offset = timedelta(seconds=location['utc_offset'])
    local_time = datetime.fromtimestamp(weather_data['current']['time'], timezone.utc).astimezone(timezone(utc_offset))
    
    timezone_str = location['timezone'].decode() if isinstance(location['timezone'], bytes) else location['timezone']
    timezone_abbr = location['timezone_abbreviation'].decode() if isinstance(location['timezone_abbreviation'], bytes) else location['timezone_abbreviation']
    
    lat = float(location['latitude'])
    lon = float(location['longitude'])
    elev = float(location['elevation'])
    
    embed = discord.Embed(
        title=f"Weather in {city_info['name']}",
        description=f"📍 Coordinates: {lat:.{rnd}f}°N, {lon:.{rnd}f}°E\n"
                   f"⛰️ Elevation: {elev:.{rnd}f}m\n"
                   f"🌍 Timezone: {timezone_str} ({timezone_abbr})",
        color=discord.Color.blue(),
        timestamp=local_time
    )
    
    current = weather_data['current']
    wind_direction = get_wind_direction(current['wind_direction'])
    embed.add_field(
        name="📊 Current Conditions",
        value=f"🌡️ Temperature: {format_temp(current['temperature'], current['feels_like'])}\n"
              f"💧 Humidity: {int(current['humidity'])}%\n"
              f"☁️ Cloud Cover: {int(current['cloud_cover'])}%\n"
              f"💨 Wind: {format_speed(current['wind_speed'])} {wind_direction} (Gusts: {format_speed(current['wind_gusts'])})\n"
              f"🌧️ Rain: {format_precip(current['rain'])}",
        inline=False
    )
    
    daily = weather_data['daily']
    dates = daily['dates']
    
    min_length = min(
        len(daily['dates']),
        len(daily['weather_codes']),
        len(daily['max_temp']),
        len(daily['min_temp']),
        len(daily['feels_like_max']),
        len(daily['feels_like_min']),
        len(daily['precip_prob']),
        len(daily['wind_speed']),
        len(daily['rain_sum'])
    )
    
    forecast_length = min(forecast_days, min_length)
    
    for i in range(forecast_length):
        try:
            date = dates[i]
            weather_emoji = get_weather_emoji(int(daily['weather_codes'][i]))
            max_temp = float(daily['max_temp'][i])
            min_temp = float(daily['min_temp'][i])
            avg_temp = (max_temp + min_temp) / 2
            
            embed.add_field(
                name=f"📅 {date.strftime('%Y-%m-%d')}",
                value=f"{weather_emoji} Weather Code: {int(daily['weather_codes'][i])}\n"
                      f"🌡️ Max: {format_temp(max_temp, daily['feels_like_max'][i])}\n"
                      f"🌡️ Min: {format_temp(min_temp, daily['feels_like_min'][i])}\n"
                      f"🌡️ Avg: {format_temp(avg_temp)}\n"
                      f"🌧️ Rain: {format_precip(float(daily['rain_sum'][i]))} ({int(daily['precip_prob'][i])}% chance)",
                inline=True
            )
        except Exception as e:
            logger.error(f"Error formatting forecast day {i}: {e}")
            continue
    
    embed.set_footer(text=f"Data from Open-Meteo | Local time: {local_time.strftime('%Y-%m-%d %H:%M %Z')}")
    return embed

# Pre-calculate wind directions
WIND_DIRECTIONS = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                  'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
DIRECTION_STEP = 360 / len(WIND_DIRECTIONS)

@lru_cache(maxsize=360)
def get_wind_direction(degrees):
    index = round(degrees / DIRECTION_STEP) % len(WIND_DIRECTIONS)
    return WIND_DIRECTIONS[index]

class Weather(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._thread_pool = ThreadPoolExecutor(
            max_workers=8,
            thread_name_prefix="weather_worker"
        )
        self._settings_cache = {}
        self._city_cache = {}
        self._weather_cache = {}
        self._cache_ttl = 300
        self._format_handlers = {
            'imperial': {
                'temp': lambda t, r: f"{(t * 9/5) + 32:.{r}f}°F",
                'speed': lambda s, r: f"{s * 0.621371:.{r}f}mph",
                'precip': lambda p, r: f"{p * 0.0393701:.{r}f}in"
            },
            'metric': {
                'temp': lambda t, r: f"{t:.{r}f}°C",
                'speed': lambda s, r: f"{s:.{r}f}km/h",
                'precip': lambda p, r: f"{p:.{r}f}mm"
            }
        }

    async def get_guild_settings(self, guild_id: str):
        if not guild_id:
            logger.debug("No guild_id provided, using default settings")
            return DEFAULT_SETTINGS.copy()

        current_time = int(time())
        cached = self._settings_cache.get(guild_id)
        
        if cached and (current_time - cached['timestamp'] < 300):
            logger.debug(f"Using cached settings for guild {guild_id}")
            return cached['settings']

        settings_cog = self.bot.get_cog('Settings')
        if settings_cog:
            try:
                settings = settings_cog.get_server_settings(guild_id)
                self._settings_cache[guild_id] = {
                    'settings': settings,
                    'timestamp': current_time
                }
                logger.debug(f"Retrieved and cached settings for guild {guild_id}: {settings}")
                return settings
            except Exception as e:
                logger.error(f"Error getting settings for guild {guild_id}: {e}")

        logger.warning(f"Using default settings for guild {guild_id}")
        return DEFAULT_SETTINGS.copy()

    async def get_cached_city_info(self, city: str):
        current_time = int(time())
        cache_key = city.lower()
        cached = self._city_cache.get(cache_key)
        
        if cached and (current_time - cached['timestamp'] < self._cache_ttl):
            return cached['data']
            
        city_info = await self.bot.loop.run_in_executor(
            self._thread_pool,
            lambda: getcods(city)
        )
        
        if city_info:
            self._city_cache[cache_key] = {
                'data': city_info,
                'timestamp': current_time
            }
        
        return city_info

    @app_commands.command(name="weather")
    async def weather(self, interaction: discord.Interaction, city: str, 
                     forecast_days: Optional[int] = None, 
                     rnd: Optional[int] = None):
        logger.debug(f"Weather command called by {interaction.user} for city: {city}")

        try:
            guild_id = str(interaction.guild.id) if interaction.guild else None
            settings = await self.get_guild_settings(guild_id)
            logger.debug(f"Settings for guild {guild_id}: {settings}")

            try:
                rnd = int(rnd) if rnd is not None else settings['decimal_places']
                forecast_days = int(forecast_days) if forecast_days is not None else settings['forecast_days']
                
                if not (1 <= rnd <= 5) or not (1 <= forecast_days <= 5):
                    await interaction.response.send_message(
                        "Invalid parameters. Values must be between 1 and 5.",
                        ephemeral=True
                    )
                    return
            except ValueError:
                await interaction.response.send_message(
                    "Please provide valid numbers.",
                    ephemeral=True
                )
                return

            await interaction.response.defer(thinking=True)
            logger.debug(f"Deferred interaction for {interaction.user}")

            city_info = await self.get_cached_city_info(city)
            if not city_info:
                await interaction.followup.send("Could not find the specified location.")
                return

            weather_data = await self.get_cached_weather(
                f"{city_info['lat']},{city_info['lon']},{forecast_days}",
                city_info,
                forecast_days
            )

            if not weather_data:
                await interaction.followup.send("Could not fetch weather data.")
                return

            embed = await self.bot.loop.run_in_executor(
                self._thread_pool,
                partial(create_weather_embed, city_info, weather_data, rnd, forecast_days, settings)
            )
            
            await interaction.followup.send(embed=embed)

        except discord.errors.NotFound as e:
            logger.warning(f"Interaction expired for {interaction.user}: {e}")
        except discord.errors.HTTPException as e:
            logger.error(f"HTTP error in weather command: {e}")
        except Exception as e:
            error_trace = traceback.format_exc()
            logger.error(f"Error in weather command: {e}\n{error_trace}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "An error occurred while processing your request.",
                    ephemeral=True
                )

    async def get_cached_weather(self, cache_key: str, city_info: dict, forecast_days: int):
        current_time = int(time())
        cached = self._weather_cache.get(cache_key)
        
        if cached and (current_time - cached['timestamp'] < 300):
            return cached['data']
            
        weather_data = await self.bot.loop.run_in_executor(
            self._thread_pool,
            lambda: getweather(city_info['lat'], city_info['lon'], forecast_days)
        )
        
        if weather_data:
            self._weather_cache[cache_key] = {
                'data': weather_data,
                'timestamp': current_time
            }
        
        return weather_data

    def cog_unload(self):
        self._settings_cache.clear()
        self._thread_pool.shutdown(wait=False)

async def setup(bot: commands.Bot):
    await bot.add_cog(Weather(bot))
