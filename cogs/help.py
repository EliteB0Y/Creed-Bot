import discord
import logging
from discord.ext import commands
from typing import Dict, List

logger = logging.getLogger("CreedBot")


# ─────────────────────────────────────────────────────────────────────────────
#  Cog metadata — emoji + one-line description shown in the hub
# ─────────────────────────────────────────────────────────────────────────────

_COG_META: Dict[str, tuple] = {
    "Basic":        ("🛠️",  "General utility and fun commands"),
    "Games":        ("🎮",  "Minigames and tournaments"),
    "PokemonCreed": ("⚔️",  "Pokémon Creed tools, rates & collection"),
    "Owner":        ("🔐",  "Owner-only bot management"),
    "Help":         ("📚",  "Help and command browser"),
}
_DEFAULT_EMOJI = "📦"
_DEFAULT_DESC  = "Miscellaneous commands"
_COLOR         = 0x5865F2  # Discord blurple


def _cog_emoji(cog_name: str) -> str:
    return _COG_META.get(cog_name, (_DEFAULT_EMOJI, ""))[0]


def _cog_desc(cog_name: str) -> str:
    return _COG_META.get(cog_name, ("", _DEFAULT_DESC))[1]


# ─────────────────────────────────────────────────────────────────────────────
#  Permission-aware command resolver
# ─────────────────────────────────────────────────────────────────────────────

async def get_runnable_commands(
    bot: commands.Bot, ctx: commands.Context
) -> Dict[str, List[commands.Command]]:
    """
    Returns {cog_name: [Command, ...]} containing only the top-level commands
    that the invoker can actually run. Hidden commands are always excluded.
    Cogs with zero visible commands are omitted.
    """
    result: Dict[str, List[commands.Command]] = {}
    for cog_name, cog in bot.cogs.items():
        visible: List[commands.Command] = []
        for cmd in cog.get_commands():
            if cmd.hidden:
                continue
            try:
                runnable = await cmd.can_run(ctx)
            except (commands.CheckFailure, Exception):
                runnable = False
            if runnable:
                visible.append(cmd)
        if visible:
            result[cog_name] = sorted(visible, key=lambda c: c.name)
    return result


# ─────────────────────────────────────────────────────────────────────────────
#  Embed builders
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_usage(cmd: commands.Command, prefix: str) -> str:
    """Return a formatted usage string, e.g. `!ratebox [pokemon]`."""
    if cmd.usage:
        return f"`{prefix}{cmd.qualified_name} {cmd.usage}`"
    if cmd.signature:
        return f"`{prefix}{cmd.qualified_name} {cmd.signature}`"
    return f"`{prefix}{cmd.qualified_name}`"


def make_hub_embed(
    bot: commands.Bot,
    ctx: commands.Context,
    visible: Dict[str, List[commands.Command]],
    prefix: str,
) -> discord.Embed:
    embed = discord.Embed(
        title=f"{bot.user.display_name} — Help",
        description=(
            f"Browse commands using the **select menu** below.\n"
            f"Current prefix: **`{prefix}`**\n"
        ),
        color=_COLOR,
    )
    for cog_name in sorted(visible):
        cmds = visible[cog_name]
        emoji = _cog_emoji(cog_name)
        embed.add_field(
            name=f"{emoji}  {cog_name}",
            value=f"{_cog_desc(cog_name)}\n`{len(cmds)} command(s)`",
            inline=True,
        )
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.set_footer(
        text=f"Requested by {ctx.author.display_name}",
        icon_url=ctx.author.display_avatar.url,
    )
    return embed


def make_category_embed(
    cog_name: str,
    cog: commands.Cog,
    cmds: List[commands.Command],
    prefix: str,
    ctx: commands.Context,
) -> discord.Embed:
    emoji = _cog_emoji(cog_name)
    cog_description = (cog.description if cog and cog.description else None) or _cog_desc(cog_name)

    lines = []
    for cmd in cmds:
        short = (cmd.brief or (cmd.help or "No description.").split("\n")[0])[:80]
        alias_str = f"\n   *(Aliases: {', '.join(f'`{a}`' for a in cmd.aliases)})*" if cmd.aliases else ""
        
        lines.append(
            f"**`{prefix}{cmd.name}`**\n"
            f"↳ {short}{alias_str}"
        )

    embed = discord.Embed(
        title=f"{emoji}  {cog_name}",
        description=f"*{cog_description}*\n\u200b\n" + "\n\n".join(lines),
        color=_COLOR,
    )
    embed.set_footer(
        text=f"Select a command below for full details  •  Requested by {ctx.author.display_name}",
        icon_url=ctx.author.display_avatar.url,
    )
    return embed


def make_command_embed(
    cmd: commands.Command,
    prefix: str,
    ctx: commands.Context,
) -> discord.Embed:
    cog_name = cmd.cog_name or "Uncategorized"
    emoji = _cog_emoji(cog_name)

    embed = discord.Embed(
        title=f"{emoji}  {prefix}{cmd.qualified_name}",
        description=cmd.help or cmd.brief or "*No description available.*",
        color=_COLOR,
    )

    # Usage
    embed.add_field(name="Usage", value=_fmt_usage(cmd, prefix), inline=False)

    # Aliases
    if cmd.aliases:
        embed.add_field(
            name="Aliases",
            value="  ".join(f"`{a}`" for a in cmd.aliases),
            inline=True,
        )

    # Cooldown
    if cmd._buckets and cmd._buckets._cooldown:
        cd = cmd._buckets._cooldown
        embed.add_field(
            name="Cooldown",
            value=f"`{cd.rate}` use(s) per `{cd.per:.0f}s`",
            inline=True,
        )

    # Subcommands (Groups only)
    if isinstance(cmd, commands.Group) and cmd.commands:
        sub_lines = [
            f"`{prefix}{sub.qualified_name}` — "
            f"{sub.brief or (sub.help or '').split(chr(10))[0] or 'No description.'}"
            for sub in sorted(cmd.commands, key=lambda c: c.name)
        ]
        embed.add_field(
            name=f"Subcommands ({len(cmd.commands)})",
            value="\n".join(sub_lines),
            inline=False,
        )

    embed.set_footer(
        text=f"Category: {cog_name}  •  Requested by {ctx.author.display_name}",
        icon_url=ctx.author.display_avatar.url,
    )
    return embed


# ─────────────────────────────────────────────────────────────────────────────
#  Command Detail View
# ─────────────────────────────────────────────────────────────────────────────

class HelpCommandView(discord.ui.View):
    def __init__(
        self,
        bot: commands.Bot,
        ctx: commands.Context,
        visible: Dict[str, List[commands.Command]],
        cog_name: str,
        prefix: str,
        author_id: int,
    ):
        super().__init__(timeout=120)
        self.bot       = bot
        self.ctx       = ctx
        self.visible   = visible
        self.cog_name  = cog_name
        self.prefix    = prefix
        self.author_id = author_id
        self.message   = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This help menu is not for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="← Back to Category", style=discord.ButtonStyle.secondary, row=0)
    async def back_to_category(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog  = self.bot.cogs.get(self.cog_name)
        cmds = self.visible.get(self.cog_name, [])
        embed     = make_category_embed(self.cog_name, cog, cmds, self.prefix, self.ctx)
        cat_view  = HelpCategoryView(
            self.bot, self.ctx, self.visible, self.cog_name, self.prefix, self.author_id
        )
        cat_view.message = self.message
        await interaction.response.edit_message(embed=embed, view=cat_view)

    @discord.ui.button(label="← Back to Hub", style=discord.ButtonStyle.primary, row=0)
    async def back_to_hub(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed     = make_hub_embed(self.bot, self.ctx, self.visible, self.prefix)
        hub_view  = HelpHubView(self.bot, self.ctx, self.visible, self.prefix, self.author_id)
        hub_view.message = self.message
        await interaction.response.edit_message(embed=embed, view=hub_view)

    async def on_timeout(self):
        if self.message:
            try:
                for item in self.children:
                    item.disabled = True
                await self.message.edit(view=self)
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
#  Category View
# ─────────────────────────────────────────────────────────────────────────────

class HelpCategoryView(discord.ui.View):
    def __init__(
        self,
        bot: commands.Bot,
        ctx: commands.Context,
        visible: Dict[str, List[commands.Command]],
        cog_name: str,
        prefix: str,
        author_id: int,
    ):
        super().__init__(timeout=120)
        self.bot       = bot
        self.ctx       = ctx
        self.visible   = visible
        self.cog_name  = cog_name
        self.prefix    = prefix
        self.author_id = author_id
        self.message   = None

        # Populate command select — groups get a folder emoji, regular commands get a pin
        cmds = visible.get(cog_name, [])
        options = [
            discord.SelectOption(
                label=f"{prefix}{cmd.name}",
                value=cmd.qualified_name,
                description=(cmd.brief or (cmd.help or "No description.").split("\n")[0])[:100],
                emoji="📁" if isinstance(cmd, commands.Group) else "📌",
            )
            for cmd in cmds[:25]
        ]
        if options:
            self.command_select.options = options
        else:
            self.command_select.options = [discord.SelectOption(label="(none)", value="__none__")]
            self.command_select.disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This help menu is not for you.", ephemeral=True)
            return False
        return True

    @discord.ui.select(placeholder="📌  Select a command for details…", row=0)
    async def command_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        qualified = select.values[0]
        cmd = self.bot.get_command(qualified)
        if not cmd:
            await interaction.response.send_message("Command not found.", ephemeral=True)
            return
        embed       = make_command_embed(cmd, self.prefix, self.ctx)
        detail_view = HelpCommandView(
            self.bot, self.ctx, self.visible, self.cog_name, self.prefix, self.author_id
        )
        detail_view.message = self.message
        await interaction.response.edit_message(embed=embed, view=detail_view)

    @discord.ui.button(label="← Back to Hub", style=discord.ButtonStyle.primary, row=1)
    async def back_to_hub(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed     = make_hub_embed(self.bot, self.ctx, self.visible, self.prefix)
        hub_view  = HelpHubView(self.bot, self.ctx, self.visible, self.prefix, self.author_id)
        hub_view.message = self.message
        await interaction.response.edit_message(embed=embed, view=hub_view)

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

class HelpHubView(discord.ui.View):
    def __init__(
        self,
        bot: commands.Bot,
        ctx: commands.Context,
        visible: Dict[str, List[commands.Command]],
        prefix: str,
        author_id: int,
    ):
        super().__init__(timeout=120)
        self.bot       = bot
        self.ctx       = ctx
        self.visible   = visible
        self.prefix    = prefix
        self.author_id = author_id
        self.message   = None

        # Populate cog select (max 25 Discord options)
        options = [
            discord.SelectOption(
                label=cog_name,
                value=cog_name,
                description=_cog_desc(cog_name)[:100],
                emoji=_cog_emoji(cog_name),
            )
            for cog_name in sorted(visible)[:25]
        ]
        if options:
            self.cog_select.options = options
        else:
            self.cog_select.options = [discord.SelectOption(label="(no categories)", value="__none__")]
            self.cog_select.disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This help menu is not for you.", ephemeral=True)
            return False
        return True

    @discord.ui.select(placeholder="📚  Select a category…", row=0)
    async def cog_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        cog_name = select.values[0]
        cog      = self.bot.cogs.get(cog_name)
        cmds     = self.visible.get(cog_name, [])
        embed    = make_category_embed(cog_name, cog, cmds, self.prefix, self.ctx)
        cat_view = HelpCategoryView(
            self.bot, self.ctx, self.visible, cog_name, self.prefix, self.author_id
        )
        cat_view.message = self.message
        await interaction.response.edit_message(embed=embed, view=cat_view)

    async def on_timeout(self):
        if self.message:
            try:
                for item in self.children:
                    item.disabled = True
                await self.message.edit(view=self)
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
#  Help Cog
# ─────────────────────────────────────────────────────────────────────────────

class Help(commands.Cog):
    """Help and command browser."""

    def __init__(self, client: commands.Bot):
        self.client = client

    @commands.command(name="help", aliases=["h", "cmds"])
    async def help_cmd(self, ctx: commands.Context, *, query: str = None):
        """Browse all commands available to you, or look up a specific command.

        Usage:
          !help            — open the interactive command browser
          !help <command>  — jump directly to a command's detail page
        """
        # Resolve the guild prefix (last element of when_mentioned_or list)
        raw_prefix = await self.client.get_prefix(ctx.message)
        prefix = raw_prefix[-1] if isinstance(raw_prefix, (list, tuple)) else raw_prefix
        if not prefix:
            prefix = "!"  # fallback for empty-prefix DM mode

        # ── Direct command lookup: !help <command> ────────────────────────────
        if query:
            cmd = self.client.get_command(query.lower())
            if cmd and not cmd.hidden:
                try:
                    runnable = await cmd.can_run(ctx)
                except Exception:
                    runnable = False
                if runnable:
                    visible  = await get_runnable_commands(self.client, ctx)
                    embed    = make_command_embed(cmd, prefix, ctx)
                    cog_name = cmd.cog_name or "Uncategorized"
                    view     = HelpCommandView(
                        self.client, ctx, visible, cog_name, prefix, ctx.author.id
                    )
                    msg = await ctx.send(embed=embed, view=view)
                    view.message = msg
                    return
            await ctx.send(
                f"{self.client.emotes.get('redtick', '❌')} "
                f"`Command '{query}' not found or not available to you.`",
                delete_after=10,
            )
            return

        # ── Hub ───────────────────────────────────────────────────────────────
        visible  = await get_runnable_commands(self.client, ctx)
        embed    = make_hub_embed(self.client, ctx, visible, prefix)
        hub_view = HelpHubView(self.client, ctx, visible, prefix, ctx.author.id)
        msg      = await ctx.send(embed=embed, view=hub_view)
        hub_view.message = msg


async def setup(client: commands.Bot):
    await client.add_cog(Help(client))
