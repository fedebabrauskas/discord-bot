import os
import asyncio
import random
from collections import Counter
from typing import Dict, List, Set

import discord
from discord.ext import commands
from dotenv import load_dotenv

from among_us.game_state import GameState
from among_us.constants import *

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

games_by_channel: Dict[int, GameState] = {}

intents = discord.Intents.default()
intents.message_content = True
# intents.members = True
# intents.guilds = True
# intents.dm_messages = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


@bot.command(name="start")
@commands.has_permissions(manage_guild=True)
async def start_cmd(ctx: commands.Context):
    channel = ctx.channel
    if channel.id in games_by_channel and games_by_channel[channel.id].active:
        await ctx.send(
            "⚠️ There's already an active game in this channel. Use `!stop` first or finish the current game."
        )
        return

    # Create a fresh game
    game = GameState(guild_id=ctx.guild.id, channel_id=channel.id)
    games_by_channel[channel.id] = game

    # Open lobby
    lobby_msg = await ctx.send(
        f"🎮 **Fake Among Us** lobby is open! React with {JOIN_EMOJI} within **{LOBBY_SECONDS} seconds** to join.\n"
        f"(I will DM you your secret word, so keep DMs open.)"
    )
    try:
        await lobby_msg.add_reaction(JOIN_EMOJI)
    except discord.Forbidden:
        pass

    # Wait for reactions
    await asyncio.sleep(LOBBY_SECONDS)

    # Fetch updated message to read reactions
    lobby_msg = await channel.fetch_message(lobby_msg.id)
    joined_users: Set[int] = set()

    for reaction in lobby_msg.reactions:
        if str(reaction.emoji) != JOIN_EMOJI:
            continue
        # Users who reacted
        async for user in reaction.users():
            if user.bot:
                continue
            joined_users.add(user.id)

    # Build player list
    players: List[discord.Member] = []
    for uid in joined_users:
        member = ctx.guild.get_member(uid)
        if member and not member.bot:
            players.append(member)

    # Validate player count
    if len(players) < 3:
        game.active = False
        await ctx.send("Not enough players (need at least 3). Game canceled.")
        del games_by_channel[channel.id]
        return

    # Try DM each player to ensure we can reach them
    reachable: List[discord.Member] = []
    for m in players:
        try:
            dm = await m.create_dm()
            await dm.send(f"✅ You joined **Fake Among Us** in **#{channel.name}**!")
            reachable.append(m)
        except discord.Forbidden:
            await ctx.send(
                f"⚠️ I can't DM {m.mention}. They will be removed from this game."
            )
        await asyncio.sleep(0.2)

    if len(reachable) < 3:
        game.active = False
        await ctx.send(
            "Not enough DM-reachable players (need at least 3). Game canceled."
        )
        del games_by_channel[channel.id]
        return

    # Finalize players
    game.players = reachable
    game.player_ids = {p.id for p in reachable}

    # Assign words & impostor
    common_word = random.choice(WORDS)
    impostor = random.choice(game.players)
    game.impostor_id = impostor.id
    game.common_word = common_word

    # DM roles/words
    for p in game.players:
        dm = await p.create_dm()

        if p.id == game.impostor_id:
            await dm.send(
                "🤫 You are the **IMPOSTOR**.\n"
                "Blend in by saying words that *could* relate to the crew's theme."
            )
        else:
            await dm.send(
                "🧑‍🚀 You are **Crew**.\n"
                f"Your secret word is: **{common_word}**\n"
                "In the channel, say **one related word** per round to nudge the crew without giving it away!"
            )
        await asyncio.sleep(0.2)

    await ctx.send(
        f"✅ Game is starting with **{len(game.players)} players**. I've DMed your roles.\n"
        "When the round starts, each player must post **exactly one related word** (any message) in this channel.\n"
        "After all players have spoken, I'll DM you a voting prompt."
    )

    # Begin first round
    await begin_round(ctx, game)


async def begin_round(ctx: commands.Context, game: GameState):
    if not game.active:
        return

    game.reset_round()
    await ctx.send(
        f"🌀 **Round {game.round_number}** begins!\n"
        f"Each player must post **one (1)** word hint now. You have **{ROUND_HINT_TIMEOUT} seconds**.\n"
        f"({len(game.players)} players total)"
    )

    # Wait until all players have spoken OR timeout
    try:
        await asyncio.wait_for(
            wait_for_all_hints(ctx, game), timeout=ROUND_HINT_TIMEOUT
        )
    except asyncio.TimeoutError:
        pass  # proceed with whatever we collected

    # If nobody played, end
    if not game.collected_hints:
        await ctx.send("No hints were submitted. Ending game.")
        await end_game(ctx, game, reveal=False)
        return

    # Announce we are moving to voting
    await ctx.send(
        "🗳️ All hints in (or time is up). Check your DMs to vote for the **impostor**!"
    )

    # Run voting phase
    result = await run_voting_phase(game)
    if result is None:
        await ctx.send("No votes received. Ending game.")
        await end_game(ctx, game, reveal=True)
        return

    top_id, top_count, tally = result
    impostor_caught = top_id == game.impostor_id

    # Announce results
    names = {p.id: p.display_name for p in game.players}
    lines = ["**Voting results:**"]
    for pid, cnt in tally.items():
        lines.append(f"- {names.get(pid, str(pid))}: {cnt}")
    await ctx.send("\n".join(lines))

    if impostor_caught:
        await ctx.send(
            f"🎉 The crew voted out **{names.get(top_id, "Unknown")}** — the **IMPOSTOR**! Crew wins! 🎉"
        )
        await end_game(ctx, game, reveal=True)
    else:
        await ctx.send("😼 The impostor **survives**. A new round begins...")
        await asyncio.sleep(2)
        await begin_round(ctx, game)


async def wait_for_all_hints(ctx: commands.Context, game: GameState):
    """Resolve when all registered players have posted one hint, otherwise return when timeout hits."""
    while game.active and len(game.spoken_this_round) < len(game.players):
        await asyncio.sleep(0.5)


async def end_game(ctx: commands.Context, game: GameState, reveal: bool = True):
    if reveal and game.common_word:
        names = {p.id: p.display_name for p in game.players}
        impostor_name = names.get(game.impostor_id, "Unknown")
        await ctx.send(
            f"🧾 **Reveal**\n"
            f"- Crew word: **{game.common_word}**\n"
            f"- Impostor: **{impostor_name}**"
        )

    game.active = False
    if ctx.channel.id in games_by_channel:
        del games_by_channel[ctx.channel.id]


async def run_voting_phase(game: GameState):
    """DM each player a numbered ballot and collect votes."""
    if not game.active:
        return None

    # Build menu
    candidates = game.players[:]
    index_to_id = {i + 1: m.id for i, m in enumerate(candidates)}

    # Send ballots
    ballot_text = "🗳️ **Vote for the IMPOSTOR**\nReply with the number:\n"
    for i, m in enumerate(candidates, start=1):
        ballot_text += f"{i}. {m.display_name}\n"

    async def dm_and_wait(member: discord.Member):
        try:
            dm = await member.create_dm()
            await dm.send(ballot_text)
        except discord.Forbidden:
            return

        def check(msg: discord.Message):
            if msg.author.id != member.id:
                return False
            if msg.channel.type != discord.ChannelType.private:
                return False
            content = msg.content.strip()
            return content.isdigit() and (1 <= int(content) <= len(candidates))

        try:
            reply: discord.Message = await bot.wait_for(
                "message", check=check, timeout=VOTE_TIMEOUT
            )
        except asyncio.TimeoutError:
            return

        choice = int(reply.content.strip())
        target_id = index_to_id[choice]
        game.votes[member.id] = target_id

    # Collect votes concurrently
    await asyncio.gather(*(dm_and_wait(m) for m in game.players))

    if not game.votes:
        return None

    # Tally
    counts = Counter(game.votes.values())
    # Find top vote-getter (if tie, pick none; continue new round)
    most_common = counts.most_common()
    top_id, top_count = most_common[0]
    if len(most_common) > 1 and most_common[1][1] == top_count:
        # Tie -> nobody ejected
        return (-1, top_count, dict(counts))
    return (top_id, top_count, dict(counts))


@bot.command(name="stop")
@commands.has_permissions(manage_guild=True)
async def stop_cmd(ctx: commands.Context):
    game = games_by_channel.get(ctx.channel.id)
    if not game or not game.active:
        await ctx.send("There's no active game in this channel.")
        return
    game.active = False
    await ctx.send("🛑 Game stopped.")
    del games_by_channel[ctx.channel.id]


@bot.event
async def on_message(message: discord.Message):
    # Let commands run first if it's a command
    if message.author.bot:
        return

    await bot.process_commands(message)

    # Check if this message belongs to an active game round for this channel
    game = games_by_channel.get(message.channel.id)
    if not game or not game.active:
        return

    # Only players, only one message per round, ignore commands
    if message.author.id not in game.player_ids:
        return
    if message.content.startswith("!"):
        return
    if message.author.id in game.spoken_this_round:
        return

    # Record this hint
    game.spoken_this_round.add(message.author.id)
    game.collected_hints[message.author.id] = message.content.strip()

    remain = len(game.players) - len(game.spoken_this_round)
    if remain > 0:
        await message.channel.send(
            f"Noted **{message.author.display_name}**. {remain} to go…"
        )
    else:
        # Everyone submitted – move to voting
        await message.channel.send("All hints received! Starting DM voting…")


@start_cmd.error
async def start_error(ctx: commands.Context, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need **Manage Server** permission to start a game.")
    else:
        await ctx.send(f"Error: {error}")


@stop_cmd.error
async def stop_error(ctx: commands.Context, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need **Manage Server** permission to stop a game.")
    else:
        await ctx.send(f"Error: {error}")


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Please set DISCORD_TOKEN environment variable")
    bot.run(TOKEN)
