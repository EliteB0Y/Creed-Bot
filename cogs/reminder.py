import discord
import asyncio
import logging
import re
import secrets
import string
import heapq
from datetime import datetime, timezone, timedelta
from discord.ext import commands

logger = logging.getLogger("CreedBot")

class ConfirmView(discord.ui.View):
    def __init__(self, author_id, emotes=None, timeout=30.0):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.value = None
        if emotes:
            # Dynamically update standard button emojis using configured client emotes
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    if item.label == "Confirm":
                        item.emoji = emotes.get("greentick") or "✅"
                    elif item.label == "Cancel":
                        item.emoji = emotes.get("redtick") or "❌"

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


class ReminderView(discord.ui.View):
    """View containing a link button to jump to the original message where reminder was set."""
    def __init__(self, jump_url: str):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="Jump to Message", url=jump_url, style=discord.ButtonStyle.link))


def parse_duration(time_str: str) -> int:
    """Parses a time string like '1d4h5s' or '5m' and returns duration in seconds.
    
    Raises ValueError if invalid.
    """
    time_str = time_str.strip()
    matches = re.findall(r'(\d+)\s*([dhms])', time_str, re.IGNORECASE)
    if not matches:
        raise ValueError("Invalid duration format. Use format like `1d4h30m5s`, `2h`, `10m`, etc.")
    
    reconstructed = "".join(f"{val}{unit}" for val, unit in matches)
    clean_original = re.sub(r'\s+', '', time_str).lower()
    if clean_original != reconstructed.lower():
        raise ValueError("Invalid characters in duration. Use only `d`, `h`, `m`, `s` for time units.")
        
    total_seconds = 0
    time_units = {
        'd': 86400,
        'h': 3600,
        'm': 60,
        's': 1
    }
    
    for val, unit in matches:
        total_seconds += int(val) * time_units[unit.lower()]
        
    return total_seconds


class Reminder(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.heap = []            # list of (expires_at, reminder_id) for heapq
        self.reminders_map = {}   # dict mapping reminder_id to reminder_doc dict
        self.scheduler_event = asyncio.Event()
        self.scheduler_task = None

    async def cog_load(self):
        self.scheduler_task = asyncio.create_task(self.run_scheduler())
        asyncio.create_task(self.load_reminders())

    def cog_unload(self):
        if self.scheduler_task:
            self.scheduler_task.cancel()
        logger.info("Reminder cog unloaded and scheduler task cancelled.")

    async def load_reminders(self):
        """Loads reminders from DB, synchronizes DB configs, and prepares heap."""
        await self.client.wait_until_ready()

        # Load existing reminders from MongoDB
        try:
            reminders = await asyncio.to_thread(lambda: list(self.client.db.reminders.find()))
        except Exception as e:
            logger.error("Failed to load reminders from DB", exc_info=e)
            return

        now = datetime.now(timezone.utc)
        for doc in reminders:
            rem_id = doc["_id"]
            expires_at = doc["expires_at"]
            
            # Make expires_at offset-aware in UTC
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            else:
                expires_at = expires_at.astimezone(timezone.utc)
            
            doc["expires_at"] = expires_at
            self.reminders_map[rem_id] = doc
            
            if expires_at <= now:
                # Reminder already expired while bot was offline
                asyncio.create_task(self.trigger_reminder(doc, missed=True))
            else:
                # Add to memory heap
                heapq.heappush(self.heap, (expires_at, rem_id))
                
        # Alert the scheduler to evaluate new sleep duration
        self.scheduler_event.set()
        logger.info(f"Loaded {len(reminders)} active reminders from MongoDB.")

    async def run_scheduler(self):
        """Single background loop executing reminders in priority queue order."""
        while True:
            try:
                self.scheduler_event.clear()
                
                if not self.heap:
                    # No reminders scheduled, wait until awakened by scheduler_event
                    await self.scheduler_event.wait()
                    continue
                    
                expires_at, rem_id = self.heap[0]
                
                # Verify if reminder was cancelled/deleted (lazy deletion)
                doc = self.reminders_map.get(rem_id)
                if not doc or doc.get("cancelled"):
                    heapq.heappop(self.heap)
                    self.reminders_map.pop(rem_id, None)
                    continue
                    
                now = datetime.now(timezone.utc)
                delay = (expires_at - now).total_seconds()
                
                if delay <= 0:
                    # It's time! Pop and execute
                    heapq.heappop(self.heap)
                    self.reminders_map.pop(rem_id, None)
                    asyncio.create_task(self.trigger_reminder(doc))
                    continue
                    
                try:
                    # Sleep until expiration or until scheduler_event wakes us up early
                    await asyncio.wait_for(self.scheduler_event.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    # Natural wakeup, next loop run will execute the reminder
                    pass
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in reminder scheduler loop", exc_info=e)
                await asyncio.sleep(1) # Prevent tight loop on constant errors

    async def trigger_reminder(self, doc, missed=False):
        """Notifies the user and cleans up the database record."""
        rem_id = doc["_id"]
        user_id = doc["user_id"]
        channel_id = doc.get("channel_id")
        message_id = doc.get("message_id")
        guild_id = doc.get("guild_id")
        content = doc.get("content", "Reminder!")
        
        # Delete from MongoDB
        try:
            await asyncio.to_thread(self.client.db.reminders.delete_one, {"_id": rem_id})
        except Exception as e:
            logger.error(f"Failed to delete triggered reminder {rem_id} from DB", exc_info=e)

        # Get user object
        user = self.client.get_user(user_id) or await self.client.fetch_user(user_id)
        if not user:
            logger.warning(f"Could not find user {user_id} for reminder {rem_id}")
            return

        # Get channel object
        channel = None
        if channel_id:
            channel = self.client.get_channel(channel_id)
            if not channel:
                try:
                    channel = await self.client.fetch_channel(channel_id)
                except Exception:
                    pass

        # Build view with Jump to Message button
        view = None
        if message_id:
            guild_str = str(guild_id) if guild_id else "@me"
            jump_url = f"https://discord.com/channels/{guild_str}/{channel_id}/{message_id}"
            view = ReminderView(jump_url)

        # Build plain text reminder message
        bell_emoji = self.client.emotes.get('timer',  "⏰")
        missed_text = " *(Note: This reminder was delayed because the bot was offline)*" if missed else ""
        message_text = f"{bell_emoji} {user.mention}: {content}\n{missed_text}"

        sent = False
        if channel:
            try:
                await channel.send(content=message_text, view=view)
                sent = True
            except Exception as e:
                logger.warning(f"Failed to send reminder in channel {channel_id}: {e}. Falling back to DM.")

        if not sent:
             try:
                 await user.send(content=message_text, view=view)
             except Exception as e:
                 logger.error(f"Failed to DM user {user_id} for reminder {rem_id}: {e}")

    @commands.group(name="reminder", aliases=["remind"], invoke_without_command=True)
    async def reminder_group(self, ctx):
        """Reminder command group. Lists all reminder subcommands."""
        prefix = ctx.prefix
        timer_emoji = self.client.emotes.get('timer', "⏰")
        embed = discord.Embed(
            title=f"Reminder Commands",
            description=f"{timer_emoji} Manage your reminders using the commands below:\n\n"
                        f"• `{prefix}remind set <duration> <message>` - Set a reminder (e.g., `{prefix}remind set 1d4h5s walk the dog`)\n"
                        f"• `{prefix}remind list` - Show your active reminders\n"
                        f"• `{prefix}remind delete <id>` - Delete a specific reminder\n"
                        f"• `{prefix}remind clear` - Clear all your active reminders\n\n"
                        f"*Limit of 5 active reminders per user. Supported time units: `d` (days), `h` (hours), `m` (minutes), `s` (seconds).* ",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)

    @reminder_group.command(name="set")
    async def remind_set(self, ctx, duration_str: str, *, content: str):
        """Sets a reminder for a given duration."""
        redtick_emoji = self.client.emotes.get('redtick', "❌")
        try:
            duration = parse_duration(duration_str)
        except ValueError as e:
            await ctx.send(embed=discord.Embed(description=f"{redtick_emoji} {e}", color=discord.Color.red()))
            return

        if duration < 1:
            await ctx.send(embed=discord.Embed(description=f"{redtick_emoji} Duration must be at least 1 second.", color=discord.Color.red()))
            return

        if duration > 30 * 86400:
            await ctx.send(embed=discord.Embed(description=f"{redtick_emoji} Reminders cannot be set for longer than 30 days (720h).", color=discord.Color.red()))
            return

        # Check maximum limit of 5 reminders
        try:
            count = await asyncio.to_thread(
                self.client.db.reminders.count_documents, {"user_id": ctx.author.id}
            )
        except Exception as e:
            logger.error("DB error counting reminders", exc_info=e)
            await ctx.send(embed=discord.Embed(description=f"{redtick_emoji} Database error. Please try again later.", color=discord.Color.red()))
            return

        if count >= 5:
            await ctx.send(embed=discord.Embed(description=f"{redtick_emoji} You can only have up to 5 active reminders at a time.", color=discord.Color.red()))
            return

        # Generate unique 6-character ID
        while True:
            rem_id = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(6))
            try:
                exists = await asyncio.to_thread(self.client.db.reminders.find_one, {"_id": rem_id})
                if not exists:
                     break
            except Exception as e:
                logger.error("DB error checking unique id", exc_info=e)
                await ctx.send(embed=discord.Embed(description=f"{redtick_emoji} Database error. Please try again later.", color=discord.Color.red()))
                return

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=duration)

        doc = {
            "_id": rem_id,
            "user_id": ctx.author.id,
            "channel_id": ctx.channel.id,
            "message_id": ctx.message.id,
            "guild_id": ctx.guild.id if ctx.guild else None,
            "created_at": now,
            "expires_at": expires_at,
            "content": content
        }

        try:
            await asyncio.to_thread(self.client.db.reminders.insert_one, doc)
        except Exception as e:
            logger.error("DB error inserting reminder", exc_info=e)
            await ctx.send(embed=discord.Embed(description=f"{redtick_emoji} Database error saving reminder.", color=discord.Color.red()))
            return

        # Update in-memory tracker
        self.reminders_map[rem_id] = doc
        
        # Insert to heap and wake scheduler if it's the new earliest
        current_earliest = self.heap[0][0] if self.heap else None
        heapq.heappush(self.heap, (expires_at, rem_id))
        
        if current_earliest is None or expires_at < current_earliest:
            self.scheduler_event.set()

        greentick_emoji = self.client.emotes.get('greentick') or "✅"
        message_text = (
            f"{greentick_emoji} **Reminder Set!**\n"
            f"I will remind you about: **{content}**\n"
            f"Expires: <t:{int(expires_at.timestamp())}:f> (<t:{int(expires_at.timestamp())}:R>)\n"
            f"ID: `{rem_id}`"
        )
        await ctx.send(content=message_text)

    @reminder_group.command(name="list")
    async def remind_list(self, ctx):
        """Lists active reminders for the user."""
        redtick_emoji = self.client.emotes.get('redtick') or "❌"
        try:
            user_reminders = await asyncio.to_thread(
                lambda: list(self.client.db.reminders.find({"user_id": ctx.author.id}).sort("expires_at", 1))
            )
        except Exception as e:
            logger.error("DB error listing reminders", exc_info=e)
            await ctx.send(embed=discord.Embed(description=f"{redtick_emoji} Database error. Please try again later.", color=discord.Color.red()))
            return

        if not user_reminders:
            info_emoji = self.client.emotes.get('info') or "ℹ️"
            await ctx.send(embed=discord.Embed(description=f"{info_emoji} You have no active reminders.", color=discord.Color.blue()))
            return

        timer_emoji = self.client.emotes.get('timer', "⏰")
        embed = discord.Embed(
            title="Your Active Reminders",
            description=f"{timer_emoji} Here are your active reminders:",
            color=discord.Color.blue()
        )

        for idx, doc in enumerate(user_reminders, 1):
            expires_at = doc["expires_at"]
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            else:
                expires_at = expires_at.astimezone(timezone.utc)
            
            timestamp = int(expires_at.timestamp())
            embed.add_field(
                name=f"{idx}. ID: `{doc['_id']}`",
                value=f"**Message**: {doc['content']}\n"
                      f"**Due**: <t:{timestamp}:f> (<t:{timestamp}:R>)",
                inline=False
            )

        embed.set_footer(text=f"Total: {len(user_reminders)}/5 reminders")
        await ctx.send(embed=embed)

    @reminder_group.command(name="delete")
    async def remind_delete(self, ctx, reminder_id: str):
        """Deletes a specific reminder by its ID."""
        reminder_id = reminder_id.strip().lower()
        redtick_emoji = self.client.emotes.get('redtick') or "❌"

        try:
            doc = await asyncio.to_thread(self.client.db.reminders.find_one, {"_id": reminder_id})
        except Exception as e:
            logger.error("DB error finding reminder for deletion", exc_info=e)
            await ctx.send(embed=discord.Embed(description=f"{redtick_emoji} Database error. Please try again later.", color=discord.Color.red()))
            return

        if not doc:
            await ctx.send(embed=discord.Embed(description=f"{redtick_emoji} No reminder found with that ID.", color=discord.Color.red()))
            return

        if doc["user_id"] != ctx.author.id:
            await ctx.send(embed=discord.Embed(description=f"{redtick_emoji} That reminder does not belong to you.", color=discord.Color.red()))
            return

        # Lazy delete in memory
        if reminder_id in self.reminders_map:
            self.reminders_map[reminder_id]["cancelled"] = True
        
        # Delete from DB
        try:
            await asyncio.to_thread(self.client.db.reminders.delete_one, {"_id": reminder_id})
        except Exception as e:
            logger.error("DB error deleting reminder", exc_info=e)
            await ctx.send(embed=discord.Embed(description=f"{redtick_emoji} Database error. Could not delete from DB.", color=discord.Color.red()))
            return

        greentick_emoji = self.client.emotes.get('greentick') or "✅"
        await ctx.send(embed=discord.Embed(
            description=f"{greentick_emoji} Deleted reminder `{reminder_id}`: *{doc['content']}*",
            color=discord.Color.green()
        ))

    @reminder_group.command(name="clear")
    async def remind_clear(self, ctx):
        """Clears all active reminders for the user."""
        redtick_emoji = self.client.emotes.get('redtick') or "❌"
        try:
            user_reminders = await asyncio.to_thread(
                lambda: list(self.client.db.reminders.find({"user_id": ctx.author.id}))
            )
        except Exception as e:
            logger.error("DB error clearing reminders", exc_info=e)
            await ctx.send(embed=discord.Embed(description=f"{redtick_emoji} Database error. Please try again later.", color=discord.Color.red()))
            return

        if not user_reminders:
            info_emoji = self.client.emotes.get('info') or "ℹ️"
            await ctx.send(embed=discord.Embed(description=f"{info_emoji} You have no active reminders to clear.", color=discord.Color.blue()))
            return

        view = ConfirmView(ctx.author.id, emotes=self.client.emotes, timeout=20.0)
        alert_emoji = self.client.emotes.get('alert') or "⚠️"
        embed = discord.Embed(
            description=f"{alert_emoji} Are you sure you want to clear all **{len(user_reminders)}** active reminders?",
            color=discord.Color.orange()
        )
        msg = await ctx.send(embed=embed, view=view)
        await view.wait()

        if view.value is True:
            # Lazy delete in memory
            for doc in user_reminders:
                rem_id = doc["_id"]
                if rem_id in self.reminders_map:
                    self.reminders_map[rem_id]["cancelled"] = True

            # Delete from DB
            try:
                await asyncio.to_thread(self.client.db.reminders.delete_many, {"user_id": ctx.author.id})
            except Exception as e:
                logger.error("DB error bulk deleting reminders", exc_info=e)
                await msg.edit(embed=discord.Embed(description=f"{redtick_emoji} Database error clearing reminders.", color=discord.Color.red()), view=None)
                return

            greentick_emoji = self.client.emotes.get('greentick') or "✅"
            await msg.edit(embed=discord.Embed(
                description=f"{greentick_emoji} Successfully cleared all your reminders.",
                color=discord.Color.green()
            ), view=None)
        else:
            await msg.edit(embed=discord.Embed(
                description=f"{redtick_emoji} Cancelled clearing reminders.",
                color=discord.Color.red()
            ), view=None)


async def setup(client):
    await client.add_cog(Reminder(client))
