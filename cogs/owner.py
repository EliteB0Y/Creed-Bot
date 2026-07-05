import discord
import json
import logging
from discord.ext import commands
from bson import ObjectId
from bson.errors import InvalidId

logger = logging.getLogger("CreedBot")


class Owner(commands.Cog):
    """Owner exclusive commands."""

    def __init__(self, client):
        self.client = client

    async def cog_check(self, ctx):
        """Ensure all commands in this cog are owner-only."""
        return await self.client.is_owner(ctx.author)

    # ==========================================
    #  Helper: Format documents for display
    # ==========================================

    def _format_docs(self, docs, max_chars=1800):
        """Format a list of MongoDB documents into a readable code block."""
        if not docs:
            return "`No documents found.`"
        formatted = []
        for doc in docs:
            if "_id" in doc and isinstance(doc["_id"], ObjectId):
                doc["_id"] = str(doc["_id"])
            formatted.append(doc)
        output = json.dumps(formatted, indent=2, default=str)
        if len(output) > max_chars:
            output = output[:max_chars] + "\n... (truncated)"
        return f"```json\n{output}\n```"

    # ==========================================
    #  Command Group: MongoDB
    # ==========================================

    @commands.group(name="mongodb", aliases=["mdb"], invoke_without_command=True)
    async def mongodb(self, ctx):
        """Interact with the MongoDB database."""
        p = ctx.prefix
        msg = (
            f"**MongoDB Commands**\n"
            f"```\n"
            f"{p}mdb collections        — List all collections\n"
            f"{p}mdb find <col> [query] — Find documents\n"
            f"{p}mdb insert <col> <doc> — Insert a document\n"
            f"{p}mdb update <col> <f> <u>— Update documents\n"
            f"{p}mdb delete <col> <f>   — Delete documents\n"
            f"{p}mdb drop <col>         — Drop a collection\n"
            f"{p}mdb count <col> [query]— Count documents\n"
            f"```"
        )
        await ctx.send(msg)

    @mongodb.command(name="collections", aliases=["cols", "list"])
    async def mongodb_collections(self, ctx):
        """List all collections in the database."""
        collections = self.client.db.list_collection_names()
        if not collections:
            return await ctx.send("`No collections found.`")
        listing = "\n".join(f"  {i}. {name}" for i, name in enumerate(collections, 1))
        await ctx.send(f"**Collections** ({len(collections)})\n```\n{listing}\n```")

    @mongodb.command(name="find", aliases=["read", "get"])
    async def mongodb_find(self, ctx, collection: str, *, filter_json: str = "{}"):
        """Find documents in a collection. Optionally pass a JSON filter."""
        try:
            query = eval(filter_json)  # owner-only, safe context
        except Exception as ex:
            return await ctx.send(f"{self.client.emotes.get('redtick', '❌')} Invalid filter: `{ex}`")

        col = self.client.db.get_collection(collection)
        docs = list(col.find(query).limit(20))
        header = f"**Find — {collection}** | {len(docs)} result(s) | Filter: `{filter_json}`"
        await ctx.send(f"{header}\n{self._format_docs(docs)}")

    @mongodb.command(name="insert", aliases=["add", "create"])
    async def mongodb_insert(self, ctx, collection: str, *, document_json: str):
        """Insert a document into a collection."""
        try:
            document = eval(document_json)
        except Exception as ex:
            return await ctx.send(f"{self.client.emotes.get('redtick', '❌')} Invalid document: `{ex}`")

        col = self.client.db.get_collection(collection)
        result = col.insert_one(document)
        await ctx.send(
            f"{self.client.emotes.get('greentick', '✅')} **Insert — {collection}**\n"
            f"Inserted document with ID: `{result.inserted_id}`"
        )

    @mongodb.command(name="update", aliases=["edit", "modify"])
    async def mongodb_update(self, ctx, collection: str, filter_json: str, *, update_json: str):
        """Update documents in a collection. Provide a filter and an update expression."""
        try:
            query = eval(filter_json)
            update = eval(update_json)
        except Exception as ex:
            return await ctx.send(f"{self.client.emotes.get('redtick', '❌')} Invalid input: `{ex}`")

        # Wrap in $set if user didn't use an update operator
        if not any(key.startswith("$") for key in update):
            update = {"$set": update}

        col = self.client.db.get_collection(collection)
        result = col.update_many(query, update)
        await ctx.send(
            f"{self.client.emotes.get('greentick', '✅')} **Update — {collection}**\n"
            f"Matched: `{result.matched_count}` | Modified: `{result.modified_count}`"
        )

    @mongodb.command(name="delete", aliases=["remove", "del"])
    async def mongodb_delete(self, ctx, collection: str, *, filter_json: str):
        """Delete documents from a collection matching the filter."""
        try:
            query = eval(filter_json)
        except Exception as ex:
            return await ctx.send(f"{self.client.emotes.get('redtick', '❌')} Invalid filter: `{ex}`")

        col = self.client.db.get_collection(collection)

        # Safety: show what will be deleted first
        count = col.count_documents(query)
        if count == 0:
            return await ctx.send(f"{self.client.emotes.get('redtick', '❌')} No documents match that filter.")

        confirm_msg = await ctx.send(
            f"⚠️ This will delete **{count}** document(s) from `{collection}`. React ✅ to confirm."
        )
        await confirm_msg.add_reaction("✅")

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) == "✅" and reaction.message.id == confirm_msg.id

        try:
            await self.client.wait_for("reaction_add", timeout=15.0, check=check)
        except Exception:
            return await ctx.send(f"{self.client.emotes.get('timer', '⏱️')} Delete cancelled — timed out.")

        result = col.delete_many(query)
        await ctx.send(
            f"{self.client.emotes.get('greentick', '✅')} **Delete — {collection}**\n"
            f"Deleted `{result.deleted_count}` document(s)."
        )

    @mongodb.command(name="drop")
    async def mongodb_drop(self, ctx, *, collection: str):
        """Drop an entire collection."""
        if collection not in self.client.db.list_collection_names():
            return await ctx.send(f"{self.client.emotes.get('redtick', '❌')} Collection `{collection}` does not exist.")

        confirm_msg = await ctx.send(
            f"🚨 **WARNING**: This will permanently drop `{collection}`. React ✅ to confirm."
        )
        await confirm_msg.add_reaction("✅")

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) == "✅" and reaction.message.id == confirm_msg.id

        try:
            await self.client.wait_for("reaction_add", timeout=15.0, check=check)
        except Exception:
            return await ctx.send(f"{self.client.emotes.get('timer', '⏱️')} Drop cancelled — timed out.")

        self.client.db.drop_collection(collection)
        await ctx.send(
            f"{self.client.emotes.get('greentick', '✅')} **Drop — {collection}**\n"
            f"Collection `{collection}` has been dropped."
        )

    @mongodb.command(name="count")
    async def mongodb_count(self, ctx, collection: str, *, filter_json: str = "{}"):
        """Count documents in a collection, optionally with a filter."""
        try:
            query = eval(filter_json)
        except Exception as ex:
            return await ctx.send(f"{self.client.emotes.get('redtick', '❌')} Invalid filter: `{ex}`")

        col = self.client.db.get_collection(collection)
        count = col.count_documents(query)
        await ctx.send(
            f"**Count — {collection}**\n"
            f"`{count:,}` document(s) | Filter: `{filter_json}`"
        )

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


async def setup(client):
    await client.add_cog(Owner(client))
