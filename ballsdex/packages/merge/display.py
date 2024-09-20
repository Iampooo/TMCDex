from typing import TYPE_CHECKING, Iterable

import discord

from ballsdex.core.models import Merge as MergeModel
from ballsdex.core.utils import menus
from ballsdex.core.utils.paginator import Pages
from ballsdex.packages.merge.merge_user import MergingUser

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


class MergeViewFormat(menus.ListPageSource):
    def __init__(self, entries: Iterable[MergeModel], header: str, bot: "BallsDexBot"):
        self.header = header
        self.bot = bot
        super().__init__(entries, per_page=1)

    async def format_page(self, menu: Pages, merge: MergeModel) -> discord.Embed:
        embed = discord.Embed(
            title=f"Merge history for {self.header}",
            description=f"Merge ID: {merge.pk:0X}",
            timestamp=merge.date,
        )
        embed.set_footer(
            text=f"Merge {menu.current_page + 1 }/{menu.source.get_max_pages()} | Mrade date: "
        )
        fill_merge_embed_fields(
            embed,
            self.bot,
            await MergingUser.from_merge_model(merge, merge.player1, self.bot),
            await MergingUser.from_merge_model(merge, merge.player2, self.bot),
        )
        return embed


def _get_prefix_emote(merger: MergingUser) -> str:
    if merger.cancelled:
        return "\N{NO ENTRY SIGN}"
    elif merger.accepted:
        return "\N{WHITE HEAVY CHECK MARK}"
    elif merger.locked:
        return "\N{LOCK}"
    else:
        return ""


def _build_list_of_strings(
    merger: MergingUser, bot: "BallsDexBot", short: bool = False
) -> list[str]:
    # this builds a list of strings always lower than 1024 characters
    # while not cutting in the middle of a line
    proposal: list[str] = [""]
    i = 0

    for countryball in merger.proposal:
        cb_text = countryball.description(short=short, include_emoji=True, bot=bot, is_trade=True)
        if merger.locked:
            text = f"- *{cb_text}*\n"
        else:
            text = f"- {cb_text}\n"
        if merger.cancelled:
            text = f"~~{text}~~"

        if len(text) + len(proposal[i]) > 950:
            # move to a new list element
            i += 1
            proposal.append("")
        proposal[i] += text

    if not proposal[0]:
        proposal[0] = "*Empty*"

    return proposal


def fill_merge_embed_fields(
    embed: discord.Embed,
    bot: "BallsDexBot",
    merger1: MergingUser,
    compact: bool = False,
):
    """
    Fill the fields of an embed with the items part of a merge.

    This handles embed limits and will shorten the content if needed.

    Parameters
    ----------
    embed: discord.Embed
        The embed being updated. Its fields are cleared.
    bot: BallsDexBot
        The bot object, used for getting emojis.
    merger1: MergingUser
        The player that initiated the merge, displayed on the left side.
    compact: bool
        If `True`, display countryballs in a compact way. This should not be used directly.
    """
    embed.clear_fields()

    # first, build embed strings
    # to play around the limit of 1024 characters per field, we'll be using multiple fields
    # these vars are list of fields, being a list of lines to include
    merger1_proposal = _build_list_of_strings(merger1, bot, compact)

    # then display the text. first page is easy
    embed.add_field(
        name=f"{_get_prefix_emote(merger1)} {merger1.user.name}",
        value=merger1_proposal[0],
        inline=True,
    )

    if len(merger1_proposal) > 1:
        # we'll have to trick for displaying the other pages
        # fields have to stack themselves vertically
        # to do this, we add a 3rd empty field on each line (since 3 fields per line)
        i = 1
        while i < len(merger1_proposal):
            embed.add_field(name="\u200B", value="\u200B", inline=True)  # empty

            if i < len(merger1_proposal):
                embed.add_field(name="\u200B", value=merger1_proposal[i], inline=True)
            else:
                embed.add_field(name="\u200B", value="\u200B", inline=True)

            i += 1

        # always add an empty field at the end, otherwise the alignment is off
        embed.add_field(name="\u200B", value="\u200B", inline=True)

    if len(embed) > 6000:
        if not compact:
            return fill_merge_embed_fields(embed, bot, merger1, compact=True)
        else:
            embed.clear_fields()
            embed.add_field(
                name=f"{_get_prefix_emote(merger1)} {merger1.user.name}",
                value=f"Merge too long, only showing last page:\n{merger1_proposal[-1]}",
                inline=True,
            )