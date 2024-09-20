from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, cast

import discord
from discord.ui import Button, View, button

from ballsdex.core.models import BallInstance
from ballsdex.core.models import balls
from ballsdex.packages.merge.display import fill_merge_embed_fields
from ballsdex.packages.merge.merge_user import MergingUser
from ballsdex.settings import settings
from ballsdex.core.utils.transformers import BallTransform

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot
    from ballsdex.packages.merge.cog import Merge as MergeCog

log = logging.getLogger("ballsdex.packages.merge.menu")

recipes = {
    "四君子湯": ["人參", "白朮", "茯苓", "甘草"],
    "四物湯": ["熟地", "當歸", "白芍", "川芎"],
    "八珍湯": ["四君子湯", "四物湯"],
    "十全大補湯": ["八珍湯", "黃耆", "肉桂"],
    "六味地黃丸": ["熟地", "山藥", "茯苓", "牡丹皮"],
    "桂枝湯": ["桂枝", "白芍", "生薑", "甘草", "大棗"],
    "二陳湯": ["陳皮", "半夏", "茯苓", "甘草", "大棗"],
    "黃連解毒湯": ["黃芩", "黃連", "黃柏", "梔子"],
    "龜鹿二仙膠": ["龜龜", "謝一如"],
    "溫婕伶": ["豬苓", "豬苓", "豬苓", "豬苓", "豬苓", "豬苓", "豬苓", "豬苓","豬苓", "豬苓", "豬苓", "豬苓", "豬苓", "豬苓", "豬苓", "豬苓", "豬苓","豬苓", "豬苓", "豬苓", "豬苓", "豬苓", "豬苓", "豬苓", "豬苓",],
    }


class InvalidMergeOperation(Exception):
    pass


class MergeView(View):
    def __init__(self, merge: MergeMenu):
        super().__init__(timeout=60 * 30)
        self.merge = merge

    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        try:
            self.merge._get_merger(interaction.user)
        except RuntimeError:
            await interaction.response.send_message(
                "You are not allowed to interact with this merge.", ephemeral=True
            )
            return False
        else:
            return True

    @button(label="Lock proposal", emoji="\N{LOCK}", style=discord.ButtonStyle.primary)
    async def lock(self, interaction: discord.Interaction, button: Button):
        merger = self.merge._get_merger(interaction.user)
        if merger.locked:
            await interaction.response.send_message(
                "You have already locked your proposal!", ephemeral=True
            )
            return
        await self.merge.lock(merger)
        if self.merge.merger1.locked:
            await interaction.response.send_message(
                "Your proposal has been locked. Now confirm again to end the merge.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "Your proposal has been locked. "
                "You can wait for the other user to lock their proposal.",
                ephemeral=True,
            )

    @button(label="Reset", emoji="\N{DASH SYMBOL}", style=discord.ButtonStyle.secondary)
    async def clear(self, interaction: discord.Interaction, button: Button):
        merger = self.merge._get_merger(interaction.user)
        if merger.locked:
            await interaction.response.send_message(
                "You have locked your proposal, it cannot be edited! "
                "You can click the cancel button to stop the merge instead.",
                ephemeral=True,
            )
        else:
            for countryball in merger.proposal:
                await countryball.unlock()
            merger.proposal.clear()
            await interaction.response.send_message("Proposal cleared.", ephemeral=True)

    @button(
        label="Cancel merge",
        emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}",
        style=discord.ButtonStyle.danger,
    )
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await self.merge.user_cancel(self.merge._get_merger(interaction.user))
        await interaction.response.send_message("Merge has been cancelled.", ephemeral=True)


class ConfirmView(View):
    def __init__(self, merge: MergeMenu):
        super().__init__(timeout=90)
        self.merge = merge

    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        try:
            self.merge._get_merger(interaction.user)
        except RuntimeError:
            await interaction.response.send_message(
                "You are not allowed to interact with this merge.", ephemeral=True
            )
            return False
        else:
            return True

    @discord.ui.button(
        style=discord.ButtonStyle.success, emoji="\N{HEAVY CHECK MARK}\N{VARIATION SELECTOR-16}"
    )
    async def accept_button(self, interaction: discord.Interaction, button: Button):
        merger = self.merge._get_merger(interaction.user)
        if merger.accepted:
            await interaction.response.send_message(
                "You have already accepted this merge.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        result = await self.merge.confirm(merger)
        if self.merge.merger1.accepted:
            if result:
                await interaction.followup.send("You have confirmed your proposal.", ephemeral=True)
            else:
                await interaction.followup.send(
                    ":warning: An error occurred while concluding the merge.", ephemeral=True
                )
        else:
            await interaction.followup.send(
                "You have accepted the merge.", ephemeral=True
            )

    @discord.ui.button(
        style=discord.ButtonStyle.danger,
        emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}",
    )
    async def deny_button(self, interaction: discord.Interaction, button: Button):
        await self.merge.user_cancel(self.merge._get_merger(interaction.user))
        await interaction.response.send_message("Merge has been cancelled.", ephemeral=True)


class MergeMenu:
    def __init__(
        self,
        cog: MergeCog,
        interaction: discord.Interaction["BallsDexBot"],
        merger1: MergingUser,
        ball: BallTransform,
    ):
        self.cog = cog
        self.bot = interaction.client
        self.channel: discord.TextChannel = cast(discord.TextChannel, interaction.channel)
        self.merger1 = merger1
        self.embed = discord.Embed()
        self.task: asyncio.Task | None = None
        self.current_view: MergeView | ConfirmView = MergeView(self)
        self.message: discord.Message
        self.ball = ball

    def _get_merger(self, user: discord.User | discord.Member) -> MergingUser:
        if user.id == self.merger1.user.id:
            return self.merger1

        raise RuntimeError(f"User with ID {user.id} cannot be found in the merge")

    def _generate_embed(self):
        add_command = self.cog.add.extras.get("mention", "`/merge add`")
        remove_command = self.cog.remove.extras.get("mention", "`/merge remove`")

        self.embed.title = f"Try to merge a {self.ball.country}."
        self.embed.color = discord.Colour.blurple()
        self.embed.description = (
            f"Add or remove {settings.collectible_name}s you want to merge "
            f"using the {add_command} and {remove_command} commands.\n"
            "Once you're finished, click the lock button below to confirm your proposal.\n\n"
            "*You have 30 minutes before this interaction ends.*"
        )
        self.embed.set_footer(
            text="This message is updated every 15 seconds, "
            "but you can keep on editing your proposal."
        )

    async def update_message_loop(self):
        """
        A loop task that updates each 5 second the menu with the new content.
        """

        assert self.task
        start_time = datetime.utcnow()

        while True:
            await asyncio.sleep(15)
            if datetime.utcnow() - start_time > timedelta(minutes=15):
                self.embed.colour = discord.Colour.dark_red()
                await self.cancel("The merge timed out")
                return

            try:
                fill_merge_embed_fields(self.embed, self.bot, self.merger1)
                await self.message.edit(embed=self.embed)
            except Exception:
                log.exception(
                    "Failed to refresh the merge menu "
                    f"guild={self.message.guild.id} "  # type: ignore
                    f"merger1={self.merger1.user.id}"
                )
                self.embed.colour = discord.Colour.dark_red()
                await self.cancel("The merge timed out")
                return

    async def start(self):
        """
        Start the merge by sending the initial message and opening up the proposals.
        """
        self._generate_embed()
        fill_merge_embed_fields(self.embed, self.bot, self.merger1)
        self.message = await self.channel.send(
            content=f"{self.merger1.user.mention} is conducting a merge!",
            embed=self.embed,
            view=self.current_view,
        )
        self.task = self.bot.loop.create_task(self.update_message_loop())

    async def cancel(self, reason: str = "The merge has been cancelled."):
        """
        Cancel the merge immediately.
        """
        if self.task:
            self.task.cancel()

        for countryball in self.merger1.proposal:
            await countryball.unlock()

        self.current_view.stop()
        for item in self.current_view.children:
            item.disabled = True  # type: ignore

        fill_merge_embed_fields(self.embed, self.bot, self.merger1)
        self.embed.description = f"**{reason}**"
        await self.message.edit(content=None, embed=self.embed, view=self.current_view)

    async def lock(self, merger: MergingUser):
        """
        Mark a user's proposal as locked, ready for next stage
        """
        merger.locked = True
        if self.merger1.locked:
            if self.task:
                self.task.cancel()
            self.current_view.stop()
            fill_merge_embed_fields(self.embed, self.bot, self.merger1)

            self.embed.colour = discord.Colour.yellow()
            self.embed.description = (
                "You locked your propositions! Now confirm to conclude this merge."
            )
            self.current_view = ConfirmView(self)
            await self.message.edit(content=None, embed=self.embed, view=self.current_view)

    async def user_cancel(self, merger: MergingUser):
        """
        Register a user request to cancel the merge
        """
        merger.cancelled = True
        self.embed.colour = discord.Colour.red()
        await self.cancel()

    async def check_recipe(self, recipe: list):
        if(len(self.merger1.proposal) != len(recipe)):
            return False

        recipe_cp = [ingre for ingre in recipe]

        for cb in self.merger1.proposal:
            bb = cb.countryball
            if(bb.country in recipe_cp):
                recipe_cp.remove(bb.country)

        if(len(recipe_cp) == 0):
            return True

        return False

    async def perform_merge(self):
        # valid_transferable_countryballs: list[BallInstance] = []

        # merge = await Merge.create(player1=self.merger1.player)

        recipe = recipes[self.ball.country]
        success = await self.check_recipe(recipe)
        if(not success):
            self.merger1.cancelled = True
            self.embed.colour = discord.Colour.dark_red()
            for countryball in self.merger1.proposal:
                await countryball.unlock()
                await countryball.save()
            self.merger1.proposal = []
            await self.cancel("Ho Ho Ho, the ingredients are not correct!")
            return

        instance = await BallInstance.create(
            ball=self.ball,
            player=self.merger1.player,
            shiny=(random.randint(1, 2048) == 1),
            attack_bonus=(random.randint(-20, 20)),
            health_bonus=(random.randint(-20, 20)),
            special=None,
        )

        for countryball in self.merger1.proposal:
            await countryball.refresh_from_db()
            await countryball.delete()

        # await interaction.followup.send(
        #     f"`{ball.country}` {settings.collectible_name} was successfully given to `{user}`.\n"
        #     f"Special: `{special.name if special else None}` • ATK:`{instance.attack_bonus:+d}` • "
        #     f"HP:`{instance.health_bonus:+d}` • Shiny: `{instance.shiny}`"
        # )
        # await log_action(
        #     f"{interaction.user} gave {settings.collectible_name} {ball.country} to {user}. "
        #     f"Special={special.name if special else None} ATK={instance.attack_bonus:+d} "
        #     f"HP={instance.health_bonus:+d} shiny={instance.shiny}",
        #     self.bot,
        # )




            # valid_transferable_countryballs.append(countryball)
            # await MergeObject.create(
            #     merge=merge, ballinstance=countryball, player=self.merger1.player
            # )

        # for countryball in self.merger2.proposal:
        #     if countryball.player.discord_id != self.merger2.player.discord_id:
        #         # This is a invalid mutation, the player is not the owner of the countryball
        #         raise InvalidMergeOperation()
        #     countryball.player = self.merger1.player
        #     countryball.merge_player = self.merger2.player
        #     countryball.favorite = False
        #     valid_transferable_countryballs.append(countryball)
        #     await MergeObject.create(
        #         merge=merge, ballinstance=countryball, player=self.merger2.player
        #     )

        # for countryball in valid_transferable_countryballs:
        #     await countryball.unlock()
        #     await countryball.save()

    async def confirm(self, merger: MergingUser) -> bool:
        """
        Mark a user's proposal as accepted. If both user accept, end the merge now

        If the merge is concluded, return True, otherwise if an error occurs, return False
        """
        result = True
        merger.accepted = True
        fill_merge_embed_fields(self.embed, self.bot, self.merger1)
        if self.merger1.accepted:
            if self.task and not self.task.cancelled():
                # shouldn't happen but just in case
                self.task.cancel()

            self.embed.description = "All ingredients added!"
            self.embed.colour = discord.Colour.green()
            self.current_view.stop()
            for item in self.current_view.children:
                item.disabled = True  # type: ignore

            try:
                await self.perform_merge()
            except InvalidMergeOperation:
                log.warning(f"Illegal merge operation of {self.merger1=}")
                self.embed.description = (
                    f":warning: An attempt to modify the {settings.collectible_name}s "
                    "during the merge was detected and the merge was cancelled."
                )
                self.embed.colour = discord.Colour.red()
                result = False
            except Exception:
                log.exception(f"Failed to conclude merge {self.merger1=}")
                self.embed.description = "An error occured when concluding the merge."
                self.embed.colour = discord.Colour.red()
                result = False

        await self.message.edit(content=None, embed=self.embed, view=self.current_view)
        return result