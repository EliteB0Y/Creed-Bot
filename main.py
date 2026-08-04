import os, discord, asyncio, signal
import logging
from logging.handlers import TimedRotatingFileHandler
import sys
from discord.ext import commands
from datetime import datetime, timezone, timedelta
import motor.motor_asyncio

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
    
    # Custom converter to output IST times
    def ist_converter(timestamp):
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        ist_dt = dt.astimezone(timezone(timedelta(hours=5, minutes=30)))
        return ist_dt.timetuple()
        
    formatter.converter = ist_converter
    
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

    def __init__(self, command_prefix, intents):
        super().__init__(command_prefix=command_prefix, intents=intents, help_command=None, case_insensitive=True)
        self._cache_block = None
        self._cache_emoji = None
        # Runtime state
        self.promo = ""
        self.active_games = {}  # {channel_id: {"name": str, "type": str, "host_id": int}}
        self.inviteurl = ""
        self.rate_cache = {}
        self.start_time = datetime.now(timezone.utc)
        # Config defaults — overridden at startup from the bot_config MongoDB collection.
        # Any key present in the DB document is set dynamically via setattr in load_bot_config().
        self.disabledCogs = []              # cogs to skip loading, e.g. ["cogs.extra"]
        self.enabledCogs = [                # cogs to load; override this list from MongoDB
            'cogs.pokemoncreed', 'cogs.basic', 'cogs.games',
            'cogs.extra', 'cogs.error', 'cogs.owner', 'cogs.help', 'jishaku',
            'cogs.reminder'
        ]
        self.boxrateconfig = {"base": 1, "unbase": 0.8, "other": 3}
        self.collection_allowed_guilds = [] # guild IDs allowed to use !collection
        
    @property
    def emotes(self):
        """Returns the in-memory emoji cache (populated at startup via load_cache)."""
        return self._cache_emoji or {}
        
    @property
    def blocklist(self):
        """Returns the in-memory blocklist cache (populated at startup via load_cache)."""
        return self._cache_block or []

    async def load_cache(self):
        """Populate emoji and blocklist caches from MongoDB (motor async iterators)."""
        self._cache_emoji = {r['name']: r['emoji'] async for r in self.db.emojis.find()}
        self._cache_block = [r['userid'] async for r in self.db.blocklist.find()]
        logger.info("Cache loaded: %d emote(s), %d blocked user(s).", len(self._cache_emoji), len(self._cache_block))

    async def update_cache(self):
        """Refresh the in-memory emoji and blocklist caches from MongoDB."""
        self._cache_emoji = {r['name']: r['emoji'] async for r in self.db.emojis.find()}
        self._cache_block  = [r['userid'] async for r in self.db.blocklist.find()]
        return "`Updated the cache`"

    async def close(self):
        """Graceful shutdown: backup rate_cache to MongoDB before closing."""
        try:
            if hasattr(self, 'db') and self.rate_cache:
                await self.db.backups.update_one(
                    {"_id": "rate_cache"},
                    {"$set": {"data": self.rate_cache}},
                    upsert=True
                )
                logger.info(f"Backed up rate_cache ({len(self.rate_cache)} entries) to MongoDB.")
            else:
                logger.info("No rate_cache data to back up.")
        except Exception as e:
            logger.error("Failed to backup rate_cache!", exc_info=e)
        await super().close()

    @property
    def get_time(self):
        ist_tz = timezone(timedelta(hours=5, minutes=30))
        return datetime.now(ist_tz).strftime("%d %b, %Y | %I:%M:%S %p")
        
async def get_prefix(client, message):
    if not message.guild:
        return commands.when_mentioned_or(*("",))(client, message)
    prefixes = client.db.get_collection("prefixes_cb")
    p = await prefixes.find_one({"serverid": message.guild.id})
    if p:
        pf = p["prefix"]
        return commands.when_mentioned_or(*(pf,))(client, message)
    else:
        await prefixes.insert_one({"serverid": message.guild.id, "prefix": "!"})
        return commands.when_mentioned_or(*("!",))(client, message)
        
# Creating the Bot using MyBot class
client = MyBot(command_prefix = get_prefix, intents = discord.Intents.all())

#Connect to the database
async def create_db_connection():
    try:
        mclient = motor.motor_asyncio.AsyncIOMotorClient(os.environ.get('MONGODB'))
        client.db = mclient.get_database("my_db")
        logger.info("Database connection successful!")
    except Exception as e:
        logger.error("Database connection failed!", exc_info=e)

async def load_bot_config():
    """Load ALL keys from the single bot_config MongoDB document as client attributes.

    Every key in the document (except _id) is set as client.<key>, making it
    accessible across all cogs as self.client.<key>. Defaults defined in
    MyBot.__init__ are used as fallbacks if the document is missing or a key
    is absent.
    """
    try:
        config = await client.db.bot_config.find_one()
        if config:
            for key, value in config.items():
                if key == "_id":
                    continue
                setattr(client, key, value)
            logger.info("Bot config loaded from MongoDB: %s", [k for k in config if k != "_id"])
        else:
            logger.warning("No bot_config document found in MongoDB — using hardcoded defaults.")
    except Exception as e:
        logger.error("Failed to load bot config from MongoDB!", exc_info=e)


@client.tree.command(name="ping", description="shows the bot latency.")
async def _ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"{client.emotes.get('typing','')} `Pong! {round(client.latency * 1000, 2)}ms.`")

@client.event
async def on_ready():
    await client.change_presence(status = discord.Status.idle, activity = discord.Game('Pokemon Creed!'))
    #await client.change_presence(status = discord.Status.dnd, activity = discord.Game('with EliteBOY'))
    logger.info('The Bot is online. Guilds: %s | Users: %s', len(client.guilds), len(client.users))

@client.event
async def on_command(ctx):
    logger.info(
        "CMD: %s | Cog: %s | User: %s (%s) | Guild: %s (%s) | Channel: %s | Input: %s",
        ctx.command.qualified_name,
        ctx.command.cog_name or "None",
        ctx.author,
        ctx.author.id,
        ctx.guild.name if ctx.guild else "DM",
        ctx.guild.id if ctx.guild else "N/A",
        ctx.channel.id,
        ctx.message.content,
    )

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
        embed.set_author(name=f'Hello {message.author.display_name}', icon_url=message.author.display_avatar.url)
        await channel.send(embed = embed)

    await client.process_commands(message)


# Jishaku configuration 
os.environ["JISHAKU_NO_UNDERSCORE"]="True"
os.environ["JISHAKU_HIDE"]="True"


async def main():
    await create_db_connection()
    await load_bot_config()
    await client.load_cache()

    # Restore rate_cache from MongoDB backup
    backup = await client.db.backups.find_one({"_id": "rate_cache"})
    if backup and "data" in backup:
        client.rate_cache = backup["data"]
        logger.info(f"Restored rate_cache ({len(client.rate_cache)} entries) from MongoDB backup.")
    else:
        logger.info("No rate_cache backup found — starting with empty cache.")

    async with client:
        # Register signal handlers for graceful shutdown
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.ensure_future(client.close()))

        for extension in client.enabledCogs:
            if extension not in client.disabledCogs:
                try:
                    await client.load_extension(extension)
                    logger.info(f'Successfully loaded [{extension}] extension.')
                except Exception as e:
                    logger.error(f'Failed to load [{extension}] extension!', exc_info=e)
        await client.start(os.environ.get('TOKEN'))

asyncio.run(main())

# <# Run the Bot - End #>
