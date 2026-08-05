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
    Ephemeral roster viewer — shows the full team at once.

    Layout (per Pokémon, inside one Container)
    -------------------------------------------
    Section
      TextDisplay  — "{slot}. {Name} {G}\nLevel: `N`"
      accessory: Thumbnail (sprite, right-aligned)
    Separator       ← between entries, not after last
    ...
    """

    def __init__(self, author_id: int, roster: list, embed_color: int, timeout: float = 120.0):
        super().__init__(timeout=timeout)

        self.author_id = author_id
        self.roster = roster
        self.embed_color = embed_color

        self._build()

    # ------------------------------------------------------------------
    # Build  (called once — no interactive elements, no rebuilds needed)
    # ------------------------------------------------------------------

    def _build(self):
        self.clear_items()

        color = self.embed_color
        if isinstance(color, str) and color.startswith("#"):
            color = int(color.lstrip("#"), 16)

        if not self.roster:
            container = discord.ui.Container(
                discord.ui.TextDisplay("*No Pokémon on roster.*"),
                accent_color=color,
            )
            self.add_item(container)
            return

        sections: list = []
        for i, mon in enumerate(self.roster):
            name     = mon.get("name", "Unknown")
            nickname = mon.get("nickname", "")
            gender   = _gender_icon(mon.get("gender", ""))
            exp      = int(mon.get("totalexp", 0))
            level    = _level_from_exp(exp)
            slot     = mon.get("slot", i + 1)

            name_line = f"**{name}** {gender}"
            if nickname:
                name_line += f" *({nickname})*"

            text = f"**{slot}.** {name_line}\nLevel: `{level:,}`"

            safe        = _safe_name(name)
            sprite_url  = f"{HOST}/sprites/{safe}.png"

            sections.append(
                discord.ui.Section(
                    discord.ui.TextDisplay(text),
                    accessory=discord.ui.Thumbnail(media=sprite_url),
                )
            )

            # Separator between entries (not after the last one)
            if i < len(self.roster) - 1:
                sections.append(discord.ui.Separator(spacing=SeparatorSpacing.small))

        container = discord.ui.Container(*sections, accent_color=color)
        self.add_item(container)


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
