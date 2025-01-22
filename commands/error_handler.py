import discord
from discord.ext import commands
from discord import app_commands
import traceback
import logging
import sys

logger = logging.getLogger('weatherbot')

class ErrorHandler(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """Handle command errors"""
        logger.error(f"Command error in {ctx.command}: {error}\n{traceback.format_exc()}")
        await ctx.send(f"An error occurred: {str(error)}")

    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Handle slash command errors"""
        error_msg = f"Error in {interaction.command.name}: {error.__class__.__name__}: {str(error)}"
        trace = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        
        logger.error(f"{error_msg}\nTraceback:\n{trace}")
        
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"❌ {error_msg}\nPlease try again or contact support.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ {error_msg}\nPlease try again or contact support.",
                    ephemeral=True
                )
        except Exception as e:
            logger.error(f"Error sending error message: {e}\n{traceback.format_exc()}")

async def setup(bot: commands.Bot):
    await bot.add_cog(ErrorHandler(bot))
