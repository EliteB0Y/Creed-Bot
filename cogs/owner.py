import discord
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

    def _format_docs(self, docs, max_chars=3800):
        """Format a list of MongoDB documents into a readable string."""
        if not docs:
            return "No documents found."
        lines = []
        for i, doc in enumerate(docs, 1):
            # Convert ObjectId to string for display
            if "_id" in doc and isinstance(doc["_id"], ObjectId):
                doc["_id"] = str(doc["_id"])
            lines.append(f"**{i}.** ```json\n{doc}\n```")
        result = "\n".join(lines)
        if len(result) > max_chars:
            result = result[:max_chars] + "\n... (truncated)"
        return result

    # ==========================================
    #  Command Group: MongoDB
    # ==========================================

    @commands.group(invoke_without_command=True)
    async def mongodb(self, ctx):
        """Interact with the MongoDB database."""
        e = discord.Embed(
            title="MongoDB Commands",
            description=(
                "Use the following subcommands:\n\n"
                f"`{ctx.prefix}mongodb collections` — List all collections\n"
                f"`{ctx.prefix}mongodb find <collection> [filter]` — Find documents\n"
                f"`{ctx.prefix}mongodb insert <collection> <document>` — Insert a document\n"
                f"`{ctx.prefix}mongodb update <collection> <filter> <update>` — Update documents\n"
                f"`{ctx.prefix}mongodb delete <collection> <filter>` — Delete documents\n"
                f"`{ctx.prefix}mongodb drop <collection>` — Drop an entire collection\n"
                f"`{ctx.prefix}mongodb count <collection> [filter]` — Count documents"
            ),
            color=discord.Color.blurple()
        )
        await ctx.send(embed=e)

    @mongodb.command(name="collections", aliases=["cols", "list"])
    async def mongodb_collections(self, ctx):
        """List all collections in the database."""
        collections = self.client.db.list_collection_names()
        if not collections:
            desc = "No collections found."
        else:
            desc = "\n".join(f"`{i}.` **{name}**" for i, name in enumerate(collections, 1))
        e = discord.Embed(
            title="Collections",
            description=desc,
            color=discord.Color.blurple()
        )
        await ctx.send(embed=e)

    @mongodb.command(name="find", aliases=["read", "get"])
    async def mongodb_find(self, ctx, collection: str, *, filter_json: str = "{}"):
        """Find documents in a collection. Optionally pass a JSON filter."""
        try:
            query = eval(filter_json)  # owner-only, safe context
        except Exception as ex:
            return await ctx.send(f"{self.client.emotes.get('redtick', '❌')} Invalid filter: `{ex}`")

        col = self.client.db.get_collection(collection)
        docs = list(col.find(query).limit(20))
        e = discord.Embed(
            title=f"Find — {collection}",
            description=self._format_docs(docs),
            color=discord.Color.green()
        )
        e.set_footer(text=f"Showing up to 20 results | Filter: {filter_json}")
        await ctx.send(embed=e)

    @mongodb.command(name="insert", aliases=["add", "create"])
    async def mongodb_insert(self, ctx, collection: str, *, document_json: str):
        """Insert a document into a collection."""
        try:
            document = eval(document_json)
        except Exception as ex:
            return await ctx.send(f"{self.client.emotes.get('redtick', '❌')} Invalid document: `{ex}`")

        col = self.client.db.get_collection(collection)
        result = col.insert_one(document)
        e = discord.Embed(
            title=f"Insert — {collection}",
            description=f"{self.client.emotes.get('greentick', '✅')} Inserted document with ID: `{result.inserted_id}`",
            color=discord.Color.green()
        )
        await ctx.send(embed=e)

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
        e = discord.Embed(
            title=f"Update — {collection}",
            description=(
                f"{self.client.emotes.get('greentick', '✅')} "
                f"Matched **{result.matched_count}** | Modified **{result.modified_count}**"
            ),
            color=discord.Color.green()
        )
        await ctx.send(embed=e)

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
        e = discord.Embed(
            title=f"Delete — {collection}",
            description=f"{self.client.emotes.get('greentick', '✅')} Deleted **{result.deleted_count}** document(s).",
            color=discord.Color.red()
        )
        await ctx.send(embed=e)

    @mongodb.command(name="drop")
    async def mongodb_drop(self, ctx, *, collection: str):
        """Drop an entire collection."""
        if collection not in self.client.db.list_collection_names():
            return await ctx.send(f"{self.client.emotes.get('redtick', '❌')} Collection `{collection}` does not exist.")

        confirm_msg = await ctx.send(
            f"🚨 **WARNING**: This will permanently drop the entire `{collection}` collection. React ✅ to confirm."
        )
        await confirm_msg.add_reaction("✅")

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) == "✅" and reaction.message.id == confirm_msg.id

        try:
            await self.client.wait_for("reaction_add", timeout=15.0, check=check)
        except Exception:
            return await ctx.send(f"{self.client.emotes.get('timer', '⏱️')} Drop cancelled — timed out.")

        self.client.db.drop_collection(collection)
        e = discord.Embed(
            title=f"Drop — {collection}",
            description=f"{self.client.emotes.get('greentick', '✅')} Collection `{collection}` has been dropped.",
            color=discord.Color.red()
        )
        await ctx.send(embed=e)

    @mongodb.command(name="count")
    async def mongodb_count(self, ctx, collection: str, *, filter_json: str = "{}"):
        """Count documents in a collection, optionally with a filter."""
        try:
            query = eval(filter_json)
        except Exception as ex:
            return await ctx.send(f"{self.client.emotes.get('redtick', '❌')} Invalid filter: `{ex}`")

        col = self.client.db.get_collection(collection)
        count = col.count_documents(query)
        e = discord.Embed(
            title=f"Count — {collection}",
            description=f"**{count:,}** document(s) match the filter.",
            color=discord.Color.blurple()
        )
        e.set_footer(text=f"Filter: {filter_json}")
        await ctx.send(embed=e)

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
