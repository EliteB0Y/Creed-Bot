import discord, json, asyncio, random
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
            await interaction.response.send_message("This game is not for you.", ephemeral=True)
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


class WTPJoinView(discord.ui.View):
    def __init__(self, host, emotes, timeout=35.0):
        super().__init__(timeout=timeout)
        self.host = host
        self.players = {}  # Host is not forced to join automatically

        pokeball_emoji = emotes.get("pokeball") or "🔴"
        self.join_btn.emoji = pokeball_emoji

    @discord.ui.button(label="Join Game", style=discord.ButtonStyle.success)
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.players:
            await interaction.response.send_message("You have already joined the game!", ephemeral=True)
        else:
            self.players[interaction.user.id] = interaction.user
            await interaction.response.send_message(
                f"✅ You joined Who's That Pokémon! ({len(self.players)} player(s) in lobby)",
                ephemeral=True
            )


class PKQuizJoinView(discord.ui.View):
    def __init__(self, host, emotes, timeout=35.0):
        super().__init__(timeout=timeout)
        self.host = host
        self.players = {}

        pokeball_emoji = emotes.get("pokeball") or "🔴"
        self.join_btn.emoji = pokeball_emoji

    @discord.ui.button(label="Join Quiz", style=discord.ButtonStyle.success)
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.players:
            await interaction.response.send_message("You have already joined the quiz!", ephemeral=True)
        else:
            self.players[interaction.user.id] = interaction.user
            await interaction.response.send_message(
                f"✅ You joined the Pokédex Quiz! ({len(self.players)} player(s) in lobby)",
                ephemeral=True
            )


class TimingGameView(discord.ui.View):
    def __init__(self, author_id, timeout=20.0):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.click_time = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This game is not for you.", ephemeral=True)
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
    async def wtp_stop(self, ctx):
        """Stops an ongoing Who's That Pokémon game in the channel."""
        if ctx.channel.id not in self.client.wtpList:
            await ctx.send(f"{self.client.emotes.get('redtick', '❌')} `No Who's That Pokémon game is currently running in this channel.`")
            return

        host_id = self.client.wtpList.get(ctx.channel.id)
        is_allowed = (
            ctx.author.id == self.client.owner_id or
            ctx.author.id == host_id or
            (hasattr(ctx.author, 'guild_permissions') and ctx.author.guild_permissions.manage_messages)
        )
        if not is_allowed:
            await ctx.send(f"{self.client.emotes.get('redtick', '❌')} `Only the game host, server moderators, or bot owner can stop this game.`")
            return

        self.client.wtpList.pop(ctx.channel.id, None)
        await ctx.send(f"{self.client.emotes.get('greentick', '✅')} **Who's That Pokémon game has been stopped by {ctx.author.display_name}.**")

    @wtp.command(name = 'start')
    @commands.guild_only()
    async def wtp_start(self, ctx, *, args: str = "10"):
        """Starts Who's That Pokémon minigame. Usage: !wtp start [count=10]"""
        if ctx.channel.id in self.client.wtpList:
            await ctx.send(f"{self.client.emotes.get('redtick', '❌')} `A Who's That Pokémon game is already running in this channel!`")
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

        self.client.wtpList[ctx.channel.id] = ctx.author.id

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
                if ctx.channel.id not in self.client.wtpList:
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

            player_names = ", ".join([p.display_name for p in players.values()])

            game_start_time = int(datetime.now(timezone.utc).timestamp()) + 5
            start_embed = discord.Embed(
                title="🎮 Who's That Pokémon — Game Starting!",
                description=f"**{len(players)} Player(s) joined:** {player_names}\n\nGet ready! Round 1 is starting <t:{game_start_time}:R>...",
                color=discord.Color.green()
            )
            start_embed.set_thumbnail(url="https://i.imgur.com/MItw5zU.png")
            await lobby_msg.edit(embed=start_embed, view=join_view)
            await asyncio.sleep(5)

            # Load Pokémon dataset
            with open('./files/wtpNames.json', 'r') as f:
                wtpData = json.load(f)

            scores = {p_id: 0 for p_id in players}
            round_time = 15.0

            for current_round in range(1, count + 1):
                if ctx.channel.id not in self.client.wtpList:
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
                    if message.content.lower().strip() in ["!wtp stop", "wtp stop", "!wtp end", "!wtp cancel"]:
                        host_id = self.client.wtpList.get(ctx.channel.id)
                        is_allowed = (
                            message.author.id == self.client.owner_id or
                            message.author.id == host_id or
                            (hasattr(message.author, 'guild_permissions') and message.author.guild_permissions.manage_messages)
                        )
                        if is_allowed:
                            self.client.wtpList.pop(ctx.channel.id, None)
                            return True

                    return message.author.id in players and message.content.lower().strip() == pokeName

                try:
                    msg = await self.client.wait_for('message', timeout=round_time, check=check)
                except asyncio.TimeoutError:
                    if ctx.channel.id not in self.client.wtpList:
                        break
                    embed.title = f"Round {current_round}/{count} — Time's Up!"
                    embed.description = f"{self.client.emotes.get('redtick', '❌')} Nobody guessed **{wtpPoke['name'].title()}**!"
                    embed.set_image(url=pokeImgOrg)
                    embed.color = discord.Color.red()
                    await round_msg.edit(embed=embed)
                else:
                    if ctx.channel.id not in self.client.wtpList:
                        break
                    if msg.content.lower().strip() == pokeName:
                        scores[msg.author.id] += 1
                        embed.title = f"Round {current_round}/{count} — Correct!"
                        embed.description = f"{self.client.emotes.get('greentick', '✅')} **{msg.author.display_name}** guessed it correctly! It's **{wtpPoke['name'].title()}**!"
                        embed.set_image(url=pokeImgOrg)
                        embed.color = discord.Color.green()
                        await round_msg.edit(embed=embed)

                if current_round < count:
                    if ctx.channel.id not in self.client.wtpList:
                        break
                    await asyncio.sleep(3)

            # Final Leaderboard (if not forcibly stopped early)
            if ctx.channel.id in self.client.wtpList:
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

                lb_embed.description = "\n".join(lb_lines) if lb_lines else "No participants scored points!"
                lb_embed.set_footer(text=f"Game Over | Total Rounds: {count}", icon_url=ctx.author.display_avatar.url)

                await ctx.send(embed=lb_embed)

        finally:
            self.client.wtpList.pop(ctx.channel.id, None)
        
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
    
    @commands.command()
    @commands.guild_only()
    async def rps(self, ctx):
        """Rock-Paper-Scissors game"""
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
    async def pkquiz_stop(self, ctx):
        """Stops an ongoing Pokédex Quiz in the channel."""
        if ctx.channel.id not in self.client.activeQuiz:
            await ctx.send(f"{self.client.emotes.get('redtick', '❌')} `No Pokédex Quiz is currently running in this channel.`")
            return

        host_id = self.client.activeQuiz.get(ctx.channel.id)
        is_allowed = (
            ctx.author.id == self.client.owner_id or
            ctx.author.id == host_id or
            (hasattr(ctx.author, 'guild_permissions') and ctx.author.guild_permissions.manage_messages)
        )
        if not is_allowed:
            await ctx.send(f"{self.client.emotes.get('redtick', '❌')} `Only the quiz host, server moderators, or bot owner can stop this quiz.`")
            return

        self.client.activeQuiz.pop(ctx.channel.id, None)
        await ctx.send(f"{self.client.emotes.get('greentick', '✅')} **Pokédex Quiz has been stopped by {ctx.author.display_name}.**")

    @pkquiz.command(name='start')
    @commands.guild_only()
    async def pkquiz_start(self, ctx, *, args: str = "10"):
        """Starts Pokédex Quiz minigame. Usage: !pkquiz start [count=10]"""
        if ctx.channel.id in self.client.activeQuiz:
            await ctx.send(f"{self.client.emotes.get('redtick', '❌')} `A Pokédex Quiz is already running in this channel!`")
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

        self.client.activeQuiz[ctx.channel.id] = ctx.author.id

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
                if ctx.channel.id not in self.client.activeQuiz:
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

            player_names = ", ".join([p.display_name for p in players.values()])

            game_start_time = int(datetime.now(timezone.utc).timestamp()) + 5
            start_embed = discord.Embed(
                title="📖 Pokédex Quiz — Game Starting!",
                description=f"**{len(players)} Player(s) joined:** {player_names}\n\nGet ready! Question 1 is starting <t:{game_start_time}:R>...",
                color=discord.Color.green()
            )
            start_embed.set_thumbnail(url="https://i.imgur.com/MItw5zU.png")
            await lobby_msg.edit(embed=start_embed, view=join_view)
            await asyncio.sleep(5)

            # Load Pokédex entries dataset
            with open("./files/dex_entries.json", "r") as f:
                data = json.load(f)

            scores = {p_id: 0 for p_id in players}
            round_time = 45.0

            for current_round in range(1, count + 1):
                if ctx.channel.id not in self.client.activeQuiz:
                    break

                c = random.choice(list(data.keys()))
                quiz_raw = f"{data[c][0]}\n{data[c][1]}"
                answer = c.lower().strip()

                # Mask Pokemon name in clue
                masked_name = "_" * len(c)
                if c.lower() in quiz_raw.lower():
                    # Replace case-insensitively
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
                    if message.content.lower().strip() in ["!pkquiz stop", "pkquiz stop", "!pkquiz end", "!pkquiz cancel"]:
                        host_id = self.client.activeQuiz.get(ctx.channel.id)
                        is_allowed = (
                            message.author.id == self.client.owner_id or
                            message.author.id == host_id or
                            (hasattr(message.author, 'guild_permissions') and message.author.guild_permissions.manage_messages)
                        )
                        if is_allowed:
                            self.client.activeQuiz.pop(ctx.channel.id, None)
                            return True

                    return message.author.id in players and message.content.lower().strip() == answer

                try:
                    msg = await self.client.wait_for('message', timeout=round_time, check=check)
                except asyncio.TimeoutError:
                    if ctx.channel.id not in self.client.activeQuiz:
                        break
                    embed.title = f"Question {current_round}/{count} — Time's Up!"
                    embed.description = f"{self.client.emotes.get('redtick', '❌')} Nobody guessed **{c.title()}**!\n\n{quiz_styled}"
                    embed.color = discord.Color.red()
                    await round_msg.edit(embed=embed)
                else:
                    if ctx.channel.id not in self.client.activeQuiz:
                        break
                    if msg.content.lower().strip() == answer:
                        scores[msg.author.id] += 1
                        embed.title = f"Question {current_round}/{count} — Correct!"
                        embed.description = f"{self.client.emotes.get('greentick', '✅')} **{msg.author.display_name}** guessed it correctly! It's **{c.title()}**!\n\n{quiz_styled}"
                        embed.color = discord.Color.green()
                        await round_msg.edit(embed=embed)

                if current_round < count:
                    if ctx.channel.id not in self.client.activeQuiz:
                        break
                    await asyncio.sleep(4)

            # Final Leaderboard (if not forcibly stopped early)
            if ctx.channel.id in self.client.activeQuiz:
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

                lb_embed.description = "\n".join(lb_lines) if lb_lines else "No participants scored points!"
                lb_embed.set_footer(text=f"Quiz Complete | Total Questions: {count}", icon_url=ctx.author.display_avatar.url)

                await ctx.send(embed=lb_embed)

        finally:
            self.client.activeQuiz.pop(ctx.channel.id, None)

            
async def setup(client):
    await client.add_cog(Games(client))