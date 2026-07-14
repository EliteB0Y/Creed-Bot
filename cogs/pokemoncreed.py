import discord, mechanicalsoup, asyncio, json, aiohttp
from datetime import datetime, timezone
import logging
from discord.ext import commands, menus

logger = logging.getLogger("CreedBot")

class BoxMenu(menus.Menu):
    def __init__(self, ctx, results):
        super().__init__()
        self.ctx = ctx
        self.results = results
        self.pg = 0
    
    async def mystbin(self, text):
        async with aiohttp.ClientSession() as session:
            payload = {"files":[{"content": text, "name": "No Title"}]}
            headers = {"Content-Type": "application/json"}
            async with session.post(url="https://api.pastey.gg/pastes", json=payload, headers=headers) as r:
                if r.status == 201:
                    mdata = await r.json()
                    return f"https://pastey.gg/{mdata['id']}"
                else:
                    logger.warning("pastey.gg upload failed: HTTP %s", r.status)
                    return f"https://pastey.gg/"

    async def cleanResults(self):
        if self.results["success"]:
            self.uname = self.results["data"]["name"]
            self.uid = self.results["data"]["id"]
            self.desc = ""
            coloreds = ["Ancient", "Cursed", "Glitter", "Golden", "Luminous", "Rainbow", "Shadow"]
            op = [i["name"] + " " + i["gender"] + " - Level: " + str(i["level"]) for i in self.results["data"]["pokemon"] if
                  i["loan"] == "0" and any(i["name"].startswith(x) for x in coloreds)]
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
            self.desc = f"`Please provide a valid username.`"
            self.results = None

    def genEmbed(self):
        embed = discord.Embed(color = discord.Color.dark_gold())
        embed.set_author(name = "Box of " + self.uname + ' - #' + self.uid)
        return embed
    
    def getPagewiseDetails(self, pg):
        result = self.results
        if result == []:
            embed = discord.Embed()
            embed.set_author(name = "Box of " + self.uname + ' - #' + self.uid)
            embed.description = self.desc
            embed.set_footer(text=f"Box Organizer", icon_url= self.ctx.me.avatar)
            return embed

        if result is None:
            embed = discord.Embed()
            embed.set_author(name = "Username not found")
            embed.description = self.desc
            embed.set_footer(text=f"Box Organizer", icon_url= self.ctx.me.avatar)
            return embed

        embed = self.genEmbed()
        self.desc = f"**(This box contains {self.pkcount} colored pokemons)**\n[Click here to get the complete list!]({self.pasteURL})\n\n"
        embed.description = self.desc + "\n".join(result[pg])
        embed.set_footer(text=f"Box Organizer | Page {pg+1} of {len(result)}", icon_url= self.ctx.me.avatar)
        return embed
                    
    def check(self, payload):
        return payload.message_id == self.message.id and payload.user_id == self.ctx.author.id
                    
    async def send_initial_message(self, ctx, channel):
        await self.cleanResults()
        embed = self.getPagewiseDetails(self.pg)
        return await channel.send(embed=embed)
    
    buttonz = {"first": "<:first:800209150227120158>","back": "<:back:800215055634399232>", "stop": "<:stop:800214101791735808>", "next": "<:next:800214875669528596>", "last": "<:last:800209919734972426>", "page": "\U0001f522"}
    
    @menus.button(buttonz.get("first"))
    async def on_first_button(self, payload):
        if not self.check(payload):
            return 
        self.pg = 0
        self.pg %=  len(self.results)
        await self.message.edit(embed=self.getPagewiseDetails(self.pg))
    
    @menus.button(buttonz.get("back"))
    async def on_previous_button(self, payload):
        if not self.check(payload):
            return
        self.pg -= 1
        self.pg %=  len(self.results)
        await self.message.edit(embed=self.getPagewiseDetails(self.pg))
                
    @menus.button(buttonz.get("stop"))
    async def on_stop_button(self, payload):
        if not self.check(payload):
            return
        self.stop()
        await self.message.delete()
                        
    @menus.button(buttonz.get("next"))
    async def on_next_button(self, payload):
        if not self.check(payload):
            return 
        self.pg += 1
        self.pg %=  len(self.results)
        await self.message.edit(embed=self.getPagewiseDetails(self.pg))
        
    @menus.button(buttonz.get("last"))
    async def on_last_button(self, payload):
        if not self.check(payload):
            return 
        self.pg = -1
        self.pg %=  len(self.results)
        await self.message.edit(embed=self.getPagewiseDetails(self.pg))

    @menus.button(buttonz.get("page"))
    async def on_page_button(self, payload):
        if not self.check(payload):
            return
        tmp = await self.message.channel.send(f"`Enter the Page Number (1 - {len(self.results)}):`")

        def check(message):
            return message.author == payload.member

        try:
            msg  = await self.bot.wait_for('message', timeout = 10, check=check)
        except asyncio.TimeoutError:
            await tmp.delete()
            await self.message.channel.send('`Too bad!! You did not enter the page number...`', delete_after=3)
        else:
            try:
                await tmp.delete()
                await msg.delete()
                x = int(msg.content) - 1
                if 0 < x <= len(self.results):
                    self.pg = x
                    await self.message.edit(embed=self.getPagewiseDetails(self.pg))
                else:
                    raise Exception
            except Exception as e:
                logger.debug("Invalid page number input: %s", e)
                await self.message.channel.send('`Invalid page number.`', delete_after=3)


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
        async with aiohttp.ClientSession() as session:
            payload = {"files":[{"content": text, "name": "No Title"}]}
            headers = {"Content-Type": "application/json"}
            async with session.post(url="https://api.pastey.gg/pastes", json=payload, headers=headers) as r:
                if r.status == 201:
                    mdata = await r.json()
                    return f"https://pastey.gg/{mdata['id']}"
                else:
                    logger.warning("pastey.gg upload failed: HTTP %s", r.status)
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
            async with aiohttp.ClientSession() as session:
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
    
    @commands.command(aliases = ["ratebox"])
    @commands.cooldown(1, 120, commands.BucketType.user)
    async def boxrater(self, ctx, *, userName):
        """Box Rater (Beta) for Pokemon Creed users. [2 mins cooldown]"""

        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://pokemoncreed.net/ajax/box.php?user={userName}") as r:
                data = await r.text()

        result = json.loads(data)
        if result["success"]:
            uname = result["data"]["name"]
            uid = result["data"]["id"]

            embed = discord.Embed(title=f"Box Rater: {uname} - #{uid}")
            embed.description = f"{self.client.emotes.get('loading', '')} Initializing ...\n"
            zzz = await ctx.send(embed=embed)

            coloreds = ["Cursed", "Glitter", "Golden", "Luminous", "Rainbow", "Shadow"]

            output = {"base": [], "unbase": [], "other": []}
            findrates = []
            embed.description = f"""{self.client.emotes.get('greentick', '')} Initializing ...\n
                                    {self.client.emotes.get('loading','')} Collecting pokemons ...\n"""
            await zzz.edit(embed = embed)
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
                embed.description = f"{uname} -#{uid} has no colored pokemons to rate!"
                await zzz.edit(embed = embed)
            else:
                embed.description = f"""{self.client.emotes.get('greentick', '')} Initializing ...\n
                                    {self.client.emotes.get('greentick','')} Collecting pokemons ...\n
                                    {self.client.emotes.get('loading','')} Fetching rates ...\n"""
                await zzz.edit(embed = embed)
                #try to find rates of every pokemon that the user has (no duplicates)
                foundrates = {}
                for poke in findrates:
                    pkrate = await self.findRate(poke)
                    pkrate = pkrate.replace("+", "")

                    try:
                        pkrate = self.convertNumber(pkrate.split(" ", 1)[0])
                        foundrates[poke] = pkrate
                    except (ValueError, KeyError) as e:
                        #Silently ignore the convertion error.
                        pass
                        #logger.warning("Could not parse rate for '%s': %s", poke, e)

                #Now the actual calculation starts
                considered = []
                considered_rates = {}
                ignored = []
                sumthese = []
                embed.description = f"""{self.client.emotes.get('greentick', '')} Initializing ...\n
                                    {self.client.emotes.get('greentick','')} Collecting pokemons ...\n
                                    {self.client.emotes.get('greentick','')} Fetching rates ...\n
                                    {self.client.emotes.get('loading','')} Calculating ...\n"""
                await zzz.edit(embed = embed)
                for category in output:
                    for poke in output[category]:
                        if foundrates.get(poke["name"], False):
                            rate = foundrates.get(poke["name"]) * self.client.boxrateconfig[category]
                            considered.append(f"{poke['name']} {poke['gender']} - Level: {poke['level']}")
                            considered_rates[f"{poke['name']} {poke['gender']} - Level: {poke['level']}"] = rate
                            sumthese.append(rate)
                        else:
                            ignored.append(f"{poke['name']} {poke['gender']} - Level: {poke['level']}")

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

                pasteURL = await self.mystbin(mytext)
                embed.description = f"{self.client.emotes.get('greentick','')} **Total Rating:** {self.human_format(sum(sumthese))}\n"
                embed.description += f"{self.client.emotes.get('pin','')} [click here for details]({pasteURL})"
                await zzz.edit(embed = embed)
        else:
            await ctx.send("Username not found!")

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
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://pokemoncreed.net/ajax/pokedex.php?pokemon={pokemon}") as r:
                data = await r.text()
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
        browser = mechanicalsoup.StatefulBrowser()
        browser.open(url)
        data = browser.get_current_page().text
        result = json.loads(data)
        bm = BoxMenu(ctx, result)
        await bm.start(ctx)


    @commands.command(aliases = ['pkrate'])
    async def pokerate(self, ctx, *, pkmn):
        """Computes the total rate of given pokemon(s)."""
        browser = mechanicalsoup.StatefulBrowser()
        pkmn = pkmn.replace("+", ",").replace("\n", ",").split(',')
        considered = []
        not_considered = []
        rates = []
        desc = f"{self.client.emotes.get('loading','')} Computing rates...\n(This might take some time!)"
        embed = discord.Embed(description = desc)
        embed.set_author(name = "Creed Bot (Pokemon Rater)", icon_url = ctx.me.avatar)
        m = await ctx.send(embed = embed)
        for pk in pkmn:
            tmp = pk.split('*')
            pk = tmp[0].strip()
            try:
                c = int(tmp[1])
            except Exception as e:
                c = 1

            url = 'https://pokemoncreed.net/ajax/pokedex.php?pokemon=' + pk
            browser.open(url)
            data = browser.get_current_page().text
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
        embed.set_author(name = "Creed Bot (Pokemon Rater)", icon_url = ctx.me.avatar)
        embed.set_footer(text = f'Requested by {ctx.author.name}', icon_url = ctx.author.avatar)
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
        embed = discord.Embed(title="Collection Commands:", color=discord.Color.dark_gold())
        embed.description = (
            f"```\n"
            f"{p}collection view [@user|id] - View a user's collection\n"
            f"{p}collection set <text>      - Set your collection\n"
            f"{p}collection clear           - Clear your collection\n"
            f"```"
        )
        embed.set_footer(text=f"Alias: {p}cl | do {p}help collection <subcommand> for more info")
        await ctx.send(embed=embed)

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
        record = col.find_one({"user_id": target.id})

        if not record:
            logger.info("collection view: no collection found for %s (%s), requested by %s (%s)", target, target.id, ctx.author, ctx.author.id)
            await ctx.send(f"`{target.display_name} has not set a collection yet.`")
            return

        embed = discord.Embed(color=discord.Color.dark_gold())
        embed.set_author(name=f"{target.display_name}'s Collection", icon_url=target.display_avatar.url)
        embed.description = record["text"]

        footer_parts = []
        if "created_at" in record:
            footer_parts.append(f"Created: {record['created_at']}")
        if "updated_at" in record:
            footer_parts.append(f"Updated: {record['updated_at']}")
        embed.set_footer(text=" | ".join(footer_parts) if footer_parts else "Collection")

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

        existing = col.find_one({"user_id": ctx.author.id})

        update_data = {
            "$set": {
                "user_id": ctx.author.id,
                "text": text,
                "updated_at": now
            }
        }
        if not existing:
            update_data["$set"]["created_at"] = now

        col.update_one({"user_id": ctx.author.id}, update_data, upsert=True)
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
        record = col.find_one({"user_id": ctx.author.id})

        if not record:
            await ctx.send(f"{self.client.emotes.get('redtick', '❌')} `You don't have a collection to clear.`")
            return

        confirm_msg = await ctx.send("⚠️ Are you sure you want to clear your collection? React ✅ to confirm.")
        await confirm_msg.add_reaction("✅")

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) == "✅" and reaction.message.id == confirm_msg.id

        try:
            await self.client.wait_for("reaction_add", timeout=15.0, check=check)
        except asyncio.TimeoutError:
            logger.info("collection clear: %s (%s) timed out on confirmation", ctx.author, ctx.author.id)
            await ctx.send(f"{self.client.emotes.get('timer', '⏱️')} `Collection clear cancelled — timed out.`")
            return

        col.delete_one({"user_id": ctx.author.id})
        logger.info("collection clear: %s (%s) cleared their collection", ctx.author, ctx.author.id)
        await ctx.send(f"{self.client.emotes.get('greentick', '✅')} `Your collection has been cleared.`")


async def setup(client):
    await client.add_cog(PokemonCreed(client))
