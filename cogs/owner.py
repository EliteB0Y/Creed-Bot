import discord
import json
import logging
import re
import aiohttp
from discord.ext import commands
from bson import ObjectId

logger = logging.getLogger("CreedBot")


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _serialize(value):
    """Recursively convert MongoDB types (ObjectId, etc.) to JSON-safe values."""
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize(i) for i in value]
    if isinstance(value, ObjectId):
        return str(value)
    return value


def _paginate(docs, page_size=5):
    """Split docs into pages of page_size. Always returns at least one page."""
    if not docs:
        return [[]]
    return [docs[i : i + page_size] for i in range(0, len(docs), page_size)]


async def _make_hub_embed(db):
    """Build the hub embed listing all collections with their document counts."""
    collections = sorted(await db.list_collection_names())
    embed = discord.Embed(title="🗄️ MongoDB Manager", color=0x00C9A7)
    if not collections:
        embed.description = "*No collections found in this database.*"
    else:
        lines = []
        for col in collections:
            count = await db[col].count_documents({})
            lines.append(f"**`{col}`** — {count:,} doc(s)")
        embed.description = "\n".join(lines)
    embed.set_footer(text=f"{len(collections)} collection(s)  •  Select one below to manage it")
    return embed, collections


async def _make_panel_embed(collection, db):
    """Build the collection panel embed."""
    count = await db[collection].count_documents({})
    embed = discord.Embed(
        title=f"📁 {collection}",
        description=f"**{count:,}** document(s)\n\nChoose an operation:",
        color=0x5865F2,
    )
    return embed


def _make_find_embed(collection, pages, page_idx, filter_str):
    """Build a paginated find-result embed."""
    total = sum(len(p) for p in pages)
    page_docs = pages[page_idx]
    if page_docs:
        raw = json.dumps([_serialize(d) for d in page_docs], indent=2, default=str)
        if len(raw) > 1800:
            raw = raw[:1800] + "\n… (truncated)"
        desc = f"```json\n{raw}\n```"
    else:
        desc = "`No documents found.`"
    embed = discord.Embed(
        title=f"🔍 Find — `{collection}`",
        description=desc,
        color=0x5865F2,
    )
    embed.set_footer(
        text=f"{total} result(s)  •  Page {page_idx + 1}/{len(pages)}  •  Filter: {filter_str}"
    )
    return embed


def _error_embed(detail):
    """Build a red error embed for invalid JSON or other failures."""
    return discord.Embed(
        title="❌ Invalid JSON",
        description=f"```{detail}```",
        color=discord.Color.red(),
    )


EMOJI_REGEX = re.compile(r"<(?P<animated>a)?:(?P<name>[a-zA-Z0-9_]+):(?P<id>\d+)>")
URL_REGEX = re.compile(r"https?://\S+")


async def _extract_image_url(ctx, emoji_arg: str = None) -> str:
    """Resolve an image URL from direct argument, attachments, or referenced message."""
    # 1. Direct argument
    if emoji_arg:
        match = EMOJI_REGEX.search(emoji_arg)
        if match:
            ext = "gif" if match.group("animated") else "png"
            return f"https://cdn.discordapp.com/emojis/{match.group('id')}.{ext}"
        if emoji_arg.startswith(("http://", "https://")):
            return emoji_arg

    # 2. Attachments on the command message
    if ctx.message.attachments:
        return ctx.message.attachments[0].url

    # 3. Referenced message (reply)
    ref_msg = None
    if ctx.message.reference:
        if ctx.message.reference.resolved and isinstance(ctx.message.reference.resolved, discord.Message):
            ref_msg = ctx.message.reference.resolved
        elif ctx.message.reference.message_id:
            try:
                ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            except (discord.NotFound, discord.HTTPException):
                pass

    if ref_msg:
        if ref_msg.attachments:
            return ref_msg.attachments[0].url
        match = EMOJI_REGEX.search(ref_msg.content)
        if match:
            ext = "gif" if match.group("animated") else "png"
            return f"https://cdn.discordapp.com/emojis/{match.group('id')}.{ext}"
        url_match = URL_REGEX.search(ref_msg.content)
        if url_match:
            return url_match.group(0)
        if ref_msg.stickers and hasattr(ref_msg.stickers[0], "url") and ref_msg.stickers[0].url:
            return ref_msg.stickers[0].url

    return None


async def _fetch_image_bytes(url: str) -> bytes:
    """Download raw image bytes from a URL."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.read()
            raise ValueError(f"HTTP {resp.status} while fetching image.")


# ─────────────────────────────────────────────────────────────────────────────
#  Modals
# ─────────────────────────────────────────────────────────────────────────────

class FindModal(discord.ui.Modal, title="Find Documents"):
    filter_json = discord.ui.TextInput(
        label="Filter (JSON)",
        placeholder='e.g.  {"serverid": 123456789}',
        default="{}",
        required=False,
        style=discord.TextStyle.paragraph,
        max_length=1000,
    )

    def __init__(self, collection, db, message, panel_view):
        super().__init__()
        self.collection = collection
        self.db = db
        self.message = message
        self.panel_view = panel_view

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        raw = self.filter_json.value.strip() or "{}"
        try:
            query = json.loads(raw)
        except json.JSONDecodeError as e:
            await self.message.edit(embed=_error_embed(str(e)), view=self.panel_view)
            return

        docs = [d async for d in self.db[self.collection].find(query).limit(50)]
        pages = _paginate(docs)
        embed = _make_find_embed(self.collection, pages, 0, raw)
        result_view = FindResultView(
            self.collection, self.db, pages, raw, self.panel_view, interaction.user.id
        )
        result_view.message = self.message
        await self.message.edit(embed=embed, view=result_view)


class InsertModal(discord.ui.Modal, title="Insert Document"):
    document_json = discord.ui.TextInput(
        label="Document (JSON)",
        placeholder='e.g.  {"name": "test", "value": 42}',
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=2000,
    )

    def __init__(self, collection, db, message, panel_view):
        super().__init__()
        self.collection = collection
        self.db = db
        self.message = message
        self.panel_view = panel_view

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            document = json.loads(self.document_json.value)
        except json.JSONDecodeError as e:
            await self.message.edit(embed=_error_embed(str(e)), view=self.panel_view)
            return

        result = await self.db[self.collection].insert_one(document)
        embed = discord.Embed(
            title=f"✅ Inserted — `{self.collection}`",
            description=f"Document inserted with ID:\n`{result.inserted_id}`",
            color=discord.Color.green(),
        )
        await self.message.edit(embed=embed, view=self.panel_view)


class UpdateModal(discord.ui.Modal, title="Update Documents"):
    filter_json = discord.ui.TextInput(
        label="Filter (JSON)",
        placeholder='e.g.  {"_id": "main"}',
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=1000,
    )
    update_json = discord.ui.TextInput(
        label='Update (JSON — use "$set", "$unset", etc.)',
        placeholder='e.g.  {"$set": {"key": "new_value"}}',
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=1000,
    )

    def __init__(self, collection, db, message, panel_view):
        super().__init__()
        self.collection = collection
        self.db = db
        self.message = message
        self.panel_view = panel_view

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            query = json.loads(self.filter_json.value)
            update = json.loads(self.update_json.value)
        except json.JSONDecodeError as e:
            await self.message.edit(embed=_error_embed(str(e)), view=self.panel_view)
            return

        # Auto-wrap in $set if no update operators are present
        if not any(k.startswith("$") for k in update):
            update = {"$set": update}

        result = await self.db[self.collection].update_many(query, update)
        embed = discord.Embed(
            title=f"✅ Updated — `{self.collection}`",
            description=f"**Matched:** `{result.matched_count}`\n**Modified:** `{result.modified_count}`",
            color=discord.Color.green(),
        )
        await self.message.edit(embed=embed, view=self.panel_view)


class DeleteModal(discord.ui.Modal, title="Delete Documents"):
    filter_json = discord.ui.TextInput(
        label="Filter (JSON)",
        placeholder='e.g.  {"_id": "main"}',
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=1000,
    )

    def __init__(self, collection, db, message, panel_view):
        super().__init__()
        self.collection = collection
        self.db = db
        self.message = message
        self.panel_view = panel_view

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            query = json.loads(self.filter_json.value)
        except json.JSONDecodeError as e:
            await self.message.edit(embed=_error_embed(str(e)), view=self.panel_view)
            return

        count = await self.db[self.collection].count_documents(query)
        if count == 0:
            embed = discord.Embed(
                title="❌ No Match",
                description="No documents match that filter.",
                color=discord.Color.red(),
            )
            await self.message.edit(embed=embed, view=self.panel_view)
            return

        # Show inline confirm before deleting
        embed = discord.Embed(
            title="⚠️ Confirm Delete",
            description=(
                f"This will delete **{count}** document(s) from `{self.collection}`.\n"
                "This **cannot** be undone. Proceed?"
            ),
            color=0xFFA500,
        )
        confirm_view = DeleteConfirmView(
            self.collection, self.db, query, self.panel_view, interaction.user.id
        )
        confirm_view.message = self.message
        await self.message.edit(embed=embed, view=confirm_view)


class CountModal(discord.ui.Modal, title="Count Documents"):
    filter_json = discord.ui.TextInput(
        label="Filter (JSON, optional — blank = count all)",
        placeholder="Leave blank to count all documents",
        default="{}",
        required=False,
        style=discord.TextStyle.paragraph,
        max_length=1000,
    )

    def __init__(self, collection, db, message, panel_view):
        super().__init__()
        self.collection = collection
        self.db = db
        self.message = message
        self.panel_view = panel_view

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        raw = self.filter_json.value.strip() or "{}"
        try:
            query = json.loads(raw)
        except json.JSONDecodeError as e:
            await self.message.edit(embed=_error_embed(str(e)), view=self.panel_view)
            return

        count = await self.db[self.collection].count_documents(query)
        embed = discord.Embed(
            title=f"🔢 Count — `{self.collection}`",
            description=f"**{count:,}** document(s) match.\nFilter: `{raw}`",
            color=0x5865F2,
        )
        await self.message.edit(embed=embed, view=self.panel_view)


# ─────────────────────────────────────────────────────────────────────────────
#  Find Result Paginator View
# ─────────────────────────────────────────────────────────────────────────────

class FindResultView(discord.ui.View):
    def __init__(self, collection, db, pages, filter_str, panel_view, author_id):
        super().__init__(timeout=120)
        self.collection = collection
        self.db = db
        self.pages = pages
        self.filter_str = filter_str
        self.panel_view = panel_view
        self.author_id = author_id
        self.page = 0
        self.message = None
        self._refresh_buttons()

    def _refresh_buttons(self):
        self.prev_btn.disabled = (self.page == 0)
        self.next_btn.disabled = (self.page >= len(self.pages) - 1)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary, row=0)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        self._refresh_buttons()
        await interaction.response.edit_message(
            embed=_make_find_embed(self.collection, self.pages, self.page, self.filter_str),
            view=self,
        )

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, row=0)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        self._refresh_buttons()
        await interaction.response.edit_message(
            embed=_make_find_embed(self.collection, self.pages, self.page, self.filter_str),
            view=self,
        )

    @discord.ui.button(label="← Back to Panel", style=discord.ButtonStyle.primary, row=1)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=await _make_panel_embed(self.collection, self.db),
            view=self.panel_view,
        )

    async def on_timeout(self):
        if self.message:
            try:
                for item in self.children:
                    item.disabled = True
                await self.message.edit(view=self)
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
#  Delete & Drop Inline Confirm Views
# ─────────────────────────────────────────────────────────────────────────────

class DeleteConfirmView(discord.ui.View):
    def __init__(self, collection, db, query, panel_view, author_id):
        super().__init__(timeout=30)
        self.collection = collection
        self.db = db
        self.query = query
        self.panel_view = panel_view
        self.author_id = author_id
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Yes, Delete", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        result = await self.db[self.collection].delete_many(self.query)
        embed = discord.Embed(
            title=f"✅ Deleted — `{self.collection}`",
            description=f"Deleted **{result.deleted_count}** document(s).",
            color=discord.Color.green(),
        )
        await interaction.response.edit_message(embed=embed, view=self.panel_view)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=await _make_panel_embed(self.collection, self.db),
            view=self.panel_view,
        )

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(
                    embed=await _make_panel_embed(self.collection, self.db),
                    view=self.panel_view,
                )
            except Exception:
                pass


class DropConfirmView(discord.ui.View):
    def __init__(self, collection, db, panel_view, author_id):
        super().__init__(timeout=30)
        self.collection = collection
        self.db = db
        self.panel_view = panel_view
        self.author_id = author_id
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Drop Collection", style=discord.ButtonStyle.danger, emoji="💣")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.db.drop_collection(self.collection)
        # Return to a refreshed hub after dropping
        hub_embed, _ = await _make_hub_embed(self.db)
        hub_view = MongoHubView(self.db, self.author_id)
        await hub_view.populate()
        hub_view.message = self.message
        await interaction.response.edit_message(embed=hub_embed, view=hub_view)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=await _make_panel_embed(self.collection, self.db),
            view=self.panel_view,
        )

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(
                    embed=await _make_panel_embed(self.collection, self.db),
                    view=self.panel_view,
                )
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
#  Collection Panel View
# ─────────────────────────────────────────────────────────────────────────────

class CollectionPanelView(discord.ui.View):
    def __init__(self, collection, db, author_id):
        super().__init__(timeout=120)
        self.collection = collection
        self.db = db
        self.author_id = author_id
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return False
        return True

    # Row 0 — Read operations
    @discord.ui.button(label="Find", emoji="🔍", style=discord.ButtonStyle.primary, row=0)
    async def find_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            FindModal(self.collection, self.db, self.message, self)
        )

    @discord.ui.button(label="Count", emoji="🔢", style=discord.ButtonStyle.secondary, row=0)
    async def count_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            CountModal(self.collection, self.db, self.message, self)
        )

    # Row 1 — Write operations
    @discord.ui.button(label="Insert", emoji="➕", style=discord.ButtonStyle.success, row=1)
    async def insert_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            InsertModal(self.collection, self.db, self.message, self)
        )

    @discord.ui.button(label="Update", emoji="✏️", style=discord.ButtonStyle.primary, row=1)
    async def update_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            UpdateModal(self.collection, self.db, self.message, self)
        )

    @discord.ui.button(label="Delete", emoji="🗑️", style=discord.ButtonStyle.danger, row=1)
    async def delete_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            DeleteModal(self.collection, self.db, self.message, self)
        )

    # Row 2 — Danger zone + navigation
    @discord.ui.button(label="Drop Collection", emoji="💣", style=discord.ButtonStyle.danger, row=2)
    async def drop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="🚨 Confirm Drop",
            description=(
                f"This will **permanently drop** the entire `{self.collection}` collection "
                f"and **all** its documents.\n\n**This cannot be undone.** Are you sure?"
            ),
            color=discord.Color.red(),
        )
        confirm_view = DropConfirmView(self.collection, self.db, self, self.author_id)
        confirm_view.message = self.message
        await interaction.response.edit_message(embed=embed, view=confirm_view)

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.secondary, row=2)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        hub_embed, _ = await _make_hub_embed(self.db)
        hub_view = MongoHubView(self.db, self.author_id)
        await hub_view.populate()
        hub_view.message = self.message
        await interaction.response.edit_message(embed=hub_embed, view=hub_view)

    async def on_timeout(self):
        if self.message:
            try:
                for item in self.children:
                    item.disabled = True
                await self.message.edit(view=self)
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
#  Hub View
# ─────────────────────────────────────────────────────────────────────────────

class MongoHubView(discord.ui.View):
    def __init__(self, db, author_id):
        super().__init__(timeout=120)
        self.db = db
        self.author_id = author_id
        self.message = None
        # Options are populated via async populate() before the view is sent
        self.collection_select.options = [
            discord.SelectOption(label="Loading...", value="__loading__")
        ]
        self.collection_select.disabled = True

    async def populate(self):
        """Async method to populate the collection select with current DB collections."""
        collections = sorted(await self.db.list_collection_names())[:25]
        if collections:
            self.collection_select.options = [
                discord.SelectOption(label=col, value=col, emoji="📁")
                for col in collections
            ]
            self.collection_select.disabled = False
        else:
            self.collection_select.options = [
                discord.SelectOption(label="(no collections)", value="__none__")
            ]
            self.collection_select.disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return False
        return True

    @discord.ui.select(placeholder="📁  Select a collection to manage…", row=0)
    async def collection_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        collection = select.values[0]
        panel_view = CollectionPanelView(collection, self.db, self.author_id)
        panel_view.message = self.message
        await interaction.response.edit_message(
            embed=await _make_panel_embed(collection, self.db),
            view=panel_view,
        )

    @discord.ui.button(label="Refresh 🔄", style=discord.ButtonStyle.secondary, row=1)
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        hub_embed, _ = await _make_hub_embed(self.db)
        new_view = MongoHubView(self.db, self.author_id)
        await new_view.populate()
        new_view.message = self.message
        await interaction.response.edit_message(embed=hub_embed, view=new_view)

    async def on_timeout(self):
        if self.message:
            try:
                for item in self.children:
                    item.disabled = True
                await self.message.edit(view=self)
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
#  Owner Cog
# ─────────────────────────────────────────────────────────────────────────────

class Owner(commands.Cog):
    """Owner exclusive commands."""

    def __init__(self, client):
        self.client = client

    async def cog_check(self, ctx):
        """Ensure all commands in this cog are owner-only."""
        return await self.client.is_owner(ctx.author)

    # ==========================================
    #  Command: Reload Bot Config
    # ==========================================

    @commands.command(name="reloadconfig", aliases=["rcfg"])
    async def reload_config(self, ctx):
        """Reload bot config from the bot_config MongoDB collection."""
        import sys
        load_bot_config = sys.modules['__main__'].load_bot_config
        await load_bot_config()
        await ctx.message.add_reaction(self.client.emotes.get("greentick", "✅"))

    # ==========================================
    #  Command: MongoDB Manager
    # ==========================================

    @commands.command(name="db", aliases=["mongodb"])
    async def mdb(self, ctx):
        """Open the interactive MongoDB Manager."""
        hub_embed, _ = await _make_hub_embed(self.client.db)
        view = MongoHubView(self.client.db, ctx.author.id)
        await view.populate()
        msg = await ctx.send(embed=hub_embed, view=view)
        view.message = msg

    # ==========================================
    #  Command: Sync Application Commands
    # ==========================================

    @commands.command(name="sync")
    async def sync_tree(self, ctx, guild_id: int = None):
        """Sync application / slash command tree globally or to a specific guild."""
        if guild_id:
            guild = discord.Object(id=guild_id)
            synced = await self.client.tree.sync(guild=guild)
            await ctx.send(f"{self.client.emotes.get('greentick', '✅')} Synced `{len(synced)}` app command(s) to guild `{guild_id}`.")
        else:
            synced = await self.client.tree.sync()
            await ctx.send(f"{self.client.emotes.get('greentick', '✅')} Synced `{len(synced)}` app command(s) globally.")

    # ==========================================
    #  Command: Emit (re-process a message)
    # ==========================================

    @commands.command()
    async def emit(self, ctx, message: discord.Message = None):
        """Re-process a message through on_message (triggering commands).

        Usage:
          - Reply to a message:  !emit  (with a message reference)
          - By message link/ID:  !emit <message_id>
                                 !emit <channel_id>-<message_id>
        """
        # If no message argument, try the replied-to message
        if message is None:
            if ctx.message.reference and ctx.message.reference.resolved:
                message = ctx.message.reference.resolved
            elif ctx.message.reference:
                try:
                    message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                except discord.NotFound:
                    return await ctx.send(f"{self.client.emotes.get('redtick', '❌')} Referenced message not found.")
            else:
                return await ctx.send(
                    f"{self.client.emotes.get('redtick', '❌')} "
                    "Please reply to a message or provide a message ID/link."
                )

        # Re-dispatch the message through the bot's on_message pipeline
        self.client.dispatch("message", message)
        await ctx.message.add_reaction(self.client.emotes.get("greentick", "✅"))

    # ==========================================
    #  Command Group: Application Emoji Management
    # ==========================================

    @commands.group(name="emoji", aliases=["appemoji"], invoke_without_command=True)
    async def emoji_group(self, ctx):
        """Manage Discord Application Emojis for the bot."""
        await ctx.send_help(ctx.command)

    @emoji_group.command(name="upload", aliases=["add"])
    async def emoji_upload(self, ctx, name: str, emoji_or_url: str = None):
        """Upload a new application emoji for the bot.

        Usage:
          !emoji upload <name> <emoji/URL>
          !emoji upload <name> (with attached image or replying to a message)
        """
        # Validate emoji name (Discord rules: 2-32 alphanumeric or underscores)
        if not (2 <= len(name) <= 32) or not re.match(r"^[a-zA-Z0-9_]+$", name):
            return await ctx.send(
                f"{self.client.emotes.get('redtick', '❌')} "
                "Emoji name must be 2-32 characters long and contain only letters, numbers, and underscores."
            )

        image_url = await _extract_image_url(ctx, emoji_or_url)
        if not image_url:
            return await ctx.send(
                f"{self.client.emotes.get('redtick', '❌')} "
                "Could not find an emoji or image. Provide an emoji/URL, attach an image, or reply to a message containing one."
            )

        async with ctx.typing():
            try:
                image_bytes = await _fetch_image_bytes(image_url)
            except Exception as e:
                return await ctx.send(
                    f"{self.client.emotes.get('redtick', '❌')} Failed to download image: `{e}`"
                )

            # Check 256 KB limit
            if len(image_bytes) > 256 * 1024:
                size_kb = len(image_bytes) / 1024
                return await ctx.send(
                    f"{self.client.emotes.get('redtick', '❌')} "
                    f"Image size (`{size_kb:.1f} KB`) exceeds Discord's 256 KB limit for emojis."
                )

            try:
                emoji = await self.client.create_application_emoji(name=name, image=image_bytes)
            except discord.HTTPException as e:
                return await ctx.send(
                    f"{self.client.emotes.get('redtick', '❌')} Failed to create application emoji: `{e.text}`"
                )
            except Exception as e:
                return await ctx.send(
                    f"{self.client.emotes.get('redtick', '❌')} An unexpected error occurred: `{e}`"
                )

        embed = discord.Embed(
            title="✅ Application Emoji Uploaded",
            color=0x57F287,
        )
        embed.add_field(name="Name", value=f"`{emoji.name}`", inline=True)
        embed.add_field(name="Emoji", value=str(emoji), inline=True)
        embed.add_field(name="ID", value=f"`{emoji.id}`", inline=True)
        embed.set_thumbnail(url=emoji.url)
        await ctx.send(embed=embed)

    @emoji_group.command(name="view", aliases=["show", "info"])
    async def emoji_view(self, ctx, name: str):
        """Display details of a bot application emoji by name or ID."""
        try:
            emojis = await self.client.fetch_application_emojis()
        except Exception as e:
            return await ctx.send(f"{self.client.emotes.get('redtick', '❌')} Failed to fetch application emojis: `{e}`")

        emoji = discord.utils.find(
            lambda e: e.name.lower() == name.lower() or str(e.id) == name,
            emojis
        )

        if not emoji:
            return await ctx.send(
                f"{self.client.emotes.get('redtick', '❌')} "
                f"Application emoji `{name}` not found."
            )

        embed = discord.Embed(
            title=f"Application Emoji: {emoji.name}",
            color=0x5865F2,
        )
        embed.add_field(name="Preview", value=str(emoji), inline=True)
        embed.add_field(name="Formatted", value=f"`{emoji}`", inline=True)
        embed.add_field(name="ID", value=f"`{emoji.id}`", inline=True)
        embed.add_field(name="Animated", value=f"`{emoji.animated}`", inline=True)
        embed.add_field(name="CDN URL", value=f"[Link]({emoji.url})", inline=True)
        embed.set_thumbnail(url=emoji.url)
        await ctx.send(embed=embed)

    @emoji_group.command(name="list")
    async def emoji_list(self, ctx):
        """List all application emojis owned by the bot."""
        try:
            emojis = await self.client.fetch_application_emojis()
        except Exception as e:
            return await ctx.send(f"{self.client.emotes.get('redtick', '❌')} Failed to fetch application emojis: `{e}`")

        if not emojis:
            return await ctx.send("No application emojis found for this bot.")

        lines = [f"{e} `{e.name}` — `{e.id}`" for e in emojis]

        embed = discord.Embed(
            title=f"Application Emojis ({len(emojis)})",
            description="\n".join(lines[:30]),
            color=0x5865F2,
        )
        if len(lines) > 30:
            embed.set_footer(text=f"Showing 30 of {len(emojis)} emojis")
        await ctx.send(embed=embed)

    @emoji_group.command(name="delete", aliases=["remove", "del"])
    async def emoji_delete(self, ctx, name: str):
        """Delete an application emoji by name or ID."""
        try:
            emojis = await self.client.fetch_application_emojis()
        except Exception as e:
            return await ctx.send(f"{self.client.emotes.get('redtick', '❌')} Failed to fetch application emojis: `{e}`")

        emoji = discord.utils.find(
            lambda e: e.name.lower() == name.lower() or str(e.id) == name,
            emojis
        )

        if not emoji:
            return await ctx.send(
                f"{self.client.emotes.get('redtick', '❌')} "
                f"Application emoji `{name}` not found."
            )

        try:
            await emoji.delete()
        except discord.HTTPException as e:
            return await ctx.send(
                f"{self.client.emotes.get('redtick', '❌')} Failed to delete emoji: `{e.text}`"
            )

        await ctx.send(
            f"{self.client.emotes.get('greentick', '✅')} "
            f"Successfully deleted application emoji **{emoji.name}** (`{emoji.id}`)."
        )


async def setup(client):
    await client.add_cog(Owner(client))
