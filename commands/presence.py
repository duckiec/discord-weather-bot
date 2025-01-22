import discord
from discord.ext import commands, tasks
from geocoding import getcods
from fetchweather import getweather
from utils.database import DEFAULT_SETTINGS
import random
from datetime import datetime, timedelta
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import logging

logger = logging.getLogger('weatherbot')

CITIES = [
    "Tokyo", "New York", "London", "Paris", "Sydney",
    "Moscow", "Dubai", "Singapore", "Rome", "Toronto",
    "Berlin", "Madrid", "Seoul", "Mumbai", "Cairo", "Montreal", 
    "Chicago"
]

class Presence(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._city_cache = {}
        self._cache_timestamps = {}
        # Use deque for O(1) operations
        self._last_cities = deque(maxlen=len(CITIES) // 2)
        self._available_cities = list(CITIES)
        self._thread_pool = ThreadPoolExecutor(max_workers=2)
        self._default_settings = DEFAULT_SETTINGS.copy()
        self.update_presence.start()

    def cog_unload(self):
        self.update_presence.cancel()
        self._thread_pool.shutdown(wait=False)

    @tasks.loop(minutes=15)
    async def update_presence(self):
        try:
            # Run heavy operations in thread pool
            city, weather = await self.bot.loop.run_in_executor(
                self._thread_pool,
                self._get_city_weather
            )
            
            if city and weather:
                temp = round(weather['current']['temperature'], 1)
                # Always use metric for presence display
                await self.bot.change_presence(
                    activity=discord.Activity(
                        type=discord.ActivityType.watching,
                        name=f"{temp}°C in {city}"
                    )
                )
        except Exception as e:
            logger.error(f"Error updating presence: {e}")

    def _get_city_weather(self):
        """Get weather for a random city (runs in thread pool)"""
        current_time = datetime.now()
        
        # Batch clean expired cache
        expired = {
            city for city, timestamp in self._cache_timestamps.items()
            if (current_time - timestamp).total_seconds() > 86400
        }
        for city in expired:
            self._city_cache.pop(city, None)
            self._cache_timestamps.pop(city, None)

        if not self._available_cities:
            self._available_cities = [c for c in CITIES if c not in self._last_cities]
            if not self._available_cities:
                self._available_cities = list(CITIES)
                self._last_cities.clear()

        city = random.choice(self._available_cities)
        self._available_cities.remove(city)
        self._last_cities.append(city)

        city_info = self._city_cache.get(city)
        if not city_info:
            city_info = getcods(city)
            if city_info:
                self._city_cache[city] = city_info
                self._cache_timestamps[city] = current_time

        if city_info:
            return city, getweather(city_info['lat'], city_info['lon'], 1)
        return None, None

    @update_presence.before_loop
    async def before_update_presence(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(Presence(bot))
