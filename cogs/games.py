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
            embed = discord.Embed()
            embed.set_author(name="Minigame: Who's that Pokémon?", icon_url="https://i.imgur.com/MItw5zU.png")
            desc = "```This is a minigame where you have to guess the Pokémon name!\nGame includes Pokémon from 8 generations (Currently includes 897 Pokémons).```"
            rules = "```1. You have to guess the Pokémon name within 15 seconds.\n2. For every correct guess, the guessing time reduces by 0.2 seconds. (Game gets harder as you score more points!)\n3. Only English names are allowed. (Case Insensitive)\n4. Failing to Guess or Wrong guess will end the game.\n```"
            embed.description = desc
            embed.add_field(name="Rules:", value=rules)
            embed.add_field(name="Good Luck!", value="\u200b", inline=False)
            embed.set_image(url="https://i.imgur.com/yAz3xCI.jpg")
            embed.set_footer(text= "To Start the Game | wtp start")
            await ctx.send(embed=embed)
            return
    
    @wtp.command(name = 'start')
    async def wtp_start(self, ctx):
        """Starts who's that pokemon minigame."""
        if ctx.author.id in self.client.wtpList:
            await ctx.send(f"`Hello {ctx.author.name}, You are already playing who's that pokemon! Please wait until it ends.`")
            return
            
        self.client.wtpList.append(ctx.author.id)
        with open('./files/wtpNames.json','r') as f:
            wtpData = json.load(f)
        start = True
        points = 0
        time_left = 15.0
        count = 0
        while start:
            pokeID = random.randrange(1,897)
            wtpPoke = wtpData.get(f"{pokeID}")
            pokeName = wtpPoke["name"]
            pokeImgOrg = f"https://github.com/EliteB0Y/TestBot/raw/master/WTP/{pokeID:03d}.png"
            pokeImgWtp = f"https://github.com/EliteB0Y/TestBot/raw/master/WTP/{pokeID:03d}x.png"
            embed = discord.Embed()
            embed.set_author(name="Who's that Pokémon?", icon_url="https://i.imgur.com/MItw5zU.png")
            embed.set_image(url=pokeImgWtp)
            embed.set_footer(text=f"{ctx.author.name} | Current Score: {points} points", icon_url=ctx.author.display_avatar.url)
            x = await ctx.send(embed=embed)
                    
                
            def check(message):
                return message.author == ctx.author and message.channel.id == ctx.channel.id
        
            try:
                msg = await self.client.wait_for('message', timeout = time_left, check = check)
            except asyncio.TimeoutError:
                embed = discord.Embed(description = f"{self.client.emotes.get('redtick', '')}  **You failed to guess {pokeName.title()}**")
                embed.set_author(name="Who's that Pokémon?", icon_url="https://i.imgur.com/MItw5zU.png")
                embed.set_image(url=pokeImgOrg)
                embed.set_footer(text=f"{ctx.author.name} | Final Score: {points} points", icon_url=ctx.author.display_avatar.url)
                await x.edit(embed=embed)
                start = False
            else:
                if msg.content.lower() == pokeName:
                    count += 1
                    points += 5
                    time_left -= 0.2
                    embed = discord.Embed(description = f"{self.client.emotes.get('greentick', '')} **Correct!! It's {pokeName.title()}**")
                    embed.set_author(name="Who's that Pokémon?", icon_url="https://i.imgur.com/MItw5zU.png")
                    embed.set_image(url=pokeImgOrg)
                    embed.set_footer(text=f"{ctx.author.name} | Current Score: {points} points", icon_url=ctx.author.display_avatar.url)
                    await x.edit(embed=embed)
                else:
                    embed = discord.Embed(description = f"{self.client.emotes.get('redtick', '')}  **You failed to guess {pokeName.title()}**")
                    embed.set_author(name="Who's that Pokémon?", icon_url="https://i.imgur.com/MItw5zU.png")
                    embed.set_image(url=pokeImgOrg)
                    embed.set_footer(text=f"{ctx.author.name} | Final Score: {points} points", icon_url=ctx.author.display_avatar.url)
                    await x.edit(embed=embed)
                    start = False

        if points > 200:
            txt = 'Marvelous'
        elif points > 150:
            txt = 'Unbelievable'
        elif points > 100:
            txt = 'Fantastic'
        elif points > 50:
            txt = 'Good Job'
        else:
            txt = 'Hello'
        embed = discord.Embed()
        embed.set_author(name="Who's that Pokémon?", icon_url="https://i.imgur.com/MItw5zU.png")
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.description = f"```{txt} {ctx.author.name}! You have guessed {count} pokemon(s) correctly and scored {points} points.```"
        await ctx.send(embed=embed)
        self.client.wtpList.remove(ctx.author.id)
        
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