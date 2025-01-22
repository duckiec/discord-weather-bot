import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import sys
import logging
import asyncio

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('weatherbot')

load_dotenv()

# List of major cities for random selection
CITIES = [
    "Tokyo", "New York", "London", "Paris", "Sydney",
    "Moscow", "Dubai", "Singapore", "Rome", "Toronto",
    "Berlin", "Madrid", "Seoul", "Mumbai", "Cairo"
]

# Validate required environment variables
required_env_vars = {
    "DISCORD_TOKEN": os.getenv("DISCORD_TOKEN"),
    "APPLICATION_ID": os.getenv("APPLICATION_ID")
}

for var_name, var_value in required_env_vars.items():
    if not var_value or var_value.startswith("your_"):
        print(f"Error: {var_name} is not properly configured in .env file")
        sys.exit(1)

class WeatherBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=discord.Intents.all(),
            application_id=int(os.getenv("APPLICATION_ID"))
        )
        self.initial_extensions = []
        for filename in os.listdir("./commands"):
            if filename.endswith(".py") and not filename.startswith("_"):
                self.initial_extensions.append(f"commands.{filename[:-3]}")
        self.cleanup_task = None

    async def setup_hook(self):
        # Load extensions before syncing commands
        for extension in self.initial_extensions:
            try:
                await self.load_extension(extension)
                logger.info(f"Loaded extension {extension}")
            except Exception as e:
                logger.error(f"Failed to load extension {extension}: {e}")
        
        try:
            await self.tree.sync()
            logger.info("Command tree synced")
        except Exception as e:
            logger.error(f"Failed to sync command tree: {e}")

        self.cleanup_task = self.loop.create_task(self.periodic_cleanup())

    async def periodic_cleanup(self):
        """Periodically cleanup inactive servers"""
        while not self.is_closed():
            try:
                settings_cog = self.get_cog('Settings')
                if settings_cog:
                    settings_cog.db.cleanup_inactive_servers()
                await asyncio.sleep(86400)  # Run once per day
            except Exception as e:
                logger.error(f"Error in periodic cleanup: {e}")
                await asyncio.sleep(3600)  # Retry after an hour if there's an error

    async def close(self):
        """Cleanup on bot shutdown"""
        if self.cleanup_task:
            self.cleanup_task.cancel()
        await super().close()

    async def on_ready(self):
        logger.info(f"{self.user} is ready and online!")

def main():
    try:
        bot = WeatherBot()
        bot.run(os.getenv("DISCORD_TOKEN"))
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()