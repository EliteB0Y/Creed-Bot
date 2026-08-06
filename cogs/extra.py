import discord, os, mechanicalsoup, asyncio, json, aiohttp, requests, re
import logging
from discord.ext import commands, tasks
from bs4 import BeautifulSoup
from datetime import datetime, timezone

logger = logging.getLogger("CreedBot")

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
      

    def _sync_scrape_hd(self):
        """Synchronous hitdown scraping — runs in a thread executor."""
        username, password = os.environ.get('CREED_LOGIN').split(',')
        login_url = 'https://pokemoncreed.net/login.php'
        scrape_url = 'https://pokemoncreed.net/hitdown.php'
        
        session = requests.Session()
        
        login_page = session.get(login_url, timeout=15)
        soup = BeautifulSoup(login_page.content, 'html.parser')
        
        token = soup.find('input', {'name': 'token'})['value']
        backuptoken = soup.find('input', {'name': 'backuptoken'})['value']
        
        credentials = {
            'username': username,
            'password': password,
            'token': token ,
            'backuptoken': backuptoken
        }
        
        login_response = session.post(login_url, data=credentials, timeout=15)
        
        if 'logout' in login_response.text:
            
            scrape_response = session.get(scrape_url, timeout=15)
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
            
            return time_dict
        else:
            logger.error("Creed login failed — hitdown scrape aborted.")
            return None

    async def scrape_hd(self):
        """Async wrapper that runs the synchronous scrape in a thread executor with timeout."""
        try:
            t = await asyncio.wait_for(
                asyncio.get_running_loop().run_in_executor(None, self._sync_scrape_hd),
                timeout=30
            )
        except asyncio.TimeoutError:
            logger.warning("Hitdown scrape timed out.")
            return None
        if t is not None:
            self.client.next_hitdown = t
        return t

    # <# BG Task: Hitdown - Start #>

    @tasks.loop(seconds = 120)
    async def hitdownBGTask(self):
        hd_channel = self.get_hd_channel

        try:
            current_ts = int(datetime.now(timezone.utc).timestamp())
            hd_doc = await self.client.db.extra.find_one({"_id": "hitdown"})
            hitdown_ts = hd_doc.get("timestamp") if hd_doc else None

            if hitdown_ts and isinstance(hitdown_ts, (int, float)) and hitdown_ts > current_ts:
                logger.info("Hitdown: using persistent timestamp from MongoDB (%s).", hitdown_ts)
                target_ts = int(hitdown_ts)
            else:
                logger.info("Hitdown: timestamp in past or missing. Scraping website...")
                t = await self.scrape_hd()
                if not t:
                    logger.warning("Hitdown scrape failed. Retrying in 120s.")
                    await asyncio.sleep(120)
                    return

                delta_sec = (t['h'] * 3600) + (t['m'] * 60) + t['s']
                target_ts = current_ts + delta_sec
                await self.client.db.extra.update_one(
                    {"_id": "hitdown"},
                    {"$set": {"timestamp": target_ts}},
                    upsert=True
                )
                logger.info("Hitdown: scraped and updated MongoDB with new timestamp (%s).", target_ts)

            sec = max(0, target_ts - current_ts - 100)
            logger.info("Hitdown: next alert scheduled in %ss.", sec)
            await asyncio.sleep(sec)
            await hd_channel.send('@everyone, It\'s Hitdown time!')
            await asyncio.sleep(300)
        except Exception as e:
            logger.warning("Hitdown task error, restarting in 120s.", exc_info=e)
            await asyncio.sleep(120)
            self.hitdownBGTask.restart()

    @hitdownBGTask.before_loop
    async def before_hitdownBGTask(self):
        logger.info("Hitdown BG task waiting for bot to be ready.")
        await self.client.wait_until_ready()
        logger.info("Hitdown BG task started.")

    # <# BG Task: Hitdown - End #>

    # <# BG Task: Promo - Start #>

    @tasks.loop(seconds = 10)
    async def promoBGTask(self):
        promo_channel = self.get_promo_channel
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"https://pokemoncreed.net/ajax/pokedex.php?pokemon=promo") as r:
                    if r.status != 200:
                        logger.warning("Promo check failed: HTTP %s", r.status)
                        return
                    data = await r.text()
            result = json.loads(data)
            current_promo = result["name"]
            if self.client.promo == "":
                self.client.promo = current_promo
                logger.info(f"Promo set as {self.client.promo}")
            elif self.client.promo != current_promo:
                self.client.promo = current_promo
                logger.info(f"Promo change detected: {self.client.promo}")
                await promo_channel.send(f"@everyone New Promo: {self.client.promo}")
        except Exception as e:
            logger.exception("Promo BG task error.")

  
    @promoBGTask.before_loop
    async def before_promoBGTask(self):
        logger.info("Promo BG task waiting for bot to be ready.")
        await self.client.wait_until_ready()
        logger.info("Promo BG task started.")


async def setup(client):
    await client.add_cog(Extra(client))
