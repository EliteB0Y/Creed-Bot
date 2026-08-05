import discord
from discord import SeparatorSpacing


HOST = "https://pokemoncreed.net"


def _level_from_exp(exp: int) -> int:
    """Derive Pokémon level from total XP (same formula as the game)."""
    return round(exp ** (1 / 3))


def _safe_name(name: str) -> str:
    """Sanitise a Pokémon name for use in image URLs."""
    return name.replace(".", "").replace(" ", "%20")


def _gender_icon(gender: str) -> str:
    if gender == "M":
        return "♂"
    if gender == "F":
        return "♀"
    return "G"  # genderless / unknown


# ──────────────────────────────────────────────────────────────────────────────
# Roster View  (ephemeral, shown when "Show Team" is clicked)
# ──────────────────────────────────────────────────────────────────────────────

class RosterView(discord.ui.LayoutView):
    """
    Ephemeral paginated roster viewer.

    Layout
    ------
    Container
      TextDisplay  — team header + Pokémon name / nickname / level / XP / moves
      MediaGallery — Pokémon sprite
      Separator
      ActionRow    — ◀ ▶
    """

    def __init__(self, author_id: int, roster: list, embed_color: int, timeout: float = 120.0):
        super().__init__(timeout=timeout)

        self.author_id = author_id
        self.roster = roster
        self.embed_color = embed_color
        self.pg = 0

        self._build()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _current_mon(self) -> dict:
        return self.roster[self.pg] if self.roster else {}

    def _sprite_url(self) -> str:
        if not self.roster:
            return f"{HOST}/img/icon/Missingno.gif"
        safe = _safe_name(self._current_mon().get("name", "Missingno"))
        return f"{HOST}/sprites/{safe}.png"

    def _roster_text(self) -> str:
        if not self.roster:
            return "**Team:** *No Pokémon on roster.*"

        mon      = self._current_mon()
        name     = mon.get("name", "Unknown")
        nickname = mon.get("nickname", "")
        gender   = _gender_icon(mon.get("gender", ""))
        exp      = int(mon.get("totalexp", 0))
        level    = _level_from_exp(exp)
        slot     = mon.get("slot", self.pg + 1)
        total    = len(self.roster)

        moves     = [mon.get(f"move{i}", "") for i in range(1, 5) if mon.get(f"move{i}")]
        moves_str = " / ".join(moves) if moves else "—"

        header   = f"-# **Team**  •  Slot {slot} of {total}"
        mon_line = f"### **{name}** {gender}"
        if nickname:
            mon_line += f" *({nickname})*"
        return (
            f"{header}\n{mon_line}\n"
            f"**Level: `{level:,}`**  •  **XP: `{exp:,}`**\n"
            f"-# **Moves:** {moves_str}"
        )

    def _update_nav_buttons(self):
        has_many = len(self.roster) > 1
        self.btn_prev.disabled = not has_many or self.pg == 0
        self.btn_next.disabled = not has_many or self.pg == len(self.roster) - 1

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self):
        self.clear_items()

        color = self.embed_color
        if isinstance(color, str) and color.startswith("#"):
            color = int(color.lstrip("#"), 16)

        self.btn_prev = discord.ui.Button(
            emoji="◀️", style=discord.ButtonStyle.primary, custom_id="roster_prev"
        )
        self.btn_next = discord.ui.Button(
            emoji="▶️", style=discord.ButtonStyle.primary, custom_id="roster_next"
        )
        self._update_nav_buttons()
        self.btn_prev.callback = self._on_prev
        self.btn_next.callback = self._on_next

        nav_row = discord.ui.ActionRow(self.btn_prev, self.btn_next)

        container = discord.ui.Container(
            discord.ui.TextDisplay(self._roster_text()),
            discord.ui.MediaGallery(
                discord.MediaGalleryItem(media=self._sprite_url()),
            ),
            discord.ui.Separator(spacing=SeparatorSpacing.small),
            nav_row,
            accent_color=color,
        )

        self.add_item(container)

    # ------------------------------------------------------------------
    # Interaction guard
    # ------------------------------------------------------------------

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This isn't your team view.", ephemeral=True
            )
            return False
        return True

    # ------------------------------------------------------------------
    # Button callbacks
    # ------------------------------------------------------------------

    async def _on_prev(self, interaction: discord.Interaction):
        self.pg = max(0, self.pg - 1)
        self._build()
        await interaction.response.edit_message(view=self)

    async def _on_next(self, interaction: discord.Interaction):
        self.pg = min(len(self.roster) - 1, self.pg + 1)
        self._build()
        await interaction.response.edit_message(view=self)


# ──────────────────────────────────────────────────────────────────────────────
# Profile View  (main message — shows stats + box rating + "Show Team" button)
# ──────────────────────────────────────────────────────────────────────────────

class ProfileView(discord.ui.LayoutView):
    """
    Displays a Pokemon Creed user profile using Discord Components V2.

    Layout
    ------
    Container (accent = embed_color)
      TextDisplay  — header: username - #id  (hyperlink to profile)
      Separator
      Section      — trainer stats (Last Seen / Level / Coins / Cash)
                     accessory: Thumbnail (user avatar)
      Separator
      TextDisplay  — Box Rating (subtext) + Details link
      Separator
      ActionRow    — [Show Team]
    """

    def __init__(
        self,
        author_id: int,
        username: str,
        user_id: str,
        trainer_level: str,
        coins: str,
        cash: str,
        last_active: str,
        avatar: str,
        roster: list,
        box_rating: dict,
        embed_color: int = 0x2B2D31,
        timeout: float = 120.0,
    ):
        super().__init__(timeout=timeout)

        self.author_id = author_id
        self.username = username
        self.user_id = user_id
        self.trainer_level = trainer_level
        self.coins = coins
        self.cash = cash
        self.last_active = last_active
        self.avatar = avatar
        self.roster = roster
        self.box_rating = box_rating
        self.embed_color = embed_color
        self.message = None

        self._build()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _profile_url(self) -> str:
        return f"{HOST}/prof.php?user={self.username.replace(' ', '%20')}"

    def _avatar_url(self) -> str:
        return f"{HOST}/img/avatars/{self.avatar}.png"

    def _box_rating_text(self) -> str:
        if self.box_rating.get("error"):
            return "-# **Box Rating: `N/A`**"
        rating = self.box_rating.get("total_rating_formatted", "N/A")
        paste  = self.box_rating.get("paste_url", "")
        return f"-# **Box Rating: `{rating}`**\n-# **[Details Here]({paste})**"

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self):
        self.clear_items()

        color = self.embed_color
        if isinstance(color, str) and color.startswith("#"):
            color = int(color.lstrip("#"), 16)

        header_text = f"## [{self.username} - #{self.user_id}]({self._profile_url()})"

        stats_text = (
            f"**Last Seen:** <t:{self.last_active}:R>\n"
            f"**Trainer Level:** `{self.trainer_level}`\n"
            f"**Coins:** `{self.coins}`\n"
            f"**Cash:** `{self.cash}`"
        )

        self.btn_show_team = discord.ui.Button(
            label="Show Team",
            style=discord.ButtonStyle.primary,
            emoji="🔥",
            custom_id="profile_show_team",
            disabled=not bool(self.roster),
        )
        self.btn_show_team.callback = self._on_show_team

        container = discord.ui.Container(
            discord.ui.TextDisplay(header_text),
            discord.ui.Separator(spacing=SeparatorSpacing.small),
            discord.ui.Section(
                discord.ui.TextDisplay(stats_text),
                accessory=discord.ui.Thumbnail(media=self._avatar_url()),
            ),
            discord.ui.Separator(spacing=SeparatorSpacing.small),
            discord.ui.TextDisplay(self._box_rating_text()),
            discord.ui.Separator(spacing=SeparatorSpacing.small),
            discord.ui.ActionRow(self.btn_show_team),
            accent_color=color,
        )

        self.add_item(container)

    # ------------------------------------------------------------------
    # Interaction guard
    # ------------------------------------------------------------------

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "You cannot control this profile view.", ephemeral=True
            )
            return False
        return True

    # ------------------------------------------------------------------
    # Timeout
    # ------------------------------------------------------------------

    async def on_timeout(self):
        if self.message:
            try:
                self._build()
                self.btn_show_team.disabled = True
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    # ------------------------------------------------------------------
    # Button callbacks
    # ------------------------------------------------------------------

    async def _on_show_team(self, interaction: discord.Interaction):
        roster_view = RosterView(
            author_id=self.author_id,
            roster=self.roster,
            embed_color=self.embed_color,
        )
        await interaction.response.send_message(view=roster_view, ephemeral=True)
