import discord, json, asyncio, random, re
import logging
from discord.ext import commands
from datetime import datetime, timezone

logger = logging.getLogger("CreedBot")

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


class Games(commands.Cog):

    def __init__(self, client):
        self.client = client

    async def _stop_game_in_channel(self, ctx, target_channel=None):
        """Helper to stop active minigame by channel mention/ID or smart fallback."""
        target_channel_id = None

        if target_channel is not None:
            if isinstance(target_channel, discord.TextChannel):
                target_channel_id = target_channel.id
            else:
                digits = re.sub(r"\D", "", str(target_channel))
                if digits:
                    target_channel_id = int(digits)
                else:
                    await ctx.send(f"{self.client.emotes.get('redtick', '❌')} `Invalid channel format. Please specify a channel mention or numeric Channel ID.`")
                    return
        else:
            # 1. Direct match on current channel
            if ctx.channel.id in self.client.active_games:
                target_channel_id = ctx.channel.id
            else:
                # 2. Check if user is host of a game in another channel
                user_hosted = [ch_id for ch_id, info in self.client.active_games.items() if info.get("host_id") == ctx.author.id]
                if len(user_hosted) == 1:
                    target_channel_id = user_hosted[0]
                elif len(self.client.active_games) == 1:
                    # 3. If exactly 1 minigame is active server/bot-wide, target it
                    target_channel_id = list(self.client.active_games.keys())[0]

        if not target_channel_id or target_channel_id not in self.client.active_games:
            if not self.client.active_games:
                await ctx.send(f"{self.client.emotes.get('redtick', '❌')} `No active minigame is currently running in any channel.`")
            else:
                active_list = []
                for cid, info in self.client.active_games.items():
                    ch_obj = self.client.get_channel(cid)
                    ch_name = ch_obj.mention if ch_obj else f"Channel `{cid}`"
                    active_list.append(f"• **{info.get('name', 'Minigame')}** in {ch_name}")
                await ctx.send(
                    f"{self.client.emotes.get('redtick', '❌')} `No active minigame found in this channel.`\n\n"
                    f"🎮 **Currently active games:**\n" + "\n".join(active_list) + "\n\n"
                    f"💡 *Use `!game stop <channel_id>` to stop a specific game.*"
                )
            return

        game_info = self.client.active_games.get(target_channel_id)
        host_id = game_info.get("host_id")
        game_name = game_info.get("name", "Minigame")

        is_allowed = (
            ctx.author.id == self.client.owner_id or
            ctx.author.id == host_id or
            (hasattr(ctx.author, 'guild_permissions') and ctx.author.guild_permissions.manage_messages)
        )
        if not is_allowed:
            await ctx.send(f"{self.client.emotes.get('redtick', '❌')} `Only the game host, server moderators, or bot owner can stop this game.`")
            return

        # Pop from active games dictionary
        self.client.active_games.pop(target_channel_id, None)

        # Cancel game task if active
        task = game_info.get("task")
        if task and not task.done() and task != asyncio.current_task():
            task.cancel()

        target_ch_obj = self.client.get_channel(target_channel_id)
        ch_str = target_ch_obj.mention if target_ch_obj else f"Channel ID `{target_channel_id}`"
        await ctx.send(f"{self.client.emotes.get('greentick', '✅')} **{game_name} in {ch_str} has been stopped by {ctx.author.display_name}.**")

    @commands.group(invoke_without_command=True, aliases=["games"])
    @commands.guild_only()
    async def game(self, ctx):
        """Minigame manager and controls."""
        if ctx.invoked_subcommand is None:
            embed = discord.Embed(
                title="🎮 CreedBot Minigames Manager",
                description=(
                    "**Available Commands:**\n"
                    "• `!game stop [channel]` (or `!stopgame`) — Stop active minigame (in current or specified channel)\n"
                    "• `!game status` — Check active minigames across all channels/servers\n\n"
                    "**Available Games:**\n"
                    "• `!wtp` / `!wtp start [count=10]` — Who's That Pokémon\n"
                    "• `!pkquiz` / `!pkquiz start [count=10]` — Pokédex Entry Quiz\n"
                    "• `!rps` / `!rps start` — Rock-Paper-Scissors Tournament"
                ),
                color=discord.Color.gold()
            )
            embed.set_footer(text=f"Requested by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)

    @game.command(name="stop", aliases=["end", "cancel", "quit"])
    @commands.guild_only()
    async def game_stop(self, ctx, *, channel: str = None):
        """Stops minigame in current channel or specified channel ID / mention."""
        await self._stop_game_in_channel(ctx, target_channel=channel)

    @game.command(name="status", aliases=["list"])
    @commands.guild_only()
    async def game_status(self, ctx, *, channel: str = None):
        """Check active minigames across all channels/servers or in a specific channel."""
        if channel is not None:
            target_channel_id = ctx.channel.id
            if isinstance(channel, discord.TextChannel):
                target_channel_id = channel.id
            else:
                digits = re.sub(r"\D", "", str(channel))
                if digits:
                    target_channel_id = int(digits)
                else:
                    await ctx.send(f"{self.client.emotes.get('redtick', '❌')} `Invalid channel format. Please specify a channel mention or numeric Channel ID.`")
                    return

            info = self.client.active_games.get(target_channel_id)
            if not info:
                await ctx.send(f"ℹ️ `No active minigame is currently running in channel ID {target_channel_id}.`")
                return

            embed = discord.Embed(title="🎮 Active Minigame Status", color=discord.Color.blue())
            ch_obj = self.client.get_channel(target_channel_id)
            if ch_obj:
                ch_str = f"{ch_obj.mention} (`{target_channel_id}`)"
                guild_str = f" in **{ch_obj.guild.name}**"
            else:
                ch_str = f"Channel ID `{target_channel_id}`"
                guild_str = ""

            embed.description = f"• **{info.get('name', 'Minigame')}**{guild_str} — Channel {ch_str} (Host: <@{info.get('host_id')}>)"
            embed.set_footer(text=f"To stop this game: !game stop {target_channel_id}", icon_url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)
            return

        if not self.client.active_games:
            await ctx.send(f"ℹ️ `No active minigames are running right now.`")
            return

        embed = discord.Embed(title="🎮 Active Minigames Status", color=discord.Color.blue())
        lines = []
        for ch_id, info in self.client.active_games.items():
            channel_obj = self.client.get_channel(ch_id)
            if channel_obj:
                ch_str = f"{channel_obj.mention} (`{ch_id}`)"
                guild_str = f" in **{channel_obj.guild.name}**"
            else:
                ch_str = f"Channel ID `{ch_id}`"
                guild_str = ""
            lines.append(f"• **{info.get('name', 'Minigame')}**{guild_str} — Channel {ch_str} (Host: <@{info.get('host_id')}>)")

        embed.description = "\n".join(lines) if lines else "No active minigames running."
        embed.set_footer(text="To stop a game remotely: !game stop <channel_id>", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="stopgame", aliases=["cancelgame", "endgame"])
    @commands.guild_only()
    async def stopgame_cmd(self, ctx, *, channel: str = None):
        """Universal command to stop any active minigame in current or specified channel."""
        await self._stop_game_in_channel(ctx, target_channel=channel)

    
    @commands.group()
    @commands.guild_only()
    async def wtp(self, ctx):
        """Who's that pokemon game."""
        if ctx.invoked_subcommand is None:
            embed = discord.Embed(color=discord.Color.gold())
            embed.set_author(name="Minigame: Who's that Pokémon?", icon_url="https://i.imgur.com/MItw5zU.png")
            desc = "```This is a multiplayer minigame where you guess the Pokémon name!\nIncludes Pokémon from 8 generations (896 Pokémons).```"
            rules = (
                "```1. Click 'Join Game' during the 30-second lobby to join.\n"
                "2. You have 15 seconds to guess the Pokémon name each round.\n"
                "3. The first participant to type the correct name wins the round point.\n"
                "4. Only English names are allowed (Case Insensitive).\n"
                "5. Player with the highest score at the end of all rounds wins!\n```"
            )
            embed.description = desc
            embed.add_field(name="Rules:", value=rules)
            embed.add_field(name="Good Luck!", value="\u200b", inline=False)
            embed.set_image(url="https://i.imgur.com/yAz3xCI.jpg")
            embed.set_footer(text= "To Start the Game | wtp start [count=10]", icon_url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)
            return

    @wtp.command(name='stop', aliases=['end', 'cancel', 'quit'])
    @commands.guild_only()
    async def wtp_stop(self, ctx, *, channel: str = None):
        """Stops an ongoing Who's That Pokémon game in current or specified channel."""
        await self._stop_game_in_channel(ctx, target_channel=channel)

    @wtp.command(name = 'start')
    @commands.guild_only()
    async def wtp_start(self, ctx, *, args: str = "10"):
        """Starts Who's That Pokémon minigame. Usage: !wtp start [count=10]"""
        if ctx.channel.id in self.client.active_games:
            game_name = self.client.active_games[ctx.channel.id].get("name", "minigame")
            await ctx.send(f"{self.client.emotes.get('redtick', '❌')} `A {game_name} is already running in this channel!`")
            return

        # Parse count argument (e.g. 10 or count=10)
        count = 10
        cleaned_args = args.replace("count=", "").strip()
        try:
            count = int(cleaned_args)
        except ValueError:
            count = 10

        if count < 1 or count > 50:
            await ctx.send(f"{self.client.emotes.get('redtick', '❌')} `Number of pokemons must be between 1 and 50.`")
            return

        self.client.active_games[ctx.channel.id] = {
            "name": "Who's That Pokémon",
            "type": "wtp",
            "host_id": ctx.author.id,
            "task": asyncio.current_task()
        }

        lobby_ended = False
        try:
            # 1. Open 30-second lobby window
            lobby_end_time = int(datetime.now(timezone.utc).timestamp()) + 30
            join_view = WTPJoinView(ctx.author, self.client.emotes, timeout=35.0)
            embed = discord.Embed(
                title="🎮 Who's That Pokémon — Lobby Open!",
                description=(
                    f"**{ctx.author.display_name}** is starting a WTP game with **{count} Pokémon(s)**!\n\n"
                    f"Click **Join Game** below to participate! Game starts <t:{lobby_end_time}:R>."
                ),
                color=discord.Color.gold()
            )
            embed.set_thumbnail(url="https://i.imgur.com/MItw5zU.png")
            embed.set_footer(text=f"Hosted by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)

            lobby_msg = await ctx.send(embed=embed, view=join_view)

            # Check for early cancellation during 30s lobby
            for _ in range(30):
                if ctx.channel.id not in self.client.active_games:
                    join_view.stop()
                    for child in join_view.children:
                        child.disabled = True
                    cancel_embed = discord.Embed(
                        title="🎮 Who's That Pokémon — Stopped",
                        description="Game was stopped by host or administrator.",
                        color=discord.Color.red()
                    )
                    await lobby_msg.edit(embed=cancel_embed, view=join_view)
                    return
                await asyncio.sleep(1)

            # Close lobby & disable buttons
            join_view.stop()
            for child in join_view.children:
                child.disabled = True

            players = join_view.players
            if not players:
                cancel_embed = discord.Embed(
                    title="🎮 Who's That Pokémon — Cancelled",
                    description="No participants joined the game! Game cancelled.",
                    color=discord.Color.red()
                )
                cancel_embed.set_thumbnail(url="https://i.imgur.com/MItw5zU.png")
                await lobby_msg.edit(embed=cancel_embed, view=join_view)
                return

            player_names = " • ".join([f"`{p.display_name}`" for p in players.values()])
            lobby_url = lobby_msg.jump_url

            game_start_time = int(datetime.now(timezone.utc).timestamp()) + 5
            start_embed = discord.Embed(
                title="🎮 Who's That Pokémon — Game Starting!",
                description=f"👥 **{len(players)} Player(s) registered:**\n{player_names}\n\nGet ready! Round 1 is starting <t:{game_start_time}:R>...",
                color=discord.Color.green()
            )
            start_embed.set_thumbnail(url="https://i.imgur.com/MItw5zU.png")
            await lobby_msg.edit(embed=start_embed, view=join_view)
            lobby_ended = True
            await asyncio.sleep(5)

            # Load Pokémon dataset
            with open('./files/wtpNames.json', 'r') as f:
                wtpData = json.load(f)

            scores = {p_id: 0 for p_id in players}
            round_time = 15.0

            for current_round in range(1, count + 1):
                if ctx.channel.id not in self.client.active_games:
                    break

                pokeID = random.randrange(1, 897)
                wtpPoke = wtpData.get(f"{pokeID}")
                pokeName = wtpPoke["name"].lower().strip()
                pokeImgOrg = f"https://github.com/EliteB0Y/TestBot/raw/master/WTP/{pokeID:03d}.png"
                pokeImgWtp = f"https://github.com/EliteB0Y/TestBot/raw/master/WTP/{pokeID:03d}x.png"

                round_end_time = int(datetime.now(timezone.utc).timestamp()) + 15
                embed = discord.Embed(
                    title=f"Round {current_round}/{count} — Who's that Pokémon?",
                    description=f"Guessing ends <t:{round_end_time}:R>!",
                    color=discord.Color.blurple()
                )
                embed.set_author(name="Who's that Pokémon?", icon_url="https://i.imgur.com/MItw5zU.png")
                embed.set_image(url=pokeImgWtp)
                embed.set_footer(text=f"Round {current_round} of {count}")

                round_msg = await ctx.send(embed=embed)

                def check(message):
                    if message.channel.id != ctx.channel.id:
                        return False

                    # Check if stop requested
                    if message.content.lower().strip() in ["!game stop", "!stopgame", "!wtp stop", "wtp stop", "!wtp end", "!wtp cancel"]:
                        game_info = self.client.active_games.get(ctx.channel.id)
                        host_id = game_info.get("host_id") if game_info else None
                        is_allowed = (
                            message.author.id == self.client.owner_id or
                            message.author.id == host_id or
                            (hasattr(message.author, 'guild_permissions') and message.author.guild_permissions.manage_messages)
                        )
                        if is_allowed:
                            self.client.active_games.pop(ctx.channel.id, None)
                            return True

                    return message.author.id in players and message.content.lower().strip() == pokeName

                try:
                    msg = await self.client.wait_for('message', timeout=round_time, check=check)
                except asyncio.TimeoutError:
                    if ctx.channel.id not in self.client.active_games:
                        break
                    embed.title = f"Round {current_round}/{count} — Time's Up!"
                    embed.description = f"{self.client.emotes.get('redtick', '❌')} Nobody guessed **{wtpPoke['name'].title()}**!"
                    embed.set_image(url=pokeImgOrg)
                    embed.color = discord.Color.red()
                    await round_msg.edit(embed=embed)
                else:
                    if ctx.channel.id not in self.client.active_games:
                        break
                    if msg.content.lower().strip() == pokeName:
                        scores[msg.author.id] += 1
                        embed.title = f"Round {current_round}/{count} — Correct!"
                        embed.description = f"{self.client.emotes.get('greentick', '✅')} **{msg.author.display_name}** guessed it correctly! It's **{wtpPoke['name'].title()}**!"
                        embed.set_image(url=pokeImgOrg)
                        embed.color = discord.Color.green()
                        await round_msg.edit(embed=embed)

                if current_round < count:
                    if ctx.channel.id not in self.client.active_games:
                        break
                    await asyncio.sleep(5)

            # Final Leaderboard (if not forcibly stopped early)
            if ctx.channel.id in self.client.active_games:
                sorted_scores = sorted(scores.items(), key=lambda item: item[1], reverse=True)

                lb_embed = discord.Embed(
                    title="🏆 Who's That Pokémon — Final Leaderboard",
                    color=discord.Color.gold()
                )
                lb_embed.set_thumbnail(url="https://i.imgur.com/MItw5zU.png")

                lb_lines = []
                medals = ["🥇", "🥈", "🥉"]
                for rank, (p_id, score) in enumerate(sorted_scores, 1):
                    user = players.get(p_id)
                    name = user.display_name if user else f"User {p_id}"
                    medal = medals[rank - 1] if rank <= 3 else f"`#{rank}`"
                    lb_lines.append(f"{medal} **{name}**: `{score}` point(s)")

                scores_str = "\n".join(lb_lines) if lb_lines else "No participants scored points!"
                lb_embed.description = f"🔗 [**Jump to Game Lobby**]({lobby_url})\n\n{scores_str}"
                lb_embed.set_footer(text=f"Game Over | Total Rounds: {count}", icon_url=ctx.author.display_avatar.url)

                await ctx.send(embed=lb_embed)

        except asyncio.CancelledError:
            if not lobby_ended and 'join_view' in locals() and 'lobby_msg' in locals():
                try:
                    join_view.stop()
                    for child in join_view.children:
                        child.disabled = True
                    cancel_embed = discord.Embed(
                        title="🎮 Who's That Pokémon — Stopped",
                        description="Game was stopped by host or administrator.",
                        color=discord.Color.red()
                    )
                    cancel_embed.set_thumbnail(url="https://i.imgur.com/MItw5zU.png")
                    await lobby_msg.edit(embed=cancel_embed, view=join_view)
                except Exception:
                    pass
        finally:
            self.client.active_games.pop(ctx.channel.id, None)
        
    @commands.command(name = "10s")
    @commands.guild_only()
    async def _10s(self, ctx):
        """Test your timing by reacting at 10 sec exact!"""
        embed = discord.Embed()
        embed.set_author(name="Reaction Game", icon_url=ctx.me.display_avatar.url)
        embed.description = 'Click the button below in exact 10 seconds.\n'
        embed.set_footer(text=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        
        view = TimingGameView(ctx.author.id, timeout=20.0)
        t1 = datetime.now(timezone.utc)
        x = await ctx.send(embed=embed, view=view)
        await view.wait()

        if view.click_time is None:
            embed.description += "\nYour seconds counting sucks for real! 😂"
            await x.edit(embed=embed, view=None)
        else:
            tm = view.click_time - t1
            embed.description += f"\nYou have reacted in `{round(tm.total_seconds(), 2)}` seconds."
            await x.edit(embed=embed, view=None)

    @commands.command()
    @commands.guild_only()
    async def guess(self, ctx):
        """Number guessing game"""
        myGuess = random.randrange(1,10)
        embed = discord.Embed()
        embed.set_author(name="Guess the Number?", icon_url=ctx.me.display_avatar.url)
        embed.description = f"```Hello {ctx.author.name},\nI have guessed a number between 1 to 10. Let's see if you can guess the same number within 5 turns.```"
        embed.set_footer(text = ctx.author, icon_url = ctx.author.display_avatar.url)
        await ctx.send(embed=embed)
        
        def check(message):
            return message.author == ctx.author and message.channel.id == ctx.channel.id
        
        for i in range(5):
            try:
                message = await self.client.wait_for('message', check=check, timeout=20)
            except asyncio.TimeoutError:
                embed.description = "```You took too long to guess the number!```"
                return await ctx.send(embed=embed)
            else:
                if message.content != str(myGuess):
                    if i == 4:
                        embed.description = f"{self.client.emotes.get('redtick','')}`Oops!! No turns left. My guess was {myGuess}.`"
                        return await ctx.send(embed=embed)
                    embed.description = f"{self.client.emotes.get('redtick','')}`Nope, that's not it. You have {5-(i+1)} turns left!`"
                    await ctx.send(embed=embed)
                else:
                    embed.description = f"{self.client.emotes.get('greentick','')}`YAY!!! {myGuess} it is... You took {i+1} attempt(s) to guess the number!`"
                    return await ctx.send(embed=embed)
    
    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    async def rps(self, ctx):
        """Rock-Paper-Scissors game."""
        if ctx.invoked_subcommand is None:
            embed = discord.Embed(color=discord.Color.gold())
            embed.set_author(name="Minigame: Rock-Paper-Scissors", icon_url=ctx.me.display_avatar.url)
            desc = "```Play Rock-Paper-Scissors against the bot, challenge a friend, or join a multiplayer tournament!```"
            rules = (
                "```1. Use '!rps solo' to play a quick 1v1 game against the bot.\n"
                "2. Use '!rps duo @user' to challenge another player to a 1v1 duel.\n"
                "3. Use '!rps start' to launch a multiplayer tournament lobby (30s).\n"
                "4. Tournament: Players are paired each round to make a move (15s limit).\n"
                "5. Tournament: Losers are eliminated, while winners and tied players advance. Last player standing wins!```"
            )
            embed.description = desc
            embed.add_field(name="Game Modes & Rules:", value=rules)
            embed.set_footer(text="Solo: !rps solo | Duo: !rps duo @user | Tournament: !rps start", icon_url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)

    @rps.command(name='solo', aliases=['bot'])
    @commands.guild_only()
    async def rps_solo(self, ctx):
        """Play 1v1 Rock-Paper-Scissors against the bot."""
        options = ["rock", "paper", "scissors"]
        mine = random.choice(options)
        emoji_map = {
            "rock": self.client.emotes.get("rpsrock", "🪨"),
            "paper": self.client.emotes.get("rpspaper", "📄"),
            "scissors": self.client.emotes.get("rpsscissors", "✂️"),
        }

        embed = discord.Embed(color=discord.Color.blurple())
        embed.set_author(name="Rock Paper Scissors!", icon_url=ctx.me.display_avatar.url)
        embed.description = "🎮 **Rock-Paper-Scissors!**\n\nI have made my choice! Pick yours by clicking a button below to see who wins!"
        embed.set_footer(text=f"Requested by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)

        view = RPSView(ctx.author.id, self.client.emotes, timeout=20.0)
        x = await ctx.send(embed=embed, view=view)
        await view.wait()

        if view.user_choice is None:
            embed.color = discord.Color.dark_gray()
            embed.description = f"{self.client.emotes.get('timer', '⏱️')} You lost the Rock-Paper-Scissors game due to inactivity..."
            return await x.edit(embed=embed, view=None)

        yours = view.user_choice
        if yours == mine:
            result = "It's a draw!"
            embed.color = discord.Color.gold()
        elif (yours == "rock" and mine == "scissors") or (yours == "paper" and mine == "rock") or (yours == "scissors" and mine == "paper"):
            result = "Oh Noo!! You have won. I'll get you next time..."
            embed.color = discord.Color.green()
        else:
            result = "Haha, You have lost this one."
            embed.color = discord.Color.red()

        embed.description = (
            f"**Your choice:** {emoji_map[yours]} **{yours.title()}**\n"
            f"**My choice:** {emoji_map[mine]} **{mine.title()}**\n\n"
            f"**{result}**"
        )
        await x.edit(embed=embed, view=None)

    @rps.command(name='duo')
    @commands.guild_only()
    async def rps_duo(self, ctx, target_user: discord.Member):
        """Challenge another user to a 1v1 Rock-Paper-Scissors game."""
        if target_user.bot:
            await ctx.send(f"{self.client.emotes.get('redtick', '❌')} **You cannot challenge a bot!**")
            return
        if target_user.id == ctx.author.id:
            await ctx.send(f"{self.client.emotes.get('redtick', '❌')} **You cannot challenge yourself!**")
            return

        embed = discord.Embed(
            title="⚔️ RPS Challenge!",
            description=f"**{ctx.author.display_name}** has challenged **{target_user.display_name}** to a Rock-Paper-Scissors game!\n\nDo you accept the challenge, {target_user.mention}?",
            color=discord.Color.blurple()
        )
        embed.set_footer(text=f"Challenged by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)

        challenge_view = RPSChallengeView(ctx.author, target_user, self.client.emotes, timeout=30.0)
        challenge_msg = await ctx.send(embed=embed, view=challenge_view)
        await challenge_view.wait()

        if challenge_view.accepted is None:
            embed.color = discord.Color.dark_gray()
            embed.description = f"⏱️ Challenge timed out..."
            await challenge_msg.edit(embed=embed, view=None)
            return

        if not challenge_view.accepted:
            embed.color = discord.Color.red()
            embed.description = f"{self.client.emotes.get('redtick', '❌')} **{target_user.display_name}** declined the challenge."
            await challenge_msg.edit(embed=embed, view=None)
            return

        # Game starts!
        emoji_map = {
            "rock": self.client.emotes.get("rpsrock", "🪨"),
            "paper": self.client.emotes.get("rpspaper", "📄"),
            "scissors": self.client.emotes.get("rpsscissors", "✂️"),
        }

        match_end_time = int(datetime.now(timezone.utc).timestamp()) + 15
        match_view = RPSMatchView(ctx.author, target_user, self.client.emotes, timeout=15.0)

        match_embed = discord.Embed(
            title="⚔️ RPS Duo Match!",
            description=(
                f"🤼 **{ctx.author.display_name}** vs **{target_user.display_name}**\n\n"
                f"Click your choice below! Time ends <t:{match_end_time}:R>."
            ),
            color=discord.Color.blurple()
        )
        match_embed.set_footer(text=f"RPS Duo Game", icon_url=ctx.author.display_avatar.url)

        # Ping both players outside the embed
        await challenge_msg.edit(content=f"{ctx.author.mention} vs {target_user.mention}", embed=match_embed, view=match_view)
        await match_view.wait()

        # Disable buttons
        for child in match_view.children:
            child.disabled = True

        c1 = match_view.choices.get(ctx.author.id)
        c2 = match_view.choices.get(target_user.id)

        # Evaluate outcome
        if c1 and c2:
            c1_emoji = emoji_map.get(c1, "❓")
            c2_emoji = emoji_map.get(c2, "❓")
            if c1 == c2:
                result = "It's a draw!"
                match_embed.color = discord.Color.gold()
            elif (c1 == "rock" and c2 == "scissors") or (c1 == "paper" and c2 == "rock") or (c1 == "scissors" and c2 == "paper"):
                result = f"🏆 **{ctx.author.display_name}** wins!"
                match_embed.color = discord.Color.green()
            else:
                result = f"🏆 **{target_user.display_name}** wins!"
                match_embed.color = discord.Color.green()
            
            match_embed.description = (
                f"**{ctx.author.display_name}'s choice:** {c1_emoji} **{c1.title()}**\n"
                f"**{target_user.display_name}'s choice:** {c2_emoji} **{c2.title()}**\n\n"
                f"**{result}**"
            )
        elif c1 and not c2:
            c1_emoji = emoji_map.get(c1, "❓")
            match_embed.description = (
                f"**{ctx.author.display_name}'s choice:** {c1_emoji} **{c1.title()}**\n"
                f"⏱️ **{target_user.display_name}** timed out!\n\n"
                f"🏆 **{ctx.author.display_name}** wins!"
            )
            match_embed.color = discord.Color.green()
        elif c2 and not c1:
            c2_emoji = emoji_map.get(c2, "❓")
            match_embed.description = (
                f"⏱️ **{ctx.author.display_name}** timed out!\n"
                f"**{target_user.display_name}'s choice:** {c2_emoji} **{c2.title()}**\n\n"
                f"🏆 **{target_user.display_name}** wins!"
            )
            match_embed.color = discord.Color.green()
        else:
            match_embed.description = (
                f"⏱️ Both **{ctx.author.display_name}** and **{target_user.display_name}** timed out!\n\n"
                f"**No one wins.**"
            )
            match_embed.color = discord.Color.red()

        match_embed.title = "⚔️ RPS Duo Match — Results!"
        # Clear content (remove pings)
        await challenge_msg.edit(content=None, embed=match_embed, view=None)

    @rps.command(name='stop', aliases=['end', 'cancel', 'quit'])
    @commands.guild_only()
    async def rps_stop(self, ctx, *, channel: str = None):
        """Stops an ongoing Rock-Paper-Scissors tournament in current or specified channel."""
        await self._stop_game_in_channel(ctx, target_channel=channel)

    @rps.command(name='start')
    @commands.guild_only()
    async def rps_start(self, ctx):
        """Starts a multiplayer Rock-Paper-Scissors tournament."""
        if ctx.channel.id in self.client.active_games:
            game_name = self.client.active_games[ctx.channel.id].get("name", "minigame")
            await ctx.send(f"{self.client.emotes.get('redtick', '❌')} `A {game_name} is already running in this channel!`")
            return

        self.client.active_games[ctx.channel.id] = {
            "name": "Rock-Paper-Scissors Tournament",
            "type": "rps",
            "host_id": ctx.author.id,
            "task": asyncio.current_task()
        }

        lobby_ended = False
        try:
            # 1. 30-second lobby window
            lobby_end_time = int(datetime.now(timezone.utc).timestamp()) + 30
            join_view = RPSJoinView(ctx.author, self.client.emotes, timeout=35.0)
            embed = discord.Embed(
                title="🎮 RPS Tournament — Lobby Open!",
                description=(
                    f"**{ctx.author.display_name}** is starting a Rock-Paper-Scissors Tournament!\n\n"
                    f"Click **Join RPS Tournament** below to enter! Tournament starts <t:{lobby_end_time}:R>."
                ),
                color=discord.Color.gold()
            )
            embed.set_thumbnail(url=ctx.me.display_avatar.url)
            embed.set_footer(text=f"Hosted by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)

            lobby_msg = await ctx.send(embed=embed, view=join_view)

            # Check for cancellation during 30s lobby
            for _ in range(30):
                if ctx.channel.id not in self.client.active_games:
                    join_view.stop()
                    for child in join_view.children:
                        child.disabled = True
                    cancel_embed = discord.Embed(
                        title="🎮 RPS Tournament — Stopped",
                        description="Tournament was stopped by host or administrator.",
                        color=discord.Color.red()
                    )
                    await lobby_msg.edit(embed=cancel_embed, view=join_view)
                    return
                await asyncio.sleep(1)

            join_view.stop()
            for child in join_view.children:
                child.disabled = True

            active_players = list(join_view.players.values())
            if len(active_players) < 2:
                cancel_embed = discord.Embed(
                    title="🎮 RPS Tournament — Cancelled",
                    description="At least 2 players are required to start the tournament! Tournament cancelled.",
                    color=discord.Color.red()
                )
                cancel_embed.set_thumbnail(url=ctx.me.display_avatar.url)
                await lobby_msg.edit(embed=cancel_embed, view=join_view)
                return

            player_names = " • ".join([f"`{p.display_name}`" for p in active_players])
            lobby_url = lobby_msg.jump_url

            game_start_time = int(datetime.now(timezone.utc).timestamp()) + 5
            start_embed = discord.Embed(
                title="🎮 RPS Tournament — Starting!",
                description=f"👥 **{len(active_players)} Player(s) registered:**\n{player_names}\n\nRound 1 pairings starting <t:{game_start_time}:R>...",
                color=discord.Color.green()
            )
            start_embed.set_thumbnail(url=ctx.me.display_avatar.url)
            await lobby_msg.edit(embed=start_embed, view=join_view)
            lobby_ended = True
            await asyncio.sleep(5)

            round_num = 1
            max_rounds = 10
            emoji_map = {
                "rock": self.client.emotes.get("rpsrock", "🪨"),
                "paper": self.client.emotes.get("rpspaper", "📄"),
                "scissors": self.client.emotes.get("rpsscissors", "✂️"),
            }

            while len(active_players) > 1 and round_num <= max_rounds:
                if ctx.channel.id not in self.client.active_games:
                    break

                random.shuffle(active_players)
                next_round_players = []
                free_passes = []

                # Group into pairs of 2
                pairs = []
                for i in range(0, len(active_players), 2):
                    if i + 1 < len(active_players):
                        pairs.append((active_players[i], active_players[i + 1]))
                    else:
                        free_passes.append(active_players[i])

                # Process free passes
                for pass_player in free_passes:
                    next_round_players.append(pass_player)
                    await ctx.send(f"ℹ️ {pass_player.mention} gets a free pass for Round {round_num} and automatically advances to the next round!")

                for match_idx, (p1, p2) in enumerate(pairs, 1):
                    if ctx.channel.id not in self.client.active_games:
                        break

                    match_end_time = int(datetime.now(timezone.utc).timestamp()) + 15
                    match_view = RPSMatchView(p1, p2, self.client.emotes, timeout=15.0)

                    match_embed = discord.Embed(
                        title=f"⚔️ Round {round_num} — Match {match_idx}/{len(pairs)}",
                        description=(
                            f"🤼 **{p1.display_name}** vs **{p2.display_name}**\n\n"
                            f"Click your choice below! Time ends <t:{match_end_time}:R>."
                        ),
                        color=discord.Color.blurple()
                    )
                    match_embed.set_footer(text=f"Round {round_num} | Match {match_idx}")
                    match_msg = await ctx.send(content=f"{p1.mention} vs {p2.mention}", embed=match_embed, view=match_view)

                    await match_view.wait()

                    if ctx.channel.id not in self.client.active_games:
                        break

                    # Disable buttons
                    for child in match_view.children:
                        child.disabled = True

                    c1 = match_view.choices.get(p1.id)
                    c2 = match_view.choices.get(p2.id)

                    # Evaluate outcome
                    if c1 and c2:
                        res_desc = f"**{p1.display_name}** chose {emoji_map[c1]} **{c1.title()}**\n**{p2.display_name}** chose {emoji_map[c2]} **{c2.title()}**\n\n"
                        if c1 == c2:
                            res_desc += f"🤝 **It's a tie!** Both **{p1.display_name}** and **{p2.display_name}** advance!"
                            next_round_players.extend([p1, p2])
                            match_embed.color = discord.Color.gold()
                        elif (c1 == "rock" and c2 == "scissors") or (c1 == "paper" and c2 == "rock") or (c1 == "scissors" and c2 == "paper"):
                            res_desc += f"🏆 **{p1.display_name}** wins and advances!\n~~❌ **{p2.display_name}** is eliminated!~~"
                            next_round_players.append(p1)
                            match_embed.color = discord.Color.green()
                        else:
                            res_desc += f"🏆 **{p2.display_name}** wins and advances!\n~~❌ **{p1.display_name}** is eliminated!~~"
                            next_round_players.append(p2)
                            match_embed.color = discord.Color.green()
                    elif c1 and not c2:
                        res_desc = f"⏱️ **{p2.display_name}** timed out! \n🏆 **{p1.display_name}** advances!"
                        next_round_players.append(p1)
                        match_embed.color = discord.Color.green()
                    elif c2 and not c1:
                        res_desc = f"⏱️ **{p1.display_name}** timed out! \n🏆 **{p2.display_name}** advances!"
                        next_round_players.append(p2)
                        match_embed.color = discord.Color.green()
                    else:
                        res_desc = f"⏱️ Both **{p1.display_name}** and **{p2.display_name}** timed out and are eliminated!"
                        match_embed.color = discord.Color.red()

                    match_embed.description = res_desc
                    await match_msg.edit(embed=match_embed, view=match_view)
                    await asyncio.sleep(5)

                active_players = next_round_players
                round_num += 1

            # Tournament Outcome
            if ctx.channel.id in self.client.active_games:
                if len(active_players) == 1:
                    winner = active_players[0]
                    win_embed = discord.Embed(
                        title="🏆 RPS Tournament — Champion!",
                        description=f"🎉 **{winner.mention} ({winner.display_name})** has defeated all opponents and won the Rock-Paper-Scissors Tournament!\n\n🔗 [**Jump to Tournament Lobby**]({lobby_url})",
                        color=discord.Color.gold()
                    )
                    win_embed.set_thumbnail(url=winner.display_avatar.url)
                    await ctx.send(embed=win_embed)
                elif len(active_players) > 1:
                    co_champs = " • ".join([f"`{p.display_name}`" for p in active_players])
                    tie_embed = discord.Embed(
                        title="🏆 RPS Tournament — Co-Champions!",
                        description=f"🤝 **Tournament tied after {max_rounds} rounds!**\n\n🏆 **Co-Champions:**\n{co_champs}\n\n🔗 [**Jump to Tournament Lobby**]({lobby_url})",
                        color=discord.Color.gold()
                    )
                    await ctx.send(embed=tie_embed)
                else:
                    await ctx.send(f"🎮 **RPS Tournament finished with no remaining players!**\n🔗 [**Jump to Tournament Lobby**]({lobby_url})")

        except asyncio.CancelledError:
            if not lobby_ended and 'join_view' in locals() and 'lobby_msg' in locals():
                try:
                    join_view.stop()
                    for child in join_view.children:
                        child.disabled = True
                    cancel_embed = discord.Embed(
                        title="🎮 RPS Tournament — Stopped",
                        description="Tournament was stopped by host or administrator.",
                        color=discord.Color.red()
                    )
                    cancel_embed.set_thumbnail(url=ctx.me.display_avatar.url)
                    await lobby_msg.edit(embed=cancel_embed, view=join_view)
                except Exception:
                    pass
        finally:
            self.client.active_games.pop(ctx.channel.id, None)

    @commands.group(aliases=["pkq"])
    @commands.guild_only()
    async def pkquiz(self, ctx):
        """Guess the pokemon by dex entries."""
        if ctx.invoked_subcommand is None:
            embed = discord.Embed(color=discord.Color.gold())
            embed.set_author(name="Minigame: Pokédex Quiz", icon_url="https://i.imgur.com/MItw5zU.png")
            desc = "```This is a multiplayer quiz where you guess the Pokémon from Pokédex entry clues!```"
            rules = (
                "```1. Click 'Join Quiz' during the 30-second lobby to join.\n"
                "2. Read the Pokédex entry clues and type the Pokémon name.\n"
                "3. The first participant to guess correctly wins 1 point.\n"
                "4. Only English names are allowed (Case Insensitive).\n"
                "5. Player with the highest score at the end of all rounds wins!\n```"
            )
            embed.description = desc
            embed.add_field(name="Rules:", value=rules)
            embed.add_field(name="Good Luck!", value="\u200b", inline=False)
            embed.set_image(url="https://i.imgur.com/yAz3xCI.jpg")
            embed.set_footer(text="To Start the Quiz | !pkquiz start [count=10]", icon_url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)
            return

    @pkquiz.command(name='stop', aliases=['end', 'cancel', 'quit'])
    @commands.guild_only()
    async def pkquiz_stop(self, ctx, *, channel: str = None):
        """Stops an ongoing Pokédex Quiz in current or specified channel."""
        await self._stop_game_in_channel(ctx, target_channel=channel)

    @pkquiz.command(name='start')
    @commands.guild_only()
    async def pkquiz_start(self, ctx, *, args: str = "10"):
        """Starts Pokédex Quiz minigame. Usage: !pkquiz start [count=10]"""
        if ctx.channel.id in self.client.active_games:
            game_name = self.client.active_games[ctx.channel.id].get("name", "minigame")
            await ctx.send(f"{self.client.emotes.get('redtick', '❌')} `A {game_name} is already running in this channel!`")
            return

        count = 10
        cleaned_args = args.replace("count=", "").strip()
        try:
            count = int(cleaned_args)
        except ValueError:
            count = 10

        if count < 1 or count > 50:
            await ctx.send(f"{self.client.emotes.get('redtick', '❌')} `Number of questions must be between 1 and 50.`")
            return

        self.client.active_games[ctx.channel.id] = {
            "name": "Pokédex Quiz",
            "type": "pkquiz",
            "host_id": ctx.author.id,
            "task": asyncio.current_task()
        }

        lobby_ended = False
        try:
            # 1. Open 30-second lobby window
            lobby_end_time = int(datetime.now(timezone.utc).timestamp()) + 30
            join_view = PKQuizJoinView(ctx.author, self.client.emotes, timeout=35.0)
            embed = discord.Embed(
                title="📖 Pokédex Quiz — Lobby Open!",
                description=(
                    f"**{ctx.author.display_name}** is starting a Pokédex Quiz with **{count} Question(s)**!\n\n"
                    f"Click **Join Quiz** below to participate! Quiz starts <t:{lobby_end_time}:R>."
                ),
                color=discord.Color.gold()
            )
            embed.set_thumbnail(url="https://i.imgur.com/MItw5zU.png")
            embed.set_footer(text=f"Hosted by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)

            lobby_msg = await ctx.send(embed=embed, view=join_view)

            # Check for early cancellation during 30s lobby
            for _ in range(30):
                if ctx.channel.id not in self.client.active_games:
                    join_view.stop()
                    for child in join_view.children:
                        child.disabled = True
                    cancel_embed = discord.Embed(
                        title="📖 Pokédex Quiz — Stopped",
                        description="Quiz was stopped by host or administrator.",
                        color=discord.Color.red()
                    )
                    await lobby_msg.edit(embed=cancel_embed, view=join_view)
                    return
                await asyncio.sleep(1)

            # Close lobby & disable buttons
            join_view.stop()
            for child in join_view.children:
                child.disabled = True

            players = join_view.players
            if not players:
                cancel_embed = discord.Embed(
                    title="📖 Pokédex Quiz — Cancelled",
                    description="No participants joined the quiz! Quiz cancelled.",
                    color=discord.Color.red()
                )
                cancel_embed.set_thumbnail(url="https://i.imgur.com/MItw5zU.png")
                await lobby_msg.edit(embed=cancel_embed, view=join_view)
                return

            player_names = " • ".join([f"`{p.display_name}`" for p in players.values()])
            lobby_url = lobby_msg.jump_url

            game_start_time = int(datetime.now(timezone.utc).timestamp()) + 5
            start_embed = discord.Embed(
                title="📖 Pokédex Quiz — Game Starting!",
                description=f"👥 **{len(players)} Player(s) registered:**\n{player_names}\n\nGet ready! Question 1 is starting <t:{game_start_time}:R>...",
                color=discord.Color.green()
            )
            start_embed.set_thumbnail(url="https://i.imgur.com/MItw5zU.png")
            await lobby_msg.edit(embed=start_embed, view=join_view)
            lobby_ended = True
            await asyncio.sleep(5)

            # Load Pokédex entries dataset
            with open("./files/dex_entries.json", "r") as f:
                data = json.load(f)

            scores = {p_id: 0 for p_id in players}
            round_time = 45.0

            for current_round in range(1, count + 1):
                if ctx.channel.id not in self.client.active_games:
                    break

                c = random.choice(list(data.keys()))
                quiz_raw = f"{data[c][0]}\n{data[c][1]}"
                answer = c.lower().strip()

                # Mask Pokemon name in clue
                masked_name = "_" * len(c)
                if c.lower() in quiz_raw.lower():
                    import re
                    quiz_raw = re.sub(re.escape(c), masked_name, quiz_raw, flags=re.IGNORECASE)

                trans = quiz_raw.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", "ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ")
                quiz_styled = "```" + quiz_raw.translate(trans) + "```"

                round_end_time = int(datetime.now(timezone.utc).timestamp()) + 45
                embed = discord.Embed(
                    title=f"Question {current_round}/{count} — Guess the Pokémon!",
                    description=f"{quiz_styled}\nGuessing ends <t:{round_end_time}:R>!",
                    color=discord.Color.blurple()
                )
                embed.set_author(name="Pokédex Quiz", icon_url="https://i.imgur.com/MItw5zU.png")
                embed.set_footer(text=f"Question {current_round} of {count}")

                round_msg = await ctx.send(embed=embed)

                def check(message):
                    if message.channel.id != ctx.channel.id:
                        return False

                    # Check for stop request
                    if message.content.lower().strip() in ["!game stop", "!stopgame", "!pkquiz stop", "pkquiz stop", "!pkquiz end", "!pkquiz cancel"]:
                        game_info = self.client.active_games.get(ctx.channel.id)
                        host_id = game_info.get("host_id") if game_info else None
                        is_allowed = (
                            message.author.id == self.client.owner_id or
                            message.author.id == host_id or
                            (hasattr(message.author, 'guild_permissions') and message.author.guild_permissions.manage_messages)
                        )
                        if is_allowed:
                            self.client.active_games.pop(ctx.channel.id, None)
                            return True

                    return message.author.id in players and message.content.lower().strip() == answer

                try:
                    msg = await self.client.wait_for('message', timeout=round_time, check=check)
                except asyncio.TimeoutError:
                    if ctx.channel.id not in self.client.active_games:
                        break
                    embed.title = f"Question {current_round}/{count} — Time's Up!"
                    embed.description = f"{self.client.emotes.get('redtick', '❌')} Nobody guessed **{c.title()}**!\n\n{quiz_styled}"
                    embed.color = discord.Color.red()
                    await round_msg.edit(embed=embed)
                else:
                    if ctx.channel.id not in self.client.active_games:
                        break
                    if msg.content.lower().strip() == answer:
                        scores[msg.author.id] += 1
                        embed.title = f"Question {current_round}/{count} — Correct!"
                        embed.description = f"{self.client.emotes.get('greentick', '✅')} **{msg.author.display_name}** guessed it correctly! It's **{c.title()}**!\n\n{quiz_styled}"
                        embed.color = discord.Color.green()
                        await round_msg.edit(embed=embed)

                if current_round < count:
                    if ctx.channel.id not in self.client.active_games:
                        break
                    await asyncio.sleep(5)

            # Final Leaderboard (if not forcibly stopped early)
            if ctx.channel.id in self.client.active_games:
                sorted_scores = sorted(scores.items(), key=lambda item: item[1], reverse=True)

                lb_embed = discord.Embed(
                    title="🏆 Pokédex Quiz — Final Leaderboard",
                    color=discord.Color.gold()
                )
                lb_embed.set_thumbnail(url="https://i.imgur.com/MItw5zU.png")

                lb_lines = []
                medals = ["🥇", "🥈", "🥉"]
                for rank, (p_id, score) in enumerate(sorted_scores, 1):
                    user = players.get(p_id)
                    name = user.display_name if user else f"User {p_id}"
                    medal = medals[rank - 1] if rank <= 3 else f"`#{rank}`"
                    lb_lines.append(f"{medal} **{name}**: `{score}` point(s)")

                scores_str = "\n".join(lb_lines) if lb_lines else "No participants scored points!"
                lb_embed.description = f"🔗 [**Jump to Quiz Lobby**]({lobby_url})\n\n{scores_str}"
                lb_embed.set_footer(text=f"Quiz Complete | Total Questions: {count}", icon_url=ctx.author.display_avatar.url)

                await ctx.send(embed=lb_embed)

        except asyncio.CancelledError:
            if not lobby_ended and 'join_view' in locals() and 'lobby_msg' in locals():
                try:
                    join_view.stop()
                    for child in join_view.children:
                        child.disabled = True
                    cancel_embed = discord.Embed(
                        title="📖 Pokédex Quiz — Stopped",
                        description="Quiz was stopped by host or administrator.",
                        color=discord.Color.red()
                    )
                    cancel_embed.set_thumbnail(url="https://i.imgur.com/MItw5zU.png")
                    await lobby_msg.edit(embed=cancel_embed, view=join_view)
                except Exception:
                    pass
        finally:
            self.client.active_games.pop(ctx.channel.id, None)

            
async def setup(client):
    await client.add_cog(Games(client))