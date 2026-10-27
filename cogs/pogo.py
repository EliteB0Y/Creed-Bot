import os
import re
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timezone

import discord
import aiohttp
from discord import app_commands, ui
from discord.enums import SeparatorSpacing
from discord.ext import commands, tasks

logger = logging.getLogger("CreedBot")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

API_BASE = "https://coordinates-api.pokemongopro.com"


class Endpoints:
    """All API route constants, grouped by feature area.

    To add a new feature (e.g. Raids, Pokéstops), simply add a new inner class:

        class Raids:
            SEARCH = f"{API_BASE}/raids/search"
            ...
    """

    class Pokemon:
        SEARCH = f"{API_BASE}/search"
        REVEAL = f"{API_BASE}/reveal"

_COMMON_HEADERS = {
    "accept": "*/*",
    "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
    "content-type": "application/json",
    "origin": "https://pogocoordinates.com",
    "priority": "u=1, i",
    "referer": "https://pogocoordinates.com/",
    "sec-ch-ua": '"Not=A?Brand";v="99", "Google Chrome";v="151", "Chromium";v="151"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "cross-site",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    ),
}

_DEFAULT_PAYLOAD = {
    "shiny_only": False,
    "shiny_account": None,
    "background_only": False,
    "pvp_mode": False,
    "pvp_league": "great",
    "pvp_top_rank": None,
    "pvp_include_pre_evolutions": True,
    "pvp_min_cp": None,
    "pokemon_ids": [],
    "species_forms": [],
    "location": None,
    "cp_min": None,
    "cp_max": None,
    "level_min": None,
    "level_max": None,
    "iv_mode": "percent",
    "iv_percent_min": None,
    "iv_percent_max": None,
    "raw_iv_atk": None,
    "raw_iv_def": None,
    "raw_iv_sta": None,
    "sizes": [],
    "forms": [],
    "gender": None,
    "boosted": None,
    "weather_id": None,
    "min_ttl": None,
    "sort": "DSP",
    "center_lat": None,
    "center_lng": None,
    "radius_km": None,
    "blacklist_pokemon_ids": [],
    "blacklist_species_forms": [],
    "blacklist_forms": [],
}

# Loaded from files/pokemon_ids.json — edit that file to add/remove Pokémon.
_POKEMON_IDS_PATH = Path(__file__).parent.parent / "files" / "pokemon_ids.json"
try:
    with _POKEMON_IDS_PATH.open(encoding="utf-8") as _f:
        POKEMON_NAME_TO_ID: dict[str, int] = json.load(_f)
    logger.info("[Pogo] Loaded %d Pokémon name→ID entries from %s", len(POKEMON_NAME_TO_ID), _POKEMON_IDS_PATH)
except FileNotFoundError:
    logger.error("[Pogo] pokemon_ids.json not found at %s — Pokémon name lookup will be unavailable.", _POKEMON_IDS_PATH)
    POKEMON_NAME_TO_ID = {}
except json.JSONDecodeError as _e:
    logger.error("[Pogo] Failed to parse pokemon_ids.json: %s — Pokémon name lookup will be unavailable.", _e)
    POKEMON_NAME_TO_ID = {}

SORT_ALIASES: dict[str, str] = {
    "dsp": "DSP",
    "despawn": "DSP",
    "level": "LEVEL",
    "iv": "IV",
    "cp": "CP",
    "distance": "DISTANCE",
}

WEATHER_EMOJIS: dict[int, str] = {
    0: "☁️",
    1: "☀️",
    2: "🌧️",
    3: "⛅",
    4: "🌬️",
    5: "❄️",
    6: "🌫️",
    7: "🌩️",
}


# ---------------------------------------------------------------------------
# Help Guide Message
# ---------------------------------------------------------------------------

POKESEARCH_HELP_MESSAGE = (
    "### 📖 `/pokesearch` Search Filters Guide\n"
    "Combine any filters below into a single query! Examples at the bottom.\n\n"
    "✨ **IV & Shiny Filters**\n"
    "• `shundo` / `snundo` — Shiny 100% IV or Shiny 0% IV\n"
    "• `hundo` / `nundo` — 100% IV or 0% IV\n"
    "• `shiny` — Shiny eligible spawns only\n"
    "• `iv:90` or `iv:90-100` — Specific IV percentage range\n"
    "• `15/15/15` or `0/15/15` or `*/15/15` — Exact Atk/Def/Sta raw IVs (`*` is wildcard)\n\n"
    "🐾 **Pokémon Names (Single or Comma-Separated)**\n"
    "• `charizard` or `pokemon:charizard`\n"
    "• `pikachu, charizard, blastoise` — Multiple Pokémon (must be separated by commas)\n\n"
    "⚔️ **PVP Leagues & Ranks**\n"
    "• `pvp great` / `pvp ultra` / `pvp master` — Filter by league\n"
    "• `pvp great 10` or `great league 10` — Great League rank 10 or better\n"
    "• `rank:5` or `top:5` — Explicit rank cutoff\n\n"
    "📊 **CP & Level Filters**\n"
    "• `cp:500` or `cp:500-1500` — Minimum or range of CP\n"
    "• `level:20` or `level:20-35` — Minimum or range of Pokémon level\n\n"
    "📍 **Location & Distance**\n"
    "• `lat,lng` (e.g. `53.077283,-2.228182`)\n"
    "• `10km` or `500km` — Distance radius from coordinates\n\n"
    "🌪️ **Weather & Sorting**\n"
    "• `boosted` — Weather boosted spawns only\n"
    "• `bg` or `background` — Special background spawns only\n"
    "• `sort:dsp` (despawn time), `sort:iv`, `sort:level`, `sort:cp`, `sort:distance`\n\n"
    "💡 **Example Searches**\n"
    "• `/pokesearch query:shundo charizard, blastoise`\n"
    "• `/pokesearch query:pvp great 10 swampert, altaria`\n"
    "• `/pokesearch query:0/*/* 53.077,-2.228 50km`\n"
    "• `/pokesearch query:hundo cp:1000-2500 sort:cp`\n"
    "• `/pokesearch query:shiny snover, beldum boosted bg`\n\n"
    "🎯 **Background Spawn Sniper**\n"
    "• `/sniper start <query>` — Monitors query every 5 mins and pings you with matches\n"
    "• `/sniper stop` — Stops your active sniper\n"
    "• `/sniper status` — Views your current sniper details"
)


# ---------------------------------------------------------------------------
# Query Parser
# ---------------------------------------------------------------------------

def parse_query(query: str) -> dict:
    """Parse a free-text query string into a search payload dict."""
    payload = dict(_DEFAULT_PAYLOAD)
    # Deep-copy list fields so the default dict is never mutated
    for k, v in _DEFAULT_PAYLOAD.items():
        if isinstance(v, list):
            payload[k] = list(v)
    tokens = query.strip()

    # --- Sort: sort:dsp / sort:level / sort:iv / sort:cp / sort:distance ---
    sort_match = re.search(r"\bsort:(\w+)\b", tokens, re.IGNORECASE)
    if sort_match:
        sort_key = sort_match.group(1).lower()
        payload["sort"] = SORT_ALIASES.get(sort_key, "DSP")
        tokens = tokens[:sort_match.start()] + tokens[sort_match.end():]

    # --- Coordinates: lat,lng (e.g. 53.077283,-2.228182) ---
    coords_match = re.search(r"(-?\d{1,3}\.\d+),\s*(-?\d{1,3}\.\d+)", tokens)
    if coords_match:
        payload["center_lat"] = float(coords_match.group(1))
        payload["center_lng"] = float(coords_match.group(2))
        tokens = tokens[:coords_match.start()] + tokens[coords_match.end():]

    # --- Radius: NNkm (e.g. 10km, 1000km) ---
    radius_match = re.search(r"\b(\d+(?:\.\d+)?)\s*km\b", tokens, re.IGNORECASE)
    if radius_match:
        payload["radius_km"] = float(radius_match.group(1))
        tokens = tokens[:radius_match.start()] + tokens[radius_match.end():]

    # --- Raw IV: A/D/S (e.g. 0/15/15, */15/15, 15/*/15, 0/*/*) ---
    raw_iv_match = re.search(
        r"(?:^|(?<=\s))(\d+|\*|-1)/(\d+|\*|-1)/(\d+|\*|-1)(?=$|\s|[,\.;])", tokens
    )
    if raw_iv_match:
        payload["iv_mode"] = "raw"
        payload["iv_percent_min"] = None
        payload["iv_percent_max"] = None
        for i, key in enumerate(("raw_iv_atk", "raw_iv_def", "raw_iv_sta"), 1):
            val = raw_iv_match.group(i)
            payload[key] = None if val in ("*", "-1") else int(val)
        tokens = tokens[:raw_iv_match.start()] + tokens[raw_iv_match.end():]

    # --- IV percent: iv:90 or iv:90-100 (only when not raw mode) ---
    iv_range_match = re.search(r"\biv:(\d+)(?:-(\d+))?\b", tokens, re.IGNORECASE)
    if iv_range_match and payload["iv_mode"] != "raw":
        payload["iv_mode"] = "percent"
        payload["iv_percent_min"] = int(iv_range_match.group(1))
        if iv_range_match.group(2):
            payload["iv_percent_max"] = int(iv_range_match.group(2))
        tokens = tokens[:iv_range_match.start()] + tokens[iv_range_match.end():]

    # --- CP range: cp:500-1500 or cp:500 ---
    cp_match = re.search(r"\bcp:(\d+)(?:-(\d+))?\b", tokens, re.IGNORECASE)
    if cp_match:
        payload["cp_min"] = int(cp_match.group(1))
        if cp_match.group(2):
            payload["cp_max"] = int(cp_match.group(2))
        tokens = tokens[:cp_match.start()] + tokens[cp_match.end():]

    # --- Level range: level:20-35 or level:20 ---
    level_match = re.search(r"\blevel:(\d+)(?:-(\d+))?\b", tokens, re.IGNORECASE)
    if level_match:
        payload["level_min"] = int(level_match.group(1))
        if level_match.group(2):
            payload["level_max"] = int(level_match.group(2))
        tokens = tokens[:level_match.start()] + tokens[level_match.end():]

    # --- Explicit pokemon: keyword (supports comma-separated names) ---
    pokemon_kw_match = re.search(r"\bpokemon:([\w\-. ,]+)", tokens, re.IGNORECASE)
    if pokemon_kw_match:
        for raw in pokemon_kw_match.group(1).split(","):
            name = raw.strip().lower()
            pid = POKEMON_NAME_TO_ID.get(name)
            if pid and pid not in payload["pokemon_ids"]:
                payload["pokemon_ids"].append(pid)
        tokens = tokens[:pokemon_kw_match.start()] + tokens[pokemon_kw_match.end():]

    # --- Keyword flags (evaluated on remaining tokens) ---
    lower = tokens.lower()

    # Shundo: shiny + min_iv = 100
    if re.search(r"\bshundo\b|\bshiny\s+hundo\b|\bhundo\s+shiny\b", lower):
        payload["shiny_only"] = True
        if payload["iv_mode"] != "raw":
            payload["iv_mode"] = "percent"
            payload["iv_percent_min"] = 100
            payload["iv_percent_max"] = None

    # Snundo: shiny + max_iv = 0
    elif re.search(r"\bsnundo\b|\bshiny\s+nundo\b|\bnundo\s+shiny\b", lower):
        payload["shiny_only"] = True
        if payload["iv_mode"] != "raw":
            payload["iv_mode"] = "percent"
            payload["iv_percent_min"] = None
            payload["iv_percent_max"] = 0

    else:
        if re.search(r"\bshiny\b", lower):
            payload["shiny_only"] = True

        if re.search(r"\bhundo\b|\b100iv\b", lower) and payload["iv_mode"] != "raw":
            payload["iv_mode"] = "percent"
            payload["iv_percent_min"] = 100
            payload["iv_percent_max"] = None
        elif re.search(r"\bnundo\b|\b0iv\b", lower) and payload["iv_mode"] != "raw":
            payload["iv_mode"] = "percent"
            payload["iv_percent_min"] = None
            payload["iv_percent_max"] = 0

    # PVP mode, league, and optional top rank (e.g. "pvp great 10", "pvp ultra 5", "great league 10")
    rank_kw = re.search(r"\b(?:rank|top):(\d+)\b", lower)
    if rank_kw:
        payload["pvp_mode"] = True
        payload["pvp_top_rank"] = int(rank_kw.group(1))

    pvp_match = re.search(
        r"\bpvp\s+(great|ultra|master)(?:\s+(\d+))?\b|"
        r"\b(great|ultra|master)\s+league(?:\s+(\d+))?\b",
        lower,
    )
    if pvp_match:
        payload["pvp_mode"] = True
        league = (pvp_match.group(1) or pvp_match.group(3)).lower()
        payload["pvp_league"] = league
        rank = pvp_match.group(2) or pvp_match.group(4)
        if rank:
            payload["pvp_top_rank"] = int(rank)
    elif re.search(r"\bpvp(?:\s+(\d+))?\b", lower):
        payload["pvp_mode"] = True
        m = re.search(r"\bpvp\s+(\d+)\b", lower)
        if m:
            payload["pvp_top_rank"] = int(m.group(1))

    # Boosted
    if re.search(r"\bboosted\b", lower):
        payload["boosted"] = True

    # Background only
    bg_match = re.search(r"\b(?:bg|background)\b", tokens, re.IGNORECASE)
    if bg_match:
        payload["background_only"] = True
        tokens = tokens[:bg_match.start()] + tokens[bg_match.end():]

    # --- Bare Pokémon names (must be comma-separated if multiple) ---
    if not payload["pokemon_ids"]:
        segments = [s.strip() for s in tokens.split(",") if s.strip()]
        for seg in segments:
            seg_lower = seg.lower()
            # Sort by length descending so "dragonite" matches before "dragon"
            for name in sorted(POKEMON_NAME_TO_ID.keys(), key=len, reverse=True):
                pattern = r"\b" + re.escape(name) + r"\b"
                if re.search(pattern, seg_lower):
                    pid = POKEMON_NAME_TO_ID[name]
                    if pid not in payload["pokemon_ids"]:
                        payload["pokemon_ids"].append(pid)
                    break

    return payload


# ---------------------------------------------------------------------------
# Discord UI — Components v2 (Container & Sections)
# ---------------------------------------------------------------------------

def resolve_emoji(bot: commands.Bot, name: str, fallback: str) -> str:
    """Find custom emoji in client.emojis or client.emotes by name, or fall back to default."""
    if hasattr(bot, "emojis"):
        emoji = discord.utils.get(bot.emojis, name=name)
        if emoji:
            return str(emoji)
    if hasattr(bot, "emotes") and isinstance(bot.emotes, dict):
        if name in bot.emotes:
            return str(bot.emotes[name])
    return fallback


class RevealButton(ui.Button):
    """Accessory magnifying glass button that reveals spawn coordinates ephemerally."""

    def __init__(self, reveal_code: str | None, token: str):
        super().__init__(emoji="🔍", style=discord.ButtonStyle.secondary)
        self.reveal_code = reveal_code
        self.token = token

    async def callback(self, interaction: discord.Interaction):
        if not self.reveal_code:
            await interaction.response.send_message(
                "No coordinates available for this spawn.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        headers = {**_COMMON_HEADERS, "authorization": self.token}
        timeout = aiohttp.ClientTimeout(total=15)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"{Endpoints.Pokemon.REVEAL}/{self.reveal_code}", headers=headers
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        coords = data.get("coords", "")
                        if coords:
                            await interaction.followup.send(f"`{coords}`", ephemeral=True)
                        else:
                            await interaction.followup.send(
                                "⚠️ Coordinates not found.", ephemeral=True
                            )
                    elif resp.status == 401:
                        await interaction.followup.send(
                            "⚠️ **Unauthorized** — Your saved auth token is invalid or expired.\n"
                            "Please update it using `/auth`.",
                            ephemeral=True,
                        )
                    else:
                        await interaction.followup.send(
                            f"⚠️ Reveal failed (HTTP {resp.status}).", ephemeral=True
                        )
        except asyncio.TimeoutError:
            await interaction.followup.send(
                "⏳ Reveal request timed out. Please try again.", ephemeral=True
            )
        except Exception as e:
            logger.error("Reveal request error:", exc_info=e)
            await interaction.followup.send(
                "❌ An unexpected error occurred during reveal.", ephemeral=True
            )


class PogoLayoutView(ui.LayoutView):
    """Components v2 LayoutView containing a container with up to 5 Pokémon sections."""

    def __init__(
        self,
        chunk: list[dict],
        bot: commands.Bot,
        token: str,
        show_coords: bool = False,
        timeout: float = 600.0,
    ):
        super().__init__(timeout=timeout)
        self.chunk = chunk
        self.bot = bot
        self.token = token
        self.show_coords = show_coords

        container_children = []
        for i, item in enumerate(chunk):
            if i > 0:
                container_children.append(
                    ui.Separator(spacing=SeparatorSpacing.large)
                )
            sec_text = self.build_section_text(item, bot, show_coords=show_coords)
            if show_coords:
                container_children.append(ui.TextDisplay(sec_text))
            else:
                btn = RevealButton(reveal_code=item.get("reveal_code"), token=token)
                section = ui.Section(
                    ui.TextDisplay(sec_text),
                    accessory=btn,
                )
                container_children.append(section)

        self.add_item(ui.Container(*container_children))

    @staticmethod
    def build_section_text(result: dict, bot: commands.Bot, show_coords: bool = False) -> str:
        name = result.get("pokemon_name", "Unknown")
        shiny = result.get("shiny", False)
        iv_pct = result.get("iv_percent", 0.0) or 0.0
        is_hundo = iv_pct == 100.0

        # Line 1: ### {optional shiny emoji} {optional hundred emoji} Pokemon_Name_Here
        header_parts = ["###"]
        if shiny:
            header_parts.append("✨")
        if is_hundo:
            header_parts.append("💯")
        header_parts.append(name)
        line1 = " ".join(header_parts)

        # Line 2: {IV emoji} iv% (raw ivs here) - {level emoji} level_here - {cp emoji} CP_here
        iv_emoji = resolve_emoji(bot, "iv", "IV")
        cp_emoji = resolve_emoji(bot, "cp", "CP")
        lvl_emoji = resolve_emoji(bot, "level", "LVL")
        raw_iv = result.get("raw_iv") or "?/?/?"
        lvl = result.get("level", "?")
        cp = result.get("cp", "?")
        line2 = f"{iv_emoji} {iv_pct:.1f}% ({raw_iv}) - {lvl_emoji} {lvl} - {cp_emoji} {cp}"

        # Line 3: {moveset emoji} move1 / move2
        fast_move = result.get("fast_move", "?")
        charge_move = result.get("charge_move", "?")
        line3 = f"💥 {fast_move} / {charge_move}"

        # Line 4: {timer emoji} despawn time here
        timer_emoji = resolve_emoji(bot, "slowmode", "⏰")
        despawn_str = result.get("despawn_at", "")
        despawn_display = "Unknown"
        if despawn_str:
            try:
                despawn_clean = despawn_str.replace("Z", "+00:00")
                dt = datetime.fromisoformat(despawn_clean)
                ts = int(dt.timestamp())
                despawn_display = f"<t:{ts}:R>"
            except ValueError:
                despawn_display = despawn_str
        line4 = f"{timer_emoji} {despawn_display}"

        # Line 5: Location details
        location = result.get("location", "Unknown")
        line5 = f"🌍 {location}"

        lines = [line1, line2, line3, line4, line5]
        if show_coords:
            coords = result.get("coords")
            if coords:
                lines.append(f"📍 `{coords}`")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Auth Modal
# ---------------------------------------------------------------------------

class AuthModal(ui.Modal, title="PogoCoordinates Auth"):
    token_input = ui.TextInput(
        label="Bearer Auth Token",
        style=discord.TextStyle.paragraph,
        placeholder="Paste your token here (Bearer eyJ...)",
        required=True,
        max_length=2000,
    )

    def __init__(self, db):
        super().__init__()
        self.db = db

    async def on_submit(self, interaction: discord.Interaction):
        raw_token = self.token_input.value.strip()
        if not raw_token:
            await interaction.response.send_message(
                "⚠️ Token cannot be empty.", ephemeral=True
            )
            return

        token = raw_token if raw_token.lower().startswith("bearer ") else f"Bearer {raw_token}"

        col = self.db.get_collection("pogo_users")
        await col.update_one(
            {"_id": interaction.user.id},
            {
                "$set": {
                    "token": token,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )

        await interaction.response.send_message(
            "✅ **Auth token saved successfully!**\nYou can now use `/pokesearch`.",
            ephemeral=True,
        )


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class Pogo(commands.Cog):
    """Pokémon GO coordinate search, authentication, and spawn sniping."""

    def __init__(self, client: commands.Bot):
        self.client = client

    async def cog_load(self):
        self.sniper_loop.start()

    def cog_unload(self):
        self.sniper_loop.cancel()

    @app_commands.command(
        name="auth",
        description="Set up or update your personal PogoCoordinates auth token.",
    )
    async def auth(self, interaction: discord.Interaction):
        """Open a modal for the user to configure their auth token."""
        await interaction.response.send_modal(AuthModal(self.client.db))

    @app_commands.command(
        name="pokesearch",
        description=(
            "Search for Pokémon GO spawns. "
            "E.g: shundo | snundo | hundo charizard | 0/15/15 53.07,-2.22 10km"
        ),
    )
    @app_commands.describe(
        query=(
            "Filters: help (view guide), shundo, snundo, hundo, nundo, pvp great/ultra/master, "
            "iv:90, 0/15/15, 53.07,-2.22, 10km, cp:500-1500, level:20-35, pokemon:<name>"
        )
    )
    async def pokesearch(self, interaction: discord.Interaction, query: str):
        # 0. Help shortcut
        if query.strip().lower() in ("help", "h", "--help", "-h"):
            await interaction.response.send_message(POKESEARCH_HELP_MESSAGE, ephemeral=True)
            return

        # 1. Fetch user auth token from database
        col = self.client.db.get_collection("pogo_users")
        user_doc = await col.find_one({"_id": interaction.user.id})
        user_token = user_doc.get("token") if user_doc else None

        if not user_token:
            await interaction.response.send_message(
                "⚠️ **Authentication Required**\n"
                "You haven't set up your auth token yet.\n"
                "Please run `/auth` to configure your token before searching.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        payload = parse_query(query)
        headers = {**_COMMON_HEADERS, "authorization": user_token}
        timeout = aiohttp.ClientTimeout(total=15)

        logger.info(
            "POGO /pokesearch | User: %s (%s) | Query: %r | Active filters: %s",
            interaction.user,
            interaction.user.id,
            query,
            {k: v for k, v in payload.items() if v not in (None, False, [], "")},
        )

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    Endpoints.Pokemon.SEARCH, json=payload, headers=headers
                ) as resp:
                    if resp.status == 401:
                        await interaction.followup.send(
                            "⚠️ **Unauthorized** — Your saved auth token is invalid or expired.\n"
                            "Please update it using `/auth`.",
                            ephemeral=True,
                        )
                        return
                    if resp.status != 200:
                        body = await resp.text()
                        logger.error(
                            "Search API returned HTTP %s: %s", resp.status, body[:300]
                        )
                        await interaction.followup.send(
                            f"❌ API error (HTTP {resp.status}). Please try again later.",
                            ephemeral=True,
                        )
                        return
                    data = await resp.json()

        except asyncio.TimeoutError:
            await interaction.followup.send(
                "⏳ The search request timed out. Please try again.", ephemeral=True
            )
            return
        except Exception as e:
            logger.error("Search request error:", exc_info=e)
            await interaction.followup.send(
                "❌ An unexpected error occurred. Please try again later.",
                ephemeral=True,
            )
            return

        results: list[dict] = data.get("results", [])

        if not results:
            await interaction.followup.send(
                f"🔍 **No Results Found**\n"
                f"No Pokémon matched your search: `{query}`\n"
                f"Try broadening your filters.",
                ephemeral=True,
            )
            return

        CHUNK_SIZE = 5
        chunks = [
            results[i : i + CHUNK_SIZE] for i in range(0, len(results), CHUNK_SIZE)
        ]

        # Send up to 5 messages (25 results max) to respect Discord rate limits
        for chunk in chunks[:5]:
            view = PogoLayoutView(chunk, bot=self.client, token=user_token)
            await interaction.followup.send(view=view, ephemeral=True)

    # ------------------------------------------------------------------
    # Sniper Commands
    # ------------------------------------------------------------------

    sniper = app_commands.Group(
        name="sniper",
        description="Monitor queries every 5 minutes and get alerted on matches",
    )

    @sniper.command(
        name="start",
        description="Start a background sniper that pings you when matches are found.",
    )
    @app_commands.describe(
        query="Filter query to monitor (e.g. shundo froakie, pvp great 10 swampert)"
    )
    async def sniper_start(self, interaction: discord.Interaction, query: str):
        """Register or update an active spawn sniper for the invoking user."""
        if query.strip().lower() in ("help", "h", "--help", "-h"):
            await interaction.response.send_message(POKESEARCH_HELP_MESSAGE, ephemeral=True)
            return

        # 1. Require authentication
        col_users = self.client.db.get_collection("pogo_users")
        user_doc = await col_users.find_one({"_id": interaction.user.id})
        user_token = user_doc.get("token") if user_doc else None

        if not user_token:
            await interaction.response.send_message(
                "⚠️ **Authentication Required**\n"
                "You haven't set up your auth token yet.\n"
                "Please run `/auth` to configure your token before starting a sniper.",
                ephemeral=True,
            )
            return

        # 2. Upsert sniper in database
        col_snipers = self.client.db.get_collection("pogo_snipers")
        now = datetime.now(timezone.utc)
        await col_snipers.update_one(
            {"_id": interaction.user.id},
            {
                "$set": {
                    "user_id": interaction.user.id,
                    "channel_id": interaction.channel_id,
                    "guild_id": interaction.guild_id,
                    "query": query.strip(),
                    "seen_spawn_ids": [],
                    "created_at": now,
                    "last_checked_at": now,
                }
            },
            upsert=True,
        )

        await interaction.response.send_message(
            f"🎯 **Sniper Activated!**\n"
            f"• **Query:** `{query.strip()}`\n"
            f"• **Channel:** <#{interaction.channel_id}>\n"
            f"• **Interval:** Every 5 minutes\n\n"
            f"I'll ping you here whenever a new matching spawn is found! Run `/sniper stop` anytime to cancel."
        )

    @sniper.command(
        name="stop",
        description="Stop your active spawn sniper.",
    )
    async def sniper_stop(self, interaction: discord.Interaction):
        """Cancel the user's active spawn sniper."""
        col_snipers = self.client.db.get_collection("pogo_snipers")
        deleted = await col_snipers.find_one_and_delete({"_id": interaction.user.id})

        if deleted:
            await interaction.response.send_message(
                f"🛑 **Sniper Stopped**\nYour sniper for `{deleted.get('query')}` has been deactivated.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "ℹ️ You do not have an active sniper running.",
                ephemeral=True,
            )

    @sniper.command(
        name="status",
        description="View your active spawn sniper configuration.",
    )
    async def sniper_status(self, interaction: discord.Interaction):
        """Display details of the user's current sniper."""
        col_snipers = self.client.db.get_collection("pogo_snipers")
        doc = await col_snipers.find_one({"_id": interaction.user.id})

        if doc:
            created = doc.get("created_at")
            created_ts = int(created.timestamp()) if isinstance(created, datetime) else None
            created_str = f"<t:{created_ts}:R>" if created_ts else "Unknown"
            await interaction.response.send_message(
                f"🎯 **Active Sniper Status**\n"
                f"• **Query:** `{doc.get('query')}`\n"
                f"• **Channel:** <#{doc.get('channel_id')}>\n"
                f"• **Started:** {created_str}\n"
                f"• **Interval:** Every 5 minutes\n\n"
                f"Use `/sniper stop` to deactivate.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "ℹ️ You do not have an active sniper running. Start one using `/sniper start <query>`.",
                ephemeral=True,
            )

    # ------------------------------------------------------------------
    # Background Sniper Loop (runs every 5 minutes)
    # ------------------------------------------------------------------

    @tasks.loop(minutes=5)
    async def sniper_loop(self):
        """Checks all active snipers every 5 minutes and pings users with matches."""
        try:
            col_snipers = self.client.db.get_collection("pogo_snipers")
            col_users = self.client.db.get_collection("pogo_users")

            snipers = [s async for s in col_snipers.find()]
            if not snipers:
                return

            for sniper in snipers:
                user_id = sniper["user_id"]
                channel_id = sniper.get("channel_id")
                query = sniper.get("query")
                if not channel_id or not query:
                    continue

                # 1. Fetch user token
                user_doc = await col_users.find_one({"_id": user_id})
                user_token = user_doc.get("token") if user_doc else None
                if not user_token:
                    continue

                # 2. Query search endpoint
                payload = parse_query(query)
                headers = {**_COMMON_HEADERS, "authorization": user_token}
                timeout = aiohttp.ClientTimeout(total=15)
                results: list[dict] = []
                try:
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        async with session.post(
                            Endpoints.Pokemon.SEARCH, json=payload, headers=headers
                        ) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                results = data.get("results", [])
                            elif resp.status == 401:
                                logger.warning("[Sniper] User %s auth token expired during sniper check", user_id)
                                channel = self.client.get_channel(channel_id)
                                if channel:
                                    await channel.send(
                                        f"⚠️ <@{user_id}> **Sniper Paused:** Your auth token is invalid or expired. "
                                        f"Please update it using `/auth`."
                                    )
                                continue
                            else:
                                continue
                except Exception as e:
                    logger.debug("[Sniper] Failed search query for user %s: %s", user_id, e)
                    continue

                if not results:
                    continue

                # 3. Filter out previously alerted spawns
                seen_spawn_ids = set(sniper.get("seen_spawn_ids") or [])
                new_results = []
                new_seen_ids = []
                for r in results:
                    spawn_key = (
                        str(r.get("encounter_id"))
                        if r.get("encounter_id")
                        else f"{r.get('pokemon_id')}_{r.get('cp')}_{r.get('despawn_at')}"
                    )
                    if spawn_key not in seen_spawn_ids:
                        new_results.append(r)
                        new_seen_ids.append(spawn_key)

                if not new_results:
                    continue

                # 4. Send ping and result containers in target channel
                channel = self.client.get_channel(channel_id)
                if not channel:
                    try:
                        channel = await self.client.fetch_channel(channel_id)
                    except Exception:
                        channel = None

                if channel:
                    alert_results = new_results[:15]

                    # Concurrently resolve coordinates for each new spawn to display directly in components
                    async def _fetch_coords(session, item):
                        rc = item.get("reveal_code")
                        if not rc:
                            return
                        try:
                            async with session.get(
                                f"{Endpoints.Pokemon.REVEAL}/{rc}", headers=headers
                            ) as resp:
                                if resp.status == 200:
                                    data = await resp.json()
                                    item["coords"] = data.get("coords")
                        except Exception as e:
                            logger.debug("[Sniper] Failed to fetch coords for reveal code %s: %s", rc, e)

                    try:
                        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                            await asyncio.gather(*[_fetch_coords(session, item) for item in alert_results])
                    except Exception as e:
                        logger.error("[Sniper] Error resolving coordinates for sniper alert:", exc_info=e)

                    CHUNK_SIZE = 5
                    chunks = [
                        alert_results[i : i + CHUNK_SIZE]
                        for i in range(0, len(alert_results), CHUNK_SIZE)
                    ]
                    # Send user ping notification with found spawn names
                    found_names = list(
                        dict.fromkeys(
                            r.get("pokemon_name") or f"Pokémon #{r.get('pokemon_id', '?')}"
                            for r in alert_results
                        )
                    )
                    bold_names = [f"**{name}**" for name in found_names]
                    header = f"🎯 <@{user_id}> **Found:** {', '.join(bold_names)}"
                    await channel.send(header)

                    for chunk in chunks:
                        view = PogoLayoutView(chunk, bot=self.client, token=user_token, show_coords=True)
                        await channel.send(view=view)

                # 5. Update seen_spawn_ids in database (capped to last 100 to avoid unbounded growth)
                updated_seen = list(seen_spawn_ids.union(new_seen_ids))[-100:]
                await col_snipers.update_one(
                    {"_id": user_id},
                    {
                        "$set": {
                            "seen_spawn_ids": updated_seen,
                            "last_checked_at": datetime.now(timezone.utc),
                        }
                    },
                )

        except Exception as e:
            logger.error("[Sniper] Error in sniper background loop:", exc_info=e)

    @sniper_loop.before_loop
    async def before_sniper_loop(self):
        await self.client.wait_until_ready()


async def setup(client: commands.Bot):
    await client.add_cog(Pogo(client))
