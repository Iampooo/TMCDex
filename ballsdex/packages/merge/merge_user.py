from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import discord

    from ballsdex.core.bot import BallsDexBot
    from ballsdex.core.models import BallInstance, Player, Merge


@dataclass(slots=True)
class MergingUser:
    user: "discord.User | discord.Member"
    player: "Player"
    proposal: list["BallInstance"] = field(default_factory=list)
    locked: bool = False
    cancelled: bool = False
    accepted: bool = False

    @classmethod
    async def from_merge_model(cls, merge: "Merge", player: "Player", bot: "BallsDexBot"):
        proposal = await merge.mergeobjects.filter(player=player).prefetch_related("ballinstance")
        user = await bot.fetch_user(player.discord_id)
        return cls(user, player, [x.ballinstance for x in proposal])