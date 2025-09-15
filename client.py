import discord


class Client(discord.Client):
    async def on_ready(self):
        print(f"Logged on as {self.user}!")

    async def on_message(self, message):
        if message.author == self.user:
            return

        print(f"Message from {message.author}: {message.content}")

        if message.content.startswith("hello"):
            await message.channel.send("Hello!")
