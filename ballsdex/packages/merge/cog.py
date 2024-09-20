from collections import defaultdict
from typing import TYPE_CHECKING, cast

import discord
from discord import app_commands
from discord.ext import commands
from discord.utils import MISSING
from tortoise.expressions import Q
from tortoise.exceptions import DoesNotExist

from ballsdex.core.models import Player
# from ballsdex.core.models import Merge as MergeModel
from ballsdex.core.utils.buttons import ConfirmChoiceView
from ballsdex.core.utils.paginator import Pages
from ballsdex.core.utils.transformers import (
    BallTransform,
    BallInstanceTransform,
    SpecialEnabledTransform,
    MergeCommandType,
)
from ballsdex.packages.merge.display import MergeViewFormat
from ballsdex.packages.merge.menu import MergeMenu, recipes
from ballsdex.packages.merge.merge_user import MergingUser
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


class Merge(commands.GroupCog):
    """
    Merge countryballs into another
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self.merges: dict[int, dict[int, list[MergeMenu]]] = defaultdict(lambda: defaultdict(list))

    def get_merge(
        self,
        interaction: discord.Interaction | None = None,
        *,
        channel: discord.TextChannel | None = None,
        user: discord.User | discord.Member = MISSING,
    ) -> tuple[MergeMenu, MergingUser] | tuple[None, None]:
        """
        Find an ongoing merge for the given interaction.

        Parameters
        ----------
        interaction: discord.Interaction
            The current interaction, used for getting the guild, channel and author.

        Returns
        -------
        tuple[MergeMenu, MergingUser] | tuple[None, None]
            A tuple with the `MergeMenu` and `MergingUser` if found, else `None`.
        """
        guild: discord.Guild
        if interaction:
            guild = cast(discord.Guild, interaction.guild)
            channel = cast(discord.TextChannel, interaction.channel)
            user = interaction.user
        elif channel:
            guild = channel.guild
        else:
            raise TypeError("Missing interaction or channel")

        if guild.id not in self.merges:
            return (None, None)
        if channel.id not in self.merges[guild.id]:
            return (None, None)
        to_remove: list[MergeMenu] = []
        for merge in self.merges[guild.id][channel.id]:
            if (
                merge.current_view.is_finished()
                or merge.merger1.cancelled
            ):
                # remove what was supposed to have been removed
                to_remove.append(merge)
                continue
            try:
                merger = merge._get_merger(user)
            except RuntimeError:
                continue
            else:
                break
        else:
            for merge in to_remove:
                self.merges[guild.id][channel.id].remove(merge)
            return (None, None)

        for merge in to_remove:
            self.merges[guild.id][channel.id].remove(merge)
        return (merge, merger)

    @app_commands.command()
    async def recipe(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        ball: BallTransform,

    ):
        """
        Show the recipe of a fatfat.

        """

        user = interaction.user

        if(ball.country not in recipes.keys()):
            await interaction.response.send_message(
                f"This {settings.collectible_name} is not able to merge!!", ephemeral=True
            )
            return

        player = await Player.get(discord_id=user.id)

        await player.fetch_related("balls")
        countryballs = await player.balls.all()
        cb_name = list(cb.countryball.country for cb in countryballs)

        _recipe = recipes[ball.country]
        response = f"Recipe of {ball.country}:\n--------------------"

        for ing in _recipe:
            response = response + '\n' + ing + f' (You own {str(cb_name.count(ing))})'

        await interaction.response.send_message(
            response + "\n--------------------", ephemeral=True
        )

        return


    @app_commands.command()
    async def begin(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        ball: BallTransform,
    ):
        """
        Begin a merge.

        """

        merge1, merger1 = self.get_merge(interaction)

        if merge1 or merger1:
            await interaction.response.send_message(
                "You already have an ongoing merge.", ephemeral=True
            )
            return

        if(ball.country not in recipes.keys()):
            await interaction.response.send_message(
                f"This {settings.collectible_name} is not able to merge!!", ephemeral=True
            )
            return

        player1, _ = await Player.get_or_create(discord_id=interaction.user.id)

        menu = MergeMenu(
            self, interaction, MergingUser(interaction.user, player1), ball
        )
        self.merges[interaction.guild.id][interaction.channel.id].append(menu)  # type: ignore
        await menu.start()
        await interaction.response.send_message("Merge started!", ephemeral=True)

    @app_commands.command(extras={"merge": MergeCommandType.PICK})
    async def add(
        self,
        interaction: discord.Interaction,
        countryball: BallInstanceTransform,
        special: SpecialEnabledTransform | None = None,
        shiny: bool | None = None,
    ):
        """
        Add a countryball to the ongoing merge.

        Parameters
        ----------
        countryball: BallInstance
            The countryball you want to add to your proposal
        special: Special
            Filter the results of autocompletion to a special event. Ignored afterwards.
        shiny: bool
            Filter the results of autocompletion to shinies. Ignored afterwards.
        """
        if not countryball:
            return
        # if not countryball.is_tradeable:
        #     await interaction.response.send_message(
        #         "You cannot trade this countryball.", ephemeral=True
        #     )
        #     return
        await interaction.response.defer(ephemeral=True, thinking=True)
        if countryball.favorite:
            view = ConfirmChoiceView(interaction)
            await interaction.followup.send(
                "This countryball is a favorite, are you sure you want to merge it?",
                view=view,
                ephemeral=True,
            )
            await view.wait()
            if not view.value:
                return

        merge, merger = self.get_merge(interaction)
        if not merge or not merger:
            await interaction.followup.send("You do not have an ongoing merge.", ephemeral=True)
            return
        if merger.locked:
            await interaction.followup.send(
                "You have locked your proposal, it cannot be edited! "
                "You can click the cancel button to stop the merge instead.",
                ephemeral=True,
            )
            return
        if countryball in merger.proposal:
            await interaction.followup.send(
                f"You already have this {settings.collectible_name} in your proposal.",
                ephemeral=True,
            )
            return
        if await countryball.is_locked():
            await interaction.followup.send(
                "This countryball is currently in an active merge or donation, "
                "please try again later.",
                ephemeral=True,
            )
            return

        await countryball.lock_for_merge()
        merger.proposal.append(countryball)
        await interaction.followup.send(
            f"{countryball.countryball.country} added.", ephemeral=True
        )

    @app_commands.command(extras={"merge": MergeCommandType.REMOVE})
    async def remove(self, interaction: discord.Interaction, countryball: BallInstanceTransform):
        """
        Remove a countryball from what you proposed in the ongoing merge.

        Parameters
        ----------
        countryball: BallInstance
            The countryball you want to remove from your proposal
        """
        if not countryball:
            return

        merge, merger = self.get_merge(interaction)
        if not merge or not merger:
            await interaction.response.send_message(
                "You do not have an ongoing merge.", ephemeral=True
            )
            return
        if merger.locked:
            await interaction.response.send_message(
                "You have locked your proposal, it cannot be edited! "
                "You can click the cancel button to stop the merge instead.",
                ephemeral=True,
            )
            return
        if countryball not in merger.proposal:
            await interaction.response.send_message(
                f"That {settings.collectible_name} is not in your proposal.", ephemeral=True
            )
            return
        merger.proposal.remove(countryball)
        await interaction.response.send_message(
            f"{countryball.countryball.country} removed.", ephemeral=True
        )
        await countryball.unlock()

    @app_commands.command()
    async def cancel(self, interaction: discord.Interaction):
        """
        Cancel the ongoing merge.
        """
        merge, merger = self.get_merge(interaction)
        if not merge or not merger:
            await interaction.response.send_message(
                "You do not have an ongoing merge.", ephemeral=True
            )
            return

        await merge.user_cancel(merger)
        await interaction.response.send_message("Merge cancelled.", ephemeral=True)

    # @app_commands.command()
    # @app_commands.choices(
    #     sorting=[
    #         app_commands.Choice(name="Most Recent", value="-date"),
    #         app_commands.Choice(name="Oldest", value="date"),
    #     ]
    # )
    # async def history(
    #     self,
    #     interaction: discord.Interaction["BallsDexBot"],
    #     sorting: app_commands.Choice[str],
    # ):
    #     """
    #     Show the history of your merges.

    #     Parameters
    #     ----------
    #     sorting: str
    #         The sorting order of the merges
    #     """
    #     await interaction.response.defer(ephemeral=True, thinking=True)
    #     user = interaction.user

    #     history_queryset = MergeModel.filter(
    #         Q(player1__discord_id=user.id)
    #     )
    #     history = await history_queryset.order_by(sorting.value).prefetch_related(
    #         "player1"
    #     )
    #     if not history:
    #         await interaction.followup.send("No history found.", ephemeral=True)
    #         return
    #     source = MergeViewFormat(history, interaction.user.name, self.bot)
    #     pages = Pages(source=source, interaction=interaction)
    #     await pages.start()