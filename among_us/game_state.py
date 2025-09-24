from typing import Dict, List, Optional, Set

import discord


class GameState:
    def __init__(self, guild_id: int, channel_id: int):
        self.guild_id = guild_id
        self.channel_id = channel_id

        self.players: List[discord.Member] = []
        self.player_ids: Set[int] = set()

        self.impostor_id: Optional[int] = None
        self.common_word: Optional[str] = None

        self.round_number: int = 0

        self.spoken_this_round: Set[int] = set()
        self.collected_hints: Dict[int, str] = {}

        self.votes: Dict[int, int] = {}

        self.active: bool = True

    def reset_round(self):
        self.round_number += 1
        self.spoken_this_round.clear()
        self.collected_hints.clear()
        self.votes.clear()

    def is_impostor(self, member_id: int) -> bool:
        return member_id == self.impostor_id
