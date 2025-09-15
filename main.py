import sys
import os

import discord
from dotenv import load_dotenv

from client import Client


def main():
    load_dotenv()
    bot_token = os.getenv("BOT_TOKEN")

    if not bot_token:
        print(f'The "BOT_TOKEN" environment variable is not set')
        sys.exit(1)

    intents = discord.Intents.default()
    intents.message_content = True

    client = Client(intents=intents)
    client.run(bot_token)


if __name__ == "__main__":
    main()
