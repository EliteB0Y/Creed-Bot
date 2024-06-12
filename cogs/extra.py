import discord, os, mechanicalsoup, asyncio, json, aiohttp
from discord.ext import commands, tasks
from datetime import datetime

class Extra(commands.Cog):
    """Extra Features for Premium Servers!"""
    def __init__(self, client):
        #uncomment the below line before uploading to github
        self.hitdownBGTask.start()
        self.promoBGTask.start()
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

    @property
    def get_hd_channel(self):
        return self.client.get_channel(1003494747521949716)

    @property
    def get_promo_channel(self):
        return self.client.get_channel(1073949084244770856)
      

    async def scrape_hd(self):
        cred = os.environ.get('CREED_LOGIN').split(',')
        time_dict = {}
        browser = mechanicalsoup.StatefulBrowser()
        browser.open('https://pokemoncreed.net/login.php')
        browser.get_current_page()
        browser.select_form()
        browser["username"] = cred[0]
        browser["password"] = cred[1]
        response = browser.submit_selected()
        await asyncio.sleep(1)
        browser.open('https://pokemoncreed.net/hitdown.php')
        data = browser.get_current_page().text
        data = data[data.index('Time till next round:'):]
        data = data[22:data.index('.')]
        tmp = ''
        for i in range(len(data) - 1):
            if data[i].isnumeric():
                tmp += data[i]
            elif data[i + 1].isnumeric():
                tmp += ':'
            else:
                continue

        if all(i in data for i in ['hour', 'minutes']):
            t = tmp.split(':')
            time_dict['h'] = int(t[0])
            time_dict['m'] = int(t[1])
            time_dict['s'] = int(t[2])

        elif 'hour' not in data and 'minutes' in data:
            t = tmp.split(':')
            time_dict['h'] = 0
            time_dict['m'] = int(t[0])
            time_dict['s'] = int(t[1])

        elif 'hour' in data and 'minutes' not in data:
            t = tmp.split(':')
            time_dict['h'] = int(t[0])
            time_dict['m'] = 0
            time_dict['s'] = int(t[1])
        else:
            t = tmp.split(':')
            time_dict['h'] = 0
            time_dict['m'] = 0
            time_dict['s'] = int(tmp)

        browser.open('https://pokemoncreed.net/logout.php')
        return time_dict

    # <# BG Task: Hitdown - Start #>

    @tasks.loop(seconds = 120)
    async def hitdownBGTask(self):
        hd_channel = self.get_hd_channel

        try:
            t = await self.scrape_hd()
            sec = (t['h'] * 60 * 60) + (t['m'] * 60) + t['s'] - 100
            await asyncio.sleep(sec)
            await hd_channel.send('@everyone, It\'s Hitdown time!')
            await asyncio.sleep(300)
        except:
            print(f'Restarting Hitdown Nootification!')
            await asyncio.sleep(120)
            self.hitdownBGTask.restart()

    @hitdownBGTask.before_loop
    async def before_hitdownBGTask(self):
        await self.client.wait_until_ready()

    # <# BG Task: Hitdown - End #>

    # <# BG Task: Promo - Start #>

    @tasks.loop(seconds = 10)
    async def promoBGTask(self):
        promo_channel = self.get_promo_channel
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://pokemoncreed.net/ajax/pokedex.php?pokemon=promo") as r:
                data = await r.text()
        result = json.loads(data)
        current_promo = result["name"]
        if self.client.promo == "":
            self.client.promo = current_promo
            print(f"Promo set as {self.client.promo}")
        elif self.client.promo != current_promo:
            self.client.promo = current_promo
            print(f"Promo change detected: {self.client.promo}")
            await promo_channel.send(f"@everyone New Promo: {self.client.promo}")

  
    @promoBGTask.before_loop
    async def before_promoBGTask(self):
        await self.client.wait_until_ready()


async def setup(client):
    await client.add_cog(Extra(client))
