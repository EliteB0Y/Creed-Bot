import os
import re
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime

import discord
import aiohttp
from discord import app_commands, ui
from discord.enums import SeparatorSpacing
from discord.ext import commands

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

    # --- Raw IV: A/D/S (e.g. 0/15/15, */15/15, 15/*/15) ---
    raw_iv_match = re.search(r"\b(\d+|\*|-1)/(\d+|\*|-1)/(\d+|\*|-1)\b", tokens)
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

    # --- Explicit pokemon: keyword ---
    pokemon_kw_match = re.search(r"\bpokemon:([\w\-. ]+)", tokens, re.IGNORECASE)
    if pokemon_kw_match:
        name = pokemon_kw_match.group(1).strip().lower()
        pid = POKEMON_NAME_TO_ID.get(name)
        if pid:
            payload["pokemon_ids"] = [pid]
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

    # PVP league
    if re.search(r"\bpvp\s+ultra\b|\bultra\s+league\b", lower):
        payload["pvp_mode"] = True
        payload["pvp_league"] = "ultra"
    elif re.search(r"\bpvp\s+great\b|\bgreat\s+league\b", lower):
        payload["pvp_mode"] = True
        payload["pvp_league"] = "great"
    elif re.search(r"\bpvp\s+master\b|\bmaster\s+league\b", lower):
        payload["pvp_mode"] = True
        payload["pvp_league"] = "master"

    # Boosted
    if re.search(r"\bboosted\b", lower):
        payload["boosted"] = True

    # --- Bare Pokémon name fallback (if not already set) ---
    if not payload["pokemon_ids"]:
        # Sort by length descending so "dragonite" matches before "dragon"
        for name in sorted(POKEMON_NAME_TO_ID.keys(), key=len, reverse=True):
            pattern = r"\b" + re.escape(name) + r"\b"
            if re.search(pattern, lower):
                payload["pokemon_ids"] = [POKEMON_NAME_TO_ID[name]]
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
                            await interaction.followup.send(coords, ephemeral=True)
                        else:
                            await interaction.followup.send(
                                "⚠️ Coordinates not found.", ephemeral=True
                            )
                    elif resp.status == 401:
                        await interaction.followup.send(
                            "⚠️ Unauthorized — the API token may be invalid or expired.",
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
    """Components v2 LayoutView containing a container with up to 3 Pokémon sections."""

    def __init__(
        self,
        chunk: list[dict],
        bot: commands.Bot,
        token: str,
        timeout: float = 600.0,
    ):
        super().__init__(timeout=timeout)
        self.chunk = chunk
        self.bot = bot
        self.token = token

        container_children = []
        for i, item in enumerate(chunk):
            if i > 0:
                container_children.append(
                    ui.Separator(spacing=SeparatorSpacing.large)
                )
            btn = RevealButton(reveal_code=item.get("reveal_code"), token=token)
            sec_text = self.build_section_text(item, bot)
            section = ui.Section(
                ui.TextDisplay(sec_text),
                accessory=btn,
            )
            container_children.append(section)

        self.add_item(ui.Container(*container_children))

    @staticmethod
    def build_section_text(result: dict, bot: commands.Bot) -> str:
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
        iv_emoji = resolve_emoji(bot, "iv", "🧬")
        cp_emoji = resolve_emoji(bot, "cp", "CP")
        lvl_emoji = resolve_emoji(bot, "level", "L")
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

        return f"{line1}\n{line2}\n{line3}\n{line4}\n{line5}"


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class Pogo(commands.Cog):
    """Pokémon GO coordinate search via /pokesearch."""

    def __init__(self, client: commands.Bot):
        self.client = client
        self.token: str = os.environ.get("POGO_TOKEN", "")
        if not self.token:
            logger.warning(
                "[Pogo] POGO_TOKEN is not set in environment. "
                "/pokesearch will fail until it is configured."
            )

    @app_commands.command(
        name="pokesearch",
        description=(
            "Search for Pokémon GO spawns. "
            "E.g: shundo | snundo | hundo charizard | 0/15/15 53.07,-2.22 10km"
        ),
    )
    @app_commands.describe(
        query=(
            "Filters: shundo, snundo, hundo, nundo, shiny, pvp great/ultra/master, "
            "iv:90, 0/15/15, 53.07,-2.22, 10km, cp:500-1500, level:20-35, pokemon:<name>"
        )
    )
    async def pokesearch(self, interaction: discord.Interaction, query: str):
        if not self.token:
            await interaction.response.send_message(
                "⚠️ The API token is not configured. Please contact the bot owner.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        payload = parse_query(query)
        headers = {**_COMMON_HEADERS, "authorization": self.token}
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
                            "⚠️ Unauthorized — the API token may be invalid or expired.",
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
                f"Try broadening your filters."
            )
            return

        CHUNK_SIZE = 3
        chunks = [
            results[i : i + CHUNK_SIZE] for i in range(0, len(results), CHUNK_SIZE)
        ]

        # Send up to 5 messages (15 results max) to respect Discord rate limits
        for chunk in chunks[:5]:
            view = PogoLayoutView(chunk, bot=self.client, token=self.token)
            await interaction.followup.send(view=view)


async def setup(client: commands.Bot):
    await client.add_cog(Pogo(client))
