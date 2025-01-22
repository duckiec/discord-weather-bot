import discord
from discord.ext import commands
from discord import app_commands
from typing import Literal, Optional
import logging
from utils.database import DatabaseManager, DEFAULT_SETTINGS
from time import time

logger = logging.getLogger('weatherbot')

class Settings(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = DatabaseManager()
        self._settings_cache = {}
        self._cache_ttl = 300  # 5 minutes

    def get_server_settings(self, guild_id: str):
        """Get settings with better caching and logging"""
        current_time = int(time())
        cached = self._settings_cache.get(guild_id)

        if cached and (current_time - cached['timestamp'] < self._cache_ttl):
            logger.debug(f"Using cached settings for guild {guild_id}")
            return cached['settings']

        settings = self.db.get_server_settings(guild_id)
        self._settings_cache[guild_id] = {
            'settings': settings,
            'timestamp': current_time
        }
        logger.debug(f"Retrieved fresh settings for guild {guild_id}")
        return settings

    @app_commands.command(name="setup", description="Configure server settings")
    @app_commands.describe(
        setting="Setting to configure",
        value="Select the value to set"
    )
    @app_commands.choices(
        setting=[
            app_commands.Choice(name="Units (Metric/Imperial)", value="units"),
            app_commands.Choice(name="Decimal Places (0-5)", value="decimal_places"),
            app_commands.Choice(name="Forecast Days (1-5)", value="forecast_days")
        ]
    )
    async def setup(
        self,
        interaction: discord.Interaction,
        setting: str,
        value: Optional[str] = None
    ):
        # No defer here - we handle the interaction directly
        try:
            if not interaction.guild:
                await interaction.response.send_message(
                    "This command can only be used in servers!",
                    ephemeral=True
                )
                return

            guild_id = str(interaction.guild.id)
            try:
                # Clear the cache for this guild
                self._settings_cache.pop(guild_id, None)

                # Run database operations in thread pool
                server_settings = await self.bot.loop.run_in_executor(
                    None,
                    self.db.get_server_settings,
                    guild_id
                )

                if value is None:
                    current = server_settings[setting]
                    choices = {
                        "units": ["metric", "imperial"],
                        "decimal_places": list(range(6)),
                        "forecast_days": list(range(1, 6))
                    }
                    
                    value_options = choices.get(setting, [])
                    if not value_options:
                        await interaction.response.send_message("Invalid setting type.", ephemeral=True)
                        return
                    
                    await interaction.response.send_message(
                        f"Current value for {setting}: {current}\n"
                        f"Valid values: {', '.join(map(str, value_options))}",
                        ephemeral=True
                    )
                    return

                # Validate and update settings
                valid_update = True
                error_message = None

                try:
                    if setting == "units":
                        if value.lower() in ["metric", "imperial"]:
                            server_settings["units"] = value.lower()
                        else:
                            valid_update = False
                            error_message = "Please select either Metric or Imperial"

                    elif setting == "decimal_places":
                        dp = int(value)
                        if 0 <= dp <= 5:
                            server_settings["decimal_places"] = dp
                        else:
                            valid_update = False
                            error_message = "Please select a value between 0 and 5"

                    elif setting == "forecast_days":
                        days = int(value)
                        if 1 <= days <= 5:
                            server_settings["forecast_days"] = days
                        else:
                            valid_update = False
                            error_message = "Please select a value between 1 and 5"

                    if valid_update:
                        # Use transaction for atomic update
                        success = await self.bot.loop.run_in_executor(
                            None,  # Use default executor
                            lambda: self.db.set_server_settings(guild_id, server_settings)
                        )
                        if success:
                            await interaction.response.send_message(f"✅ Updated {setting} to {value}", ephemeral=True)
                        else:
                            await interaction.response.send_message("❌ Failed to save settings", ephemeral=True)
                    else:
                        await interaction.response.send_message(f"❌ {error_message}", ephemeral=True)

                except ValueError:
                    await interaction.response.send_message(f"❌ Invalid value format for {setting}", ephemeral=True)

            except Exception as e:
                logger.error(f"Error in setup command: {e}")
                await interaction.response.send_message("An error occurred while processing your request.", ephemeral=True)

        except Exception as e:
            logger.error(f"Error in setup command: {e}")
            await interaction.response.send_message("An error occurred while processing your request.", ephemeral=True)

    @app_commands.command(name="reset", description="Reset all settings to default values")
    async def reset(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in servers!")
            return

        guild_id = str(interaction.guild.id)
        if self.db.set_server_settings(guild_id, DEFAULT_SETTINGS.copy()):
            embed = discord.Embed(
                title="Settings Reset",
                color=discord.Color.green(),
                description="All settings have been reset to default values:"
            )
            
            for setting, value in DEFAULT_SETTINGS.items():
                embed.add_field(
                    name=setting.replace('_', ' ').title(),
                    value=str(value),
                    inline=True
                )
            
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message("❌ Failed to reset settings")

    @app_commands.command(name="viewsettings", description="View current server settings")
    async def viewsettings(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in servers!")
            return

        settings = self.db.get_server_settings(str(interaction.guild.id))
        
        embed = discord.Embed(
            title="Server Settings",
            color=discord.Color.blue(),
            description="Current weather bot configuration"
        )
        
        for setting, value in settings.items():
            embed.add_field(
                name=setting.replace('_', ' ').title(),
                value=str(value),
                inline=True
            )
            
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Settings(bot))
