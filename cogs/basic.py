import discord, os, random, requests, async_cse, asyncio, io
from discord.ext import commands

class Basic(commands.Cog):

    def __init__(self, client):
        self.client = client

    # <# Event: On Guild Join - Start #>

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        prefixes = self.client.db.get_collection("prefixes")
        p = prefixes.find_one({"serverid": guild.id})
        if not p:
            prefixes.insert_one({"serverid": guild.id, "prefix": "!"})

    # <# Event: On Guild Join - End #>

    # <# Event: On Guild Remove - Start #>

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        prefixes = self.client.db.get_collection("prefixes")
        p = prefixes.find_one({"serverid": guild.id})
        if p:
            prefixes.delete_one({"serverid": guild.id})

    # <# Event: On Guild Remove - End #>

    @commands.command(aliases = ["change_prefix", "cp", "changeprefix"])
    @commands.guild_only()
    @commands.check_any(commands.has_permissions(manage_guild = True), commands.is_owner())
    async def prefix(self, ctx, *, new_prefix):
        """Changes command prefix."""
        new_prefix = new_prefix.replace('"','').replace("'","")
        if 0 < len(new_prefix) <= 10:
            def check(message):
                return message.author == ctx.author and any(
                    i == message.content.lower() for i in ["y", "n", "yes", "no", "confirm"])
    
            m = f"Hello {ctx.author.display_name}, \nCommand prefix will be changed to {self.client.emotes.get('arrowright','**')} {new_prefix} {self.client.emotes.get('arrowleft','**')}\nPlease confirm if you want to continue? \nType any of these `[y/yes/confirm]`"
            embed = discord.Embed(description = m)
            x = await ctx.send(embed = embed)
            try:
                msg = await self.client.wait_for("message", timeout = 20.0, check = check)
            except asyncio.TimeoutError:
                embed = discord.Embed(description = f"{self.client.emotes.get('timer','')} Session timed out! Command prefix did not change.",
                                      color = discord.Color.red())
                await x.edit(embed = embed)
            else:
                if any(i == msg.content.lower() for i in ["y", "yes", "confirm"]):
                    prefixes = self.client.db.get_collection("prefixes")
                    p = prefixes.find_one({"serverid": ctx.guild.id})
                    prefixes.update_one({"serverid": ctx.guild.id}, {"$set": {"prefix": new_prefix}})
                    desc = f"{self.client.emotes.get('accepted','')} Command prefix changed to {self.client.emotes.get('arrowright','**')} {new_prefix} {self.client.emotes.get('arrowleft','**')}"
                    embed = discord.Embed(title = f"Hello {ctx.author.display_name}",
                                  description = desc)
                    await x.edit(embed = embed)
                else:
                    desc = f"{self.client.emotes.get('denied','')} Command prefix did not change."
                    embed = discord.Embed(title = f"Hello {ctx.author.display_name}",
                                  description = desc)
                    await x.edit(embed = embed)
    
        else:
            embed = discord.Embed(description = f"{self.client.emotes.get('alert','')} Command prefixes can only be of 1 to 10 characters long.",
                                  color = discord.Color.red())
            await ctx.send(embed = embed)

    @commands.command()
    async def ping(self, ctx):
        """Displays the bot latency."""
        await ctx.send(f"{self.client.emotes.get('typing','')} `Pong! {round(self.client.latency * 1000, 2)}ms.`")
    
    @commands.command(aliases = ["toss"])
    async def flip(self, ctx):
        """Flips a coin."""
        result = random.choice(["Heads", "Tails"])
        await ctx.send(f"You flipped a coin and it\'s {result}!")

    @commands.command(aliases = ["av", "pfp"])
    async def avatar(self, ctx, *, member: discord.Member = None):
        """Displays user avatar."""
        if not member:
            member = ctx.author
        ext = "gif" if member.avatar.is_animated() else "png"
        file = discord.File(io.BytesIO(await member.avatar.read()), f"{ctx.author.id}.{ext}")
        embed = discord.Embed()
        embed.set_image(url= f"attachment://{ctx.author.id}.{ext}")
        embed.set_footer(text = f"Requested by {ctx.author.name} | {self.client.get_time}", icon_url = ctx.author.avatar)
        await ctx.send(file=file, embed=embed)

    @commands.command(aliases = ["calc", "math", "="])
    async def calculate(self, ctx, *, expression = ""):
        """Calculates the expression and displays the result."""
        if expression:
            _expression = expression.replace(" ", "").replace("^", "**").replace(",","")
            try:
                result = eval(_expression)
            except:
                result = "invalid"
            if result != "invalid":
                msg = f"{self.client.emotes.get('greentick','')} `{expression} = {result:,}`"
            else:
                msg = f"{self.client.emotes.get('redtick','')} `Cannot evaluate this expression: {expression}`"
            await ctx.send(msg)
        else:
            msg = f"{self.client.emotes.get('redtick','')}  `Invalid expression to evaluate.`"
            await ctx.send(msg)

    @commands.command(name = "random", aliases = ["rand", "roll"])
    async def _random(self, ctx, *, args = "0 100"):
        """Generates a random number. (accepts space seperated interval)"""
        try:
            args = sorted(list(map(int, args.split())))
        except Exception as e:
            raise e
        if len(args) == 2:
            start, end = args[0], args[1]
        elif len(args) == 1:
            start, end = 0, args[0]
        else:
            raise ValueError
        if start == end:
            result = start
        else:
            result = random.randrange(start, end)
        await ctx.send(result)

    @commands.command(aliases = ["pick"])
    async def choose(self, ctx, *, args):
        """Selects a random option from the (comma seperated) given options."""
        try:
            args = list(map(str.strip, args.split(",")))
        except Exception as e:
            raise e
        result = random.choice(args)
        await ctx.send(f"{result}")

async def setup(client):
    await client.add_cog(Basic(client))