import os, discord, asyncio
import logging
from logging.handlers import TimedRotatingFileHandler
import sys
from discord.ext import commands
from datetime import datetime
from pymongo import MongoClient

# Configure logging
def setup_logging():
    # Ensure logs directory exists
    os.makedirs('logs', exist_ok=True)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Formatter
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)-8s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console Handler (Stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File Handler (logs/bot.log, rotating weekly on Mondays)
    file_handler = TimedRotatingFileHandler(
        filename='logs/bot.log',
        when='W0',  # Rotate weekly on Monday (0 = Monday)
        interval=1,
        encoding='utf-8',
        backupCount=10  # Keep 10 weeks of logs
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # Adjust discord.py logging levels to minimize verbosity
    logging.getLogger('discord').setLevel(logging.INFO)
    logging.getLogger('discord.http').setLevel(logging.WARNING)

setup_logging()
logger = logging.getLogger('CreedBot')

class MyBot(commands.Bot):
    #Declare Bot variables here (can be accessed in cogs using self.client.variable)
    promo = ""
    wtpList = []
    activeQuiz = []
    disabledCogs = [] #add cogs.namehere to disable
    inviteurl = ""
    boxrateconfig = {"base": 1, "unbase": 0.8, "other": 3}
    rate_cache = {}

    def __init__(self, command_prefix, intents):
        super().__init__(command_prefix=command_prefix, intents=intents)
        self._cache_block = None
        self._cache_emoji = None
        
    @property
    def emotes(self):
        if self._cache_emoji is None:
            records = self.db.emojis.find()
            self._cache_emoji = {r['name'] : r['emoji'] for r in records}
        return self._cache_emoji
        
    @property
    def blocklist(self):
        if self._cache_block is None:
            records = self.db.blocklist.find()
            self._cache_block = [r['userid'] for r in records]
        return self._cache_block
        
    @property
    def update_cache(self):
        self._cache_emoji = {r['name'] : r['emoji'] for r in self.db.emojis.find()}
        self._cache_block = [r['userid'] for r in self.db.blocklist.find()]
        return "`Updated the cache`"

    @property
    def get_time(self):
        return datetime.now().strftime("%d %b, %Y | %I:%M:%S %p")
        
async def get_prefix(client, message):
    if not message.guild:
        return commands.when_mentioned_or(*("",))(client, message)
    prefixes = client.db.get_collection("prefixes_cb")
    p = prefixes.find_one({"serverid": message.guild.id})
    if p:
        pf = p["prefix"]
        return commands.when_mentioned_or(*(pf,))(client, message)
    else:
        prefixes.insert_one({"serverid": message.guild.id, "prefix" : "!"})
        return commands.when_mentioned_or(*("!",))(client, message)
        
# Creating the Bot using MyBot class
client = MyBot(command_prefix = get_prefix, intents = discord.Intents.all())

#Connect to the database
async def create_db_connection():
    try:
        mclient = MongoClient(os.environ.get('MONGODB'))
        client.db = mclient.get_database("my_db")
        logger.info("Database connection successful!")
    except Exception as e:
        logger.error("Database connection failed!", exc_info=e)


@client.tree.command(name="ping", description="shows the bot latency.")
async def _ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"{client.emotes.get('typing','')} `Pong! {round(client.latency * 1000, 2)}ms.`")

@client.event
async def on_ready():
    await client.change_presence(status = discord.Status.idle, activity = discord.Game('Pokemon Creed!'))
    #await client.change_presence(status = discord.Status.dnd, activity = discord.Game('with EliteBOY'))
    logger.info('The Bot is online.')

@client.event
async def on_message(message):
    channel = message.channel
        
    if isinstance(message.channel, discord.DMChannel):
        if message.author.id != client.owner_id:
            return

    if message.author.bot or message.author.id in client.blocklist:
        return 

    if client.user in message.mentions and message.type == discord.MessageType.default and len(message.content.split())==1:
        prefix = await client.get_prefix(message)
        desc = f"My prefix in this server is {client.emotes.get('arrowright','')} **{prefix[-1]}** {client.emotes.get('arrowleft','')}"
        embed = discord.Embed(description = desc)
        embed.set_author(name=f'Hello {message.author.display_name}', icon_url=message.author.avatar)
        await channel.send(embed = embed)

    await client.process_commands(message)


# Jishaku configuration 
os.environ["JISHAKU_NO_UNDERSCORE"]="True"
os.environ["JISHAKU_HIDE"]="True"


async def main():
    await create_db_connection()
    extensions = ['cogs.pokemoncreed', 'cogs.basic', 'cogs.games', 'cogs.extra', 'cogs.error', 'jishaku']
    async with client:
        for extension in extensions:
            if extension not in client.disabledCogs:
                await client.load_extension(extension)
                logger.info(f'Successfullly loaded [{extension}] extension!')
        await client.start(os.environ.get('TOKEN'))

asyncio.run(main())

# <# Run the Bot - End #>