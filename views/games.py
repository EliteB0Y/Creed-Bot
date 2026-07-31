import discord
import asyncio
from datetime import datetime, timezone

class RPSView(discord.ui.View):
    def __init__(self, author_id, emotes, timeout=20.0):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.user_choice = None

        rock_emoji = emotes.get("rpsrock") or "🪨"
        paper_emoji = emotes.get("rpspaper") or "📄"
        scissors_emoji = emotes.get("rpsscissors") or "✂️"

        self.rock_btn.emoji = rock_emoji
        self.paper_btn.emoji = paper_emoji
        self.scissors_btn.emoji = scissors_emoji

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                f"{interaction.client.emotes.get('redtick', '❌')} **This game is not for you!**",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Rock", style=discord.ButtonStyle.primary)
    async def rock_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.user_choice = "rock"
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Paper", style=discord.ButtonStyle.primary)
    async def paper_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.user_choice = "paper"
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Scissors", style=discord.ButtonStyle.primary)
    async def scissors_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.user_choice = "scissors"
        self.stop()
        await interaction.response.defer()


class RPSJoinView(discord.ui.View):
    def __init__(self, host, emotes, timeout=35.0):
        super().__init__(timeout=timeout)
        self.host = host
        self.emotes = emotes
        self.players = {}

        rock_emoji = emotes.get("rpsrock") or "🪨"
        self.join_btn.emoji = rock_emoji

    @discord.ui.button(label="Join RPS Tournament", style=discord.ButtonStyle.success)
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.players:
            await interaction.response.send_message(
                f"{self.emotes.get('redtick', '❌')} **You have already joined this tournament lobby!**",
                ephemeral=True
            )
        else:
            self.players[interaction.user.id] = interaction.user
            await interaction.response.send_message(
                f"{self.emotes.get('greentick', '✅')} **You joined the Rock-Paper-Scissors Tournament!**\n👥 **Total Players in Lobby:** `{len(self.players)}`",
                ephemeral=True
            )

    @discord.ui.button(label="Cancel Tournament", style=discord.ButtonStyle.danger, emoji="🛑")
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        is_allowed = (
            interaction.user.id == self.host.id or
            (hasattr(interaction.client, 'owner_id') and interaction.user.id == interaction.client.owner_id) or
            (hasattr(interaction.user, 'guild_permissions') and interaction.user.guild_permissions.manage_messages)
        )
        if not is_allowed:
            await interaction.response.send_message(f"{self.emotes.get('redtick', '❌')} **Only the tournament host or server moderator can cancel this tournament.**", ephemeral=True)
            return

        game_info = interaction.client.active_games.pop(interaction.channel.id, None)
        if game_info:
            task = game_info.get("task")
            if task and not task.done():
                task.cancel()

        self.stop()
        await interaction.response.send_message(f"🛑 **RPS Tournament was cancelled by {interaction.user.display_name}.**")


class RPSChallengeView(discord.ui.View):
    def __init__(self, challenger, target_user, emotes, timeout=30.0):
        super().__init__(timeout=timeout)
        self.challenger = challenger
        self.target_user = target_user
        self.emotes = emotes
        self.accepted = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.target_user.id:
            await interaction.response.send_message(
                f"{self.emotes.get('redtick', '❌')} **This challenge is not for you!**",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.accepted = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.accepted = False
        self.stop()
        await interaction.response.defer()


class RPSMatchView(discord.ui.View):
    def __init__(self, player1, player2, emotes, timeout=15.0):
        super().__init__(timeout=timeout)
        self.player1 = player1
        self.player2 = player2
        self.emotes = emotes
        self.choices = {}

        rock_emoji = emotes.get("rpsrock") or "🪨"
        paper_emoji = emotes.get("rpspaper") or "📄"
        scissors_emoji = emotes.get("rpsscissors") or "✂️"

        self.rock_btn.emoji = rock_emoji
        self.paper_btn.emoji = paper_emoji
        self.scissors_btn.emoji = scissors_emoji

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id not in (self.player1.id, self.player2.id):
            await interaction.response.send_message(f"{self.emotes.get('redtick', '❌')} **You are not part of this match!**", ephemeral=True)
            return False
        if interaction.user.id in self.choices:
            await interaction.response.send_message(f"{self.emotes.get('redtick', '❌')} **You have already submitted your move for this round!**", ephemeral=True)
            return False
        return True

    async def record_choice(self, interaction: discord.Interaction, choice: str):
        self.choices[interaction.user.id] = choice
        await interaction.response.send_message(
            f"{self.emotes.get('greentick', '✅')} **Move Locked In:** `{choice.title()}`",
            ephemeral=True
        )
        if len(self.choices) == 2:
            self.stop()

    @discord.ui.button(label="Rock", style=discord.ButtonStyle.primary)
    async def rock_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.record_choice(interaction, "rock")

    @discord.ui.button(label="Paper", style=discord.ButtonStyle.primary)
    async def paper_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.record_choice(interaction, "paper")

    @discord.ui.button(label="Scissors", style=discord.ButtonStyle.primary)
    async def scissors_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.record_choice(interaction, "scissors")


class WTPJoinView(discord.ui.View):
    def __init__(self, host, emotes, timeout=35.0):
        super().__init__(timeout=timeout)
        self.host = host
        self.emotes = emotes
        self.players = {}

        pokeball_emoji = emotes.get("pokeball") or "🔴"
        self.join_btn.emoji = pokeball_emoji

    @discord.ui.button(label="Join Game", style=discord.ButtonStyle.success)
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.players:
            await interaction.response.send_message(
                f"{self.emotes.get('redtick', '❌')} **You have already joined this game lobby!**",
                ephemeral=True
            )
        else:
            self.players[interaction.user.id] = interaction.user
            await interaction.response.send_message(
                f"{self.emotes.get('greentick', '✅')} **You joined Who's That Pokémon!**\n👥 **Total Players in Lobby:** `{len(self.players)}`",
                ephemeral=True
            )

    @discord.ui.button(label="Cancel Game", style=discord.ButtonStyle.danger, emoji="🛑")
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        is_allowed = (
            interaction.user.id == self.host.id or
            (hasattr(interaction.client, 'owner_id') and interaction.user.id == interaction.client.owner_id) or
            (hasattr(interaction.user, 'guild_permissions') and interaction.user.guild_permissions.manage_messages)
        )
        if not is_allowed:
            await interaction.response.send_message(f"{self.emotes.get('redtick', '❌')} **Only the game host or server moderator can cancel this game.**", ephemeral=True)
            return

        game_info = interaction.client.active_games.pop(interaction.channel.id, None)
        if game_info:
            task = game_info.get("task")
            if task and not task.done():
                task.cancel()

        self.stop()
        await interaction.response.send_message(f"🛑 **Who's That Pokémon game was cancelled by {interaction.user.display_name}.**")


class PKQuizJoinView(discord.ui.View):
    def __init__(self, host, emotes, timeout=35.0):
        super().__init__(timeout=timeout)
        self.host = host
        self.emotes = emotes
        self.players = {}

        pokeball_emoji = emotes.get("pokeball") or "🔴"
        self.join_btn.emoji = pokeball_emoji

    @discord.ui.button(label="Join Quiz", style=discord.ButtonStyle.success)
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.players:
            await interaction.response.send_message(
                f"{self.emotes.get('redtick', '❌')} **You have already joined this quiz lobby!**",
                ephemeral=True
            )
        else:
            self.players[interaction.user.id] = interaction.user
            await interaction.response.send_message(
                f"{self.emotes.get('greentick', '✅')} **You joined the Pokédex Quiz!**\n👥 **Total Players in Lobby:** `{len(self.players)}`",
                ephemeral=True
            )

    @discord.ui.button(label="Cancel Quiz", style=discord.ButtonStyle.danger, emoji="🛑")
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        is_allowed = (
            interaction.user.id == self.host.id or
            (hasattr(interaction.client, 'owner_id') and interaction.user.id == interaction.client.owner_id) or
            (hasattr(interaction.user, 'guild_permissions') and interaction.user.guild_permissions.manage_messages)
        )
        if not is_allowed:
            await interaction.response.send_message(f"{self.emotes.get('redtick', '❌')} **Only the quiz host or server moderator can cancel this quiz.**", ephemeral=True)
            return

        game_info = interaction.client.active_games.pop(interaction.channel.id, None)
        if game_info:
            task = game_info.get("task")
            if task and not task.done():
                task.cancel()

        self.stop()
        await interaction.response.send_message(f"🛑 **Pokédex Quiz was cancelled by {interaction.user.display_name}.**")


class TimingGameView(discord.ui.View):
    def __init__(self, author_id, timeout=20.0):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.click_time = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                f"{interaction.client.emotes.get('redtick', '❌')} **This game is not for you!**",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="React Now!", emoji="⏱️", style=discord.ButtonStyle.success)
    async def click_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.click_time = datetime.now(timezone.utc)
        self.stop()
        await interaction.response.defer()
