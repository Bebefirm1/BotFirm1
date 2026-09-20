
import re
import os
import json
import time
import random
import asyncio
import datetime
import logging
import traceback

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)

try:
    from keep_alive import keep_alive
    KEEP_ALIVE_AVAILABLE = True
except ImportError:
    KEEP_ALIVE_AVAILABLE = False

load_dotenv()
token = os.getenv("Token_bot")

COLOR_PRIMARY = 0x5865F2
COLOR_SUCCESS = 0x57F287
COLOR_WARNING = 0xFEE75C
COLOR_ERROR   = 0xED4245
COLOR_INFO    = 0x00B0FF

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot  = commands.Bot(command_prefix="/", intents=intents)
tree = bot.tree

open_tickets: dict[int, dict] = {}
spam_tracker: dict[int, dict[int, list]] = {}

SPAM_LIMIT_DEFAULT  = 5
SPAM_WINDOW_DEFAULT = 5
SPAM_MUTE_DEFAULT   = 5

TICKET_CATEGORY_NAME = "🎫 Tickets"
OWNER_ID = 1338467533392576612
BOT_LABEL = "Bot Discord"
TICKET_DEFAULTS = {
    "panel_title": "🎫 Support",
    "panel_description": "Besoin d'aide ? Ouvrez un ticket et l'équipe vous répondra en privé.",
    "panel_color": COLOR_PRIMARY,
    "panel_image_url": "",
    "panel_image_uploaded": False,
    "ticket_image_url": "",
    "ticket_image_uploaded": False,
    "open_button_label": "🎫 Ouvrir un ticket",
    "info_button_label": "📖 Informations",
    "info_message": "Un seul ticket peut être ouvert à la fois. Choisissez la bonne catégorie et décrivez votre demande.",
    "panel_step_one": "",
    "panel_step_two": "",
    "panel_rules": "",
    "panel_staff_title": "",
    "ticket_open_title": "🎫 Votre ticket",
    "close_button_label": "🔒 Fermer le ticket",
    "ticket_prefix": "ticket",
    "default_category_name": TICKET_CATEGORY_NAME,
    "welcome_message": "Bienvenue {user} !\n\n> {reason}\n\nLe staff vous répondra dès que possible.",
    "close_delay": 5,
}

def firm1_embed(
    title: str,
    description: str = "",
    color: int = COLOR_PRIMARY,
    footer: str | None = None,
    thumbnail: str | None = None,
    fields: list[tuple[str, str, bool]] | None = None,
) -> discord.Embed:
    embed = bot_embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )
    embed.set_footer(text=footer or BOT_LABEL)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
    return embed


def bot_embed(*args, **kwargs) -> discord.Embed:
    """Habillage visuel commun à tous les panneaux du bot."""
    embed = discord.Embed(*args, **kwargs)
    embed.set_author(name=BOT_LABEL)
    embed.set_footer(text="Nadouja · Mitteg · Not Feller")
    return embed

CONFIG_FILE = "ticket_config.json"

def _load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def _save_config(data: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_guild_config(guild_id: int) -> dict:
    cfg = _load_config()
    return cfg.get(str(guild_id), {})

def set_guild_config(guild_id: int, key: str, value):
    cfg = _load_config()
    gid = str(guild_id)
    if gid not in cfg:
        cfg[gid] = {}
    cfg[gid][key] = value
    _save_config(cfg)

def get_ticket_settings(guild_id: int) -> dict:
    return TICKET_DEFAULTS | get_guild_config(guild_id).get("ticket_settings", {})

def contains_banned_word(content: str, words: list[str]) -> bool:
    """Détecte les mots entiers : `con` ne correspond pas à `compliqué`."""
    normalized = content.casefold()
    return any(re.search(r"(?<!\w)" + re.escape(word.casefold()) + r"(?!\w)", normalized) for word in words)

async def send_mod_log(guild: discord.Guild, **kwargs):
    cfg     = get_guild_config(guild.id)
    log_id  = cfg.get("mod_log_channel_id")
    if not log_id:
        return
    channel = guild.get_channel(log_id)
    if not channel:
        return
    embed = bot_embed(
        title=kwargs.get("title", "Action de modération"),
        color=kwargs.get("color", COLOR_WARNING),
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )
    for name, value, inline in kwargs.get("fields", []):
        embed.add_field(name=name, value=value, inline=inline)
    embed.set_footer(text="Nadouja · Mitteg · Not Feller")
    try:
        await channel.send(embed=embed)
    except Exception:
        pass

def parse_duration(duration: str) -> int | None:
    match = re.fullmatch(r"(\d+)(s|m|h|j)", duration.lower())
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2)
    return value * {"s": 1, "m": 60, "h": 3600, "j": 86400}[unit]

def get_warns(guild_id: int, user_id: int) -> list:
    return get_guild_config(guild_id).get("warns", {}).get(str(user_id), [])

def add_warn(guild_id: int, user_id: int, raison: str, moderator: str) -> int:
    cfg   = get_guild_config(guild_id)
    warns = cfg.get("warns", {})
    uid   = str(user_id)
    if uid not in warns:
        warns[uid] = []
    warns[uid].append({"raison": raison, "by": moderator, "at": datetime.datetime.now(datetime.timezone.utc).isoformat()})
    set_guild_config(guild_id, "warns", warns)
    return len(warns[uid])

@bot.event
async def on_ready():
    print(f"✅ Bot connecté : {bot.user} (ID: {bot.user.id})")
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching, name="Nadouja & Mitteg & Not Feller"
    ))
    try:
        await tree.sync()
        print("✅ Sync global effectué.")
    except Exception as e:
        print(f"⚠️ Sync global échoué : {e}")
    for guild in bot.guilds:
        try:
            await tree.sync(guild=guild)
            print(f"✅ Commandes sync sur : {guild.name}")
        except Exception as e:
            print(f"⚠️ Sync échoué {guild.name} : {e}")

@bot.event
async def on_guild_join(guild: discord.Guild):
    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            await channel.send(embed=firm1_embed(
                "Le bot est opérationnel !",
                "Utilisez `/help` pour voir les commandes. Utilisez `/pokemon` pour configurer les rôles du classement.",
                color=COLOR_SUCCESS,
            ))
            break

@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        embed = firm1_embed("Permission refusée", "Vous n'avez pas les permissions nécessaires.", color=COLOR_ERROR)
    elif isinstance(error, app_commands.CommandOnCooldown):
        embed = firm1_embed("Cooldown", f"Attendez encore **{error.retry_after:.1f}s**.", color=COLOR_WARNING)
    else:
        embed = firm1_embed("Erreur inattendue", f"```{str(error)[:200]}```", color=COLOR_ERROR)
    try:
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except discord.InteractionResponded:
        await interaction.followup.send(embed=embed, ephemeral=True)

@tree.command(name="help", description="Affiche l'aide complète de Bot Discord")
async def help_cmd(interaction: discord.Interaction):
    page1 = bot_embed(title="🎫 Tickets — Page 1/5", description="Système de tickets de support.", color=COLOR_PRIMARY)
    page1.add_field(name="📩 Membres", value=("`/ticket` — Ouvrir un ticket\n`/fermer` — Fermer votre ticket\n`/ajouter @user` — Ajouter un membre\n`/retirer @user` — Retirer un membre"), inline=False)
    page1.add_field(name="⚙️ Administration", value=("`/panel-tickets` — Envoyer le panel\n`/config-tickets` — Voir la configuration\n`/set-log-tickets` — Salon de logs\n`/ajouter-role-ticket` — Ajouter rôle ping\n`/retirer-role-ticket` — Retirer rôle ping\n`/ajouter-categorie-ticket` — Ajouter catégorie\n`/retirer-categorie-ticket` — Retirer catégorie\n`/reset-config-tickets` — Réinitialiser"), inline=False)
    page1.set_footer(text="Nadouja · Mitteg · Not Feller")
    page2 = bot_embed(title="🔨 Modération — Page 2/5", description="Commandes de modération manuelle.", color=COLOR_ERROR)
    page2.add_field(name="👮 Sanctions", value=("`/ban @user` — Bannir un membre\n`/kick @user` — Expulser un membre\n`/mute @user durée` — Mute (10s, 5m, 2h, 1j)\n`/unmute @user` — Retirer le mute\n`/warn @user raison` — Avertir\n`/warns @user` — Voir les avertissements\n`/clear 1-100` — Supprimer des messages\n`/set-log-mod` — Salon de logs mod"), inline=False)
    page2.set_footer(text="Nadouja · Mitteg · Not Feller")
    page3 = bot_embed(title="🤖 Auto-Modération — Page 3/5", description="Modération automatique configurable.", color=COLOR_WARNING)
    page3.add_field(name="⚙️ Configuration", value=("`/config-auto-mod` — Ouvrir les réglages interactifs\nMots interdits • Antispam • Liens • Images"), inline=False)
    page3.add_field(name="🚨 Automatique", value=("Mots interdits → suppression + MP\nLiens → suppression par salon\nImages → suppression par salon\nAntispam → mute automatique"), inline=False)
    page3.set_footer(text="Nadouja · Mitteg · Not Feller")
    page4 = bot_embed(title="🛡️ Whitelist & Blacklist — Page 4/5", description="Gestion des accès membres.", color=COLOR_INFO)
    page4.add_field(name="✅ Whitelist — bypass auto-mod", value=("`/whitelist-ajouter @user` — Ajouter\n`/whitelist-retirer @user` — Retirer\n`/whitelist-liste` — Voir la liste"), inline=False)
    page4.add_field(name="⛔ Blacklist — expulsion automatique", value=("`/blacklist-ajouter @user` — Blacklister\n`/blacklist-retirer @user` — Retirer\n`/blacklist-liste` — Voir la liste"), inline=False)
    page4.set_footer(text="Nadouja · Mitteg · Not Feller")
    page5 = bot_embed(title="🎮 Mini-Jeux & Utilitaires — Page 5/5", description="Jeux et outils divers.", color=COLOR_SUCCESS)
    page5.add_field(name="🎮 Mini-Jeux", value=("`/pile-ou-face` — Lancer une pièce\n`/dé` — Lancer un dé\n`/rps` — Pierre-Papier-Ciseaux\n`/nombre` — Deviner un nombre\n`/8ball` — Boule magique\n`/trivia` — Culture générale\n`/pokemon` — Quel est ce Pokémon ?\n`/pokemon-score` — Classement des dresseurs"), inline=False)
    page5.add_field(name="🛠️ Utilitaires", value=("`/ping` — Latence du bot\n`/info-serveur` — Infos serveur\n`/info-user` — Infos membre\n`/avatar` — Avatar\n`/say` — Parler à la place du bot\n`/renommer-bot` — Changer le pseudo\n`/help` — Cette aide"), inline=False)
    page5.set_footer(text="Nadouja · Mitteg · Not Feller")
    pages = [page1, page2, page3, page4, page5]

    class HelpView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=120)
            self.page = 0
            self.prev_btn.disabled = True
            self.page_btn.label = "1 / 5"
        def update_buttons(self):
            self.prev_btn.disabled = (self.page == 0)
            self.next_btn.disabled = (self.page == len(pages) - 1)
            self.page_btn.label = f"{self.page + 1} / {len(pages)}"
        @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
        async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=pages[self.page], view=self)
        @discord.ui.button(label="1 / 5", style=discord.ButtonStyle.primary, disabled=True)
        async def page_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.defer()
        @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
        async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=pages[self.page], view=self)

    view = HelpView()
    await interaction.response.send_message(embed=pages[0], view=view, ephemeral=True)


@tree.command(name="ping", description="Affiche la latence du bot")
async def ping_cmd(interaction: discord.Interaction):
    lat    = round(bot.latency * 1000)
    color  = COLOR_SUCCESS if lat < 100 else (COLOR_WARNING if lat < 200 else COLOR_ERROR)
    status = "🟢 Excellent" if lat < 100 else ("🟡 Correct" if lat < 200 else "🔴 Élevé")
    embed = bot_embed(
        title="🏓 Pong",
        description="Connexion au serveur Discord vérifiée.",
        color=color,
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )
    embed.add_field(name="Latence", value=f"`{lat} ms`", inline=True)
    embed.add_field(name="État", value=status, inline=True)
    await interaction.response.send_message(embed=embed)

@tree.command(name="info-serveur", description="Informations sur le serveur")
async def server_info(interaction: discord.Interaction):
    g = interaction.guild
    await interaction.response.send_message(embed=firm1_embed(f"Serveur — {g.name}", g.description or "Aucune description.", color=COLOR_INFO, thumbnail=g.icon.url if g.icon else None, fields=[("👑 Propriétaire", str(g.owner), True), ("👥 Membres", str(g.member_count), True), ("📁 Salons", str(len(g.channels)), True), ("🎭 Rôles", str(len(g.roles)), True), ("🔒 Vérification", str(g.verification_level).title(), True), ("📅 Créé le", f"<t:{int(g.created_at.timestamp())}:D>", True)]))

@tree.command(name="info-user", description="Informations sur un utilisateur")
@app_commands.describe(membre="L'utilisateur à inspecter (optionnel)")
async def user_info(interaction: discord.Interaction, membre: discord.Member | None = None):
    m     = membre or interaction.user
    roles = [r.mention for r in m.roles if r.name != "@everyone"]
    await interaction.response.send_message(embed=firm1_embed(f"Utilisateur — {m.display_name}", f"**Tag :** {m}\n**ID :** `{m.id}`", color=COLOR_INFO, thumbnail=m.display_avatar.url, fields=[("📅 Compte créé", f"<t:{int(m.created_at.timestamp())}:D>", True), ("📥 A rejoint le", f"<t:{int(m.joined_at.timestamp())}:D>", True), ("🎭 Rôles", " ".join(roles) if roles else "Aucun", False)]))

@tree.command(name="avatar", description="Affiche l'avatar d'un utilisateur")
@app_commands.describe(membre="L'utilisateur (optionnel)")
async def avatar_cmd(interaction: discord.Interaction, membre: discord.Member | None = None):
    m     = membre or interaction.user
    embed = firm1_embed(f"Avatar de {m.display_name}", f"[Ouvrir en plein écran]({m.display_avatar.url})", color=COLOR_INFO)
    embed.set_image(url=m.display_avatar.url)
    await interaction.response.send_message(embed=embed)

@tree.command(name="say", description="[Admin] Envoie un texte ou une image avec le bot")
@app_commands.describe(message="Texte à envoyer (optionnel)", salon="Salon cible (optionnel)", image="Image à joindre (optionnel)")
@app_commands.checks.has_permissions(administrator=True)
async def say_cmd(interaction: discord.Interaction, message: str = "", salon: discord.TextChannel | None = None, image: discord.Attachment | None = None):
    if not message.strip() and image is None:
        await interaction.response.send_message(embed=firm1_embed("Contenu manquant", "Ajoutez un message, une image, ou les deux.", color=COLOR_ERROR), ephemeral=True)
        return
    if image and image.content_type and not image.content_type.startswith("image/"):
        await interaction.response.send_message(embed=firm1_embed("Fichier invalide", "Le fichier joint doit être une image.", color=COLOR_ERROR), ephemeral=True)
        return
    target = salon or interaction.channel
    await interaction.response.defer(ephemeral=True)
    try:
        file = await image.to_file() if image else None
        await target.send(content=message or None, file=file)
        await interaction.followup.send(embed=firm1_embed("✅ Message envoyé", f"Envoyé dans {target.mention}.", color=COLOR_SUCCESS), ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send(embed=firm1_embed("Erreur", f"Pas la permission d'envoyer dans {target.mention}.", color=COLOR_ERROR), ephemeral=True)


@tree.command(name="renommer-bot", description="[Admin] Change le pseudo du bot sur ce serveur")
@app_commands.describe(nom="Nouveau pseudo (max 32 caractères)")
@app_commands.checks.has_permissions(administrator=True)
async def rename_bot(interaction: discord.Interaction, nom: str):
    if len(nom) > 32:
        await interaction.response.send_message(embed=firm1_embed("Erreur", "Max **32 caractères**.", color=COLOR_ERROR), ephemeral=True)
        return
    try:
        await interaction.guild.me.edit(nick=nom)
        await interaction.response.send_message(embed=firm1_embed("✅ Pseudo mis à jour", f"Le bot s'appelle désormais **{nom}** sur ce serveur.", color=COLOR_SUCCESS, fields=[("⚠️ Limite", "Max 2 changements par heure.", False)]), ephemeral=True)
    except discord.HTTPException as e:
        msg = "Trop de changements. Réessayez dans **1 heure**." if e.status == 429 else f"`{e}`"
        await interaction.response.send_message(embed=firm1_embed("Erreur", msg, color=COLOR_WARNING), ephemeral=True)



@tree.command(name="mp", description="[Propriétaire] Envoie un message privé à un utilisateur")
@app_commands.describe(membre="Destinataire", message="Message à envoyer")
async def owner_mp(interaction: discord.Interaction, membre: discord.User, message: str):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message(embed=firm1_embed("Accès refusé", "Cette commande est réservée au propriétaire du bot.", color=COLOR_ERROR), ephemeral=True)
        return
    try:
        await membre.send(message)
    except discord.Forbidden:
        await interaction.response.send_message(embed=firm1_embed("MP impossible", f"{membre.mention} bloque les messages privés.", color=COLOR_ERROR), ephemeral=True)
        return
    recap = firm1_embed("✅ Message privé envoyé", f"**Conversation :** {membre} (`{membre.id}`)\n**Message :** {message[:1500]}", color=COLOR_SUCCESS)
    try:
        await interaction.user.send(embed=recap)
    except discord.Forbidden:
        pass
    await interaction.response.send_message(embed=firm1_embed("Message envoyé", "Un récapitulatif vous a été envoyé en MP.", color=COLOR_SUCCESS), ephemeral=True)

# ═══════════════════════════════════════════════════════════
#  SYSTÈME DE TICKETS
# ═══════════════════════════════════════════════════════════

class TicketReasonModal(discord.ui.Modal, title="📋 Ouvrir un ticket"):
    raison = discord.ui.TextInput(label="Raison de votre demande", placeholder="Décrivez brièvement votre problème...", style=discord.TextStyle.paragraph, max_length=300, required=True)
    def __init__(self, categorie_label: str, category_id: int | None, ticket_type: str | None = None):
        super().__init__(title=f"📋 Ticket — {categorie_label}"[:45])
        self.categorie_label = categorie_label
        self.category_id     = category_id
        self.ticket_type = ticket_type
    async def on_submit(self, interaction: discord.Interaction):
        await _creer_ticket(interaction, raison=f"[{self.categorie_label}] {self.raison.value}", category_id=self.category_id, ticket_type=self.ticket_type)

class TicketCategorySelect(discord.ui.Select):
    def __init__(self, categories: list[dict], raison: str | None = None):
        self.raison = raison
        options = [discord.SelectOption(label=c["label"], description=c.get("description", "")[:100], emoji=c.get("emoji", "🎫"), value=str(i)) for i, c in enumerate(categories)]
        super().__init__(placeholder="Choisissez un type de ticket...", min_values=1, max_values=1, options=options, custom_id="ticket_category_select")
        self.categories = categories
    async def callback(self, interaction: discord.Interaction):
        cat = self.categories[int(self.values[0])]
        modal = TicketReasonModal(categorie_label=cat["label"], category_id=cat.get("discord_category_id"), ticket_type=cat["label"])
        if self.raison is not None:
            modal.raison.default = self.raison[:300]
        await interaction.response.send_modal(modal)

class TicketCategoryView(discord.ui.View):
    def __init__(self, categories: list[dict], raison: str | None = None):
        super().__init__(timeout=60)
        self.add_item(TicketCategorySelect(categories, raison))

class TicketCloseConfirmView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)
    @discord.ui.button(label="✅ Confirmer la fermeture", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _fermer_ticket(interaction)
    @discord.ui.button(label="❌ Annuler", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=firm1_embed("Fermeture annulée", "Le ticket reste ouvert.", color=COLOR_SUCCESS), ephemeral=True)
        self.stop()

class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="🔒 Fermer le ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=firm1_embed("Confirmation", "Êtes-vous sûr de vouloir fermer ce ticket ?", color=COLOR_WARNING), view=TicketCloseConfirmView(), ephemeral=True)
    @discord.ui.button(label="📌 Revendiquer", style=discord.ButtonStyle.success, custom_id="claim_ticket")
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg      = get_guild_config(interaction.guild.id)
        ticket = next((t for t in open_tickets.values() if t["channel_id"] == interaction.channel.id), {})
        ping_ids = ticket.get("ping_roles", cfg.get("ping_roles", []))
        is_staff = (interaction.user.guild_permissions.administrator or any(r.id in ping_ids for r in interaction.user.roles))
        if not is_staff:
            await interaction.response.send_message(embed=firm1_embed("Accès refusé", "Seul le staff peut revendiquer un ticket.", color=COLOR_ERROR), ephemeral=True)
            return
        button.disabled = True
        button.label    = f"📌 {interaction.user.display_name}"
        await interaction.message.edit(view=self)
        await interaction.response.send_message(embed=firm1_embed("Ticket revendiqué 📌", f"Ce ticket est géré par {interaction.user.mention}.", color=COLOR_SUCCESS))

class TicketOpenView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="🎫 Ouvrir un ticket", style=discord.ButtonStyle.primary, custom_id="open_ticket_btn")
    async def open_ticket_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg        = get_guild_config(interaction.guild.id)
        categories = cfg.get("ticket_categories", [])
        if not categories:
            await interaction.response.send_modal(TicketReasonModal(categorie_label="Support général", category_id=None))
        else:
            await interaction.response.send_message(embed=firm1_embed("Type de ticket", "Sélectionnez le type correspondant à votre demande.", color=COLOR_INFO), view=TicketCategoryView(categories), ephemeral=True)
    @discord.ui.button(label="📖 Comment ça marche ?", style=discord.ButtonStyle.secondary, custom_id="ticket_info_btn")
    async def info_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = get_ticket_settings(interaction.guild.id)
        await interaction.response.send_message(embed=firm1_embed(settings["info_button_label"], settings["info_message"], color=COLOR_INFO), ephemeral=True)

async def _creer_ticket(interaction: discord.Interaction, raison: str = "Non spécifiée", category_id: int | None = None, ticket_type: str | None = None):
    guild, user = interaction.guild, interaction.user
    cfg         = get_guild_config(guild.id)
    if user.id in open_tickets:
        ch = guild.get_channel(open_tickets[user.id]["channel_id"])
        if ch:
            await interaction.response.send_message(embed=firm1_embed("Ticket déjà ouvert", f"Vous avez déjà un ticket ouvert : {ch.mention}", color=COLOR_WARNING), ephemeral=True)
            return
    route = None
    if ticket_type is not None:
        route = next((c for c in cfg.get("ticket_categories", []) if c["label"] == ticket_type), None)
        if route is None:
            await interaction.response.send_message("Ce type de ticket n'existe plus. Rouvrez le panel.", ephemeral=True)
            return
        category_id = route.get("discord_category_id")
    settings = get_ticket_settings(guild.id)
    category = guild.get_channel(category_id) if category_id else guild.get_channel(settings.get("default_category_id"))
    if (category_id or settings.get("default_category_id")) and not isinstance(category, discord.CategoryChannel):
        await interaction.response.send_message("La catégorie Discord configurée est introuvable. Demandez au staff de la corriger dans /config-tickets.", ephemeral=True)
        return
    if not category:
        category = discord.utils.get(guild.categories, name=settings["default_category_name"])
    await interaction.response.defer(ephemeral=True)
    if not category:
        category = await guild.create_category(settings["default_category_name"])
    ping_role_ids: list = route.get("ping_roles", cfg.get("ping_roles", [])) if route is not None else cfg.get("ping_roles", [])
    ping_mentions: list[str] = []
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        user:               discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me:           discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
    }
    for rid in ping_role_ids:
        role = guild.get_role(rid)
        if role and not role.is_default():
            overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            ping_mentions.append(role.mention)
    channel = await category.create_text_channel(f"{settings['ticket_prefix']}-{user.name.lower().replace(' ', '-')}", overwrites=overwrites)
    open_tickets[user.id] = {"channel_id": channel.id, "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "reason": raison, "ping_roles": list(ping_role_ids), "ticket_type": ticket_type}
    embed = discord.Embed(
        title=(route or {}).get("ticket_open_title", settings["ticket_open_title"]),
        description=(route or {}).get("welcome_message", settings["welcome_message"]).replace("{user}", user.mention).replace("{reason}", raison),
        color=COLOR_SUCCESS,
    )
    close_view = TicketCloseView()
    close_view.children[0].label = settings["close_button_label"]
    banner = route.get("banner_storage", "") if route is not None else ""
    settings = settings | {"ticket_image_uploaded": bool(banner), "ticket_image_url": "", "ticket_image_storage": banner}
    await send_ticket_embed(channel, guild.id, "ticket", settings, embed, content=f"{user.mention} {' '.join(ping_mentions)}".strip(), view=close_view)
    await interaction.followup.send(embed=firm1_embed("Ticket créé !", f"Votre ticket est disponible ici : {channel.mention}", color=COLOR_SUCCESS), ephemeral=True)
    log_ch = guild.get_channel(cfg.get("log_channel_id")) if cfg.get("log_channel_id") else None
    if log_ch:
        await log_ch.send(embed=firm1_embed("📥 Nouveau ticket ouvert", f"**Canal :** {channel.mention}\n**Raison :** {raison}", color=COLOR_INFO, fields=[("👤 Utilisateur", f"{user} (`{user.id}`)", True), ("🔔 Rôles notifiés", " ".join(ping_mentions) if ping_mentions else "Aucun", True)]))

async def _fermer_ticket(interaction: discord.Interaction):
    channel, guild = interaction.channel, interaction.guild
    cfg     = get_guild_config(guild.id)
    user_id = next((uid for uid, d in open_tickets.items() if d["channel_id"] == channel.id), None)
    if user_id is None:
        await interaction.response.send_message(embed=firm1_embed("Erreur", "Ce salon n'est pas un ticket.", color=COLOR_ERROR), ephemeral=True)
        return
    await interaction.response.send_message(embed=firm1_embed("Ticket en cours de fermeture...", "Ce salon sera supprimé dans **5 secondes**.", color=COLOR_WARNING))
    log_ch = guild.get_channel(cfg.get("log_channel_id")) if cfg.get("log_channel_id") else None
    if log_ch:
        opener = guild.get_member(user_id)
        await log_ch.send(embed=firm1_embed("📤 Ticket fermé", f"**Canal :** #{channel.name}\n**Fermé par :** {interaction.user.mention}", color=COLOR_ERROR, fields=[("👤 Demandeur initial", str(opener) if opener else f"ID {user_id}", True)]))
    del open_tickets[user_id]
    await asyncio.sleep(get_ticket_settings(guild.id)["close_delay"])
    await channel.delete(reason=f"Ticket fermé par {interaction.user}")

@tree.command(name="ticket", description="Ouvre un ticket de support")
@app_commands.describe(raison="La raison de votre demande")
async def ticket_cmd(interaction: discord.Interaction, raison: str = "Non spécifiée", type_ticket: str | None = None):
    categories = get_guild_config(interaction.guild.id).get("ticket_categories", [])
    if categories and type_ticket is None:
        await interaction.response.send_message("Choisissez un type de ticket, puis précisez votre demande.", view=TicketCategoryView(categories, raison if raison != "Non spécifiée" else None), ephemeral=True)
        return
    await _creer_ticket(interaction, raison, ticket_type=type_ticket)

@ticket_cmd.autocomplete("type_ticket")
async def ticket_type_autocomplete(interaction: discord.Interaction, current: str):
    categories = get_guild_config(interaction.guild.id).get("ticket_categories", [])
    return [app_commands.Choice(name=c["label"][:100], value=c["label"][:100]) for c in categories if current.casefold() in c["label"].casefold()][:25]

@tree.command(name="fermer", description="Ferme votre ticket de support")
async def fermer_cmd(interaction: discord.Interaction):
    await _fermer_ticket(interaction)

@tree.command(name="ajouter", description="Ajoute un utilisateur au ticket actuel")
@app_commands.describe(membre="L'utilisateur à ajouter")
async def ajouter_cmd(interaction: discord.Interaction, membre: discord.Member):
    if not any(d["channel_id"] == interaction.channel.id for d in open_tickets.values()):
        await interaction.response.send_message(embed=firm1_embed("Erreur", "Utilisez cette commande dans un ticket.", color=COLOR_ERROR), ephemeral=True)
        return
    await interaction.channel.set_permissions(membre, read_messages=True, send_messages=True)
    await interaction.response.send_message(embed=firm1_embed("Utilisateur ajouté", f"{membre.mention} a été ajouté.", color=COLOR_SUCCESS))

@tree.command(name="retirer", description="Retire un utilisateur du ticket actuel")
@app_commands.describe(membre="L'utilisateur à retirer")
async def retirer_cmd(interaction: discord.Interaction, membre: discord.Member):
    if not any(d["channel_id"] == interaction.channel.id for d in open_tickets.values()):
        await interaction.response.send_message(embed=firm1_embed("Erreur", "Utilisez cette commande dans un ticket.", color=COLOR_ERROR), ephemeral=True)
        return
    await interaction.channel.set_permissions(membre, overwrite=None)
    await interaction.response.send_message(embed=firm1_embed("Utilisateur retiré", f"{membre.mention} a été retiré.", color=COLOR_WARNING))





def ticket_emoji_value(value: str, guild: discord.Guild) -> str:
    value = value.strip() or "🎫"
    if re.fullmatch(r"<a?:[A-Za-z0-9_]{2,32}:\d{15,22}>", value):
        return str(discord.PartialEmoji.from_str(value))
    if value.isdecimal() or re.fullmatch(r":[A-Za-z0-9_]{2,32}:", value):
        emoji = next((e for e in guild.emojis if str(e.id) == value or e.name == value.strip(":")), None)
        if emoji is not None:
            return str(emoji)
        raise ValueError("Emoji introuvable sur ce serveur. Collez sa forme <:nom:identifiant>.")
    if any(ord(c) > 127 for c in value) and not any(c.isspace() for c in value) and len(value) <= 16:
        return value
    raise ValueError("Utilisez un emoji (🎫), :nom:, son identifiant ou <:nom:identifiant> (animé : <a:nom:identifiant>).")


class TicketEmojiModal(discord.ui.Modal, title="Emoji du type de ticket"):
    emoji = discord.ui.TextInput(label="Emoji personnalisé ou classique", placeholder="<:support:123456789012345678> ou 🎫", max_length=100, required=False)

    def __init__(self, guild_id: int, label: str):
        super().__init__()
        self.guild_id, self.label = guild_id, label
        route = next((c for c in get_guild_config(guild_id).get("ticket_categories", []) if c["label"] == label), {})
        self.emoji.default = route.get("emoji", "🎫")

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild or interaction.guild.id != self.guild_id or not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Accès refusé.", ephemeral=True)
            return
        categories = get_guild_config(self.guild_id).get("ticket_categories", [])
        route = next((c for c in categories if c["label"] == self.label), None)
        if route is None:
            await interaction.response.send_message("Ce type a été supprimé. Rouvrez la configuration.", ephemeral=True)
            return
        try:
            route["emoji"] = ticket_emoji_value(self.emoji.value, interaction.guild)
        except ValueError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        set_guild_config(self.guild_id, "ticket_categories", categories)
        await interaction.response.edit_message(embed=ticket_route_embed(interaction.guild, self.label), view=TicketRoutingView(self.guild_id, self.label))


def ticket_image_path(guild_id: int, kind: str) -> str:
    if kind not in ("panel", "ticket") and not re.fullmatch(r"type_[0-9a-f]{32}", kind):
        raise ValueError("Destination d'image invalide.")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "ticket_images", f"{int(guild_id)}_{kind}.img")


def ticket_image_extension(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp"
    raise ValueError("Choisissez une image PNG, JPEG, GIF ou WebP.")


async def save_ticket_image(interaction: discord.Interaction, kind: str, attachment: discord.Attachment | None, type_label: str | None = None, notify: bool = True):
    if not interaction.guild or not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Accès refusé.", ephemeral=True)
        return False
    categories = get_guild_config(interaction.guild.id).get("ticket_categories", [])
    route = next((c for c in categories if c["label"] == type_label), None) if type_label is not None else None
    if type_label is not None and route is None:
        await interaction.response.send_message("Ce type n'existe plus.", ephemeral=True)
        return False
    storage = route.get("banner_storage") or "type_" + os.urandom(16).hex() if route is not None else kind
    path = ticket_image_path(interaction.guild.id, storage)
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True)
    try:
        if attachment is not None:
            limit = min(8 * 1024 * 1024, interaction.guild.filesize_limit)
            if attachment.size > limit:
                raise ValueError(f"L'image doit faire moins de {limit // (1024 * 1024)} Mo.")
            data = await attachment.read()
            ticket_image_extension(data)
            if len(data) > limit:
                raise ValueError("Cette image est trop volumineuse.")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            # Fixed names derived from the guild and destination, never from an uploaded filename.
            with open(path + ".tmp", "wb") as output:
                output.write(data)
            os.replace(path + ".tmp", path)
        if route is not None:
            # Reload after downloading so concurrent role/category edits are preserved.
            categories = get_guild_config(interaction.guild.id).get("ticket_categories", [])
            route = next((c for c in categories if c["label"] == type_label), None)
            if route is None:
                raise ValueError("Ce type a été supprimé pendant l'envoi.")
            route["banner_storage"] = storage if attachment is not None else ""
            set_guild_config(interaction.guild.id, "ticket_categories", categories)
        else:
            settings = get_ticket_settings(interaction.guild.id)
            settings[f"{kind}_image_uploaded"] = attachment is not None
            settings[f"{kind}_image_url"] = ""
            set_guild_config(interaction.guild.id, "ticket_settings", settings)
    except (ValueError, OSError, discord.HTTPException) as error:
        message = str(error) if isinstance(error, ValueError) else "Impossible d'enregistrer l'image. Réessayez."
        await interaction.followup.send(message, ephemeral=True)
        return False
    message = "Bannière enregistrée." if attachment is not None else "Aucune bannière."
    message += " Publiez le panneau avec /panel-tickets." if kind == "panel" else " Elle sera appliquée aux prochains tickets."
    if notify:
        await interaction.followup.send(message, ephemeral=True)
    return True


async def send_ticket_embed(channel, guild_id: int, kind: str, settings: dict, embed: discord.Embed, **kwargs):
    if settings.get(f"{kind}_image_uploaded"):
        path = ticket_image_path(guild_id, settings.get(f"{kind}_image_storage") or kind)
        with open(path, "rb") as image:
            extension = ticket_image_extension(image.read(12))
            image.seek(0)
            attachment = discord.File(image, filename=f"{kind}.{extension}")
            try:
                embed.set_image(url=f"attachment://{attachment.filename}")
                return await channel.send(embed=embed, file=attachment, **kwargs)
            finally:
                attachment.close()
    if settings.get(f"{kind}_image_url"):
        embed.set_image(url=settings[f"{kind}_image_url"])
    return await channel.send(embed=embed, **kwargs)


class TicketImageModal(discord.ui.Modal):
    def __init__(self, guild_id: int, kind: str, type_label: str | None = None):
        super().__init__(title="Bannière centrale" if kind == "panel" else "Bannière du type de ticket")
        self.guild_id, self.kind, self.type_label = guild_id, kind, type_label
        self.upload = discord.ui.FileUpload(min_values=0, max_values=1, required=False)
        self.add_item(discord.ui.Label(text="Glissez une bannière (facultatif)", description="Image horizontale conseillée, 8 Mo max. Sans fichier = aucune bannière.", component=self.upload))

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild or interaction.guild.id != self.guild_id:
            await interaction.response.send_message("Accès refusé.", ephemeral=True)
            return
        await save_ticket_image(interaction, self.kind, self.upload.values[0] if self.upload.values else None, self.type_label)


async def open_ticket_image_modal(interaction: discord.Interaction, guild_id: int, kind: str, type_label: str | None = None):
    if hasattr(discord.ui, "FileUpload"):
        await interaction.response.send_modal(TicketImageModal(guild_id, kind, type_label))
    else:
        await interaction.response.send_message("Utilisez `/image-tickets` et choisissez la destination et le type de ticket, puis déposez votre bannière dans `image`. Le dépôt dans cette fenêtre nécessite discord.py 2.7 ou plus.", ephemeral=True)


@tree.command(name="image-tickets", description="[Admin] Ajoute ou retire une image des panneaux de tickets")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.choices(destination=[app_commands.Choice(name="Panneau d'ouverture", value="panel"), app_commands.Choice(name="Ticket créé", value="ticket")])
@app_commands.describe(image="Glissez votre image ici ; laissez vide pour retirer l'image")
async def image_tickets(interaction: discord.Interaction, destination: str, image: discord.Attachment | None = None, type_ticket: str | None = None):
    if destination == "ticket" and type_ticket is None:
        await interaction.response.send_message("Choisissez le type de ticket dont vous souhaitez régler la bannière.", ephemeral=True)
        return
    await save_ticket_image(interaction, destination, image, type_ticket if destination == "ticket" else None)

@image_tickets.autocomplete("type_ticket")
async def image_ticket_type_autocomplete(interaction: discord.Interaction, current: str):
    return await ticket_type_autocomplete(interaction, current)


@tree.command(name="config-type-ticket", description="[Admin] Modifie le titre, la description, l'emoji et la bannière d'un type")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(type_ticket="Type de ticket à personnaliser", titre="Titre du message du ticket créé", description="Message du ticket ; variables {user} et {reason}", emoji="Emoji classique ou personnalisé", image="Glissez la bannière ici, comme avec /say (optionnel)", retirer_image="Retirer la bannière de ce type")
async def config_type_ticket(interaction: discord.Interaction, type_ticket: str, titre: str | None = None, description: str | None = None, emoji: str | None = None, image: discord.Attachment | None = None, retirer_image: bool = False):
    categories = get_guild_config(interaction.guild.id).get("ticket_categories", [])
    route = next((c for c in categories if c["label"] == type_ticket), None)
    if route is None:
        await interaction.response.send_message("Choisissez un type existant dans la liste.", ephemeral=True)
        return
    if (titre is not None and (not titre.strip() or len(titre) > 256)) or (description is not None and len(description) > 1500):
        await interaction.response.send_message("Titre : 1 à 256 caractères ; description : 1500 caractères maximum.", ephemeral=True)
        return
    if image is not None and retirer_image:
        await interaction.response.send_message("Choisissez une image ou son retrait, pas les deux.", ephemeral=True)
        return
    try:
        parsed_emoji = ticket_emoji_value(emoji, interaction.guild) if emoji is not None else None
    except ValueError as error:
        await interaction.response.send_message(str(error), ephemeral=True)
        return
    if image is not None or retirer_image:
        if not await save_ticket_image(interaction, "ticket", image, type_ticket, notify=False):
            return
    categories = get_guild_config(interaction.guild.id).get("ticket_categories", [])
    route = next((c for c in categories if c["label"] == type_ticket), None)
    send = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
    if route is None:
        await send("Ce type a été supprimé. Rouvrez la configuration.", ephemeral=True)
        return
    if titre is not None:
        route["ticket_open_title"] = titre
    if description is not None:
        route["welcome_message"] = description
    if parsed_emoji is not None:
        route["emoji"] = parsed_emoji
    set_guild_config(interaction.guild.id, "ticket_categories", categories)
    await send("Type enregistré. Les prochains tickets utiliseront ces textes et cette bannière.", embed=ticket_route_embed(interaction.guild, type_ticket), view=TicketRoutingView(interaction.guild.id, type_ticket), ephemeral=True)

@config_type_ticket.autocomplete("type_ticket")
async def config_type_ticket_autocomplete(interaction: discord.Interaction, current: str):
    return await ticket_type_autocomplete(interaction, current)


class TicketPanelModal(discord.ui.Modal, title="Panel d'ouverture"):
    titre = discord.ui.TextInput(label="Titre", max_length=256)
    description = discord.ui.TextInput(label="Description", style=discord.TextStyle.paragraph, max_length=1000)
    boutons = discord.ui.TextInput(label="Boutons : ouverture puis informations", placeholder="Une ligne par bouton", style=discord.TextStyle.paragraph, max_length=161)
    couleur = discord.ui.TextInput(label="Couleur (facultative)", placeholder="#5865F2", required=False, max_length=7)

    def __init__(self, guild_id: int):
        super().__init__()
        self.guild_id = guild_id
        settings = get_ticket_settings(guild_id)
        self.titre.default, self.description.default = settings["panel_title"], settings["panel_description"]
        self.boutons.default = settings["open_button_label"] + "\n" + settings["info_button_label"]
        self.couleur.default = f"#{settings.get('panel_color', COLOR_PRIMARY):06X}"
        self.upload = None
        if hasattr(discord.ui, "FileUpload"):
            self.upload = discord.ui.FileUpload(min_values=0, max_values=1, required=False)
            self.add_item(discord.ui.Label(text="Bannière centrale (facultative)", description="Glissez une image horizontale, 8 Mo max. Sans fichier = aucune bannière.", component=self.upload))

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild or interaction.guild.id != self.guild_id or not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Accès refusé.", ephemeral=True)
            return
        buttons = self.boutons.value.strip().splitlines()
        if len(buttons) != 2 or any(not b.strip() or len(b.strip()) > 80 for b in buttons):
            await interaction.response.send_message("Indiquez deux lignes : bouton d'ouverture, puis bouton informations (80 caractères chacun maximum).", ephemeral=True)
            return
        try:
            color = int(self.couleur.value.strip().lstrip("#"), 16) if self.couleur.value.strip() else COLOR_PRIMARY
            if not 0 <= color <= 0xFFFFFF:
                raise ValueError
        except ValueError:
            await interaction.response.send_message("Couleur invalide. Exemple : #5865F2.", ephemeral=True)
            return
        settings = get_ticket_settings(self.guild_id)
        settings.update(panel_title=self.titre.value, panel_description=self.description.value, open_button_label=buttons[0].strip(), info_button_label=buttons[1].strip(), panel_color=color)
        set_guild_config(self.guild_id, "ticket_settings", settings)
        if self.upload is not None:
            await save_ticket_image(interaction, "panel", self.upload.values[0] if self.upload.values else None)
        else:
            await interaction.response.send_message("Textes enregistrés. Déposez la bannière facultative avec /image-tickets (destination : panneau d'ouverture).", ephemeral=True)

class TicketPanelDetailsModal(discord.ui.Modal, title="Informations du panel"):
    etape_un = discord.ui.TextInput(label="Étape 1 (vide = masquée)", style=discord.TextStyle.paragraph, required=False, max_length=300)
    etape_deux = discord.ui.TextInput(label="Étape 2 (vide = masquée)", style=discord.TextStyle.paragraph, required=False, max_length=300)
    regles = discord.ui.TextInput(label="Règles (vide = masquées)", style=discord.TextStyle.paragraph, required=False, max_length=600)
    staff = discord.ui.TextInput(label="Équipe notifiée (vide = masquée)", required=False, max_length=100)
    def __init__(self, guild_id: int):
        super().__init__()
        self.guild_id = guild_id
        settings = get_ticket_settings(guild_id)
        self.etape_un.default, self.etape_deux.default = settings["panel_step_one"], settings["panel_step_two"]
        self.regles.default, self.staff.default = settings["panel_rules"], settings["panel_staff_title"]
    async def on_submit(self, interaction: discord.Interaction):
        settings = get_ticket_settings(self.guild_id)
        settings.update(panel_step_one=self.etape_un.value, panel_step_two=self.etape_deux.value, panel_rules=self.regles.value, panel_staff_title=self.staff.value)
        set_guild_config(self.guild_id, "ticket_settings", settings)
        await interaction.response.send_message(embed=firm1_embed("✅ Informations enregistrées", "Le prochain panel utilisera ces textes.", color=COLOR_SUCCESS), ephemeral=True)

class TicketOpenedModal(discord.ui.Modal, title="Message du ticket créé"):
    titre = discord.ui.TextInput(label="Titre", max_length=256)
    bienvenue = discord.ui.TextInput(label="Message ({user} et {reason} disponibles)", style=discord.TextStyle.paragraph, max_length=1500)
    fermer = discord.ui.TextInput(label="Bouton de fermeture", max_length=80)
    def __init__(self, guild_id: int):
        super().__init__()
        self.guild_id = guild_id
        settings = get_ticket_settings(guild_id)
        self.titre.default, self.bienvenue.default = settings["ticket_open_title"], settings["welcome_message"]
        self.fermer.default = settings["close_button_label"]
    async def on_submit(self, interaction: discord.Interaction):
        settings = get_ticket_settings(self.guild_id)
        settings.update(ticket_open_title=self.titre.value, welcome_message=self.bienvenue.value, close_button_label=self.fermer.value)
        set_guild_config(self.guild_id, "ticket_settings", settings)
        await interaction.response.send_message(embed=firm1_embed("✅ Ticket personnalisé", "Les prochains tickets utiliseront ce message.", color=COLOR_SUCCESS), ephemeral=True)


class TicketOptionsModal(discord.ui.Modal, title="Options des tickets"):
    prefixe = discord.ui.TextInput(label="Préfixe des salons", max_length=40)
    delai = discord.ui.TextInput(label="Délai de suppression (1 à 60 secondes)", max_length=2)
    informations = discord.ui.TextInput(label="Texte du bouton Informations", style=discord.TextStyle.paragraph, max_length=800)
    def __init__(self, guild_id: int):
        super().__init__()
        self.guild_id = guild_id
        settings = get_ticket_settings(guild_id)
        self.prefixe.default = settings["ticket_prefix"]
        self.delai.default = str(settings["close_delay"])
        self.informations.default = settings["info_message"]
    async def on_submit(self, interaction: discord.Interaction):
        try:
            delay = int(self.delai.value)
        except ValueError:
            await interaction.response.send_message("Le délai doit être un nombre entre 1 et 60.", ephemeral=True); return
        if not 1 <= delay <= 60:
            await interaction.response.send_message("Le délai doit être entre 1 et 60 secondes.", ephemeral=True); return
        prefix = re.sub(r"[^a-z0-9-]", "", self.prefixe.value.casefold())[:40]
        settings = get_ticket_settings(self.guild_id)
        settings.update(ticket_prefix=prefix or "ticket", close_delay=delay, info_message=self.informations.value)
        set_guild_config(self.guild_id, "ticket_settings", settings)
        await interaction.response.send_message(embed=firm1_embed("✅ Options enregistrées", "Les prochains tickets utiliseront ces réglages.", color=COLOR_SUCCESS), ephemeral=True)

class TicketAdminView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=300)
        self.guild_id = guild_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild and interaction.guild.id == self.guild_id and interaction.user.guild_permissions.administrator:
            return True
        await interaction.response.send_message("Accès refusé.", ephemeral=True)
        return False


def ticket_route_embed(guild: discord.Guild, label: str | None = None) -> discord.Embed:
    cfg = get_guild_config(guild.id)
    settings = get_ticket_settings(guild.id)
    route = next((c for c in cfg.get("ticket_categories", []) if c["label"] == label), {}) if label is not None else {}
    category_id = route.get("discord_category_id") or settings.get("default_category_id")
    roles = route.get("ping_roles", cfg.get("ping_roles", []))
    category = guild.get_channel(category_id) if category_id else None
    embed = discord.Embed(title=f"Réglages : {label or 'par défaut'}", description="Sélectionnez les rôles et la catégorie ci-dessous. Chaque choix est enregistré immédiatement.", color=COLOR_PRIMARY)
    if label is not None:
        embed.add_field(name="Emoji", value=route.get("emoji", "🎫"), inline=False)
        embed.add_field(name="Bannière", value="Personnalisée" if route.get("banner_storage") else "Aucune (facultative)", inline=False)
    embed.add_field(name="Rôles à notifier", value=" ".join(f"<@&{rid}>" for rid in roles) or "Aucun", inline=False)
    embed.add_field(name="Catégorie Discord", value=category.mention if category else settings["default_category_name"], inline=False)
    embed.set_footer(text="Rôles vides = aucun ping · Catégorie vide = catégorie par défaut")
    return embed


class TicketRoutingView(TicketAdminView):
    def __init__(self, guild_id: int, label: str | None = None):
        super().__init__(guild_id)
        self.label = label
        if label is None:
            self.remove_item(self.delete_type)
            self.remove_item(self.edit_emoji)
            self.remove_item(self.banner)

    async def save_route(self, interaction: discord.Interaction, key: str, value):
        cfg = get_guild_config(self.guild_id)
        if self.label is None:
            if key == "ping_roles":
                set_guild_config(self.guild_id, key, value)
            else:
                settings = get_ticket_settings(self.guild_id)
                settings["default_category_id"] = value
                set_guild_config(self.guild_id, "ticket_settings", settings)
        else:
            categories = cfg.get("ticket_categories", [])
            route = next((c for c in categories if c["label"] == self.label), None)
            if route is None:
                await interaction.response.send_message("Ce type a été supprimé. Rouvrez la configuration.", ephemeral=True)
                return
            route[key] = value
            set_guild_config(self.guild_id, "ticket_categories", categories)
        await interaction.response.edit_message(embed=ticket_route_embed(interaction.guild, self.label), view=self)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Rôles à notifier (vide = aucun)", min_values=0, max_values=25, row=0)
    async def roles(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        if any(role.is_default() for role in select.values):
            await interaction.response.send_message("Choisissez des rôles de support, pas @everyone : les tickets doivent rester privés.", ephemeral=True)
            return
        await self.save_route(interaction, "ping_roles", [role.id for role in select.values])

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.category], placeholder="Catégorie Discord de destination", min_values=0, max_values=1, row=1)
    async def category(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        await self.save_route(interaction, "discord_category_id", select.values[0].id if select.values else None)

    @discord.ui.button(label="Bannière (facultative)", style=discord.ButtonStyle.secondary, row=2)
    async def banner(self, interaction: discord.Interaction, button: discord.ui.Button):
        await open_ticket_image_modal(interaction, self.guild_id, "ticket", self.label)

    @discord.ui.button(label="Modifier l’emoji", style=discord.ButtonStyle.secondary, row=2)
    async def edit_emoji(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketEmojiModal(self.guild_id, self.label))

    @discord.ui.button(label="Supprimer ce type", style=discord.ButtonStyle.danger, row=2)
    async def delete_type(self, interaction: discord.Interaction, button: discord.ui.Button):
        categories = get_guild_config(self.guild_id).get("ticket_categories", [])
        set_guild_config(self.guild_id, "ticket_categories", [c for c in categories if c["label"] != self.label])
        await interaction.response.edit_message(embed=ticket_types_embed(self.guild_id), view=TicketTypesView(self.guild_id))

    @discord.ui.button(label="Retour à la configuration", style=discord.ButtonStyle.secondary, row=2)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=ticket_config_embed(interaction.guild), view=TicketConfigView(self.guild_id))


def ticket_types_embed(guild_id: int) -> discord.Embed:
    count = len(get_guild_config(guild_id).get("ticket_categories", []))
    return discord.Embed(title=f"Types de tickets ({count}/25)", description="Ajoutez un type ou sélectionnez-en un pour ses rôles et sa catégorie. Pour son titre, sa description et sa bannière ensemble : `/config-type-ticket`.", color=COLOR_PRIMARY)


class TicketTypeModal(discord.ui.Modal, title="Ajouter un type de ticket"):
    emoji = discord.ui.TextInput(label="Emoji personnalisé ou classique", placeholder="<:support:123456789012345678> ou 🎫", required=False, max_length=100)
    nom = discord.ui.TextInput(label="Nom du type", max_length=80)
    description = discord.ui.TextInput(label="Description courte", required=False, max_length=100)

    def __init__(self, guild_id: int):
        super().__init__()
        self.guild_id = guild_id
        self.upload = None
        if hasattr(discord.ui, "FileUpload"):
            self.upload = discord.ui.FileUpload(min_values=0, max_values=1, required=False)
            self.add_item(discord.ui.Label(text="Bannière du type (facultative)", description="Glissez une image horizontale. Sans fichier = aucune bannière.", component=self.upload))

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild or interaction.guild.id != self.guild_id or not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Accès refusé.", ephemeral=True)
            return
        cfg = get_guild_config(self.guild_id)
        categories = cfg.get("ticket_categories", [])
        label = self.nom.value.strip()
        if not label or any(c["label"].casefold() == label.casefold() for c in categories):
            await interaction.response.send_message("Choisissez un nom non vide et unique.", ephemeral=True)
            return
        if len(categories) >= 25:
            await interaction.response.send_message("Maximum 25 types de tickets.", ephemeral=True)
            return
        try:
            emoji = ticket_emoji_value(self.emoji.value, interaction.guild)
        except ValueError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        categories.append({"label": label, "description": self.description.value.strip(), "emoji": emoji, "discord_category_id": None, "ping_roles": list(cfg.get("ping_roles", []))})
        set_guild_config(self.guild_id, "ticket_categories", categories)
        if self.upload is not None and self.upload.values:
            await save_ticket_image(interaction, "ticket", self.upload.values[0], label)
            await interaction.edit_original_response(embed=ticket_route_embed(interaction.guild, label), view=TicketRoutingView(self.guild_id, label))
        else:
            await interaction.response.edit_message(embed=ticket_route_embed(interaction.guild, label), view=TicketRoutingView(self.guild_id, label))


class TicketTypeAdminSelect(discord.ui.Select):
    def __init__(self, categories: list[dict]):
        self.labels = [c["label"] for c in categories]
        super().__init__(placeholder="Configurer un type de ticket", options=[discord.SelectOption(label=c["label"][:100], value=str(i), emoji=c.get("emoji", "🎫")) for i, c in enumerate(categories)], row=0)

    async def callback(self, interaction: discord.Interaction):
        label = self.labels[int(self.values[0])]
        if not any(c["label"] == label for c in get_guild_config(interaction.guild.id).get("ticket_categories", [])):
            await interaction.response.send_message("Ce type a été supprimé. Rouvrez la configuration.", ephemeral=True)
            return
        await interaction.response.edit_message(embed=ticket_route_embed(interaction.guild, label), view=TicketRoutingView(interaction.guild.id, label))


class TicketTypesView(TicketAdminView):
    def __init__(self, guild_id: int):
        super().__init__(guild_id)
        categories = get_guild_config(guild_id).get("ticket_categories", [])
        if categories:
            self.add_item(TicketTypeAdminSelect(categories))

    @discord.ui.button(label="Ajouter un type", style=discord.ButtonStyle.success, row=1)
    async def add_type(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketTypeModal(self.guild_id))

    @discord.ui.button(label="Retour à la configuration", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=ticket_config_embed(interaction.guild), view=TicketConfigView(self.guild_id))



class TicketConfigView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=180)
        self.guild_id = guild_id
    def allowed(self, interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.administrator
    @discord.ui.button(label="Panel d'ouverture", style=discord.ButtonStyle.primary, emoji="🎨")
    async def panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.allowed(interaction):
            await interaction.response.send_message("Accès refusé.", ephemeral=True); return
        await interaction.response.send_modal(TicketPanelModal(self.guild_id))
    @discord.ui.button(label="Informations", style=discord.ButtonStyle.secondary, emoji="📝")
    async def details(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.allowed(interaction):
            await interaction.response.send_message("Accès refusé.", ephemeral=True); return
        await interaction.response.send_modal(TicketPanelDetailsModal(self.guild_id))
    @discord.ui.button(label="Ticket créé", style=discord.ButtonStyle.success, emoji="🎫")
    async def opened(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.allowed(interaction):
            await interaction.response.send_message("Accès refusé.", ephemeral=True); return
        await interaction.response.send_modal(TicketOpenedModal(self.guild_id))
    @discord.ui.button(label="Options", style=discord.ButtonStyle.secondary, emoji="⚙️")
    async def options(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.allowed(interaction):
            await interaction.response.send_message("Accès refusé.", ephemeral=True); return
        await interaction.response.send_modal(TicketOptionsModal(self.guild_id))
    @discord.ui.button(label="Rôles et catégorie par défaut", style=discord.ButtonStyle.secondary, row=1)
    async def routing(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.allowed(interaction):
            await interaction.response.send_message("Accès refusé.", ephemeral=True); return
        await interaction.response.edit_message(embed=ticket_route_embed(interaction.guild), view=TicketRoutingView(self.guild_id))
    @discord.ui.button(label="Types de tickets", style=discord.ButtonStyle.primary, row=1)
    async def types(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.allowed(interaction):
            await interaction.response.send_message("Accès refusé.", ephemeral=True); return
        await interaction.response.edit_message(embed=ticket_types_embed(self.guild_id), view=TicketTypesView(self.guild_id))
    @discord.ui.button(label="Actualiser", style=discord.ButtonStyle.secondary, emoji="🔄")
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=ticket_config_embed(interaction.guild), view=self)

def ticket_config_embed(guild: discord.Guild) -> discord.Embed:
    settings = get_ticket_settings(guild.id)
    embed = bot_embed(title="Configuration des tickets", description="Personnalisez les messages avec les boutons. Dans Informations, videz les détails facultatifs pour les masquer.", color=COLOR_PRIMARY, timestamp=datetime.datetime.now(datetime.timezone.utc))
    embed.add_field(name="Panel d'ouverture", value=f"**{settings['panel_title']}**\nBouton : {settings['open_button_label']}", inline=False)
    embed.add_field(name="Ticket créé", value=f"**{settings['ticket_open_title']}**\nFermeture : {settings['close_button_label']}", inline=False)
    embed.add_field(name="Images", value="`/panel-tickets` et `/config-type-ticket` : **titre**, **description** et **image** dans la même commande, comme `/say`. Image facultative ; omise = bannière conservée.", inline=False)
    embed.add_field(name="Options avancées", value="Préfixe, délai et texte Informations : bouton **Options**.", inline=False)
    cfg = get_guild_config(guild.id)
    embed.add_field(name="Routage des tickets", value=f"**{len(cfg.get('ticket_categories', []))} types** · Rôles et catégorie réglables pour chaque type.\nUtilisez les boutons ci-dessous.", inline=False)
    return embed

@tree.command(name="config-tickets", description="[Admin] Ouvre la configuration interactive des tickets")
@app_commands.checks.has_permissions(administrator=True)
async def config_tickets(interaction: discord.Interaction):
    await interaction.response.send_message(embed=ticket_config_embed(interaction.guild), view=TicketConfigView(interaction.guild.id), ephemeral=True)


@tree.command(name="set-log-tickets", description="[Admin] Définit le salon de logs des tickets")
@app_commands.describe(salon="Le salon texte qui recevra les logs")
@app_commands.checks.has_permissions(administrator=True)
async def set_log_tickets(interaction: discord.Interaction, salon: discord.TextChannel):
    set_guild_config(interaction.guild.id, "log_channel_id", salon.id)
    await interaction.response.send_message(embed=firm1_embed("✅ Salon de logs tickets configuré", f"Logs envoyés dans {salon.mention}.", color=COLOR_SUCCESS), ephemeral=True)

@tree.command(name="ajouter-role-ticket", description="[Admin] Ajoute un rôle à pinger lors d'un ticket")
@app_commands.describe(role="Le rôle à ajouter")
@app_commands.checks.has_permissions(administrator=True)
async def add_ping_role(interaction: discord.Interaction, role: discord.Role):
    cfg      = get_guild_config(interaction.guild.id)
    ping_ids = cfg.get("ping_roles", [])
    if role.id in ping_ids:
        await interaction.response.send_message(embed=firm1_embed("Déjà présent", f"{role.mention} est déjà dans la liste.", color=COLOR_WARNING), ephemeral=True)
        return
    ping_ids.append(role.id)
    set_guild_config(interaction.guild.id, "ping_roles", ping_ids)
    all_roles = [interaction.guild.get_role(rid) for rid in ping_ids if interaction.guild.get_role(rid)]
    await interaction.response.send_message(embed=firm1_embed("✅ Rôle ping ajouté", f"{role.mention} sera pingé à chaque ticket.", color=COLOR_SUCCESS, fields=[("🔔 Liste complète", " ".join(r.mention for r in all_roles), False)]), ephemeral=True)

@tree.command(name="retirer-role-ticket", description="[Admin] Retire un rôle de la liste des pings tickets")
@app_commands.describe(role="Le rôle à retirer")
@app_commands.checks.has_permissions(administrator=True)
async def remove_ping_role(interaction: discord.Interaction, role: discord.Role):
    cfg      = get_guild_config(interaction.guild.id)
    ping_ids = cfg.get("ping_roles", [])
    if role.id not in ping_ids:
        await interaction.response.send_message(embed=firm1_embed("Introuvable", f"{role.mention} n'est pas dans la liste.", color=COLOR_WARNING), ephemeral=True)
        return
    ping_ids.remove(role.id)
    set_guild_config(interaction.guild.id, "ping_roles", ping_ids)
    all_roles = [interaction.guild.get_role(rid) for rid in ping_ids if interaction.guild.get_role(rid)]
    await interaction.response.send_message(embed=firm1_embed("✅ Rôle ping retiré", f"{role.mention} ne sera plus pingé.", color=COLOR_SUCCESS, fields=[("🔔 Liste restante", " ".join(r.mention for r in all_roles) if all_roles else "Aucun", False)]), ephemeral=True)

@tree.command(name="ajouter-categorie-ticket", description="[Admin] Ajoute une catégorie de ticket")
@app_commands.describe(label="Nom affiché", categorie_discord="Catégorie Discord cible", description="Description courte (optionnel)", emoji="Emoji (optionnel)")
@app_commands.checks.has_permissions(administrator=True)
async def add_ticket_category(interaction: discord.Interaction, label: str, categorie_discord: discord.CategoryChannel, description: str = "", emoji: str = "🎫"):
    cfg        = get_guild_config(interaction.guild.id)
    categories = cfg.get("ticket_categories", [])
    if any(c["label"].lower() == label.lower() for c in categories):
        await interaction.response.send_message(embed=firm1_embed("Déjà existant", f"**{label}** existe déjà.", color=COLOR_WARNING), ephemeral=True)
        return
    if len(categories) >= 25:
        await interaction.response.send_message(embed=firm1_embed("Limite atteinte", "Maximum 25 catégories.", color=COLOR_ERROR), ephemeral=True)
        return
    categories.append({"label": label, "description": description, "emoji": emoji, "discord_category_id": categorie_discord.id})
    set_guild_config(interaction.guild.id, "ticket_categories", categories)
    await interaction.response.send_message(embed=firm1_embed("✅ Catégorie ajoutée", f"{emoji} **{label}** → {categorie_discord.mention}", color=COLOR_SUCCESS, fields=[("Total", str(len(categories)), True)]), ephemeral=True)

@tree.command(name="retirer-categorie-ticket", description="[Admin] Supprime une catégorie de ticket")
@app_commands.describe(label="Nom exact de la catégorie à supprimer")
@app_commands.checks.has_permissions(administrator=True)
async def remove_ticket_category(interaction: discord.Interaction, label: str):
    cfg        = get_guild_config(interaction.guild.id)
    categories = cfg.get("ticket_categories", [])
    new_cats   = [c for c in categories if c["label"].lower() != label.lower()]
    if len(new_cats) == len(categories):
        await interaction.response.send_message(embed=firm1_embed("Introuvable", f"Aucune catégorie **{label}**.", color=COLOR_WARNING), ephemeral=True)
        return
    set_guild_config(interaction.guild.id, "ticket_categories", new_cats)
    await interaction.response.send_message(embed=firm1_embed("✅ Catégorie supprimée", f"**{label}** retirée.", color=COLOR_SUCCESS, fields=[("Restantes", str(len(new_cats)), True)]), ephemeral=True)

@tree.command(name="reset-config-tickets", description="[Admin] Remet la config tickets par défaut")
@app_commands.checks.has_permissions(administrator=True)
async def reset_config_tickets(interaction: discord.Interaction):
    cfg = _load_config()
    gid = str(interaction.guild.id)
    if gid in cfg:
        del cfg[gid]
        _save_config(cfg)
    await interaction.response.send_message(embed=firm1_embed("🔄 Config réinitialisée", "Logs, rôles et catégories remis à zéro.", color=COLOR_WARNING), ephemeral=True)

@tree.command(name="panel-tickets", description="[Admin] Configure et envoie le panel d'ouverture de tickets")
@app_commands.describe(titre="Titre du panneau (optionnel)", description="Description du panneau (optionnelle)", image="Glissez la bannière ici, comme avec /say (optionnel)", retirer_image="Retirer la bannière enregistrée")
@app_commands.checks.has_permissions(administrator=True)
async def panel_tickets(interaction: discord.Interaction, titre: str | None = None, description: str | None = None, image: discord.Attachment | None = None, retirer_image: bool = False):
    if (titre is not None and (not titre.strip() or len(titre) > 256)) or (description is not None and len(description) > 1000):
        await interaction.response.send_message("Titre : 1 à 256 caractères ; description : 1000 caractères maximum.", ephemeral=True)
        return
    if image is not None and retirer_image:
        await interaction.response.send_message("Choisissez une image ou son retrait, pas les deux.", ephemeral=True)
        return
    if image is not None or retirer_image:
        if not await save_ticket_image(interaction, "panel", image, notify=False):
            return
    settings = get_ticket_settings(interaction.guild.id)
    if titre is not None:
        settings["panel_title"] = titre
    if description is not None:
        settings["panel_description"] = description
    if titre is not None or description is not None:
        set_guild_config(interaction.guild.id, "ticket_settings", settings)
    cfg        = get_guild_config(interaction.guild.id)
    ping_roles = [interaction.guild.get_role(rid) for rid in cfg.get("ping_roles", []) if interaction.guild.get_role(rid)]
    log_ch = interaction.guild.get_channel(cfg.get("log_channel_id")) if cfg.get("log_channel_id") else None
    settings = get_ticket_settings(interaction.guild.id)
    embed = discord.Embed(
        title=settings["panel_title"],
        description=settings["panel_description"],
        color=settings.get("panel_color", COLOR_PRIMARY),
    )
    steps = [settings[key].strip() for key in ("panel_step_one", "panel_step_two") if settings[key].strip()]
    if steps:
        embed.add_field(name="Comment ouvrir une demande", value="\n".join(f"**{i}.** {step}" for i, step in enumerate(steps, 1)), inline=False)
    if settings["panel_rules"].strip():
        embed.add_field(name="Bonnes pratiques", value=settings["panel_rules"], inline=False)
    if settings["panel_staff_title"].strip() and ping_roles:
        embed.add_field(name=settings["panel_staff_title"], value=" ".join(r.mention for r in ping_roles), inline=False)
    view = TicketOpenView()
    view.children[0].label = settings["open_button_label"]
    view.children[1].label = settings["info_button_label"]
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True)
    await send_ticket_embed(interaction.channel, interaction.guild.id, "panel", settings, embed, view=view)
    await interaction.followup.send(embed=firm1_embed("✅ Panel envoyé !", "Le panel de tickets a été créé.", color=COLOR_SUCCESS, fields=[("📁 Logs", log_ch.mention if log_ch else "❌ Non configuré", True), ("🔔 Rôles", " ".join(r.mention for r in ping_roles) if ping_roles else "❌ Aucun configuré", True)]), ephemeral=True)


# ═══════════════════════════════════════════════════════════
#  MODÉRATION
# ═══════════════════════════════════════════════════════════

@tree.command(name="set-log-mod", description="[Admin] Définit le salon de logs de modération")
@app_commands.describe(salon="Le salon qui recevra les logs de modération")
@app_commands.checks.has_permissions(administrator=True)
async def set_log_mod(interaction: discord.Interaction, salon: discord.TextChannel):
    set_guild_config(interaction.guild.id, "mod_log_channel_id", salon.id)
    await interaction.response.send_message(embed=firm1_embed("✅ Salon de logs modération configuré", f"Toutes les actions seront loggées dans {salon.mention}.", color=COLOR_SUCCESS, fields=[("📋 Actions loggées", "🔨 Ban • 👢 Kick • 🔇 Mute • 🔊 Unmute\n⚠️ Warn • 🗑️ Clear • 🚫 Badword\n🔗 Lien • 🖼️ Image • 🚨 Antispam • ⛔ Blacklist", False)]), ephemeral=True)

@tree.command(name="ban", description="[Modo] Bannir un membre")
@app_commands.describe(membre="Le membre à bannir", raison="Raison du ban")
@app_commands.checks.has_permissions(ban_members=True)
async def ban_cmd(interaction: discord.Interaction, membre: discord.Member, raison: str = "Aucune raison fournie"):
    if membre.top_role >= interaction.user.top_role:
        await interaction.response.send_message(embed=firm1_embed("Erreur", "Rôle supérieur ou égal.", color=COLOR_ERROR), ephemeral=True)
        return
    try:
        await membre.send(embed=firm1_embed("🔨 Vous avez été banni", f"**Serveur :** {interaction.guild.name}\n**Raison :** {raison}", color=COLOR_ERROR))
    except Exception:
        pass
    await membre.ban(reason=raison)
    await interaction.response.send_message(embed=firm1_embed("🔨 Membre banni", f"{membre.mention} a été banni.", color=COLOR_ERROR, fields=[("👤 Membre", str(membre), True), ("📝 Raison", raison, True), ("🛡️ Modérateur", interaction.user.mention, True)]))
    await send_mod_log(interaction.guild, title="🔨 Ban", color=COLOR_ERROR, fields=[("👤 Membre", f"{membre} (`{membre.id}`)", True), ("📝 Raison", raison, True), ("🛡️ Modérateur", str(interaction.user), True)])

@tree.command(name="kick", description="[Modo] Expulser un membre")
@app_commands.describe(membre="Le membre à expulser", raison="Raison du kick")
@app_commands.checks.has_permissions(kick_members=True)
async def kick_cmd(interaction: discord.Interaction, membre: discord.Member, raison: str = "Aucune raison fournie"):
    if membre.top_role >= interaction.user.top_role:
        await interaction.response.send_message(embed=firm1_embed("Erreur", "Rôle supérieur ou égal.", color=COLOR_ERROR), ephemeral=True)
        return
    try:
        await membre.send(embed=firm1_embed("👢 Vous avez été expulsé", f"**Serveur :** {interaction.guild.name}\n**Raison :** {raison}", color=COLOR_WARNING))
    except Exception:
        pass
    await membre.kick(reason=raison)
    await interaction.response.send_message(embed=firm1_embed("👢 Membre expulsé", f"{membre.mention} a été expulsé.", color=COLOR_WARNING, fields=[("👤 Membre", str(membre), True), ("📝 Raison", raison, True), ("🛡️ Modérateur", interaction.user.mention, True)]))
    await send_mod_log(interaction.guild, title="👢 Kick", color=COLOR_WARNING, fields=[("👤 Membre", f"{membre} (`{membre.id}`)", True), ("📝 Raison", raison, True), ("🛡️ Modérateur", str(interaction.user), True)])

@tree.command(name="mute", description="[Modo] Rendre muet un membre (ex: 10m, 2h, 1j)")
@app_commands.describe(membre="Le membre à mute", duree="Durée : 10s, 5m, 2h, 1j...", raison="Raison")
@app_commands.checks.has_permissions(moderate_members=True)
async def mute_cmd(interaction: discord.Interaction, membre: discord.Member, duree: str, raison: str = "Aucune raison fournie"):
    secondes = parse_duration(duree)
    if secondes is None:
        await interaction.response.send_message(embed=firm1_embed("Format invalide", "Utilisez : `10s`, `5m`, `2h`, `1j`.", color=COLOR_ERROR), ephemeral=True)
        return
    if secondes > 2419200:
        await interaction.response.send_message(embed=firm1_embed("Trop long", "Maximum **28 jours**.", color=COLOR_ERROR), ephemeral=True)
        return
    until = discord.utils.utcnow() + datetime.timedelta(seconds=secondes)
    await membre.timeout(until, reason=raison)
    try:
        await membre.send(embed=firm1_embed("🔇 Vous êtes en sourdine", f"**Serveur :** {interaction.guild.name}\n**Durée :** {duree}\n**Raison :** {raison}", color=COLOR_WARNING))
    except Exception:
        pass
    await interaction.response.send_message(embed=firm1_embed("🔇 Membre muet", f"{membre.mention} est muet pendant **{duree}**.", color=COLOR_WARNING, fields=[("📝 Raison", raison, True), ("🛡️ Modérateur", interaction.user.mention, True), ("⏰ Fin", f"<t:{int(until.timestamp())}:R>", True)]))
    await send_mod_log(interaction.guild, title="🔇 Mute", color=COLOR_WARNING, fields=[("👤 Membre", f"{membre} (`{membre.id}`)", True), ("⏱️ Durée", duree, True), ("📝 Raison", raison, True), ("🛡️ Modérateur", str(interaction.user), True), ("⏰ Fin", f"<t:{int(until.timestamp())}:R>", True)])

@tree.command(name="unmute", description="[Modo] Retirer le mute d'un membre")
@app_commands.describe(membre="Le membre à unmute")
@app_commands.checks.has_permissions(moderate_members=True)
async def unmute_cmd(interaction: discord.Interaction, membre: discord.Member):
    await membre.timeout(None)
    await interaction.response.send_message(embed=firm1_embed("🔊 Mute retiré", f"{membre.mention} peut à nouveau s'exprimer.", color=COLOR_SUCCESS, fields=[("🛡️ Modérateur", interaction.user.mention, True)]))
    await send_mod_log(interaction.guild, title="🔊 Unmute", color=COLOR_SUCCESS, fields=[("👤 Membre", f"{membre} (`{membre.id}`)", True), ("🛡️ Modérateur", str(interaction.user), True)])

@tree.command(name="warn", description="[Modo] Avertir un membre")
@app_commands.describe(membre="Le membre à avertir", raison="Raison")
@app_commands.checks.has_permissions(kick_members=True)
async def warn_cmd(interaction: discord.Interaction, membre: discord.Member, raison: str):
    total = add_warn(interaction.guild.id, membre.id, raison, str(interaction.user))
    try:
        await membre.send(embed=firm1_embed("⚠️ Avertissement reçu", f"**Serveur :** {interaction.guild.name}\n**Raison :** {raison}\n**Total :** {total}", color=COLOR_WARNING))
    except Exception:
        pass
    await interaction.response.send_message(embed=firm1_embed("⚠️ Membre averti", f"{membre.mention} a reçu un avertissement.", color=COLOR_WARNING, fields=[("📝 Raison", raison, True), ("🛡️ Modérateur", interaction.user.mention, True), ("📊 Total warns", str(total), True)]))
    await send_mod_log(interaction.guild, title="⚠️ Warn", color=COLOR_WARNING, fields=[("👤 Membre", f"{membre} (`{membre.id}`)", True), ("📝 Raison", raison, True), ("🛡️ Modérateur", str(interaction.user), True), ("📊 Total warns", str(total), True)])

@tree.command(name="warns", description="Voir les avertissements d'un membre")
@app_commands.describe(membre="Le membre à consulter")
@app_commands.checks.has_permissions(kick_members=True)
async def warns_cmd(interaction: discord.Interaction, membre: discord.Member):
    warns = get_warns(interaction.guild.id, membre.id)
    if not warns:
        await interaction.response.send_message(embed=firm1_embed("📋 Avertissements", f"{membre.mention} n'a aucun avertissement.", color=COLOR_SUCCESS), ephemeral=True)
        return
    desc = "\n".join(f"**{i+1}.** {w['raison']} — *par {w['by']}*" for i, w in enumerate(warns))
    await interaction.response.send_message(embed=firm1_embed(f"⚠️ Avertissements de {membre.display_name}", desc, color=COLOR_WARNING, fields=[("📊 Total", str(len(warns)), True)]), ephemeral=True)

@tree.command(name="clear", description="[Modo] Supprimer des messages")
@app_commands.describe(nombre="Nombre de messages à supprimer (1-100)")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear_cmd(interaction: discord.Interaction, nombre: int):
    if not 1 <= nombre <= 100:
        await interaction.response.send_message(embed=firm1_embed("Erreur", "Entre **1** et **100**.", color=COLOR_ERROR), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=nombre)
    await interaction.followup.send(embed=firm1_embed("🗑️ Messages supprimés", f"**{len(deleted)}** message(s) supprimé(s).", color=COLOR_SUCCESS), ephemeral=True)
    await send_mod_log(interaction.guild, title="🗑️ Clear", color=COLOR_INFO, fields=[("📊 Supprimés", str(len(deleted)), True), ("📍 Salon", interaction.channel.mention, True), ("🛡️ Modérateur", str(interaction.user), True)])


# ═══════════════════════════════════════════════════════════
#  AUTO-MODÉRATION
# ═══════════════════════════════════════════════════════════


class BadwordsModal(discord.ui.Modal, title="Mots interdits"):
    mots = discord.ui.TextInput(label="Mots", placeholder="mot1, mot2, mot3", style=discord.TextStyle.paragraph, max_length=1000)
    action = discord.ui.TextInput(label="Action : ajouter, retirer ou remplacer", default="ajouter", max_length=12)
    def __init__(self, guild_id: int):
        super().__init__()
        self.guild_id = guild_id
    async def on_submit(self, interaction: discord.Interaction):
        words = [word.strip().casefold() for word in re.split(r"[,;_\n]+", self.mots.value) if word.strip()]
        if not words:
            await interaction.response.send_message("Aucun mot valide.", ephemeral=True); return
        cfg = get_guild_config(self.guild_id)
        current = cfg.get("bad_words", [])
        action = self.action.value.casefold().strip()
        if action == "remplacer":
            current = list(dict.fromkeys(words))
        elif action == "retirer":
            current = [word for word in current if word not in words]
        elif action == "ajouter":
            current = list(dict.fromkeys(current + words))
        else:
            await interaction.response.send_message("Action invalide : utilisez ajouter, retirer ou remplacer.", ephemeral=True); return
        set_guild_config(self.guild_id, "bad_words", current)
        await interaction.response.send_message(embed=firm1_embed("✅ Mots interdits mis à jour", f"**{len(current)}** mot(s) configuré(s).", color=COLOR_SUCCESS), ephemeral=True)

class AntiSpamModal(discord.ui.Modal, title="Antispam"):
    limite = discord.ui.TextInput(label="Nombre de messages (2-50)", default="5", max_length=2)
    fenetre = discord.ui.TextInput(label="Fenêtre en secondes (1-60)", default="5", max_length=2)
    mute = discord.ui.TextInput(label="Mute en minutes (1-1440)", default="5", max_length=4)
    actif = discord.ui.TextInput(label="Actif ? oui / non", default="oui", max_length=3)
    def __init__(self, guild_id: int):
        super().__init__()
        self.guild_id = guild_id
        cfg = get_guild_config(guild_id)
        self.limite.default = str(cfg.get("spam_limit", SPAM_LIMIT_DEFAULT))
        self.fenetre.default = str(cfg.get("spam_window", SPAM_WINDOW_DEFAULT))
        self.mute.default = str(cfg.get("spam_mute", SPAM_MUTE_DEFAULT))
        self.actif.default = "oui" if cfg.get("spam_active", True) else "non"
    async def on_submit(self, interaction: discord.Interaction):
        try:
            limit, window, mute = int(self.limite.value), int(self.fenetre.value), int(self.mute.value)
        except ValueError:
            await interaction.response.send_message("Les trois premières valeurs doivent être des nombres.", ephemeral=True); return
        if not 2 <= limit <= 50 or not 1 <= window <= 60 or not 1 <= mute <= 1440:
            await interaction.response.send_message("Valeurs hors limites.", ephemeral=True); return
        active = self.actif.value.casefold().strip()
        if active not in ("oui", "non"):
            await interaction.response.send_message("Indiquez oui ou non pour l'activation.", ephemeral=True); return
        set_guild_config(self.guild_id, "spam_limit", limit)
        set_guild_config(self.guild_id, "spam_window", window)
        set_guild_config(self.guild_id, "spam_mute", mute)
        set_guild_config(self.guild_id, "spam_active", active == "oui")
        await interaction.response.send_message(embed=firm1_embed("✅ Antispam mis à jour", "Vos nouveaux paramètres sont enregistrés.", color=COLOR_SUCCESS), ephemeral=True)

class LinkChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, guild_id: int):
        super().__init__(placeholder="Ajouter ou retirer un salon sans liens", channel_types=[discord.ChannelType.text], min_values=1, max_values=1)
        self.guild_id = guild_id
    async def callback(self, interaction: discord.Interaction):
        channel = self.values[0]
        cfg = get_guild_config(self.guild_id)
        channels = cfg.get("no_link_channels", [])
        if channel.id in channels:
            channels.remove(channel.id); state = "autorisés"
        else:
            channels.append(channel.id); state = "interdits"
        set_guild_config(self.guild_id, "no_link_channels", channels)
        await interaction.response.send_message(f"Liens **{state}** dans {channel.mention}.", ephemeral=True)

class ImageChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, guild_id: int):
        super().__init__(placeholder="Ajouter ou retirer un salon sans images", channel_types=[discord.ChannelType.text], min_values=1, max_values=1)
        self.guild_id = guild_id
    async def callback(self, interaction: discord.Interaction):
        channel = self.values[0]
        cfg = get_guild_config(self.guild_id)
        channels = cfg.get("no_image_channels", [])
        if channel.id in channels:
            channels.remove(channel.id); state = "autorisées"
        else:
            channels.append(channel.id); state = "interdites"
        set_guild_config(self.guild_id, "no_image_channels", channels)
        await interaction.response.send_message(f"Images **{state}** dans {channel.mention}.", ephemeral=True)

def automod_config_embed(guild: discord.Guild) -> discord.Embed:
    cfg = get_guild_config(guild.id)
    bad_words = cfg.get("bad_words", [])
    no_link = [guild.get_channel(channel_id) for channel_id in cfg.get("no_link_channels", []) if guild.get_channel(channel_id)]
    no_image = [guild.get_channel(channel_id) for channel_id in cfg.get("no_image_channels", []) if guild.get_channel(channel_id)]
    embed = bot_embed(title="Auto-modération", description="Configurez chaque protection depuis les boutons et sélecteurs ci-dessous.", color=COLOR_PRIMARY, timestamp=datetime.datetime.now(datetime.timezone.utc))
    preview = ", ".join(f"`{word}`" for word in bad_words[:12]) or "Aucun"
    if len(bad_words) > 12:
        preview += f" · +{len(bad_words) - 12}"
    embed.add_field(name="Mots interdits", value=preview, inline=True)
    embed.add_field(name="Antispam", value=f"{'Actif' if cfg.get('spam_active', True) else 'Désactivé'} · {cfg.get('spam_limit', SPAM_LIMIT_DEFAULT)} msg / {cfg.get('spam_window', SPAM_WINDOW_DEFAULT)} s", inline=True)
    embed.add_field(name="Salons protégés", value=f"Liens : {len(no_link)} · Images : {len(no_image)}", inline=True)
    return embed

class AutoModConfigView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.add_item(LinkChannelSelect(guild_id))
        self.add_item(ImageChannelSelect(guild_id))
    @discord.ui.button(label="Mots interdits", style=discord.ButtonStyle.danger, emoji="🚫")
    async def badwords(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BadwordsModal(self.guild_id))
    @discord.ui.button(label="Antispam", style=discord.ButtonStyle.primary, emoji="🚨")
    async def antispam(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AntiSpamModal(self.guild_id))
    @discord.ui.button(label="Actualiser", style=discord.ButtonStyle.secondary, emoji="🔄")
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=automod_config_embed(interaction.guild), view=self)

@tree.command(name="config-auto-mod", description="[Admin] Ouvre la configuration interactive de l'auto-modération")
@app_commands.checks.has_permissions(administrator=True)
async def config_automod(interaction: discord.Interaction):
    await interaction.response.send_message(embed=automod_config_embed(interaction.guild), view=AutoModConfigView(interaction.guild.id), ephemeral=True)









# ═══════════════════════════════════════════════════════════
#  WHITELIST & BLACKLIST
# ═══════════════════════════════════════════════════════════

@tree.command(name="whitelist-ajouter", description="[Admin] Ajoute un membre à la whitelist")
@app_commands.describe(membre="Le membre à whitelister")
@app_commands.checks.has_permissions(administrator=True)
async def wl_add(interaction: discord.Interaction, membre: discord.Member):
    cfg = get_guild_config(interaction.guild.id)
    wl  = cfg.get("whitelist", [])
    if membre.id in wl:
        await interaction.response.send_message(embed=firm1_embed("Déjà présent", f"{membre.mention} est déjà whitelisté.", color=COLOR_WARNING), ephemeral=True)
        return
    wl.append(membre.id)
    set_guild_config(interaction.guild.id, "whitelist", wl)
    await interaction.response.send_message(embed=firm1_embed("✅ Whitelisté", f"{membre.mention} bypass désormais l'auto-mod.", color=COLOR_SUCCESS, fields=[("📊 Total", str(len(wl)), True)]), ephemeral=True)
    await send_mod_log(interaction.guild, title="📋 Whitelist — Ajout", color=COLOR_INFO, fields=[("👤 Membre", f"{membre} (`{membre.id}`)", True), ("🛡️ Admin", str(interaction.user), True)])

@tree.command(name="whitelist-retirer", description="[Admin] Retire un membre de la whitelist")
@app_commands.describe(membre="Le membre à retirer")
@app_commands.checks.has_permissions(administrator=True)
async def wl_remove(interaction: discord.Interaction, membre: discord.Member):
    cfg = get_guild_config(interaction.guild.id)
    wl  = cfg.get("whitelist", [])
    if membre.id not in wl:
        await interaction.response.send_message(embed=firm1_embed("Introuvable", f"{membre.mention} n'est pas whitelisté.", color=COLOR_WARNING), ephemeral=True)
        return
    wl.remove(membre.id)
    set_guild_config(interaction.guild.id, "whitelist", wl)
    await interaction.response.send_message(embed=firm1_embed("✅ Retiré", f"{membre.mention} est soumis à l'auto-mod.", color=COLOR_SUCCESS), ephemeral=True)

@tree.command(name="whitelist-liste", description="[Admin] Voir la whitelist")
@app_commands.checks.has_permissions(administrator=True)
async def wl_list(interaction: discord.Interaction):
    cfg  = get_guild_config(interaction.guild.id)
    wl   = cfg.get("whitelist", [])
    desc = "\n".join(f"<@{uid}> (`{uid}`)" for uid in wl) if wl else "Aucun membre whitelisté."
    await interaction.response.send_message(embed=firm1_embed("✅ Whitelist", desc, color=COLOR_INFO, fields=[("📊 Total", str(len(wl)), True)]), ephemeral=True)

@tree.command(name="blacklist-ajouter", description="[Admin] Blackliste un membre (expulsion immédiate)")
@app_commands.describe(membre="Le membre à blacklister", raison="Raison (optionnel)")
@app_commands.checks.has_permissions(administrator=True)
async def bl_add(interaction: discord.Interaction, membre: discord.Member, raison: str = "Aucune raison fournie"):
    cfg = get_guild_config(interaction.guild.id)
    bl  = cfg.get("blacklist", [])
    if membre.id not in bl:
        bl.append(membre.id)
        set_guild_config(interaction.guild.id, "blacklist", bl)
    try:
        await membre.send(embed=firm1_embed("⛔ Vous avez été blacklisté", f"**Serveur :** {interaction.guild.name}\n**Raison :** {raison}", color=COLOR_ERROR))
    except Exception:
        pass
    try:
        await membre.kick(reason=f"Blacklisté : {raison}")
    except Exception:
        pass
    await interaction.response.send_message(embed=firm1_embed("⛔ Membre blacklisté", f"{membre.mention} a été blacklisté et expulsé.", color=COLOR_ERROR, fields=[("📝 Raison", raison, True), ("📊 Total", str(len(bl)), True)]), ephemeral=True)
    await send_mod_log(interaction.guild, title="⛔ Blacklist — Ajout", color=COLOR_ERROR, fields=[("👤 Membre", f"{membre} (`{membre.id}`)", True), ("📝 Raison", raison, True), ("🛡️ Admin", str(interaction.user), True)])

@tree.command(name="blacklist-retirer", description="[Admin] Retire un membre de la blacklist")
@app_commands.describe(membre="Le membre (peut ne plus être sur le serveur)")
@app_commands.checks.has_permissions(administrator=True)
async def bl_remove(interaction: discord.Interaction, membre: discord.User):
    cfg = get_guild_config(interaction.guild.id)
    bl  = cfg.get("blacklist", [])
    if membre.id not in bl:
        await interaction.response.send_message(embed=firm1_embed("Introuvable", f"{membre.mention} n'est pas blacklisté.", color=COLOR_WARNING), ephemeral=True)
        return
    bl.remove(membre.id)
    set_guild_config(interaction.guild.id, "blacklist", bl)
    await interaction.response.send_message(embed=firm1_embed("✅ Retiré", f"{membre.mention} peut à nouveau rejoindre le serveur.", color=COLOR_SUCCESS), ephemeral=True)

@tree.command(name="blacklist-liste", description="[Admin] Voir la blacklist")
@app_commands.checks.has_permissions(administrator=True)
async def bl_list(interaction: discord.Interaction):
    cfg  = get_guild_config(interaction.guild.id)
    bl   = cfg.get("blacklist", [])
    desc = "\n".join(f"<@{uid}> (`{uid}`)" for uid in bl) if bl else "Aucun membre blacklisté."
    await interaction.response.send_message(embed=firm1_embed("⛔ Blacklist", desc, color=COLOR_ERROR, fields=[("📊 Total", str(len(bl)), True)]), ephemeral=True)


# ═══════════════════════════════════════════════════════════
#  MINI-JEUX
# ═══════════════════════════════════════════════════════════

@tree.command(name="pile-ou-face", description="Lance une pièce")
async def coin_flip(interaction: discord.Interaction):
    result = random.choice(["🪙 Pile", "🪙 Face"])
    await interaction.response.send_message(embed=firm1_embed("Pile ou Face ?", f"La pièce est tombée sur... **{result}** !", color=random.choice([COLOR_SUCCESS, COLOR_WARNING])))

@tree.command(name="dé", description="Lance un dé")
@app_commands.describe(faces="Nombre de faces (défaut : 6)")
async def dice_roll(interaction: discord.Interaction, faces: int = 6):
    if faces < 2:
        await interaction.response.send_message(embed=firm1_embed("Erreur", "Au moins **2 faces**.", color=COLOR_ERROR), ephemeral=True)
        return
    await interaction.response.send_message(embed=firm1_embed(f"🎲 Dé à {faces} faces", f"Résultat : **{random.randint(1, faces)}**", color=COLOR_INFO))

RPS_CHOICES = {"pierre": "🪨", "papier": "📄", "ciseaux": "✂️"}
RPS_WINS    = {"pierre": "ciseaux", "papier": "pierre", "ciseaux": "papier"}

@tree.command(name="rps", description="Pierre-Papier-Ciseaux contre le bot")
@app_commands.describe(choix="Votre choix")
@app_commands.choices(choix=[app_commands.Choice(name="🪨 Pierre", value="pierre"), app_commands.Choice(name="📄 Papier", value="papier"), app_commands.Choice(name="✂️ Ciseaux", value="ciseaux")])
async def rps(interaction: discord.Interaction, choix: app_commands.Choice[str]):
    player     = choix.value
    bot_choice = random.choice(list(RPS_CHOICES.keys()))
    if player == bot_choice:
        result, color = "Égalité !", COLOR_WARNING
    elif RPS_WINS[player] == bot_choice:
        result, color = "Vous gagnez ! 🎉", COLOR_SUCCESS
    else:
        result, color = "Vous perdez... 😢", COLOR_ERROR
    await interaction.response.send_message(embed=firm1_embed("Pierre-Papier-Ciseaux", result, color=color, fields=[("Vous", f"{RPS_CHOICES[player]} {player.title()}", True), ("Bot", f"{RPS_CHOICES[bot_choice]} {bot_choice.title()}", True)]))

EIGHTBALL_REPLIES = [
    ("✅ C'est certain.", COLOR_SUCCESS), ("✅ Oui, définitivement.", COLOR_SUCCESS),
    ("✅ Sans aucun doute.", COLOR_SUCCESS), ("✅ Oui, absolument.", COLOR_SUCCESS),
    ("✅ Vous pouvez compter là-dessus.", COLOR_SUCCESS),
    ("🟡 Demandez à nouveau plus tard.", COLOR_WARNING),
    ("🟡 Il vaut mieux ne pas répondre maintenant.", COLOR_WARNING),
    ("🟡 Impossible de prédire pour l'instant.", COLOR_WARNING),
    ("❌ N'y comptez pas.", COLOR_ERROR), ("❌ Ma réponse est non.", COLOR_ERROR),
    ("❌ Les perspectives ne sont pas bonnes.", COLOR_ERROR), ("❌ Très douteux.", COLOR_ERROR),
]

@tree.command(name="8ball", description="Posez une question à la boule magique")
@app_commands.describe(question="Votre question")
async def eightball(interaction: discord.Interaction, question: str):
    answer, color = random.choice(EIGHTBALL_REPLIES)
    await interaction.response.send_message(embed=firm1_embed("🎱 Boule Magique", answer, color=color, fields=[("❓ Question", question, False)]))

active_guess_games: dict[int, int] = {}

@tree.command(name="nombre", description="Devinez le nombre secret !")
@app_commands.describe(maximum="Valeur maximale (défaut : 100)")
async def guess_number(interaction: discord.Interaction, maximum: int = 100):
    channel_id = interaction.channel_id
    if channel_id in active_guess_games:
        await interaction.response.send_message(embed=firm1_embed("Partie en cours", "Une partie est déjà en cours ici.", color=COLOR_WARNING), ephemeral=True)
        return
    number = random.randint(1, maximum)
    active_guess_games[channel_id] = number
    await interaction.response.send_message(embed=firm1_embed("🔢 Devinez le nombre !", f"J'ai choisi un nombre entre **1** et **{maximum}**.\nEnvoyez votre réponse. Vous avez **30 secondes** !", color=COLOR_INFO))
    def check(m: discord.Message):
        return m.channel.id == channel_id and m.content.isdigit()
    try:
        while True:
            msg   = await bot.wait_for("message", timeout=30.0, check=check)
            guess = int(msg.content)
            if guess == number:
                active_guess_games.pop(channel_id, None)
                await msg.channel.send(embed=firm1_embed("🎉 Bonne réponse !", f"{msg.author.mention} a trouvé **{number}** !", color=COLOR_SUCCESS))
                break
            elif guess < number:
                await msg.channel.send(embed=firm1_embed("💡 Trop petit !", f"Plus grand que {guess}.", color=COLOR_WARNING), delete_after=5)
            else:
                await msg.channel.send(embed=firm1_embed("💡 Trop grand !", f"Plus petit que {guess}.", color=COLOR_WARNING), delete_after=5)
    except asyncio.TimeoutError:
        active_guess_games.pop(channel_id, None)
        await interaction.channel.send(embed=firm1_embed("⏰ Temps écoulé !", f"Le nombre était **{number}**.", color=COLOR_ERROR))

TRIVIA_QUESTIONS = [
    {"question": "Quelle est la capitale de la France ?", "options": ["Paris", "Lyon", "Marseille", "Bordeaux"], "correct": 0},
    {"question": "Combien de planètes dans le système solaire ?", "options": ["7", "8", "9", "10"], "correct": 1},
    {"question": "Qui a peint la Joconde ?", "options": ["Michel-Ange", "Raphaël", "Léonard de Vinci", "Botticelli"], "correct": 2},
    {"question": "En quelle année la Révolution française ?", "options": ["1776", "1789", "1800", "1815"], "correct": 1},
    {"question": "Formule chimique de l'eau ?", "options": ["CO2", "H2O", "O2", "NaCl"], "correct": 1},
    {"question": "Quel est le plus grand océan du monde ?", "options": ["Atlantique", "Indien", "Pacifique", "Arctique"], "correct": 2},
    {"question": "Combien de cordes a une guitare standard ?", "options": ["4", "5", "6", "7"], "correct": 2},
    {"question": "Quel pays a inventé les spaghettis ?", "options": ["France", "Chine", "Italie", "Espagne"], "correct": 2},
]

@tree.command(name="trivia", description="Question de culture générale")
async def trivia(interaction: discord.Interaction):
    q       = random.choice(TRIVIA_QUESTIONS)
    letters = ["🇦", "🇧", "🇨", "🇩"]
    opts    = "\n".join(f"{letters[i]} {opt}" for i, opt in enumerate(q["options"]))
    await interaction.response.send_message(embed=firm1_embed("🧠 Trivia !", f"**{q['question']}**\n\n{opts}\n\nRépondez avec **A**, **B**, **C** ou **D**. Vous avez **20 secondes** !", color=COLOR_INFO))
    def check(m: discord.Message):
        return m.channel.id == interaction.channel_id and m.author.id == interaction.user.id and m.content.upper() in ["A", "B", "C", "D"]
    try:
        msg = await bot.wait_for("message", timeout=20.0, check=check)
        if ["A", "B", "C", "D"].index(msg.content.upper()) == q["correct"]:
            await interaction.channel.send(embed=firm1_embed("✅ Bonne réponse !", f"C'était bien **{q['options'][q['correct']]}** ! 🎉", color=COLOR_SUCCESS))
        else:
            await interaction.channel.send(embed=firm1_embed("❌ Mauvaise réponse !", f"La bonne réponse était **{q['options'][q['correct']]}**.", color=COLOR_ERROR))
    except asyncio.TimeoutError:
        await interaction.channel.send(embed=firm1_embed("⏰ Temps écoulé !", f"La bonne réponse était **{q['options'][q['correct']]}**.", color=COLOR_ERROR))


# ═══════════════════════════════════════════════════════════
#  POKÉMON — Qui est ce Pokémon ?
# ═══════════════════════════════════════════════════════════

import unicodedata as _ud



# ═══════════════════════════════════════════════════════════
#  POKÉMON — Qui est ce Pokémon ?
# ═══════════════════════════════════════════════════════════

import unicodedata as _ud

POKEMON_LIST = [
    # ═══════════════════════════════════════
    # GEN 1 — Kanto (001–151)
    # ═══════════════════════════════════════
    {"id": 1, "fr": "Bulbizarre"}, {"id": 2, "fr": "Herbizarre"}, {"id": 3, "fr": "Florizarre"},
    {"id": 4, "fr": "Salamèche"}, {"id": 5, "fr": "Reptincel"}, {"id": 6, "fr": "Dracaufeu"},
    {"id": 7, "fr": "Carapuce"}, {"id": 8, "fr": "Carabaffe"}, {"id": 9, "fr": "Tortank"},
    {"id": 10, "fr": "Chenipan"}, {"id": 11, "fr": "Chrysacier"}, {"id": 12, "fr": "Papilusion"},
    {"id": 13, "fr": "Aspicot"}, {"id": 14, "fr": "Coconfort"}, {"id": 15, "fr": "Dardargnan"},
    {"id": 16, "fr": "Roucool"}, {"id": 17, "fr": "Roucoups"}, {"id": 18, "fr": "Roucarnage"},
    {"id": 19, "fr": "Rattata"}, {"id": 20, "fr": "Rattatac"}, {"id": 21, "fr": "Piafabec"},
    {"id": 22, "fr": "Rapasdepic"}, {"id": 23, "fr": "Abo"}, {"id": 24, "fr": "Arbok"},
    {"id": 25, "fr": "Pikachu"}, {"id": 26, "fr": "Raichu"}, {"id": 27, "fr": "Sabelette"},
    {"id": 28, "fr": "Sablaireau"}, {"id": 29, "fr": "Nidoran♀"}, {"id": 30, "fr": "Nidorina"},
    {"id": 31, "fr": "Nidoqueen"}, {"id": 32, "fr": "Nidoran♂"}, {"id": 33, "fr": "Nidorino"},
    {"id": 34, "fr": "Nidoking"}, {"id": 35, "fr": "Mélofée"}, {"id": 36, "fr": "Mélodelfe"},
    {"id": 37, "fr": "Goupix"}, {"id": 38, "fr": "Feunard"}, {"id": 39, "fr": "Rondoudou"},
    {"id": 40, "fr": "Grodoudou"}, {"id": 41, "fr": "Nosferapti"}, {"id": 42, "fr": "Nosferalto"},
    {"id": 43, "fr": "Mystherbe"}, {"id": 44, "fr": "Ortide"}, {"id": 45, "fr": "Rafflesia"},
    {"id": 46, "fr": "Paras"}, {"id": 47, "fr": "Parasect"}, {"id": 48, "fr": "Mimitoss"},
    {"id": 49, "fr": "Aéromite"}, {"id": 50, "fr": "Taupiqueur"}, {"id": 51, "fr": "Triopikeur"},
    {"id": 52, "fr": "Miaouss"}, {"id": 53, "fr": "Persian"}, {"id": 54, "fr": "Psykokwak"},
    {"id": 55, "fr": "Akwakwak"}, {"id": 56, "fr": "Férosinge"}, {"id": 57, "fr": "Colossinge"},
    {"id": 58, "fr": "Caninos"}, {"id": 59, "fr": "Arcanin"}, {"id": 60, "fr": "Ptitard"},
    {"id": 61, "fr": "Têtarte"}, {"id": 62, "fr": "Tartard"}, {"id": 63, "fr": "Abra"},
    {"id": 64, "fr": "Kadabra"}, {"id": 65, "fr": "Alakazam"}, {"id": 66, "fr": "Machoc"},
    {"id": 67, "fr": "Machopeur"}, {"id": 68, "fr": "Mackogneur"}, {"id": 69, "fr": "Chétiflor"},
    {"id": 70, "fr": "Boustiflor"}, {"id": 71, "fr": "Empiflor"}, {"id": 72, "fr": "Tentacool"},
    {"id": 73, "fr": "Tentacruel"}, {"id": 74, "fr": "Racaillou"}, {"id": 75, "fr": "Gravalanch"},
    {"id": 76, "fr": "Grolem"}, {"id": 77, "fr": "Ponyta"}, {"id": 78, "fr": "Galopa"},
    {"id": 79, "fr": "Ramoloss"}, {"id": 80, "fr": "Flagadoss"}, {"id": 81, "fr": "Magnéti"},
    {"id": 82, "fr": "Magnéton"}, {"id": 83, "fr": "Canarticho"}, {"id": 84, "fr": "Doduo"},
    {"id": 85, "fr": "Dodrio"}, {"id": 86, "fr": "Otaria"}, {"id": 87, "fr": "Lamantine"},
    {"id": 88, "fr": "Tadmorv"}, {"id": 89, "fr": "Grotadmorv"}, {"id": 90, "fr": "Kokiyas"},
    {"id": 91, "fr": "Crustabri"}, {"id": 92, "fr": "Fantominus"}, {"id": 93, "fr": "Spectrum"},
    {"id": 94, "fr": "Ectoplasma"}, {"id": 95, "fr": "Onix"}, {"id": 96, "fr": "Soporifik"},
    {"id": 97, "fr": "Hypnomade"}, {"id": 98, "fr": "Krabby"}, {"id": 99, "fr": "Krabboss"},
    {"id": 100, "fr": "Voltorbe"}, {"id": 101, "fr": "Électrode"}, {"id": 102, "fr": "Noeunoeuf"},
    {"id": 103, "fr": "Noadkoko"}, {"id": 104, "fr": "Osselait"}, {"id": 105, "fr": "Ossatueur"},
    {"id": 106, "fr": "Kicklee"}, {"id": 107, "fr": "Tygnon"}, {"id": 108, "fr": "Excelangue"},
    {"id": 109, "fr": "Smogo"}, {"id": 110, "fr": "Smogogo"}, {"id": 111, "fr": "Rhinocorne"},
    {"id": 112, "fr": "Rhinoféros"}, {"id": 113, "fr": "Leveinard"}, {"id": 114, "fr": "Saquedeneu"},
    {"id": 115, "fr": "Kangourex"}, {"id": 116, "fr": "Hypotrempe"}, {"id": 117, "fr": "Hypocéan"},
    {"id": 118, "fr": "Poissirène"}, {"id": 119, "fr": "Poissoroy"}, {"id": 120, "fr": "Stari"},
    {"id": 121, "fr": "Staross"}, {"id": 122, "fr": "M. Mime"}, {"id": 123, "fr": "Insécateur"},
    {"id": 124, "fr": "Lippoutou"}, {"id": 125, "fr": "Élektek"}, {"id": 126, "fr": "Magmar"},
    {"id": 127, "fr": "Scarabrute"}, {"id": 128, "fr": "Tauros"}, {"id": 129, "fr": "Magicarpe"},
    {"id": 130, "fr": "Léviator"}, {"id": 131, "fr": "Lokhlass"}, {"id": 132, "fr": "Métamorph"},
    {"id": 133, "fr": "Évoli"}, {"id": 134, "fr": "Aquali"}, {"id": 135, "fr": "Voltali"},
    {"id": 136, "fr": "Pyroli"}, {"id": 137, "fr": "Porygon"}, {"id": 138, "fr": "Amonita"},
    {"id": 139, "fr": "Amonistar"}, {"id": 140, "fr": "Kabuto"}, {"id": 141, "fr": "Kabutops"},
    {"id": 142, "fr": "Ptéra"}, {"id": 143, "fr": "Ronflex"}, {"id": 144, "fr": "Artikodin"},
    {"id": 145, "fr": "Électhor"}, {"id": 146, "fr": "Sulfura"}, {"id": 147, "fr": "Minidraco"},
    {"id": 148, "fr": "Draco"}, {"id": 149, "fr": "Dracolosse"}, {"id": 150, "fr": "Mewtwo"},
    {"id": 151, "fr": "Mew"},
    # ═══════════════════════════════════════
    # GEN 2 — Johto (152–251)
    # ═══════════════════════════════════════
    {"id": 152, "fr": "Germignon"}, {"id": 153, "fr": "Macronium"}, {"id": 154, "fr": "Méganium"},
    {"id": 155, "fr": "Héricendre"}, {"id": 156, "fr": "Feurisson"}, {"id": 157, "fr": "Typhlosion"},
    {"id": 158, "fr": "Kaiminus"}, {"id": 159, "fr": "Crocrodil"}, {"id": 160, "fr": "Aligatueur"},
    {"id": 161, "fr": "Fouinette"}, {"id": 162, "fr": "Fouinar"}, {"id": 163, "fr": "Hoothoot"},
    {"id": 164, "fr": "Noarfang"}, {"id": 165, "fr": "Coxy"}, {"id": 166, "fr": "Coxyclaque"},
    {"id": 167, "fr": "Mimigal"}, {"id": 168, "fr": "Migalos"}, {"id": 169, "fr": "Nostenfer"},
    {"id": 170, "fr": "Loupio"}, {"id": 171, "fr": "Lanturn"}, {"id": 172, "fr": "Pichu"},
    {"id": 173, "fr": "Mélo"}, {"id": 174, "fr": "Toudoudou"}, {"id": 175, "fr": "Togepi"},
    {"id": 176, "fr": "Togetic"}, {"id": 177, "fr": "Natu"}, {"id": 178, "fr": "Xatu"},
    {"id": 179, "fr": "Wattouat"}, {"id": 180, "fr": "Lainergie"}, {"id": 181, "fr": "Pharamp"},
    {"id": 182, "fr": "Joliflor"}, {"id": 183, "fr": "Marill"}, {"id": 184, "fr": "Azumarill"},
    {"id": 185, "fr": "Simularbre"}, {"id": 186, "fr": "Tarpaud"}, {"id": 187, "fr": "Granivol"},
    {"id": 188, "fr": "Floravol"}, {"id": 189, "fr": "Cotovol"}, {"id": 190, "fr": "Capumain"},
    {"id": 191, "fr": "Tournegrin"}, {"id": 192, "fr": "Héliatronc"}, {"id": 193, "fr": "Yanma"},
    {"id": 194, "fr": "Axoloto"}, {"id": 195, "fr": "Maraiste"}, {"id": 196, "fr": "Mentali"},
    {"id": 197, "fr": "Noctali"}, {"id": 198, "fr": "Cornèbre"}, {"id": 199, "fr": "Roigada"},
    {"id": 200, "fr": "Feuforêve"}, {"id": 201, "fr": "Zarbi"}, {"id": 202, "fr": "Qulbutoké"},
    {"id": 203, "fr": "Girafarig"}, {"id": 204, "fr": "Pomdepik"}, {"id": 205, "fr": "Foretress"},
    {"id": 206, "fr": "Insolourdo"}, {"id": 207, "fr": "Scorplane"}, {"id": 208, "fr": "Steelix"},
    {"id": 209, "fr": "Snubbull"}, {"id": 210, "fr": "Granbull"}, {"id": 211, "fr": "Qwilfish"},
    {"id": 212, "fr": "Cizayox"}, {"id": 213, "fr": "Caratroc"}, {"id": 214, "fr": "Scarhino"},
    {"id": 215, "fr": "Farfuret"}, {"id": 216, "fr": "Teddiursa"}, {"id": 217, "fr": "Ursaring"},
    {"id": 218, "fr": "Limagma"}, {"id": 219, "fr": "Volcaropod"}, {"id": 220, "fr": "Marcacrin"},
    {"id": 221, "fr": "Cochignon"}, {"id": 222, "fr": "Corayon"}, {"id": 223, "fr": "Rémoraid"},
    {"id": 224, "fr": "Octillery"}, {"id": 225, "fr": "Cadoizo"}, {"id": 226, "fr": "Démanta"},
    {"id": 227, "fr": "Airmure"}, {"id": 228, "fr": "Malosse"}, {"id": 229, "fr": "Démolosse"},
    {"id": 230, "fr": "Hyporoi"}, {"id": 231, "fr": "Phanpy"}, {"id": 232, "fr": "Donphan"},
    {"id": 233, "fr": "Porygon2"}, {"id": 234, "fr": "Cerfrousse"}, {"id": 235, "fr": "Queulorior"},
    {"id": 236, "fr": "Debugant"}, {"id": 237, "fr": "Kapoera"}, {"id": 238, "fr": "Lippouti"},
    {"id": 239, "fr": "Élekid"}, {"id": 240, "fr": "Magby"}, {"id": 241, "fr": "Écrémeuh"},
    {"id": 242, "fr": "Leuphorie"}, {"id": 243, "fr": "Raikou"}, {"id": 244, "fr": "Entei"},
    {"id": 245, "fr": "Suicune"}, {"id": 246, "fr": "Embrylex"}, {"id": 247, "fr": "Ymphect"},
    {"id": 248, "fr": "Tyranocif"}, {"id": 249, "fr": "Lugia"}, {"id": 250, "fr": "Ho-Oh"},
    {"id": 251, "fr": "Celebi"},
    # ═══════════════════════════════════════
    # GEN 3 — Hoenn (252–386)
    # ═══════════════════════════════════════
    {"id": 252, "fr": "Arcko"}, {"id": 253, "fr": "Massko"}, {"id": 254, "fr": "Jungko"},
    {"id": 255, "fr": "Poussifeu"}, {"id": 256, "fr": "Galifeu"}, {"id": 257, "fr": "Braségali"},
    {"id": 258, "fr": "Gobou"}, {"id": 259, "fr": "Flobio"}, {"id": 260, "fr": "Laggron"},
    {"id": 261, "fr": "Medhyèna"}, {"id": 262, "fr": "Grahyèna"}, {"id": 263, "fr": "Zigzaton"},
    {"id": 264, "fr": "Linéon"}, {"id": 265, "fr": "Chenipotte"}, {"id": 266, "fr": "Armulys"},
    {"id": 267, "fr": "Charmillon"}, {"id": 268, "fr": "Blindalys"}, {"id": 269, "fr": "Papinox"},
    {"id": 270, "fr": "Nénupiot"}, {"id": 271, "fr": "Lombre"}, {"id": 272, "fr": "Ludicolo"},
    {"id": 273, "fr": "Grainipiot"}, {"id": 274, "fr": "Pifeuil"}, {"id": 275, "fr": "Tengalice"},
    {"id": 276, "fr": "Nirondelle"}, {"id": 277, "fr": "Hélédelle"}, {"id": 278, "fr": "Goélise"},
    {"id": 279, "fr": "Bekipan"}, {"id": 280, "fr": "Tarsal"}, {"id": 281, "fr": "Kirlia"},
    {"id": 282, "fr": "Gardevoir"}, {"id": 283, "fr": "Arakdo"}, {"id": 284, "fr": "Maskadra"},
    {"id": 285, "fr": "Balignon"}, {"id": 286, "fr": "Chapignon"}, {"id": 287, "fr": "Parecool"},
    {"id": 288, "fr": "Vigoroth"}, {"id": 289, "fr": "Monaflèmit"}, {"id": 290, "fr": "Ningale"},
    {"id": 291, "fr": "Ninjask"}, {"id": 292, "fr": "Munja"}, {"id": 293, "fr": "Chuchmur"},
    {"id": 294, "fr": "Ramboum"}, {"id": 295, "fr": "Brouhabam"}, {"id": 296, "fr": "Makuhita"},
    {"id": 297, "fr": "Hariyama"}, {"id": 298, "fr": "Azurill"}, {"id": 299, "fr": "Tarinor"},
    {"id": 300, "fr": "Skitty"}, {"id": 301, "fr": "Delcatty"}, {"id": 303, "fr": "Mysdibule"},
    {"id": 302, "fr": "Ténéfix"}, {"id": 304, "fr": "Galekid"}, {"id": 305, "fr": "Galegon"},
    {"id": 306, "fr": "Galeking"}, {"id": 307, "fr": "Méditikka"}, {"id": 308, "fr": "Médicharme"},
    {"id": 309, "fr": "Dynavolt"}, {"id": 310, "fr": "Élecsprint"}, {"id": 311, "fr": "Posipi"},
    {"id": 312, "fr": "Négapi"}, {"id": 313, "fr": "Muciole"}, {"id": 314, "fr": "Lumivole"},
    {"id": 315, "fr": "Rosélia"}, {"id": 316, "fr": "Gloupti"}, {"id": 317, "fr": "Avaltout"},
    {"id": 318, "fr": "Carvanha"}, {"id": 319, "fr": "Sharpedo"}, {"id": 320, "fr": "Wailmer"},
    {"id": 321, "fr": "Wailord"}, {"id": 322, "fr": "Chamallot"}, {"id": 323, "fr": "Camérupt"},
    {"id": 324, "fr": "Chartor"}, {"id": 325, "fr": "Spoink"}, {"id": 326, "fr": "Groret"},
    {"id": 327, "fr": "Spinda"}, {"id": 328, "fr": "Kraknoix"}, {"id": 329, "fr": "Vibraninf"},
    {"id": 330, "fr": "Libégon"}, {"id": 331, "fr": "Cacnea"}, {"id": 332, "fr": "Cacturne"},
    {"id": 333, "fr": "Tylton"}, {"id": 334, "fr": "Altaria"}, {"id": 335, "fr": "Mangriff"},
    {"id": 336, "fr": "Séviper"}, {"id": 337, "fr": "Séléroc"}, {"id": 338, "fr": "Solaroc"},
    {"id": 339, "fr": "Barloche"}, {"id": 340, "fr": "Barbicha"}, {"id": 341, "fr": "Écrapince"},
    {"id": 342, "fr": "Colhomard"}, {"id": 343, "fr": "Balbuto"}, {"id": 344, "fr": "Kaorine"},
    {"id": 345, "fr": "Lilia"}, {"id": 346, "fr": "Vacilys"}, {"id": 347, "fr": "Anorith"},
    {"id": 348, "fr": "Armaldo"}, {"id": 349, "fr": "Barpau"}, {"id": 350, "fr": "Milobellus"},
    {"id": 351, "fr": "Morphéo"}, {"id": 352, "fr": "Kecleon"}, {"id": 353, "fr": "Polichombr"},
    {"id": 354, "fr": "Branette"}, {"id": 355, "fr": "Skelénox"}, {"id": 356, "fr": "Téraclope"},
    {"id": 357, "fr": "Tropius"}, {"id": 358, "fr": "Éoko"}, {"id": 359, "fr": "Absol"},
    {"id": 360, "fr": "Okéoké"}, {"id": 361, "fr": "Stalgamin"}, {"id": 362, "fr": "Oniglali"},
    {"id": 363, "fr": "Obalie"}, {"id": 364, "fr": "Phogleur"}, {"id": 365, "fr": "Kaimorse"},
    {"id": 366, "fr": "Coquiperl"}, {"id": 367, "fr": "Serpang"}, {"id": 368, "fr": "Rosabyss"},
    {"id": 369, "fr": "Relicanth"}, {"id": 370, "fr": "Lovdisc"}, {"id": 371, "fr": "Draby"},
    {"id": 372, "fr": "Drackhaus"}, {"id": 373, "fr": "Drattak"}, {"id": 374, "fr": "Terhal"},
    {"id": 375, "fr": "Métang"}, {"id": 376, "fr": "Métalosse"}, {"id": 377, "fr": "Regirock"},
    {"id": 378, "fr": "Regice"}, {"id": 379, "fr": "Registeel"}, {"id": 380, "fr": "Latias"},
    {"id": 381, "fr": "Latios"}, {"id": 382, "fr": "Kyogre"}, {"id": 383, "fr": "Groudon"},
    {"id": 384, "fr": "Rayquaza"}, {"id": 385, "fr": "Jirachi"}, {"id": 386, "fr": "Deoxys"},
    # ═══════════════════════════════════════
    # GEN 4 — Sinnoh (387–493)
    # ═══════════════════════════════════════
    {"id": 387, "fr": "Tortipouss"}, {"id": 388, "fr": "Boskara"}, {"id": 389, "fr": "Torterra"},
    {"id": 390, "fr": "Ouisticram"}, {"id": 391, "fr": "Chimpenfeu"}, {"id": 392, "fr": "Simiabraz"},
    {"id": 393, "fr": "Tiplouf"}, {"id": 394, "fr": "Prinplouf"}, {"id": 395, "fr": "Pingoléon"},
    {"id": 396, "fr": "Étourmi"}, {"id": 397, "fr": "Étourvol"}, {"id": 398, "fr": "Étouraptor"},
    {"id": 399, "fr": "Keunotor"}, {"id": 400, "fr": "Castorno"}, {"id": 401, "fr": "Crikzik"},
    {"id": 402, "fr": "Mélokrik"}, {"id": 403, "fr": "Lixy"}, {"id": 404, "fr": "Luxio"},
    {"id": 405, "fr": "Luxray"}, {"id": 406, "fr": "Rozbouton"}, {"id": 407, "fr": "Roserade"},
    {"id": 408, "fr": "Kranidos"}, {"id": 409, "fr": "Charkos"}, {"id": 410, "fr": "Dinoclier"},
    {"id": 411, "fr": "Bastiodon"}, {"id": 412, "fr": "Cheniti"}, {"id": 413, "fr": "Cheniselle"},
    {"id": 414, "fr": "Papilord"}, {"id": 415, "fr": "Apitrini"}, {"id": 416, "fr": "Apireine"},
    {"id": 417, "fr": "Pachirisu"}, {"id": 418, "fr": "Mustébouée"}, {"id": 419, "fr": "Mustéflott"},
    {"id": 420, "fr": "Ceribou"}, {"id": 421, "fr": "Ceriflor"}, {"id": 422, "fr": "Sancoki"},
    {"id": 423, "fr": "Tritosor"}, {"id": 424, "fr": "Capidextre"}, {"id": 425, "fr": "Baudrive"},
    {"id": 426, "fr": "Grodrive"}, {"id": 427, "fr": "Laporeille"}, {"id": 428, "fr": "Lockpin"},
    {"id": 429, "fr": "Magirêve"}, {"id": 430, "fr": "Corboss"}, {"id": 431, "fr": "Chaglam"},
    {"id": 432, "fr": "Chaffreux"}, {"id": 433, "fr": "Korillon"}, {"id": 434, "fr": "Moufouette"},
    {"id": 435, "fr": "Moufflair"}, {"id": 436, "fr": "Archéomire"}, {"id": 437, "fr": "Archéodong"},
    {"id": 438, "fr": "Manzaï"}, {"id": 439, "fr": "Mime Jr."}, {"id": 440, "fr": "Ptiravi"},
    {"id": 441, "fr": "Pijako"}, {"id": 442, "fr": "Spiritomb"}, {"id": 443, "fr": "Griknot"},
    {"id": 444, "fr": "Carmache"}, {"id": 445, "fr": "Carchacrok"}, {"id": 446, "fr": "Goinfrex"},
    {"id": 447, "fr": "Riolu"}, {"id": 448, "fr": "Lucario"}, {"id": 449, "fr": "Hippopotas"},
    {"id": 450, "fr": "Hippodocus"}, {"id": 451, "fr": "Rapion"}, {"id": 452, "fr": "Drascore"},
    {"id": 453, "fr": "Cradopaud"}, {"id": 454, "fr": "Coatox"}, {"id": 455, "fr": "Vortente"},
    {"id": 456, "fr": "Écayon"}, {"id": 457, "fr": "Luminéon"}, {"id": 458, "fr": "Babimanta"},
    {"id": 459, "fr": "Blizzi"}, {"id": 460, "fr": "Blizzaroi"}, {"id": 461, "fr": "Dimoret"},
    {"id": 462, "fr": "Magnézone"}, {"id": 463, "fr": "Coudlangue"}, {"id": 464, "fr": "Rhinastoc"},
    {"id": 465, "fr": "Bouldeneu"}, {"id": 466, "fr": "Élekable"}, {"id": 467, "fr": "Maganon"},
    {"id": 468, "fr": "Togekiss"}, {"id": 469, "fr": "Yanmega"}, {"id": 470, "fr": "Phyllali"},
    {"id": 471, "fr": "Givrali"}, {"id": 472, "fr": "Scorvol"}, {"id": 473, "fr": "Mammochon"},
    {"id": 474, "fr": "Porygon-Z"}, {"id": 475, "fr": "Gallame"}, {"id": 476, "fr": "Tarinorme"},
    {"id": 477, "fr": "Noctunoir"}, {"id": 478, "fr": "Momartik"}, {"id": 479, "fr": "Motisma"},
    {"id": 480, "fr": "Créhelf"}, {"id": 481, "fr": "Créfollet"}, {"id": 482, "fr": "Créfadet"},
    {"id": 483, "fr": "Dialga"}, {"id": 484, "fr": "Palkia"}, {"id": 485, "fr": "Heatran"},
    {"id": 486, "fr": "Regigigas"}, {"id": 487, "fr": "Giratina"}, {"id": 488, "fr": "Cresselia"},
    {"id": 489, "fr": "Phione"}, {"id": 490, "fr": "Manaphy"}, {"id": 491, "fr": "Darkrai"},
    {"id": 492, "fr": "Shaymin"}, {"id": 493, "fr": "Arceus"},
    # ═══════════════════════════════════════
    # GEN 5 — Unys (494–649)
    # ═══════════════════════════════════════
    {"id": 494, "fr": "Victini"}, {"id": 495, "fr": "Vipélierre"}, {"id": 496, "fr": "Lianaja"},
    {"id": 497, "fr": "Majaspic"}, {"id": 498, "fr": "Gruikui"}, {"id": 499, "fr": "Grotichon"},
    {"id": 500, "fr": "Roitiflam"}, {"id": 501, "fr": "Moustillon"}, {"id": 502, "fr": "Mateloutre"},
    {"id": 503, "fr": "Clamiral"}, {"id": 504, "fr": "Ratentif"}, {"id": 505, "fr": "Miradar"},
    {"id": 506, "fr": "Ponchiot"}, {"id": 507, "fr": "Ponchien"}, {"id": 508, "fr": "Mastouffe"},
    {"id": 509, "fr": "Chacripan"}, {"id": 510, "fr": "Léopardus"}, {"id": 511, "fr": "Feuillajou"},
    {"id": 512, "fr": "Feuiloutan"}, {"id": 513, "fr": "Flamajou"}, {"id": 514, "fr": "Flamoutan"},
    {"id": 515, "fr": "Flotajou"}, {"id": 516, "fr": "Flotoutan"}, {"id": 517, "fr": "Munna"},
    {"id": 518, "fr": "Mushana"}, {"id": 519, "fr": "Poichigeon"}, {"id": 520, "fr": "Colombeau"},
    {"id": 521, "fr": "Déflaisan"}, {"id": 522, "fr": "Zébibron"}, {"id": 523, "fr": "Zéblitz"},
    {"id": 524, "fr": "Nodulithe"}, {"id": 525, "fr": "Géolithe"}, {"id": 526, "fr": "Gigalithe"},
    {"id": 527, "fr": "Chovsourir"}, {"id": 528, "fr": "Rhinolove"}, {"id": 529, "fr": "Rototaupe"},
    {"id": 530, "fr": "Minotaupe"}, {"id": 531, "fr": "Nanméouïe"}, {"id": 532, "fr": "Charpenti"},
    {"id": 533, "fr": "Ouvrifier"}, {"id": 534, "fr": "Bétochef"}, {"id": 535, "fr": "Tritonde"},
    {"id": 536, "fr": "Batracné"}, {"id": 537, "fr": "Crapustule"}, {"id": 538, "fr": "Judokrak"},
    {"id": 539, "fr": "Karaclée"}, {"id": 540, "fr": "Larveyette"}, {"id": 541, "fr": "Couverdure"},
    {"id": 542, "fr": "Manternel"}, {"id": 543, "fr": "Venipatte"}, {"id": 544, "fr": "Scobolide"},
    {"id": 545, "fr": "Brutapode"}, {"id": 546, "fr": "Doudouvet"}, {"id": 547, "fr": "Farfaduvet"},
    {"id": 548, "fr": "Chlorobule"}, {"id": 549, "fr": "Fragilady"}, {"id": 550, "fr": "Bargantua"},
    {"id": 551, "fr": "Mascaïman"}, {"id": 552, "fr": "Escroco"}, {"id": 553, "fr": "Crocorible"},
    {"id": 554, "fr": "Darumarond"}, {"id": 555, "fr": "Darumacho"}, {"id": 556, "fr": "Maracachi"},
    {"id": 557, "fr": "Crabicoque"}, {"id": 558, "fr": "Crabaraque"}, {"id": 559, "fr": "Baggiguane"},
    {"id": 560, "fr": "Baggaïd"}, {"id": 561, "fr": "Cryptéro"}, {"id": 562, "fr": "Tutafeh"},
    {"id": 563, "fr": "Tutankafer"}, {"id": 564, "fr": "Carapagos"}, {"id": 565, "fr": "Mégapagos"},
    {"id": 566, "fr": "Arkéapti"}, {"id": 567, "fr": "Aéroptéryx"}, {"id": 568, "fr": "Miamiasme"},
    {"id": 569, "fr": "Miasmax"}, {"id": 570, "fr": "Zorua"}, {"id": 571, "fr": "Zoroark"},
    {"id": 572, "fr": "Chinchidou"}, {"id": 573, "fr": "Pashmilla"}, {"id": 574, "fr": "Scrutella"},
    {"id": 575, "fr": "Mesmérella"}, {"id": 576, "fr": "Sidérella"}, {"id": 577, "fr": "Nucléos"},
    {"id": 578, "fr": "Méios"}, {"id": 579, "fr": "Symbios"}, {"id": 580, "fr": "Couaneton"},
    {"id": 581, "fr": "Lakmécygne"}, {"id": 582, "fr": "Sorbébé"}, {"id": 583, "fr": "Sorboul"},
    {"id": 584, "fr": "Sorbouboul"}, {"id": 585, "fr": "Vivaldaim"}, {"id": 586, "fr": "Haydaim"},
    {"id": 587, "fr": "Emolga"}, {"id": 588, "fr": "Carabing"}, {"id": 589, "fr": "Lançargot"},
    {"id": 590, "fr": "Trompignon"}, {"id": 591, "fr": "Gaulet"}, {"id": 592, "fr": "Viskuse"},
    {"id": 593, "fr": "Moyade"}, {"id": 594, "fr": "Mamanbo"}, {"id": 595, "fr": "Statitik"},
    {"id": 596, "fr": "Mygavolt"}, {"id": 597, "fr": "Grindur"}, {"id": 598, "fr": "Noacier"},
    {"id": 599, "fr": "Tic"}, {"id": 600, "fr": "Clic"}, {"id": 601, "fr": "Cliticlic"},
    {"id": 602, "fr": "Anchwatt"}, {"id": 603, "fr": "Lampéroie"}, {"id": 604, "fr": "Ohmassacre"},
    {"id": 605, "fr": "Lewsor"}, {"id": 606, "fr": "Neitram"}, {"id": 607, "fr": "Funécire"},
    {"id": 608, "fr": "Mélancolux"}, {"id": 609, "fr": "Lugulabre"}, {"id": 610, "fr": "Coupenotte"},
    {"id": 611, "fr": "Incisache"}, {"id": 612, "fr": "Tranchodon"}, {"id": 613, "fr": "Polarhume"},
    {"id": 614, "fr": "Polagriffe"}, {"id": 615, "fr": "Hexagel"}, {"id": 616, "fr": "Escargaume"},
    {"id": 617, "fr": "Limaspeed"}, {"id": 618, "fr": "Limonde"}, {"id": 619, "fr": "Kungfouine"},
    {"id": 620, "fr": "Shaofouine"}, {"id": 621, "fr": "Drakkarmin"}, {"id": 622, "fr": "Gringolem"},
    {"id": 623, "fr": "Golemastoc"}, {"id": 624, "fr": "Scalpion"}, {"id": 625, "fr": "Scalproie"},
    {"id": 626, "fr": "Frison"}, {"id": 627, "fr": "Furaiglon"}, {"id": 628, "fr": "Gueriaigle"},
    {"id": 629, "fr": "Vostourno"}, {"id": 630, "fr": "Vaututrice"}, {"id": 631, "fr": "Aflamanoir"},
    {"id": 632, "fr": "Fermite"}, {"id": 633, "fr": "Solochi"}, {"id": 634, "fr": "Diamat"},
    {"id": 635, "fr": "Trioxhydre"}, {"id": 636, "fr": "Pyronille"}, {"id": 637, "fr": "Pyrax"},
    {"id": 638, "fr": "Cobaltium"}, {"id": 639, "fr": "Terrakium"}, {"id": 640, "fr": "Viridium"},
    {"id": 641, "fr": "Boréas"}, {"id": 642, "fr": "Fulguris"}, {"id": 643, "fr": "Reshiram"},
    {"id": 644, "fr": "Zekrom"}, {"id": 645, "fr": "Démétéros"}, {"id": 646, "fr": "Kyurem"},
    {"id": 647, "fr": "Keldeo"}, {"id": 648, "fr": "Meloetta"}, {"id": 649, "fr": "Genesect"},
    # ═══════════════════════════════════════
    # GEN 6 — Kalos (650–721)
    # ═══════════════════════════════════════
    {"id": 650, "fr": "Marisson"}, {"id": 651, "fr": "Boguérisse"}, {"id": 652, "fr": "Blindépique"},
    {"id": 653, "fr": "Feunnec"}, {"id": 654, "fr": "Roussil"}, {"id": 655, "fr": "Goupelin"},
    {"id": 656, "fr": "Grenousse"}, {"id": 657, "fr": "Croâporal"}, {"id": 658, "fr": "Amphinobi"},
    {"id": 659, "fr": "Sapereau"}, {"id": 660, "fr": "Excavarenne"}, {"id": 661, "fr": "Passerouge"},
    {"id": 662, "fr": "Braisillon"}, {"id": 663, "fr": "Flambusard"}, {"id": 664, "fr": "Lépidonille"},
    {"id": 665, "fr": "Pérégrain"}, {"id": 666, "fr": "Prismillon"}, {"id": 667, "fr": "Hélionceau"},
    {"id": 668, "fr": "Némélios"}, {"id": 676, "fr": "Couafarel"}, {"id": 669, "fr": "Flabébé"},
    {"id": 670, "fr": "Floette"}, {"id": 671, "fr": "Florges"}, {"id": 672, "fr": "Cabriolaine"},
    {"id": 673, "fr": "Chevroum"}, {"id": 674, "fr": "Pandespiègle"}, {"id": 675, "fr": "Pandarbare"},
    {"id": 677, "fr": "Psytigri"}, {"id": 678, "fr": "Mistigrix"}, {"id": 679, "fr": "Monorpale"},
    {"id": 680, "fr": "Dimoclès"}, {"id": 681, "fr": "Exagide"}, {"id": 684, "fr": "Sucroquin"},
    {"id": 685, "fr": "Cupcanaille"}, {"id": 682, "fr": "Fluvetin"}, {"id": 683, "fr": "Cocotine"},
    {"id": 686, "fr": "Sepiatop"}, {"id": 687, "fr": "Sepiatroce"}, {"id": 688, "fr": "Opermine"},
    {"id": 689, "fr": "Golgopathe"}, {"id": 690, "fr": "Venalgue"}, {"id": 691, "fr": "Kravarech"},
    {"id": 692, "fr": "Flingouste"}, {"id": 693, "fr": "Gamblast"}, {"id": 694, "fr": "Galvaran"},
    {"id": 695, "fr": "Iguolta"}, {"id": 696, "fr": "Ptyranidur"}, {"id": 697, "fr": "Rexillius"},
    {"id": 698, "fr": "Amagara"}, {"id": 699, "fr": "Dragmara"}, {"id": 700, "fr": "Nymphali"},
    {"id": 701, "fr": "Brutalibré"}, {"id": 702, "fr": "Dedenne"}, {"id": 703, "fr": "Strassie"},
    {"id": 704, "fr": "Mucuscule"}, {"id": 705, "fr": "Colimucus"}, {"id": 706, "fr": "Muplodocus"},
    {"id": 707, "fr": "Trousselin"}, {"id": 708, "fr": "Brocélôme"}, {"id": 709, "fr": "Desséliande"},
    {"id": 710, "fr": "Pitrouille"}, {"id": 711, "fr": "Banshitrouye"}, {"id": 712, "fr": "Grelaçon"},
    {"id": 713, "fr": "Séracrawl"}, {"id": 714, "fr": "Sonistrelle"}, {"id": 715, "fr": "Bruyverne"},
    {"id": 716, "fr": "Xerneas"}, {"id": 717, "fr": "Yveltal"}, {"id": 718, "fr": "Zygarde"},
    {"id": 719, "fr": "Diancie"}, {"id": 720, "fr": "Hoopa"}, {"id": 721, "fr": "Volcanion"},
    # ═══════════════════════════════════════
    # GEN 7 — Alola (722–809)
    # ═══════════════════════════════════════
    {"id": 722, "fr": "Brindibou"}, {"id": 723, "fr": "Efflèche"}, {"id": 724, "fr": "Archéduc"},
    {"id": 725, "fr": "Flamiaou"}, {"id": 726, "fr": "Matoufeu"}, {"id": 727, "fr": "Félinferno"},
    {"id": 728, "fr": "Otaquin"}, {"id": 729, "fr": "Otarlette"}, {"id": 730, "fr": "Oratoria"},
    {"id": 731, "fr": "Picassaut"}, {"id": 732, "fr": "Piclairon"}, {"id": 733, "fr": "Bazoucan"},
    {"id": 734, "fr": "Manglouton"}, {"id": 735, "fr": "Argouste"}, {"id": 736, "fr": "Larvibule"},
    {"id": 737, "fr": "Chrysapile"}, {"id": 738, "fr": "Lucanon"}, {"id": 739, "fr": "Crabagarre"},
    {"id": 740, "fr": "Crabominable"}, {"id": 741, "fr": "Plumeline"}, {"id": 742, "fr": "Bombydou"},
    {"id": 743, "fr": "Rubombelle"}, {"id": 744, "fr": "Rocabot"}, {"id": 745, "fr": "Lougaroc"},
    {"id": 746, "fr": "Froussardine"}, {"id": 747, "fr": "Vorastérie"}, {"id": 748, "fr": "Prédastérie"},
    {"id": 749, "fr": "Tiboudet"}, {"id": 750, "fr": "Bourrinos"}, {"id": 751, "fr": "Araqua"},
    {"id": 752, "fr": "Tarenbulle"}, {"id": 753, "fr": "Mimantis"}, {"id": 754, "fr": "Floramantis"},
    {"id": 755, "fr": "Spododo"}, {"id": 756, "fr": "Lampignon"}, {"id": 757, "fr": "Tritox"},
    {"id": 758, "fr": "Malamandre"}, {"id": 759, "fr": "Nounourson"}, {"id": 760, "fr": "Chelours"},
    {"id": 761, "fr": "Croquine"}, {"id": 762, "fr": "Candine"}, {"id": 763, "fr": "Sucreine"},
    {"id": 764, "fr": "Guérilande"}, {"id": 765, "fr": "Gouroutan"}, {"id": 766, "fr": "Quartermac"},
    {"id": 767, "fr": "Sovkipou"}, {"id": 768, "fr": "Sarmuraï"}, {"id": 769, "fr": "Bacabouh"},
    {"id": 770, "fr": "Trépassable"}, {"id": 771, "fr": "Concombaffe"}, {"id": 772, "fr": "Type:0"},
    {"id": 773, "fr": "Silvallié"}, {"id": 774, "fr": "Météno"}, {"id": 775, "fr": "Dodoala"},
    {"id": 776, "fr": "Boumata"}, {"id": 777, "fr": "Togedemaru"}, {"id": 778, "fr": "Mimiqui"},
    {"id": 779, "fr": "Denticrisse"}, {"id": 780, "fr": "Draïeul"}, {"id": 781, "fr": "Sinistrail"},
    {"id": 782, "fr": "Bébécaille"}, {"id": 783, "fr": "Écaïd"}, {"id": 784, "fr": "Ékaïser"},
    {"id": 785, "fr": "Tokorico"}, {"id": 786, "fr": "Tokopiyon"}, {"id": 787, "fr": "Tokotoro"},
    {"id": 788, "fr": "Tokopisco"}, {"id": 789, "fr": "Cosmog"}, {"id": 790, "fr": "Cosmovum"},
    {"id": 791, "fr": "Solgaleo"}, {"id": 792, "fr": "Lunala"}, {"id": 793, "fr": "Zéroïd"},
    {"id": 794, "fr": "Mouscoto"}, {"id": 795, "fr": "Cancrelove"}, {"id": 796, "fr": "Câblifère"},
    {"id": 797, "fr": "Bamboiselle"}, {"id": 798, "fr": "Katagami"}, {"id": 799, "fr": "Engloutyran"},
    {"id": 800, "fr": "Necrozma"}, {"id": 801, "fr": "Magearna"}, {"id": 802, "fr": "Marshadow"},
    {"id": 803, "fr": "Vémini"}, {"id": 804, "fr": "Mandrillon"}, {"id": 805, "fr": "Ama-Ama"},
    {"id": 806, "fr": "Pierroteknik"}, {"id": 807, "fr": "Zeraora"}, {"id": 808, "fr": "Meltan"},
    {"id": 809, "fr": "Melmetal"},
    # ═══════════════════════════════════════
    # GEN 8 — Galar & Hisui (810–905)
    # ═══════════════════════════════════════
    {"id": 810, "fr": "Ouistempo"}, {"id": 811, "fr": "Badabouin"}, {"id": 812, "fr": "Gorythmic"},
    {"id": 813, "fr": "Flambino"}, {"id": 814, "fr": "Lapyro"}, {"id": 815, "fr": "Pyrobut"},
    {"id": 816, "fr": "Larméléon"}, {"id": 817, "fr": "Arrozard"}, {"id": 818, "fr": "Lézargus"},
    {"id": 819, "fr": "Rongourmand"}, {"id": 820, "fr": "Rongrigou"}, {"id": 821, "fr": "Minisange"},
    {"id": 822, "fr": "Bleuseille"}, {"id": 823, "fr": "Corvaillus"}, {"id": 824, "fr": "Larvadar"},
    {"id": 825, "fr": "Coléodôme"}, {"id": 826, "fr": "Astronelle"}, {"id": 827, "fr": "Goupilou"},
    {"id": 828, "fr": "Roublenard"}, {"id": 829, "fr": "Tournicoton"}, {"id": 830, "fr": "Blancoton"},
    {"id": 831, "fr": "Moumouton"}, {"id": 832, "fr": "Moumouflon"}, {"id": 833, "fr": "Khélocrok"},
    {"id": 834, "fr": "Torgamord"}, {"id": 835, "fr": "Voltoutou"}, {"id": 836, "fr": "Fulgudog"},
    {"id": 837, "fr": "Charbi"}, {"id": 838, "fr": "Wagomine"}, {"id": 839, "fr": "Monthracite"},
    {"id": 840, "fr": "Verpom"}, {"id": 841, "fr": "Pomdrapi"}, {"id": 842, "fr": "Dratatin"},
    {"id": 843, "fr": "Dunaja"}, {"id": 844, "fr": "Dunaconda"}, {"id": 845, "fr": "Nigosier"},
    {"id": 846, "fr": "Embrochet"}, {"id": 847, "fr": "Hastacuda"}, {"id": 848, "fr": "Toxizap"},
    {"id": 849, "fr": "Salarsen"}, {"id": 850, "fr": "Grillepattes"}, {"id": 851, "fr": "Scolocendre"},
    {"id": 852, "fr": "Poulpaf"}, {"id": 853, "fr": "Krakos"}, {"id": 854, "fr": "Théffroi"},
    {"id": 855, "fr": "Polthégeist"}, {"id": 856, "fr": "Bibichut"}, {"id": 857, "fr": "Chapotus"},
    {"id": 858, "fr": "Sorcilence"}, {"id": 859, "fr": "Grimalin"}, {"id": 860, "fr": "Fourbelin"},
    {"id": 861, "fr": "Angoliath"}, {"id": 862, "fr": "Ixon"}, {"id": 863, "fr": "Berserkatt"},
    {"id": 864, "fr": "Corayôme"}, {"id": 865, "fr": "Palarticho"}, {"id": 866, "fr": "M. Glaquette"},
    {"id": 867, "fr": "Tutétékri"}, {"id": 868, "fr": "Crèmy"}, {"id": 869, "fr": "Charmilly"},
    {"id": 870, "fr": "Hexadron"}, {"id": 871, "fr": "Wattapik"}, {"id": 872, "fr": "Frissonille"},
    {"id": 873, "fr": "Beldeneige"}, {"id": 874, "fr": "Dolman"}, {"id": 875, "fr": "Bekaglaçon"},
    {"id": 876, "fr": "Wimessir"}, {"id": 877, "fr": "Morpeko"}, {"id": 878, "fr": "Charibari"},
    {"id": 879, "fr": "Pachyradjah"}, {"id": 880, "fr": "Galvagon"}, {"id": 881, "fr": "Galvagla"},
    {"id": 882, "fr": "Hydragon"}, {"id": 883, "fr": "Hydragla"}, {"id": 884, "fr": "Duralugon"},
    {"id": 885, "fr": "Fantyrm"}, {"id": 886, "fr": "Dispareptil"}, {"id": 887, "fr": "Lanssorien"},
    {"id": 888, "fr": "Zacian"}, {"id": 889, "fr": "Zamazenta"}, {"id": 890, "fr": "Éthernatos"},
    {"id": 891, "fr": "Wushours"}, {"id": 892, "fr": "Shifours"}, {"id": 893, "fr": "Zarude"},
    {"id": 894, "fr": "Regieleki"}, {"id": 895, "fr": "Regidrago"}, {"id": 896, "fr": "Blizzeval"},
    {"id": 897, "fr": "Spectreval"}, {"id": 898, "fr": "Sylveroy"}, {"id": 899, "fr": "Cerbyllin"},
    {"id": 900, "fr": "Hachecateur"}, {"id": 901, "fr": "Ursaking"}, {"id": 902, "fr": "Paragruel"},
    {"id": 903, "fr": "Farfurex"}, {"id": 904, "fr": "Qwilpik"}, {"id": 905, "fr": "Amovénus"},
    # ═══════════════════════════════════════
    # GEN 9 — Paldea (906–1025)
    # ═══════════════════════════════════════
    {"id": 906, "fr": "Poussacha"}, {"id": 907, "fr": "Matourgeon"}, {"id": 908, "fr": "Miascarade"},
    {"id": 909, "fr": "Chochodile"}, {"id": 910, "fr": "Crocogril"}, {"id": 911, "fr": "Flâmigator"},
    {"id": 912, "fr": "Coiffeton"}, {"id": 913, "fr": "Canarbello"}, {"id": 914, "fr": "Palmaval"},
    {"id": 915, "fr": "Gourmelet"}, {"id": 916, "fr": "Fragroin"}, {"id": 917, "fr": "Tissenboule"},
    {"id": 918, "fr": "Filentrappe"}, {"id": 919, "fr": "Lilliterelle"}, {"id": 920, "fr": "Gambex"},
    {"id": 921, "fr": "Pohm"}, {"id": 922, "fr": "Pohmotte"}, {"id": 923, "fr": "Pohmarmotte"},
    {"id": 924, "fr": "Compagnol"}, {"id": 925, "fr": "Famignol"}, {"id": 926, "fr": "Pâtachiot"},
    {"id": 927, "fr": "Briochien"}, {"id": 928, "fr": "Olivini"}, {"id": 929, "fr": "Olivado"},
    {"id": 930, "fr": "Arboliva"}, {"id": 931, "fr": "Tapatoès"}, {"id": 932, "fr": "Selutin"},
    {"id": 933, "fr": "Amassel"}, {"id": 934, "fr": "Gigansel"}, {"id": 935, "fr": "Charbambin"},
    {"id": 936, "fr": "Carmadura"}, {"id": 937, "fr": "Malvalame"}, {"id": 938, "fr": "Têtampoule"},
    {"id": 939, "fr": "Ampibidou"}, {"id": 940, "fr": "Zapétrel"}, {"id": 941, "fr": "Fulgulairo"},
    {"id": 942, "fr": "Grondogue"}, {"id": 943, "fr": "Dogrino"}, {"id": 944, "fr": "Gribouraigne"},
    {"id": 945, "fr": "Tag-Tag"}, {"id": 946, "fr": "Virovent"}, {"id": 947, "fr": "Virevorreur"},
    {"id": 948, "fr": "Terracool"}, {"id": 949, "fr": "Terracruel"}, {"id": 950, "fr": "Craparoi"},
    {"id": 951, "fr": "Pimito"}, {"id": 952, "fr": "Scovilain"}, {"id": 953, "fr": "Léboulérou"},
    {"id": 954, "fr": "Bérasca"}, {"id": 955, "fr": "Flotillon"}, {"id": 956, "fr": "Cléopsytra"},
    {"id": 957, "fr": "Forgerette"}, {"id": 958, "fr": "Forgella"}, {"id": 959, "fr": "Forgelina"},
    {"id": 960, "fr": "Taupikeau"}, {"id": 961, "fr": "Triopikeau"}, {"id": 962, "fr": "Lestombaile"},
    {"id": 963, "fr": "Dofin"}, {"id": 964, "fr": "Superdofin"}, {"id": 965, "fr": "Vrombi"},
    {"id": 966, "fr": "Vrombotor"}, {"id": 967, "fr": "Motorizard"}, {"id": 968, "fr": "Ferdeter"},
    {"id": 969, "fr": "Germéclat"}, {"id": 970, "fr": "Floréclat"}, {"id": 971, "fr": "Toutombe"},
    {"id": 972, "fr": "Tomberro"}, {"id": 973, "fr": "Flamenroule"}, {"id": 974, "fr": "Piétacé"},
    {"id": 975, "fr": "Balbalèze"}, {"id": 976, "fr": "Délestin"}, {"id": 977, "fr": "Oyacata"},
    {"id": 978, "fr": "Nigirigon"}, {"id": 979, "fr": "Courrousinge"}, {"id": 980, "fr": "Terraiste"},
    {"id": 981, "fr": "Farigiraf"}, {"id": 982, "fr": "Deusolourdo"}, {"id": 983, "fr": "Scalpereur"},
    {"id": 984, "fr": "Fort-Ivoire"}, {"id": 985, "fr": "Hurle-Queue"}, {"id": 986, "fr": "Fongus-Furie"},
    {"id": 987, "fr": "Flotte-Mèche"}, {"id": 988, "fr": "Rampes-Ailes"}, {"id": 989, "fr": "Pelage-Sablé"},
    {"id": 990, "fr": "Roue-de-Fer"}, {"id": 991, "fr": "Hotte-de-Fer"}, {"id": 992, "fr": "Paume-de-Fer"},
    {"id": 993, "fr": "Têtes-de-Fer"}, {"id": 994, "fr": "Mite-de-Fer"}, {"id": 995, "fr": "Épine-de-Fer"},
    {"id": 996, "fr": "Frigodo"}, {"id": 997, "fr": "Cryodo"}, {"id": 998, "fr": "Glaivodo"},
    {"id": 999, "fr": "Mordudor"}, {"id": 1000, "fr": "Gromago"}, {"id": 1001, "fr": "Chongjian"},
    {"id": 1002, "fr": "Baojian"}, {"id": 1003, "fr": "Dinglu"}, {"id": 1004, "fr": "Yuyu"},
    {"id": 1005, "fr": "Rugit-Lune"}, {"id": 1006, "fr": "Garde-de-Fer"}, {"id": 1007, "fr": "Koraidon"},
    {"id": 1008, "fr": "Miraidon"}, {"id": 1009, "fr": "Serpente-Eau"}, {"id": 1010, "fr": "Vert-de-Fer"},
    {"id": 1011, "fr": "Pomdramour"}, {"id": 1012, "fr": "Poltchageist"}, {"id": 1013, "fr": "Théffroyable"},
    {"id": 1014, "fr": "Félicanis"}, {"id": 1015, "fr": "Fortusimia"}, {"id": 1016, "fr": "Favianos"},
    {"id": 1017, "fr": "Ogerpon"}, {"id": 1018, "fr": "Pondralugon"}, {"id": 1019, "fr": "Pomdorochi"},
    {"id": 1020, "fr": "Feu-Perçant"}, {"id": 1021, "fr": "Ire-Foudre"}, {"id": 1022, "fr": "Roc-de-Fer"},
    {"id": 1023, "fr": "Chef-de-Fer"}, {"id": 1024, "fr": "Terapagos"}, {"id": 1025, "fr": "Pêchaminus"},
]


active_pokemon_games: dict[int, dict] = {}
pokemon_scores: dict[int, dict[int, int]] = {}

POKEMON_TOP_ROLES = [
    ("Professeur Pokémon",            discord.Color.gold(),                   "🥇"),
    ("Expert du pokédex",             discord.Color.light_grey(),             "🥈"),
    ("Grand connaisseur des Pokémon", discord.Color.from_rgb(205, 127, 50),  "🥉"),
]


def normalize_pokemon(text: str) -> str:
    """Normalise un texte pour comparaison souple (sans accents, minuscules, sans spéciaux)."""
    text = text.lower().strip()
    text = _ud.normalize("NFD", text)
    text = "".join(c for c in text if _ud.category(c) != "Mn")
    text = re.sub(r"[^a-z0-9\s\-]", "", text)
    return text.strip()



class PokemonRoleNamesModal(discord.ui.Modal, title="Rôles du Top 3 Pokémon"):
    premier = discord.ui.TextInput(label="Nom du rôle Top 1", default="Professeur Pokémon", max_length=100)
    deuxieme = discord.ui.TextInput(label="Nom du rôle Top 2", default="Expert du pokédex", max_length=100)
    troisieme = discord.ui.TextInput(label="Nom du rôle Top 3", default="Grand connaisseur des Pokémon", max_length=100)
    async def on_submit(self, interaction: discord.Interaction):
        roles = [(self.premier.value, 0xF1C40F), (self.deuxieme.value, 0x95A5A6), (self.troisieme.value, 0xCD7F32)]
        set_guild_config(interaction.guild.id, "pokemon_roles_enabled", True)
        set_guild_config(interaction.guild.id, "pokemon_top_roles", [{"name": name, "color": color} for name, color in roles])
        set_guild_config(interaction.guild.id, "pokemon_roles_configured", True)
        await interaction.response.send_message(embed=firm1_embed("✅ Rôles Pokémon configurés", "Ils seront créés lors de la prochaine bonne réponse. Utilisez à nouveau `/pokemon` pour lancer une partie.", color=COLOR_SUCCESS), ephemeral=True)

class PokemonRoleSetupView(discord.ui.View):
    def __init__(self): super().__init__(timeout=120)
    @discord.ui.button(label="Créer les rôles", style=discord.ButtonStyle.success)
    async def enable(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PokemonRoleNamesModal())
    @discord.ui.button(label="Ne pas créer de rôles", style=discord.ButtonStyle.secondary)
    async def disable(self, interaction: discord.Interaction, button: discord.ui.Button):
        set_guild_config(interaction.guild.id, "pokemon_roles_enabled", False)
        set_guild_config(interaction.guild.id, "pokemon_roles_configured", True)
        await interaction.response.send_message(embed=firm1_embed("Rôles Pokémon désactivés", "Le classement continue sans créer de rôles. Utilisez à nouveau `/pokemon` pour lancer une partie.", color=COLOR_INFO), ephemeral=True)


def get_pokemon_top_roles(guild: discord.Guild):
    configured = get_guild_config(guild.id).get("pokemon_top_roles")
    if configured:
        medals = ["🥇", "🥈", "🥉"]
        return [(item["name"], discord.Color(item["color"]), medals[i]) for i, item in enumerate(configured[:3])]
    return POKEMON_TOP_ROLES

async def update_pokemon_top_roles(guild: discord.Guild):
    if not get_guild_config(guild.id).get("pokemon_roles_enabled", False):
        return
    scores = pokemon_scores.get(guild.id, {})
    if not scores:
        return
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top3_uids = [uid for uid, _ in sorted_scores[:3]]
    roles = []
    for nom, couleur, _ in get_pokemon_top_roles(guild):
        role = discord.utils.get(guild.roles, name=nom)
        if not role:
            try:
                role = await guild.create_role(name=nom, color=couleur, hoist=True, reason="Rôle automatique Top Pokémon — Bot Discord")
            except discord.Forbidden:
                role = None
        roles.append(role)
    for role in roles:
        if not role:
            continue
        for member in guild.members:
            if role in member.roles:
                try:
                    await member.remove_roles(role, reason="Mise à jour classement Pokémon")
                except Exception:
                    pass
    for i, uid in enumerate(top3_uids):
        if i >= len(roles) or not roles[i]:
            continue
        member = guild.get_member(uid)
        if member:
            try:
                await member.add_roles(roles[i], reason=f"Top {i+1} Pokémon — Bot Discord")
            except Exception:
                pass


@tree.command(name="pokemon", description="Quel est ce Pokémon ? Devinez son nom en français !")
async def pokemon_cmd(interaction: discord.Interaction):
    cfg = get_guild_config(interaction.guild_id)
    if not cfg.get("pokemon_roles_configured", False):
        await interaction.response.send_message(
            embed=firm1_embed(
                "Avant de commencer",
                "Souhaitez-vous créer des rôles automatiques pour le Top 3 Pokémon de ce serveur ?\n\nVous pourrez choisir le nom des trois rôles, ou continuer sans créer de rôle.",
                color=COLOR_PRIMARY,
            ),
            view=PokemonRoleSetupView(),
            ephemeral=True,
        )
        return
    channel_id = interaction.channel_id

    if channel_id in active_pokemon_games:
        await interaction.response.send_message(embed=firm1_embed(
            "Partie en cours",
            "Une partie est déjà active ici ! Trouvez d'abord le Pokémon actuel.",
            color=COLOR_WARNING,
        ), ephemeral=True)
        return

    pokemon = random.choice(POKEMON_LIST)
    active_pokemon_games[channel_id] = {"pokemon": pokemon}

    image_url = (
        f"https://raw.githubusercontent.com/PokeAPI/sprites/master/"
        f"sprites/pokemon/other/official-artwork/{pokemon['id']}.png"
    )

    embed = bot_embed(
        title="❓ Quel est ce Pokémon ?",
        description=(
            "Regardez bien cette image et tapez le **nom français** dans le chat !\n\n"
            "⏱️ Vous avez **45 secondes** pour répondre.\n"
            "💡 Les accents ne sont pas obligatoires."
        ),
        color=COLOR_PRIMARY,
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )
    embed.set_image(url=image_url)
    embed.set_footer(text=f"Pokémon n°{pokemon['id']} • Bot Discord")
    await interaction.response.send_message(embed=embed)

    nom_normalise = normalize_pokemon(pokemon["fr"])

    def check(m: discord.Message) -> bool:
        return m.channel.id == channel_id and not m.author.bot

    # ══════════════════════════════════════════════════════
    # FIX TIMER 45s : deadline absolue pour éviter la
    # réinitialisation du timer à chaque mauvais message
    # ══════════════════════════════════════════════════════
    deadline = time.monotonic() + 45.0

    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise asyncio.TimeoutError
            msg     = await bot.wait_for("message", timeout=remaining, check=check)
            reponse = normalize_pokemon(msg.content)

            if reponse == nom_normalise:
                active_pokemon_games.pop(channel_id, None)

                gid = interaction.guild_id
                uid = msg.author.id
                if gid not in pokemon_scores:
                    pokemon_scores[gid] = {}
                pokemon_scores[gid][uid] = pokemon_scores[gid].get(uid, 0) + 1
                score = pokemon_scores[gid][uid]

                await update_pokemon_top_roles(interaction.guild)

                sorted_s = sorted(pokemon_scores[gid].items(), key=lambda x: x[1], reverse=True)
                rang = next((i+1 for i, (u, _) in enumerate(sorted_s) if u == uid), None)
                rang_txt = ""
                if rang == 1:
                    rang_txt = f"\n\n🥇 **{msg.author.display_name}** est désormais **Professeur Pokémon** !"
                elif rang == 2:
                    rang_txt = f"\n\n🥈 **{msg.author.display_name}** est désormais **Expert du pokédex** !"
                elif rang == 3:
                    rang_txt = f"\n\n🥉 **{msg.author.display_name}** est désormais **Grand connaisseur des Pokémon** !"

                win_embed = bot_embed(
                    title="🎉 Bonne réponse !",
                    description=(
                        f"{msg.author.mention} a trouvé ! C'était **{pokemon['fr']}** !\n\n"
                        f"🏅 Score : **{score}** bonne(s) réponse(s)"
                        + rang_txt
                    ),
                    color=COLOR_SUCCESS,
                    timestamp=datetime.datetime.now(datetime.timezone.utc),
                )
                win_embed.set_thumbnail(url=image_url)
                win_embed.set_footer(text=f"Pokémon n°{pokemon['id']} • Bot Discord")
                await msg.channel.send(embed=win_embed)
                break

    except asyncio.TimeoutError:
        active_pokemon_games.pop(channel_id, None)
        timeout_embed = bot_embed(
            title="⏰ Temps écoulé !",
            description=f"Personne n'a trouvé... C'était **{pokemon['fr']}** !",
            color=COLOR_ERROR,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        timeout_embed.set_thumbnail(url=image_url)
        timeout_embed.set_footer(text=f"Pokémon n°{pokemon['id']} • Bot Discord")
        await interaction.channel.send(embed=timeout_embed)


@tree.command(name="pokemon-score", description="Classement des meilleurs dresseurs du serveur")
async def pokemon_score_cmd(interaction: discord.Interaction):
    gid    = interaction.guild_id
    scores = pokemon_scores.get(gid, {})
    if not scores:
        await interaction.response.send_message(embed=firm1_embed("🏆 Classement Pokémon", "Aucune partie jouée ! Utilisez `/pokemon` pour commencer.", color=COLOR_INFO))
        return
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    medals = ["🥇", "🥈", "🥉"]
    lines  = []
    for i, (uid, score) in enumerate(sorted_scores[:10]):
        medal  = medals[i] if i < 3 else f"**#{i+1}**"
        member = interaction.guild.get_member(uid)
        name   = member.display_name if member else "Utilisateur inconnu"
        role_txt = ""
        if i == 0:   role_txt = " — *Professeur Pokémon*"
        elif i == 1: role_txt = " — *Expert du pokédex*"
        elif i == 2: role_txt = " — *Grand connaisseur des Pokémon*"
        lines.append(f"{medal} **{name}**{role_txt} : {score} bonne(s) réponse(s)")
    embed = bot_embed(title="🏆 Classement Pokémon — Meilleurs Dresseurs", description="\n".join(lines), color=COLOR_WARNING, timestamp=datetime.datetime.now(datetime.timezone.utc))
    embed.add_field(name="🎭 Titres du Top 3", value=("🥇 **1er** → Professeur Pokémon\n🥈 **2ème** → Expert du pokédex\n🥉 **3ème** → Grand connaisseur des Pokémon"), inline=False)
    embed.set_footer(text="Nadouja · Mitteg · Not Feller")
    await interaction.response.send_message(embed=embed)



# ═══════════════════════════════════════════════════════════
#  ON_MESSAGE — Auto-mod + Ping présentation
# ═══════════════════════════════════════════════════════════

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    if (
        bot.user in message.mentions
        and message.content.strip() in (f"<@{bot.user.id}>", f"<@!{bot.user.id}>")
    ):
        cfg   = get_guild_config(message.guild.id)
        embed = bot_embed(
            title="👋 Bienvenue",
            description="Je peux vous aider avec la modération, le support et les mini-jeux.\nUtilisez `/help` pour consulter toutes les commandes.",
            color=COLOR_PRIMARY,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.add_field(name="Aperçu du serveur", value=(f"🎫 Catégories tickets : **{len(cfg.get('ticket_categories', []))}**\n🚫 Mots interdits : **{len(cfg.get('bad_words', []))}**\n🔗 Salons sans liens : **{len(cfg.get('no_link_channels', []))}**\n🖼️ Salons sans images : **{len(cfg.get('no_image_channels', []))}**"), inline=True)
        embed.add_field(name="Fonctionnalités", value=("🎫 Système de tickets\n🔨 Modération complète\n🤖 Auto-modération\n🛡️ Whitelist & Blacklist\n🎮 Mini-jeux"), inline=True)
        embed.set_thumbnail(url=bot.user.display_avatar.url)
        embed.set_footer(text=f"Bot Discord • Sur {len(bot.guilds)} serveur(s)")
        await message.reply(embed=embed, mention_author=False)
        return

    cfg       = get_guild_config(message.guild.id)
    content   = message.content.casefold()
    bad_words = cfg.get("bad_words", [])
    whitelist = cfg.get("whitelist", [])

    if message.author.id != OWNER_ID and message.author.id not in whitelist and contains_banned_word(message.content, bad_words):
        await message.delete()
        try:
            await message.author.send(embed=firm1_embed("🚫 Message supprimé", f"Votre message dans **{message.guild.name}** contient un mot interdit.", color=COLOR_ERROR))
        except Exception:
            pass
        await send_mod_log(message.guild, title="🚫 Mot interdit supprimé", color=COLOR_ERROR, fields=[("👤 Membre", f"{message.author} (`{message.author.id}`)", True), ("📍 Salon", message.channel.mention, True), ("💬 Message extrait", message.content[:200], False)])
        return

    url_pattern = re.compile(r"https?://\S+|discord\.gg/\S+", re.IGNORECASE)
    if message.channel.id in cfg.get("no_link_channels", []) and url_pattern.search(message.content):
        await message.delete()
        warn_msg = await message.channel.send(embed=firm1_embed("🔗 Lien interdit", f"{message.author.mention}, les liens sont interdits dans ce salon.", color=COLOR_ERROR))
        await asyncio.sleep(5)
        await warn_msg.delete()
        await send_mod_log(message.guild, title="🔗 Lien supprimé", color=COLOR_WARNING, fields=[("👤 Membre", f"{message.author} (`{message.author.id}`)", True), ("📍 Salon", message.channel.mention, True)])
        return

    if message.channel.id in cfg.get("no_image_channels", []) and (
        message.attachments
        or any(e.type in (discord.EmbedType.image, discord.EmbedType.gifv) for e in message.embeds)
    ):
        await message.delete()
        warn_msg = await message.channel.send(embed=firm1_embed("🖼️ Image interdite", f"{message.author.mention}, les images sont interdites dans ce salon.", color=COLOR_ERROR))
        await asyncio.sleep(5)
        await warn_msg.delete()
        await send_mod_log(message.guild, title="🖼️ Image supprimée", color=COLOR_WARNING, fields=[("👤 Membre", f"{message.author} (`{message.author.id}`)", True), ("📍 Salon", message.channel.mention, True)])
        return

    spam_active = cfg.get("spam_active", True)
    if message.author.id not in whitelist and spam_active:
        spam_limit  = cfg.get("spam_limit",  SPAM_LIMIT_DEFAULT)
        spam_window = cfg.get("spam_window", SPAM_WINDOW_DEFAULT)
        spam_mute   = cfg.get("spam_mute",   SPAM_MUTE_DEFAULT)
        gid, uid    = message.guild.id, message.author.id
        now         = datetime.datetime.now(datetime.timezone.utc).timestamp()
        if gid not in spam_tracker:
            spam_tracker[gid] = {}
        if uid not in spam_tracker[gid]:
            spam_tracker[gid][uid] = []
        spam_tracker[gid][uid].append(now)
        spam_tracker[gid][uid] = [t for t in spam_tracker[gid][uid] if now - t < spam_window]
        if len(spam_tracker[gid][uid]) >= spam_limit:
            spam_tracker[gid][uid] = []
            try:
                until = discord.utils.utcnow() + datetime.timedelta(minutes=spam_mute)
                await message.author.timeout(until, reason="Antispam automatique")
                await message.channel.send(embed=firm1_embed("🚨 Spam détecté", f"{message.author.mention} a été mis en sourdine **{spam_mute} minute(s)** pour spam.", color=COLOR_ERROR))
                await send_mod_log(message.guild, title="🚨 Antispam — Mute automatique", color=COLOR_ERROR, fields=[("👤 Membre", f"{message.author} (`{message.author.id}`)", True), ("📍 Salon", message.channel.mention, True), ("🔇 Durée", f"{spam_mute} min", True)])
            except discord.Forbidden:
                await message.channel.send(embed=firm1_embed("⚠️ Antispam — Permission manquante", f"Impossible de mute {message.author.mention} : le bot n'a pas la permission ou le rôle du membre est trop élevé.", color=COLOR_WARNING))
            except Exception as e:
                print(f"❌ Erreur antispam : {e}")
                traceback.print_exc()

    await bot.process_commands(message)


@bot.event
async def on_member_join(member: discord.Member):
    cfg = get_guild_config(member.guild.id)
    if member.id in cfg.get("blacklist", []):
        try:
            await member.send(embed=firm1_embed("⛔ Accès refusé", f"Vous êtes blacklisté du serveur **{member.guild.name}**.", color=COLOR_ERROR))
        except Exception:
            pass
        await member.kick(reason="Blacklisté")
        await send_mod_log(member.guild, title="⛔ Blacklist — Expulsion automatique", color=COLOR_ERROR, fields=[("👤 Membre", f"{member} (`{member.id}`)", True), ("📋 Raison", "Membre blacklisté", True)])


# ═══════════════════════════════════════════════════════════
#  LANCEMENT
# ═══════════════════════════════════════════════════════════

if KEEP_ALIVE_AVAILABLE:
    keep_alive()

bot.run(token, reconnect=True)
