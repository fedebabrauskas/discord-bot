import sys
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
bot_token = os.getenv("BOT_TOKEN")

if not bot_token:
    print(f'The "BOT_TOKEN" environment variable is not set')
    sys.exit(1)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.tree.command(name="hello", description="Says hello to the user.")
async def hello(interaction: discord.Interaction):
    await interaction.response.send_message(f"Hello, {interaction.user.display_name}!")


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    await bot.tree.sync()


bot.run(bot_token)
