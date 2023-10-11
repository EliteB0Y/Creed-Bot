import discord, os, mechanicalsoup, asyncio, json, aiohttp
from discord.ext import commands, menus

class BoxMenu(menus.Menu):
    def __init__(self, ctx, results):
        super().__init__()
        self.ctx = ctx
        self.results = results
        self.pg = 0
    
    async def mystbin(self, text):
        async with aiohttp.ClientSession() as session:
            pastedata = {"files":[{"content": text, "filename": "No Title"}]}
            async with session.put(url="https://api.mystb.in/paste", json=pastedata) as r:
                if r.status == 201:
                    mdata = await r.json()
                    return f"https://mystb.in/{mdata['id']}"
                else:
                    print("Oops! I couldn't upload text to mystb.in")
                    return f"https://mystb.in/"

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
                mytext += "\n\n>> Box organizer by EliteBOT <<"
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
            except:
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
            pastedata = {"files":[{"content": text, "filename": "No Title"}]}
            async with session.put(url="https://api.mystb.in/paste", json=pastedata) as r:
                if r.status == 201:
                    mdata = await r.json()
                    return f"https://mystb.in/{mdata['id']}"
                else:
                    print("Oops! I couldn't upload text to mystb.in")
                    return f"https://mystb.in/"
    
    def human_format(self, num, round_to=2):
        magnitude = 0
        while abs(num) >= 1000:
            magnitude += 1
            num = round(num / 1000.0, round_to)
        return '{:.2f}{}'.format(num, ['', 'k', 'm', 'g', 't', 'p'][magnitude])
    
    async def findRate(self, pokename):
        """"Fetch rate of a pokemon and returns the result"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://pokemoncreed.net/ajax/pokedex.php?pokemon={pokename}") as r:
                data = await r.text()
        result = json.loads(data)
        if result["success"]:
            rate = result["rating"]
        else:
            rate = ""
        return rate
    
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
                    except:
                        pass

                #Now the actual calculation starts
                considered = []
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
                            considered.append(f"{poke['name']} {poke['gender']} - Level: {poke['level']} [{self.human_format(rate)}]")
                            sumthese.append(rate)
                        else:
                            ignored.append(f"{poke['name']} {poke['gender']} - Level: {poke['level']}")
                
                mytext = f"Box Rater: {uname} - #{uid}\n\n"
                mytext += f"Total Rating: {self.human_format(sum(sumthese))}\n\n"
                mytext += f"\n\n** Unbase: {self.client.boxrateconfig['unbase']}x Rate List |  Level 4 or less: {self.client.boxrateconfig['other']}x Rate List | Genderless/Special Genders are rated normal**\n\n"
                mytext += "Below pokemons are considered while rating the box: \n\n"""
                mytext += "\n".join(considered)

                mytext += "\n\nBelow pokemons are NOT considered: \n\n"""
                mytext += "\n".join(ignored)

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
        except:
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
        embed.set_author(name = "TES Bot (Pokemon Rater)", icon_url = ctx.me.avatar)
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
                pk = result["name"].strip()
                try:
                    rate = result["rating"].replace("+", "").split(" ", 1)[0]
                    rate = self.convertNumber(rate)
                    considered.append(f"{pk} - ({result['rating']}) [x{c}]")
                    rates.append(rate * c)
                except Exception as e:
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
        embed.set_author(name = "TES Bot (Pokemon Rater)", icon_url = ctx.me.avatar)
        embed.set_footer(text = f'Requested by {ctx.author.name}', icon_url = ctx.author.avatar)
        await m.edit(embed = embed)

async def setup(client):
    await client.add_cog(PokemonCreed(client))