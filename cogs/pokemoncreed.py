import discord, asyncio, json, aiohttp
from datetime import datetime, timezone
import logging
from discord.ext import commands
from views import ProfileView

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

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        self.stop()
        await interaction.response.defer()


class PageJumpModal(discord.ui.Modal, title="Jump to Page"):
    page_num = discord.ui.TextInput(
        label="Page Number",
        placeholder="Enter page number...",
        min_length=1,
        max_length=5,
        required=True
    )

    def __init__(self, view):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            page = int(self.page_num.value) - 1
            if 0 <= page < len(self.view.results):
                self.view.pg = page
                embed = self.view.getPagewiseDetails(self.view.pg)
                await interaction.response.edit_message(embed=embed, view=self.view)
            else:
                await interaction.response.send_message(
                    f"Invalid page number! Please enter between 1 and {len(self.view.results)}.",
                    ephemeral=True
                )
        except ValueError:
            await interaction.response.send_message("Please enter a valid integer.", ephemeral=True)


class BoxView(discord.ui.View):
    def __init__(self, ctx, results):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.results = results
        self.pg = 0
        self.message = None
        self.uname = ""
        self.uid = ""
        self.desc = ""
        self.pkcount = 0
        self.pasteURL = ""

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("You cannot control this menu.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def mystbin(self, text):
        timeout = aiohttp.ClientTimeout(total=15)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                payload = {"files": [{"content": text, "name": "No Title"}]}
                headers = {"Content-Type": "application/json"}
                async with session.post(url="https://api.pastey.gg/pastes", json=payload, headers=headers) as r:
                    if r.status == 201:
                        mdata = await r.json()
                        return f"https://pastey.gg/{mdata['id']}"
                    else:
                        logger.warning("pastey.gg upload failed: HTTP %s", r.status)
                        return "https://pastey.gg/"
        except asyncio.TimeoutError:
            logger.warning("pastey.gg upload timed out.")
            return "https://pastey.gg/"

    async def cleanResults(self):
        if self.results and self.results.get("success"):
            self.uname = self.results["data"]["name"]
            self.uid = self.results["data"]["id"]
            self.desc = ""
            coloreds = ["Ancient", "Cursed", "Glitter", "Golden", "Luminous", "Rainbow", "Shadow"]
            op = [
                i["name"] + " " + i["gender"] + " - Level: " + str(i["level"])
                for i in self.results["data"]["pokemon"]
                if i["loan"] == "0" and any(i["name"].startswith(x) for x in coloreds)
            ]
            self.pkcount = len(op)

            def chunks(lst, n):
                for i in range(0, len(lst), n):
                    yield lst[i: i + n]

            if not op:
                self.desc = f"`{self.uname}'s box contains no colored pokemons.`"
                self.results = []
            else:
                self.results = list(chunks(op, 20))
                mytext = f"Box of {self.uname} - #{self.uid}\n"
                mytext += f"(This box contains {self.pkcount} colored pokemons)\n\n"
                pokes = [poke for lst in self.results for poke in lst]
                mytext += "\n".join(pokes)
                mytext += "\n\n>> Box organizer by Creed Bot <<"
                self.pasteURL = await self.mystbin(mytext)
        else:
            self.desc = "`Please provide a valid username.`"
            self.results = None

    def genEmbed(self):
        embed = discord.Embed(color=discord.Color.dark_gold())
        embed.set_author(name="Box of " + self.uname + ' - #' + self.uid)
        return embed

    def getPagewiseDetails(self, pg):
        if self.results == []:
            embed = discord.Embed()
            embed.set_author(name="Box of " + self.uname + ' - #' + self.uid)
            embed.description = self.desc
            embed.set_footer(text="Box Organizer", icon_url=self.ctx.me.display_avatar.url)
            return embed

        if self.results is None:
            embed = discord.Embed()
            embed.set_author(name="Username not found")
            embed.description = self.desc
            embed.set_footer(text="Box Organizer", icon_url=self.ctx.me.display_avatar.url)
            return embed

        embed = self.genEmbed()
        self.desc = (
            f"**(This box contains {self.pkcount} colored pokemons)**\n"
            f"[Click here to get the complete list!]({self.pasteURL})\n\n"
        )
        embed.description = self.desc + "\n".join(self.results[pg])
        embed.set_footer(
            text=f"Box Organizer | Page {pg + 1} of {len(self.results)}",
            icon_url=self.ctx.me.display_avatar.url
        )
        return embed

    async def start(self):
        await self.cleanResults()
        embed = self.getPagewiseDetails(self.pg)
        if not self.results:
            self.message = await self.ctx.send(embed=embed)
        else:
            self.message = await self.ctx.send(embed=embed, view=self)

    @discord.ui.button(emoji="⏮️", style=discord.ButtonStyle.secondary)
    async def first_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.results:
            return
        self.pg = 0
        await interaction.response.edit_message(embed=self.getPagewiseDetails(self.pg), view=self)

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.primary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.results:
            return
        self.pg = (self.pg - 1) % len(self.results)
        await interaction.response.edit_message(embed=self.getPagewiseDetails(self.pg), view=self)

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger)
    async def stop_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        if self.message:
            await self.message.delete()

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.primary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.results:
            return
        self.pg = (self.pg + 1) % len(self.results)
        await interaction.response.edit_message(embed=self.getPagewiseDetails(self.pg), view=self)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary)
    async def last_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.results:
            return
        self.pg = len(self.results) - 1
        await interaction.response.edit_message(embed=self.getPagewiseDetails(self.pg), view=self)

    @discord.ui.button(emoji="🔢", style=discord.ButtonStyle.secondary)
    async def jump_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.results:
            return
        await interaction.response.send_modal(PageJumpModal(self))


class PokemonCreed(commands.Cog):
    """Pokemon Creed related commands"""
    def __init__(self, client):
        self.client = client

    def convertNumber(self, x):
        op = 0
        num_map = {'K': 1000, 'M': 1000000, 'B': 1000000000, 'T': 1000000000000, 'Q': 1000000000000000}
        if x.isdigit():
            op = int(x)
        else:
            if len(x) > 1:
                op = float(x[:-1]) * num_map.get(x[-1].upper(), 1)
        return int(op)


    async def mystbin(self, text):
        timeout = aiohttp.ClientTimeout(total=15)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                payload = {"files":[{"content": text, "name": "No Title"}]}
                headers = {"Content-Type": "application/json"}
                async with session.post(url="https://api.pastey.gg/pastes", json=payload, headers=headers) as r:
                    if r.status == 201:
                        mdata = await r.json()
                        return f"https://pastey.gg/{mdata['id']}"
                    else:
                        logger.warning("pastey.gg upload failed: HTTP %s", r.status)
                        return f"https://pastey.gg/"
        except asyncio.TimeoutError:
            logger.warning("pastey.gg upload timed out.")
            return f"https://pastey.gg/"
    
    def human_format(self, num, round_to=2):
        magnitude = 0
        while abs(num) >= 1000:
            magnitude += 1
            num = round(num / 1000.0, round_to)
        return '{:.2f}{}'.format(num, ['', 'k', 'm', 'g', 't', 'p'][magnitude])
    
    async def findRate(self, pokename):
        """"Fetch rate of a pokemon and returns the result"""
        if pokename in self.client.rate_cache:
            return self.client.rate_cache[pokename]
        
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"https://pokemoncreed.net/ajax/pokedex.php?pokemon={pokename}") as r:
                    if r.status != 200:
                        logger.warning("Pokedex API failed for '%s': HTTP %s", pokename, r.status)
                        return ""
                    data = await r.text()
            result = json.loads(data)
            if result["success"]:
                rate = result["rating"]
                self.client.rate_cache[pokename] = rate
            else:
                rate = ""
            return rate
        except Exception as e:
            logger.error("findRate failed for '%s'", pokename, exc_info=e)
            return ""
    
    async def calculate_box_rating(self, userName):
        """Fetch a user's box from Pokemon Creed and calculate the total colored-pokemon rating.

        Returns a dict with keys:
            - username (str)
            - user_id (str)
            - total_rating (int/float)
            - total_rating_formatted (str)
            - colored_count (int)
            - paste_url (str)
        Returns None with an "error" key on failure, e.g.:
            {"error": "username_not_found"} or {"error": "timeout"} or {"error": "no_colored"}
        """
        # 1. Fetch box data
        timeout = aiohttp.ClientTimeout(total=15)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"https://pokemoncreed.net/ajax/box.php?user={userName}") as r:
                    data = await r.text()
        except asyncio.TimeoutError:
            return {"error": "timeout"}

        result = json.loads(data)
        if not result["success"]:
            return {"error": "username_not_found"}

        uname = result["data"]["name"]
        uid = result["data"]["id"]

        # 2. Categorize colored pokemon
        coloreds = ["Cursed", "Glitter", "Golden", "Luminous", "Rainbow", "Shadow"]
        output = {"base": [], "unbase": [], "other": []}
        findrates = []

        for poke in result["data"]["pokemon"]:
            if poke["loan"] == "0" and any(poke["name"].startswith(x) for x in coloreds):
                if poke["name"] not in findrates:
                    findrates.append(poke["name"])

                if poke["level"] == 5:
                    output["base"].append({"name": poke["name"], "gender": poke["gender"], "level": poke["level"]})
                elif poke["level"] > 5:
                    output["unbase"].append({"name": poke["name"], "gender": poke["gender"], "level": poke["level"]})
                else:
                    output["other"].append({"name": poke["name"], "gender": poke["gender"], "level": poke["level"]})

        pkcount = len(output["base"]) + len(output["unbase"]) + len(output["other"])
        if not pkcount:
            return {"error": "no_colored", "username": uname, "user_id": uid}

        # 3. Fetch rates for each unique pokemon
        foundrates = {}
        for poke in findrates:
            pkrate = await self.findRate(poke)
            pkrate = pkrate.replace("+", "")
            try:
                pkrate = self.convertNumber(pkrate.split(" ", 1)[0])
                foundrates[poke] = pkrate
            except (ValueError, KeyError):
                pass

        # 4. Calculate rating per pokemon
        considered = []
        considered_rates = {}
        ignored = []
        sumthese = []

        for category in output:
            for poke in output[category]:
                if foundrates.get(poke["name"], False):
                    rate = foundrates.get(poke["name"]) * self.client.boxrateconfig[category]
                    label = f"{poke['name']} {poke['gender']} - Level: {poke['level']}"
                    considered.append(label)
                    considered_rates[label] = rate
                    sumthese.append(rate)
                else:
                    ignored.append(f"{poke['name']} {poke['gender']} - Level: {poke['level']}")

        # 5. Aggregate duplicates
        cleaned_considered = {}
        for poke in considered:
            if poke in cleaned_considered:
                cleaned_considered[poke][0] += 1
            else:
                cleaned_considered[poke] = [1, considered_rates[poke]]

        cleaned_ignored = {}
        for poke in ignored:
            if poke in cleaned_ignored:
                cleaned_ignored[poke][0] += 1
            else:
                cleaned_ignored[poke] = [1, ""]

        # 6. Build paste text and upload
        considered_text = ""
        for poke, details in cleaned_considered.items():
            considered_text += f"{details[0]}x {poke} [{self.human_format(details[0] * details [1])}] \n"

        ignored_text = ""
        for poke, details in cleaned_ignored.items():
            ignored_text += f"{details[0]}x {poke} \n"

        mytext = f"Box Rater: {uname} - #{uid}\n\n"
        mytext += f"Total Rating: {self.human_format(sum(sumthese))}\n\n"
        mytext += f"\n\n** Unbase: {self.client.boxrateconfig['unbase']}x Rate List |  Level 4 or less: {self.client.boxrateconfig['other']}x Rate List | Genderless/Special Genders are rated normally.**\n\n"
        mytext += "Below pokemons are considered while rating the box: \n\n"""
        mytext += considered_text
        mytext += "\n\nBelow pokemons are NOT considered: \n\n"""
        mytext += ignored_text
        mytext += "\n\n>> Box Rater by Creed Bot <<"

        paste_url = await self.mystbin(mytext)

        return {
            "username": uname,
            "user_id": uid,
            "total_rating": sum(sumthese),
            "total_rating_formatted": self.human_format(sum(sumthese)),
            "colored_count": pkcount,
            "paste_url": paste_url,
        }

    @commands.command(aliases = ["ratebox"])
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def boxrater(self, ctx, *, userName):
        """Box Rater (Beta) for Pokemon Creed users. [1 mins cooldown]"""

        embed = discord.Embed(title=f"Box Rater: {userName}")
        embed.description = f"{self.client.emotes.get('loading', '')} Analyzing your box and calculating it's total worth...\n"
        zzz = await ctx.send(embed=embed)

        rating = await self.calculate_box_rating(userName)

        if rating.get("error") == "timeout":
            embed.description = "`Request timed out. The site may be down — please try again later.`"
            await zzz.edit(embed=embed)
            return
        elif rating.get("error") == "username_not_found":
            embed.description = "Username not found!"
            await zzz.edit(embed=embed)
            return
        elif rating.get("error") == "no_colored":
            embed.description = f"{rating['username']} -#{rating['user_id']} has no colored pokemons to rate!"
            embed.title = f"Box Rater: {rating['username']} - #{rating['user_id']}"
            await zzz.edit(embed=embed)
            return

        embed.title = f"Box Rater: {rating['username']} - #{rating['user_id']}"
        embed.description = f"{self.client.emotes.get('greentick','')} **Total Rating:** {rating['total_rating_formatted']}\n"
        embed.description += f"{self.client.emotes.get('pin','')} [click here for details]({rating['paste_url']})"
        await zzz.edit(embed=embed)

    @commands.command(aliases=["creedpf", "creed_profile"])
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def profile(self, ctx, *, userName):
        """Displays the profile of a Pokemon Creed user."""
        host = "https://pokemoncreed.net"

        loading_embed = discord.Embed(title=f"Profile: {userName}")
        loading_embed.description = f"{self.client.emotes.get('loading', '')} Fetching user profile...\n"
        zzz = await ctx.send(embed=loading_embed)

        # ── 1. Fetch user profile ─────────────────────────────────────
        timeout = aiohttp.ClientTimeout(total=15)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{host}/ajax/user.php?user={userName}") as r:
                    raw = await r.text()
        except asyncio.TimeoutError:
            await zzz.edit(content="`Request timed out. The site may be down — please try again later.`", embed=None)
            return

        resp = json.loads(raw)
        data = resp.get("data", {})
        if not data:
            await zzz.edit(content="`User not found! Please provide a valid username.`", embed=None)
            return

        username   = data.get("username", "N/A")
        user_id    = data.get("id", "N/A")
        level      = f"{int(data.get('trainerlevel', 0)):,}"
        coins      = f"{int(data.get('coins', 0)):,}"
        money      = f"${int(data.get('money', 0)):,}"
        last_active = data.get("lastactive", "0")
        avatar     = data.get("avatar", "88882")
        roster     = data.get("roster", [])

        # ── 2. Derive accent colour from the first roster mon ─────────
        first_mon_name = roster[0].get("name", "Ghost") if roster else "Ghost"
        embed_color = 0x28D2EF

        # ── 3. Fetch box rating ───────────────────────────────────────
        rating = await self.calculate_box_rating(username)

        # ── 4. Build and send the component view ──────────────────────
        view = ProfileView(
            author_id=ctx.author.id,
            username=username,
            user_id=user_id,
            trainer_level=level,
            coins=coins,
            cash=money,
            last_active=last_active,
            avatar=avatar,
            roster=roster,
            box_rating=rating,
            embed_color=embed_color,
        )

        await zzz.edit(content=None, embed=None, view=view)
        view.message = zzz

    @commands.group()
    async def exp(self, ctx):
        """Exp related commands. Use !help exp for more commands."""
        scmds = [c.qualified_name + f" - {c.help}" +"\n" for c in self.exp.commands]
        if ctx.invoked_subcommand is None:
            embed = discord.Embed(title="Exp Sub Commands:")
            embed.description = f'```{"".join(scmds)}```'
            embed.set_footer(text="do !help exp <subcommand> for more info")
            await ctx.send(embed=embed)
       
    @exp.command(name = "for")
    async def exp_for(self, ctx, level:str):
        """Calculates Xp required for given Level."""
        level = level.replace(",","")
        try:
            level = self.convertNumber(level)
        except Exception as e:
            await ctx.send(f"```Invalid inputs provided!```", delete_after=3)
            return
        embed = discord.Embed()
        embed.description = f"```Level: {level:,} pokemon will have {(level ** 3) + 1:,} xp!```"
        await ctx.send(embed=embed)
        
    @exp.command(name = "gain")
    async def exp_gain(self, ctx, level:str, *, bonus = ''):
        """Calculates Xp gained against Mew for given Level."""
        multiplier = 1
        boosts = []
        level = level.replace(",","")
        if 'egg' in bonus:
            multiplier *= 1.6
            boosts.append('Lucky Egg')
        if 'vip' in bonus:
            multiplier *= 1.25
            boosts.append('VIP')
        try:
            level = self.convertNumber(level)
        except Exception as e:
            await ctx.send(f"`Invalid inputs provided!`", delete_after=3)
            return
        exp = round(multiplier * (level * 10) ** 1.7)
        embed = discord.Embed()
        
        if multiplier > 1:
            embed.description = f"```With {' & '.join(boosts)}, You will receive {exp:,} xp against Mysterious Trainer's Mew for level {level:,}.```"
        else:
            embed.description = f"```You will receive {exp:,} xp against Mysterious Trainer's Mew for level {level:,}.```"
        await ctx.send(embed=embed)
        
    @exp.command(name = "diff")
    async def exp_diff(self, ctx, level1:str, level2:str):
        """Calculates Xp difference between given two levels."""
        level1 = level1.replace(",","")
        level2 = level2.replace(",","")
        try:
            levels = sorted([self.convertNumber(lvl) for lvl in [level1, level2]])
        except Exception as e:
            await ctx.send(f"```Invalid inputs provided!```", delete_after=3)
            return
        exp = round((levels[1] ** 3 - levels[0] ** 3))
        embed = discord.Embed()
        embed.description = f'```The xp difference between level: {levels[0]:,} and level: {levels[1]:,} is {exp:,} xp!```'
        await ctx.send(embed=embed)
        
    @exp.command(name = "level")
    async def exp_level(self, ctx, experience:str):
        """Calculates Level corresponding to given Xp."""
        experience = experience.replace(",","")
        try:
            exp = self.convertNumber(experience)
        except Exception as e:
            await ctx.send(f"```Invalid inputs provided!```", delete_after=3)
            return
        level = int((exp ** (1/3)))
        embed = discord.Embed()
        embed.description = f'```Level: {level:,} pokemon will have {exp:,} xp!```'
        await ctx.send(embed=embed)
        
    @exp.command(name = "train")
    async def exp_train(self, ctx, *, levelTOexp):
        """Calculates New Level after training the given Level by given Xp."""
        levelTOexp = levelTOexp.replace(",","")
        try:
            level, exp = levelTOexp.replace(" ","").split("to")
        except ValueError:
            await ctx.send("Invalid inputs! Use `exp train <level> to <exp>`", delete_after=5)
            return
        
        try:
            level = self.convertNumber(level)
            exp = self.convertNumber(exp)
        except Exception as e:
            await ctx.send(f"```Invalid inputs provided!```", delete_after=3)
            return
        
        flevel = ((level ** 3 + 1) + exp) ** (1/3)
        embed = discord.Embed()
        embed.description = f'```Training level {level:,} to {exp:,} xp will be level {int(flevel):,}!```'
        await ctx.send(embed=embed)


    @commands.command(aliases = ['rate', 'rarity'])
    async def p(self, ctx, *, pokemon):
        """Displays rate, rarity and sprite of the Creed Pokemon."""
        timeout = aiohttp.ClientTimeout(total=15)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"https://pokemoncreed.net/ajax/pokedex.php?pokemon={pokemon}") as r:
                    data = await r.text()
        except asyncio.TimeoutError:
            await ctx.send("`Request timed out. The site may be down — please try again later.`")
            return
        result = json.loads(data)
        if result["success"]:
            self.client.rate_cache[result["name"]] = result["rating"]
            embed = discord.Embed(title = result["name"],
                                  url = "https://pokemoncreed.net/search_pokemon.php?pokemon=" + result[
                                      "name"].replace(".","").replace(" ","%20") + "&trainer=&og=&ntrainer=&gender=&search=Search",
                                  color = result["color"])
            embed.set_thumbnail(url = 'https://pokemoncreed.net/sprites/' + result["name"].replace(".","").replace(" ","%20") + '.png')
            embed.set_footer(text = result["name"] + " | Requested by " + ctx.author.name,
                             icon_url = 'https://pokemoncreed.net/img/icon/' + result["name"].replace(".","").replace(" ","%20") + '.gif')
            embed.add_field(name = "**Rarity:**",
                            value = str(result["rarity"]["total"]) + " (" + str(result["rarity"]["male"]) + "M/" +
                                    str(result["rarity"]["female"]) + "F/" + str(result["rarity"]["ungendered"]) + "G)", inline = False)
            embed.add_field(name = "**Rate:**", value = result["rating"])
            await ctx.send(embed = embed)
        else:
            embed = discord.Embed(title = "Pokemon Not Found!",
                                  description = "Try searching for a different Pokemon...",
                                  color = discord.Color.dark_gold())
            await ctx.send(embed = embed)

    @commands.command(aliases = [])
    @commands.cooldown(1, 120, commands.BucketType.user)
    async def box(self, ctx, *, uname):
        """Displays colored pokemons of a Creed user. [2 mins cooldown]"""
        url = 'https://pokemoncreed.net/ajax/box.php?user=' + uname

        timeout = aiohttp.ClientTimeout(total=15)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as r:
                    data = await r.text()
        except asyncio.TimeoutError:
            await ctx.send("`Request timed out. The site may be down — please try again later.`")
            return

        result = json.loads(data)
        bv = BoxView(ctx, result)
        await bv.start()


    @commands.command(aliases = ['pkrate'])
    async def pokerate(self, ctx, *, pkmn):
        """Computes the total rate of given pokemon(s)."""
        pkmn = pkmn.replace("+", ",").replace("\n", ",").split(',')
        considered = []
        not_considered = []
        rates = []
        desc = f"{self.client.emotes.get('loading','')} Computing rates...\n(This might take some time!)"
        embed = discord.Embed(description = desc)
        embed.set_author(name = "Creed Bot (Pokemon Rater)", icon_url = ctx.me.display_avatar.url)
        m = await ctx.send(embed = embed)
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for pk in pkmn:
                tmp = pk.split('*')
                pk = tmp[0].strip()
                try:
                    c = int(tmp[1])
                except Exception as e:
                    c = 1

                url = 'https://pokemoncreed.net/ajax/pokedex.php?pokemon=' + pk
                try:
                    async with session.get(url) as r:
                        data = await r.text()
                except asyncio.TimeoutError:
                    logger.warning("pokerate timed out for '%s'", pk)
                    not_considered.append(pk)
                    continue
                except Exception as e:
                    logger.warning("pokerate fetch failed for '%s': %s", pk, e)
                    not_considered.append(pk)
                    continue
                result = json.loads(data)

                if result["success"]:
                    self.client.rate_cache[result["name"]] = result["rating"]
                    pk = result["name"].strip()
                    try:
                        rate = result["rating"].replace("+", "").split(" ", 1)[0]
                        rate = self.convertNumber(rate)
                        considered.append(f"{pk} - ({result['rating']}) [x{c}]")
                        rates.append(rate * c)
                    except Exception as e:
                        logger.warning("Could not parse rate for '%s': %s", pk, e)
                        not_considered.append(pk)
                else:
                    not_considered.append(pk)
        desc = "\n"
        if considered:
            desc += "\n".join(considered)
            desc += f"\n\n**Total Rating: {sum(rates):,}**\n"

        embed = discord.Embed(description = desc)

        if not_considered:
            embed.add_field(name = "Below pokemon(s) are not considered:", value = "\n".join(not_considered))
        embed.set_author(name = "Creed Bot (Pokemon Rater)", icon_url = ctx.me.display_avatar.url)
        embed.set_footer(text = f'Requested by {ctx.author.name}', icon_url = ctx.author.display_avatar.url)
        await m.edit(embed = embed)

    # ==========================================
    #  Collection Commands (Guild-restricted)
    # ==========================================

    async def _resolve_user(self, ctx, user_input):
        """Resolve a user from mention, name, or raw ID."""
        if user_input is None:
            return ctx.author
        try:
            return await commands.MemberConverter().convert(ctx, user_input)
        except commands.MemberNotFound:
            pass
        try:
            return await commands.UserConverter().convert(ctx, user_input)
        except commands.UserNotFound:
            pass
        try:
            return await self.client.fetch_user(int(user_input))
        except (ValueError, discord.NotFound, discord.HTTPException):
            return None

    @commands.group(aliases=['cl'], invoke_without_command=True)
    @commands.guild_only()
    async def collection(self, ctx):
        """Collection commands for Pokemon Creed users."""
        if ctx.guild.id not in self.client.collection_allowed_guilds:
            raise commands.CheckFailure("This command is not available in this server.")

        p = ctx.prefix
        msg = (
            f"**Collection Commands:**\n"
            f"```\n"
            f"{p}collection view [@user|id] - View a user's collection\n"
            f"{p}collection set <text>      - Set your collection\n"
            f"{p}collection clear           - Clear your collection\n"
            f"```\n"
            f"Alias: `{p}cl` | do `{p}help collection <subcommand>` for more info"
        )
        await ctx.send(msg)

    @collection.before_invoke
    async def collection_before_invoke(self, ctx):
        """Guild check applied before any collection subcommand runs."""
        if ctx.guild.id not in self.client.collection_allowed_guilds:
            logger.warning("Collection command blocked in guild %s (%s) by %s (%s)", ctx.guild.name, ctx.guild.id, ctx.author, ctx.author.id)
            raise commands.CheckFailure("This command is not available in this server.")

    @collection.command(name="view", aliases=["show"])
    async def collection_view(self, ctx, *, user=None):
        """Displays the collection of a user. Accepts @mention or user ID."""
        target = await self._resolve_user(ctx, user)
        if target is None:
            logger.debug("collection view: user not found for input '%s' by %s (%s)", user, ctx.author, ctx.author.id)
            await ctx.send(f"{self.client.emotes.get('redtick', '❌')} `User not found.`")
            return

        col = self.client.db.get_collection("collections")
        record = await col.find_one({"user_id": target.id})

        if not record:
            logger.info("collection view: no collection found for %s (%s), requested by %s (%s)", target, target.id, ctx.author, ctx.author.id)
            await ctx.send(f"`{target.display_name} has not set a collection yet.`")
            return

        embed = discord.Embed(color=discord.Color.dark_gold())
        embed.set_author(name=f"{target.display_name}'s Collection", icon_url=target.display_avatar.url)
        embed.description = record["text"]

        logger.info("collection view: %s (%s) viewed collection of %s (%s)", ctx.author, ctx.author.id, target, target.id)
        await ctx.send(embed=embed)

    @collection.command(name="set", aliases=["update"])
    async def collection_set(self, ctx, *, text: str):
        """Sets or updates your collection text. (Max 4096 characters)"""
        if len(text) > 4096:
            await ctx.send(
                f"{self.client.emotes.get('redtick', '❌')} "
                f"`Collection text is too long! ({len(text)}/4096 characters)`"
            )
            return

        col = self.client.db.get_collection("collections")
        now = datetime.now(timezone.utc).strftime("%d %b, %Y | %I:%M:%S %p UTC")

        existing = await col.find_one({"user_id": ctx.author.id})

        update_data = {
            "$set": {
                "user_id": ctx.author.id,
                "text": text,
                "updated_at": now
            }
        }
        if not existing:
            update_data["$set"]["created_at"] = now

        await col.update_one({"user_id": ctx.author.id}, update_data, upsert=True)
        action = "created" if not existing else "updated"
        logger.info("collection set: %s (%s) %s their collection (%d/4096 chars)", ctx.author, ctx.author.id, action, len(text))
        await ctx.send(
            f"{self.client.emotes.get('greentick', '✅')} "
            f"`Collection set! ({len(text)}/4096 characters)`"
        )

    @collection.command(name="clear", aliases=["delete"])
    async def collection_clear(self, ctx):
        """Clears your collection after confirmation."""
        col = self.client.db.get_collection("collections")
        record = await col.find_one({"user_id": ctx.author.id})

        if not record:
            await ctx.send(f"{self.client.emotes.get('redtick', '❌')} `You don't have a collection to clear.`")
            return

        view = ConfirmView(ctx.author.id, timeout=20.0)
        confirm_msg = await ctx.send("⚠️ Are you sure you want to clear your collection?", view=view)
        await view.wait()

        if view.value is True:
            await col.delete_one({"user_id": ctx.author.id})
            logger.info("collection clear: %s (%s) cleared their collection", ctx.author, ctx.author.id)
            await confirm_msg.edit(content=f"{self.client.emotes.get('greentick', '✅')} `Your collection has been cleared.`", view=None)
        else:
            logger.info("collection clear: %s (%s) cancelled or timed out", ctx.author, ctx.author.id)
            await confirm_msg.edit(content=f"{self.client.emotes.get('timer', '⏱️')} `Collection clear cancelled.`", view=None)


async def setup(client):
    await client.add_cog(PokemonCreed(client))
