import discord, random, asyncio, io
import logging
import psutil
import platform
from datetime import datetime, timezone
from discord.ext import commands

logger = logging.getLogger("CreedBot")

class ConfirmView(discord.ui.View):
    def __init__(self, author_id, timeout=30.0):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.value = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This confirmation is not for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        self.stop()
        await interaction.response.defer()


class Basic(commands.Cog):

    def __init__(self, client):
        self.client = client

    # <# Event: On Guild Join - Start #>

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        logger.info("Joined guild: %s (%s) | Members: %s", guild.name, guild.id, guild.member_count)
        prefixes = self.client.db.get_collection("prefixes_cb")
        p = prefixes.find_one({"serverid": guild.id})
        if not p:
            prefixes.insert_one({"serverid": guild.id, "prefix": "!"})

    # <# Event: On Guild Join - End #>

    # <# Event: On Guild Remove - Start #>

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        logger.info("Left guild: %s (%s)", guild.name, guild.id)
        prefixes = self.client.db.get_collection("prefixes_cb")
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
            view = ConfirmView(ctx.author.id, timeout=20.0)
            m = f"Hello {ctx.author.display_name},\nCommand prefix will be changed to {self.client.emotes.get('arrowright','**')} **{new_prefix}** {self.client.emotes.get('arrowleft','**')}\nPlease confirm if you want to continue?"
            embed = discord.Embed(description = m)
            x = await ctx.send(embed = embed, view = view)
            await view.wait()

            if view.value is True:
                prefixes = self.client.db.get_collection("prefixes_cb")
                prefixes.update_one({"serverid": ctx.guild.id}, {"$set": {"prefix": new_prefix}}, upsert=True)
                desc = f"{self.client.emotes.get('accepted','')} Command prefix changed to {self.client.emotes.get('arrowright','**')} **{new_prefix}** {self.client.emotes.get('arrowleft','**')}"
                embed = discord.Embed(title = f"Hello {ctx.author.display_name}", description = desc)
                await x.edit(embed = embed, view = None)
            else:
                desc = f"{self.client.emotes.get('denied','')} Command prefix did not change."
                embed = discord.Embed(title = f"Hello {ctx.author.display_name}", description = desc)
                await x.edit(embed = embed, view = None)
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
        avatar_asset = member.display_avatar
        ext = "gif" if avatar_asset.is_animated() else "png"
        file = discord.File(io.BytesIO(await avatar_asset.read()), f"{ctx.author.id}.{ext}")
        embed = discord.Embed()
        embed.set_image(url= f"attachment://{ctx.author.id}.{ext}")
        embed.set_footer(text = f"Requested by {ctx.author.name} | {self.client.get_time}", icon_url = ctx.author.display_avatar.url)
        await ctx.send(file=file, embed=embed)

    @commands.command(aliases = ["calc", "math", "="])
    async def calculate(self, ctx, *, expression = ""):
        """Calculates the expression and displays the result."""
        if expression:
            _expression = expression.replace(" ", "").replace("^", "**").replace(",","")
            try:
                result = eval(_expression)
            except Exception:
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

    @commands.command(name="botinfo", aliases=["about", "info", "stats"])
    async def botinfo(self, ctx):
        """Displays information about the bot and its host server."""
        # 1. Fetch Owner Info
        owner = None
        if self.client.owner_id:
            try:
                owner = self.client.get_user(self.client.owner_id) or await self.client.fetch_user(self.client.owner_id)
            except Exception:
                pass
        
        if not owner:
            try:
                app_info = await self.client.application_info()
                owner = app_info.owner
                self.client.owner_id = owner.id
            except Exception:
                owner = "Unknown"

        owner_display = f"{owner.mention} ({owner.name})" if isinstance(owner, discord.User) else str(owner)

        # 2. Uptime calculation
        uptime_str = "Unknown"
        uptime_relative = ""
        if hasattr(self.client, 'start_time'):
            now = datetime.now(timezone.utc)
            uptime_diff = now - self.client.start_time
            
            days = uptime_diff.days
            hours, remainder = divmod(uptime_diff.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            
            parts = []
            if days > 0:
                parts.append(f"{days}d")
            if hours > 0:
                parts.append(f"{hours}h")
            if minutes > 0:
                parts.append(f"{minutes}m")
            parts.append(f"{seconds}s")
            uptime_str = " ".join(parts)
            
            epoch_time = int(self.client.start_time.timestamp())
            uptime_relative = f"<t:{epoch_time}:R>"

        # 3. System resources
        # CPU
        cpu_usage = psutil.cpu_percent()
        # Memory
        mem = psutil.virtual_memory()
        host_mem_used = mem.used / (1024 ** 3)
        host_mem_total = mem.total / (1024 ** 3)
        host_mem_percent = mem.percent
        # Bot process memory
        proc = psutil.Process()
        bot_mem = proc.memory_info().rss / (1024 * 1024)

        # 4. Emojis
        dev_emoji = self.client.emotes.get('developer', '👑')
        bot_emoji = self.client.emotes.get('bot', '🤖')
        info_emoji = self.client.emotes.get('info', 'ℹ️')
        uptime_emoji = self.client.emotes.get('timer', '⏳')
        server_emoji = self.client.emotes.get('discord', '🖥️')
        user_emoji = self.client.emotes.get('user', '👥')
        ping_emoji = self.client.emotes.get('typing', '🏓')
        ram_emoji = self.client.emotes.get('info', '💾')
        cpu_emoji = self.client.emotes.get('info', '⚙️')

        uptime_info = f"{uptime_str} ({uptime_relative})" if uptime_relative else uptime_str

        # 5. Build Embed
        desc = (
            f"{bot_emoji} **Creed-Bot** is a custom bot designed for Pokémon Creed!\n\n"
            f"{dev_emoji} **Developer:** {owner_display}\n"
            f"{uptime_emoji} **Uptime:** {uptime_info}\n\n"
            f"**{info_emoji} Bot Statistics**\n"
            f"• {server_emoji} **Servers:** `{len(self.client.guilds)}`\n"
            f"• {user_emoji} **Users:** `{len(self.client.users)}`\n"
            f"• {ping_emoji} **Ping:** `{round(self.client.latency * 1000, 2)}ms`\n"
            f"• 🐍 **Library:** `discord.py v{discord.__version__}`\n\n"
            f"**🖥️ Host Resources**\n"
            f"• {cpu_emoji} **CPU Usage:** `{cpu_usage}%`\n"
            f"• {ram_emoji} **Bot RAM:** `{bot_mem:.1f} MB`\n"
            f"• {ram_emoji} **Server RAM:** `{host_mem_used:.1f} GB / {host_mem_total:.1f} GB ({host_mem_percent}%)`"
        )

        embed = discord.Embed(
            title="Bot Information",
            description=desc,
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_thumbnail(url=self.client.user.display_avatar.url)
        
        embed.set_footer(
            text=f"Requested by {ctx.author.name} | Python v{platform.python_version()}",
            icon_url=ctx.author.display_avatar.url
        )
        
        await ctx.send(embed=embed)

async def setup(client):
    await client.add_cog(Basic(client))