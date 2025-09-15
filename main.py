import sys
import os

import discord
from dotenv import load_dotenv

load_dotenv()
bot_token = os.getenv("BOT_TOKEN")

if not bot_token:
    print(f'The "BOT_TOKEN" environment variable is not set')
    sys.exit(1)

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)


@client.event
async def on_ready():
    print(f"We have logged in as {client.user}")


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content.startswith("hello"):
        await message.channel.send("Hello!")


client.run(bot_token)
