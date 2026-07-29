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
    def __init__(self, host, emotes, timeout=30.0):
        super().__init__(timeout=timeout)
        self.host = host
        self.players = {host.id: host}

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

        self.client.wtpList.append(ctx.channel.id)

        try:
            # 1. Open 30-second lobby window
            join_view = WTPJoinView(ctx.author, self.client.emotes, timeout=30.0)
            embed = discord.Embed(
                title="🎮 Who's That Pokémon — Lobby Open!",
                description=(
                    f"**{ctx.author.display_name}** is starting a WTP game with **{count} Pokémon(s)**!\n\n"
                    f"Click **Join Game** below to participate! Game starts in **30 seconds**."
                ),
                color=discord.Color.gold()
            )
            embed.set_thumbnail(url="https://i.imgur.com/MItw5zU.png")
            embed.set_footer(text=f"Hosted by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)

            lobby_msg = await ctx.send(embed=embed, view=join_view)
            await join_view.wait()

            players = join_view.players
            player_names = ", ".join([p.display_name for p in players.values()])

            start_embed = discord.Embed(
                title="🎮 Who's That Pokémon — Game Starting!",
                description=f"**{len(players)} Player(s) joined:** {player_names}\n\nGet ready! Round 1 is starting in **5 seconds**...",
                color=discord.Color.green()
            )
            start_embed.set_thumbnail(url="https://i.imgur.com/MItw5zU.png")
            await lobby_msg.edit(embed=start_embed, view=None)
            await asyncio.sleep(5)

            # Load Pokémon dataset
            with open('./files/wtpNames.json', 'r') as f:
                wtpData = json.load(f)

            scores = {p_id: 0 for p_id in players}
            round_time = 15.0

            for current_round in range(1, count + 1):
                pokeID = random.randrange(1, 897)
                wtpPoke = wtpData.get(f"{pokeID}")
                pokeName = wtpPoke["name"].lower().strip()
                pokeImgOrg = f"https://github.com/EliteB0Y/TestBot/raw/master/WTP/{pokeID:03d}.png"
                pokeImgWtp = f"https://github.com/EliteB0Y/TestBot/raw/master/WTP/{pokeID:03d}x.png"

                embed = discord.Embed(
                    title=f"Round {current_round}/{count} — Who's that Pokémon?",
                    color=discord.Color.blurple()
                )
                embed.set_author(name="Who's that Pokémon?", icon_url="https://i.imgur.com/MItw5zU.png")
                embed.set_image(url=pokeImgWtp)
                embed.set_footer(text=f"Round {current_round} of {count} | 15 seconds to guess")

                round_msg = await ctx.send(embed=embed)

                def check(message):
                    return (
                        message.channel.id == ctx.channel.id and
                        message.author.id in players and
                        message.content.lower().strip() == pokeName
                    )

                try:
                    msg = await self.client.wait_for('message', timeout=round_time, check=check)
                except asyncio.TimeoutError:
                    embed.title = f"Round {current_round}/{count} — Time's Up!"
                    embed.description = f"{self.client.emotes.get('redtick', '❌')} Nobody guessed **{wtpPoke['name'].title()}**!"
                    embed.set_image(url=pokeImgOrg)
                    embed.color = discord.Color.red()
                    await round_msg.edit(embed=embed)
                else:
                    scores[msg.author.id] += 1
                    embed.title = f"Round {current_round}/{count} — Correct!"
                    embed.description = f"{self.client.emotes.get('greentick', '✅')} **{msg.author.display_name}** guessed it correctly! It's **{wtpPoke['name'].title()}**!"
                    embed.set_image(url=pokeImgOrg)
                    embed.color = discord.Color.green()
                    await round_msg.edit(embed=embed)

                if current_round < count:
                    await asyncio.sleep(3)

            # Final Leaderboard
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
            if ctx.channel.id in self.client.wtpList:
                self.client.wtpList.remove(ctx.channel.id)
        
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

    @commands.command()
    @commands.guild_only()
    async def pkquiz(self, ctx, points_to_win = 5):
        """Guess the pokemon by dex entries."""
        if ctx.guild.id in self.client.activeQuiz:
            await ctx.send("A quiz is already running in this server. End the quiz to start another one!")
            return
        else:
            try:
                points_to_win = int(points_to_win)
            except (ValueError, TypeError):
                _ = await ctx.send("Invalid input for `points_to_win` parameter.")
                return

            self.client.activeQuiz.append(ctx.guild.id)
            await ctx.send(f"A quiz will start in few seconds. First to {points_to_win} point wins!\n`skip` - To skip the question. \n`quit` - To end the quiz. ")
            await asyncio.sleep(5)

        

        with open("./files/dex_entries.json","r") as f:
            data = json.load(f)

        start = True
        fail_count = 0
        points_table = {}
        while start:
            c = random.choice(list(data.keys()))
            quiz = f"{data[c][0]}\n{data[c][1]}"
            answer = c
            if answer in quiz:
                quiz = quiz.replace(answer, "_" * len(answer))

            trans = quiz.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", "ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ")
            quiz = "```" + quiz.translate(trans) + "```"

            _ = await ctx.send(quiz)

            def check(message):
                if message.channel.id == ctx.channel.id:
                    if message.content.lower() == answer.lower():
                        return True
                    elif message.content.lower() == "skip" and message.author == ctx.author:
                        return True
                    elif message.content.lower() == "quit" and message.author == ctx.author:
                        return True

            try:
                msg = await self.client.wait_for('message',check=check, timeout=60)
            except asyncio.TimeoutError:
                _ = await ctx.send(f"You have failed to guess the answer: {answer}!")
                fail_count += 1

            else:
                if msg.content.lower() == answer.lower():
                    point = points_table.get(msg.author, 0) + 1
                    points_table[msg.author] = point
                    await msg.add_reaction("✅")
                    
                    if point >= points_to_win:
                        _ = await ctx.send(f"{msg.author} wins with {point} points!!!")
                        start = False
                    else:
                        _ = await ctx.send(f"{msg.author} : +1 [Total: {point} points]")

                    
                elif msg.content.lower() == "skip":
                    _ = await ctx.send(f"You have skipped this question!! The answer was: {answer}")
                elif msg.content.lower() == "quit":
                    _ = await ctx.send("You have ended the quiz!!!")
                    start = False
            
            if fail_count >= 3:
                start =  False
                _ = await ctx.send("Ending the quiz due to multiple failed guesses!!!")

            if not start:
                self.client.activeQuiz.remove(ctx.guild.id)
                points_table = dict(sorted(points_table.items(), key=lambda item: item[1], reverse=True))
                desc = "--------------------\n"
                desc += "Points Table: \n"
                desc += "--------------------\n"
                desc += "\n".join([f"{k} : {v} points" for k,v in points_table.items()])
                desc += "\n--------------------"
                _ = await ctx.send(f"```{desc}```")

            await asyncio.sleep(7)

            
async def setup(client):
    await client.add_cog(Games(client))