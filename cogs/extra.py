import discord, os, mechanicalsoup, asyncio, json, aiohttp, requests, re
from discord.ext import commands, tasks
from bs4 import BeautifulSoup
from datetime import datetime

class Extra(commands.Cog):
    """Extra Features for Premium Servers!"""
    def __init__(self, client):
        #uncomment the below line before uploading to github
        self.hitdownBGTask.start()
        self.promoBGTask.start()
        self.client = client

    @property
    def get_hd_channel(self):
        return self.client.get_channel(1003494747521949716)

    @property
    def get_promo_channel(self):
        return self.client.get_channel(1073949084244770856)
      

    async def scrape_hd(self):
        username, password = os.environ.get('CREED_LOGIN').split(',')
        login_url = 'https://pokemoncreed.net/login.php'
        scrape_url = 'https://pokemoncreed.net/hitdown.php'
        
        session = requests.Session()
        
        login_page = session.get(login_url)
        soup = BeautifulSoup(login_page.content, 'html.parser')
        
        token = soup.find('input', {'name': 'token'})['value']
        backuptoken = soup.find('input', {'name': 'backuptoken'})['value']
        
        credentials = {
            'username': username,
            'password': password,
            'token': token ,
            'backuptoken': backuptoken
        }
        
        login_response = session.post(login_url, data=credentials)
        
        if 'logout' in login_response.text:
            
            scrape_response = session.get(scrape_url)
            soup = BeautifulSoup(scrape_response.content, 'html.parser')
        
            countdown_span = soup.find('span', class_='fn-countdown')
            if countdown_span:
                time_str = countdown_span.get_text(strip=True)
            else:
                time_str = ""

            pattern = re.compile(r"(\d+)\s*hour[s]*|(\d+)\s*minute[s]*|(\d+)\s*second[s]*")
            matches = pattern.findall(time_str)
            
            # Initialize the dictionary with default values
            time_dict = {'h': 0, 'm': 0, 's': 0}
            
            # Iterate over the matches and fill the dictionary
            for match in matches:
                if match[0]:
                    time_dict['h'] = int(match[0])
                elif match[1]:
                    time_dict['m'] = int(match[1])
                elif match[2]:
                    time_dict['s'] = int(match[2])
            
            #Saving the Next HD for reference
            self.client.next_hitdown = time_dict
            return time_dict
        else:
            print("Login failed!")

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
        else:
            pass

  
    @promoBGTask.before_loop
    async def before_promoBGTask(self):
        await self.client.wait_until_ready()


async def setup(client):
    await client.add_cog(Extra(client))
