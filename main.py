"""
╔══════════════════════════════════════════════════════════╗
║           🎮 FIRM1 — Bot de Gestion Discord                        ║
║      Tickets • Modération • Auto-mod • Mini-Jeux                   ║
╚══════════════════════════════════════════════════════════╝

Dépendances : pip install discord.py python-dotenv flask
Configuration : créez un fichier .env avec Token_bot=VOTRE_TOKEN
"""

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

def firm1_embed(
    title: str,
    description: str = "",
    color: int = COLOR_PRIMARY,
    footer: str | None = None,
    thumbnail: str | None = None,
    fields: list[tuple[str, str, bool]] | None = None,
) -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )
    embed.set_footer(text=footer or "Firm1 Bot • Support Gaming")
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
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

async def send_mod_log(guild: discord.Guild, **kwargs):
    cfg     = get_guild_config(guild.id)
    log_id  = cfg.get("mod_log_channel_id")
    if not log_id:
        return
    channel = guild.get_channel(log_id)
    if not channel:
        return
    embed = discord.Embed(
        title=kwargs.get("title", "Action de modération"),
        color=kwargs.get("color", COLOR_WARNING),
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )
    for name, value, inline in kwargs.get("fields", []):
        embed.add_field(name=name, value=value, inline=inline)
    embed.set_footer(text="Firm1 Bot • Logs Modération")
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
    print(f"✅ Firm1 connecté : {bot.user} (ID: {bot.user.id})")
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching, name="🎮 /help • Support Firm1"
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
                "Firm1 Bot est opérationnel !",
                "Utilisez `/help` pour voir toutes les commandes.\nConfigurez les tickets avec `/config-tickets`.",
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

@tree.command(name="help", description="Affiche l'aide complète de Firm1 Bot")
async def help_cmd(interaction: discord.Interaction):
    page1 = discord.Embed(title="🎫 Tickets — Page 1/5", description="Système de tickets de support.", color=COLOR_PRIMARY)
    page1.add_field(name="📩 Membres", value=("`/ticket` — Ouvrir un ticket\n`/fermer` — Fermer votre ticket\n`/ajouter @user` — Ajouter un membre\n`/retirer @user` — Retirer un membre"), inline=False)
    page1.add_field(name="⚙️ Administration", value=("`/panel-tickets` — Envoyer le panel\n`/config-tickets` — Voir la configuration\n`/set-log-tickets` — Salon de logs\n`/ajouter-role-ticket` — Ajouter rôle ping\n`/retirer-role-ticket` — Retirer rôle ping\n`/ajouter-categorie-ticket` — Ajouter catégorie\n`/retirer-categorie-ticket` — Retirer catégorie\n`/reset-config-tickets` — Réinitialiser"), inline=False)
    page1.set_footer(text="Firm1 Bot • Support Gaming")
    page2 = discord.Embed(title="🔨 Modération — Page 2/5", description="Commandes de modération manuelle.", color=COLOR_ERROR)
    page2.add_field(name="👮 Sanctions", value=("`/ban @user` — Bannir un membre\n`/kick @user` — Expulser un membre\n`/mute @user durée` — Mute (10s, 5m, 2h, 1j)\n`/unmute @user` — Retirer le mute\n`/warn @user raison` — Avertir\n`/warns @user` — Voir les avertissements\n`/clear 1-100` — Supprimer des messages\n`/set-log-mod` — Salon de logs mod"), inline=False)
    page2.set_footer(text="Firm1 Bot • Support Gaming")
    page3 = discord.Embed(title="🤖 Auto-Modération — Page 3/5", description="Modération automatique configurable.", color=COLOR_WARNING)
    page3.add_field(name="⚙️ Configuration", value=("`/config-auto-mod` — Voir la config\n`/config-antispam` — Config antispam\n`/ajouter-badword` — Ajouter badword\n`/retirer-badword` — Retirer badword\n`/liste-badwords` — Liste des badwords\n`/salon-no-lien` — Toggle liens\n`/salon-no-image` — Toggle images"), inline=False)
    page3.add_field(name="🚨 Automatique", value=("Mots interdits → suppression + MP\nLiens → suppression par salon\nImages → suppression par salon\nAntispam → mute automatique"), inline=False)
    page3.set_footer(text="Firm1 Bot • Support Gaming")
    page4 = discord.Embed(title="🛡️ Whitelist & Blacklist — Page 4/5", description="Gestion des accès membres.", color=COLOR_INFO)
    page4.add_field(name="✅ Whitelist — bypass auto-mod", value=("`/whitelist-ajouter @user` — Ajouter\n`/whitelist-retirer @user` — Retirer\n`/whitelist-liste` — Voir la liste"), inline=False)
    page4.add_field(name="⛔ Blacklist — expulsion automatique", value=("`/blacklist-ajouter @user` — Blacklister\n`/blacklist-retirer @user` — Retirer\n`/blacklist-liste` — Voir la liste"), inline=False)
    page4.set_footer(text="Firm1 Bot • Support Gaming")
    page5 = discord.Embed(title="🎮 Mini-Jeux & Utilitaires — Page 5/5", description="Jeux et outils divers.", color=COLOR_SUCCESS)
    page5.add_field(name="🎮 Mini-Jeux", value=("`/pile-ou-face` — Lancer une pièce\n`/dé` — Lancer un dé\n`/rps` — Pierre-Papier-Ciseaux\n`/nombre` — Deviner un nombre\n`/8ball` — Boule magique\n`/trivia` — Culture générale\n`/pokemon` — Quel est ce Pokémon ?\n`/pokemon-score` — Classement des dresseurs"), inline=False)
    page5.add_field(name="🛠️ Utilitaires", value=("`/ping` — Latence du bot\n`/info-serveur` — Infos serveur\n`/info-user` — Infos membre\n`/avatar` — Avatar\n`/say` — Parler à la place du bot\n`/renommer-bot` — Changer le pseudo\n`/help` — Cette aide"), inline=False)
    page5.set_footer(text="Firm1 Bot • Support Gaming")
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
    await interaction.response.send_message(embed=firm1_embed("Pong !", f"**Latence :** `{lat} ms`\n**Statut :** {status}", color=color))

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

@tree.command(name="say", description="[Admin] Fait parler le bot")
@app_commands.describe(message="Le message à envoyer", salon="Salon cible (optionnel)")
@app_commands.checks.has_permissions(administrator=True)
async def say_cmd(interaction: discord.Interaction, message: str, salon: discord.TextChannel | None = None):
    target = salon or interaction.channel
    try:
        await target.send(message)
        await interaction.response.send_message(embed=firm1_embed("✅ Message envoyé", f"Envoyé dans {target.mention}.", color=COLOR_SUCCESS, fields=[("📝 Contenu", message[:1024], False)]), ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message(embed=firm1_embed("Erreur", f"Pas la permission d'envoyer dans {target.mention}.", color=COLOR_ERROR), ephemeral=True)

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


# ═══════════════════════════════════════════════════════════
#  SYSTÈME DE TICKETS
# ═══════════════════════════════════════════════════════════

class TicketReasonModal(discord.ui.Modal, title="📋 Ouvrir un ticket"):
    raison = discord.ui.TextInput(label="Raison de votre demande", placeholder="Décrivez brièvement votre problème...", style=discord.TextStyle.paragraph, max_length=300, required=True)
    def __init__(self, categorie_label: str, category_id: int | None):
        super().__init__(title=f"📋 Ticket — {categorie_label}")
        self.categorie_label = categorie_label
        self.category_id     = category_id
    async def on_submit(self, interaction: discord.Interaction):
        await _creer_ticket(interaction, raison=f"[{self.categorie_label}] {self.raison.value}", category_id=self.category_id)

class TicketCategorySelect(discord.ui.Select):
    def __init__(self, categories: list[dict]):
        options = [discord.SelectOption(label=c["label"], description=c.get("description", "")[:100], emoji=c.get("emoji", "🎫"), value=str(i)) for i, c in enumerate(categories)]
        super().__init__(placeholder="Choisissez une catégorie...", min_values=1, max_values=1, options=options, custom_id="ticket_category_select")
        self.categories = categories
    async def callback(self, interaction: discord.Interaction):
        cat = self.categories[int(self.values[0])]
        await interaction.response.send_modal(TicketReasonModal(categorie_label=cat["label"], category_id=cat.get("discord_category_id")))

class TicketCategoryView(discord.ui.View):
    def __init__(self, categories: list[dict]):
        super().__init__(timeout=60)
        self.add_item(TicketCategorySelect(categories))

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
        ping_ids = cfg.get("ping_roles", [])
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
            await interaction.response.send_message(embed=firm1_embed("Choisissez une catégorie", "Sélectionnez la catégorie correspondant à votre demande.", color=COLOR_INFO), view=TicketCategoryView(categories), ephemeral=True)
    @discord.ui.button(label="📖 Comment ça marche ?", style=discord.ButtonStyle.secondary, custom_id="ticket_info_btn")
    async def info_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=firm1_embed("Comment ouvrir un ticket ?", ("**1.** Cliquez sur **🎫 Ouvrir un ticket**\n**2.** Choisissez la catégorie\n**3.** Remplissez le formulaire\n**4.** Un salon privé sera créé\n**5.** Le staff vous répondra dès que possible\n\n⚠️ *Un seul ticket actif par utilisateur.*"), color=COLOR_INFO), ephemeral=True)

async def _creer_ticket(interaction: discord.Interaction, raison: str = "Non spécifiée", category_id: int | None = None):
    guild, user = interaction.guild, interaction.user
    cfg         = get_guild_config(guild.id)
    if user.id in open_tickets:
        ch = guild.get_channel(open_tickets[user.id]["channel_id"])
        if ch:
            await interaction.response.send_message(embed=firm1_embed("Ticket déjà ouvert", f"Vous avez déjà un ticket ouvert : {ch.mention}", color=COLOR_WARNING), ephemeral=True)
            return
    category = guild.get_channel(category_id) if category_id else None
    if not category:
        category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME)
    if not category:
        category = await guild.create_category(TICKET_CATEGORY_NAME)
    ping_role_ids: list   = cfg.get("ping_roles", [])
    ping_mentions: list[str] = []
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        user:               discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me:           discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
    }
    for rid in ping_role_ids:
        role = guild.get_role(rid)
        if role:
            overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            ping_mentions.append(role.mention)
    channel = await category.create_text_channel(f"ticket-{user.name.lower().replace(' ', '-')}", overwrites=overwrites)
    open_tickets[user.id] = {"channel_id": channel.id, "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "reason": raison}
    embed = discord.Embed(title="🎫  Ticket ouvert", description=(f"Bienvenue {user.mention} !\n\n> {raison}\n\nLe staff va vous répondre dès que possible."), color=COLOR_SUCCESS, timestamp=datetime.datetime.now(datetime.timezone.utc))
    embed.add_field(name="👤 Demandeur", value=user.mention, inline=True)
    embed.add_field(name="🆔 ID", value=f"`{user.id}`", inline=True)
    embed.add_field(name="📅 Ouvert le", value=f"<t:{int(datetime.datetime.now(datetime.timezone.utc).timestamp())}:F>", inline=False)
    if ping_mentions:
        embed.add_field(name="🔔 Staff notifié", value=" ".join(ping_mentions), inline=False)
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.set_footer(text="Firm1 • Support")
    await channel.send(content=f"{user.mention} {' '.join(ping_mentions)}".strip(), embed=embed, view=TicketCloseView())
    await interaction.response.send_message(embed=firm1_embed("Ticket créé !", f"Votre ticket est disponible ici : {channel.mention}", color=COLOR_SUCCESS), ephemeral=True)
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
    await asyncio.sleep(5)
    await channel.delete(reason=f"Ticket fermé par {interaction.user}")

@tree.command(name="ticket", description="Ouvre un ticket de support")
@app_commands.describe(raison="La raison de votre demande")
async def ticket_cmd(interaction: discord.Interaction, raison: str = "Non spécifiée"):
    await _creer_ticket(interaction, raison)

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

@tree.command(name="config-tickets", description="[Admin] Voir la config des tickets")
@app_commands.checks.has_permissions(administrator=True)
async def config_tickets(interaction: discord.Interaction):
    cfg        = get_guild_config(interaction.guild.id)
    log_ch     = interaction.guild.get_channel(cfg.get("log_channel_id")) if cfg.get("log_channel_id") else None
    ping_roles = [interaction.guild.get_role(rid) for rid in cfg.get("ping_roles", []) if interaction.guild.get_role(rid)]
    cats_value = ""
    for c in cfg.get("ticket_categories", []):
        disc_cat = interaction.guild.get_channel(c.get("discord_category_id")) if c.get("discord_category_id") else None
        cats_value += f"{c.get('emoji','🎫')} **{c['label']}** → {disc_cat.mention if disc_cat else '`défaut`'}\n"
    embed = discord.Embed(title="⚙️ Configuration — Tickets", color=COLOR_PRIMARY, timestamp=datetime.datetime.now(datetime.timezone.utc))
    embed.add_field(name="📋 Salon de logs", value=log_ch.mention if log_ch else "❌ Non configuré", inline=False)
    embed.add_field(name="🔔 Rôles pingés", value=" ".join(r.mention for r in ping_roles) if ping_roles else "❌ Aucun", inline=False)
    embed.add_field(name="🗂️ Catégories", value=cats_value if cats_value else "❌ Aucune", inline=False)
    embed.set_footer(text=f"Firm1 • {interaction.guild.name}")
    await interaction.response.send_message(embed=embed, ephemeral=True)

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

@tree.command(name="panel-tickets", description="[Admin] Envoie le panel d'ouverture de tickets")
@app_commands.checks.has_permissions(administrator=True)
async def panel_tickets(interaction: discord.Interaction):
    cfg        = get_guild_config(interaction.guild.id)
    ping_roles = [interaction.guild.get_role(rid) for rid in cfg.get("ping_roles", []) if interaction.guild.get_role(rid)]
    log_ch = interaction.guild.get_channel(cfg.get("log_channel_id")) if cfg.get("log_channel_id") else None
    embed = discord.Embed(title="🎫  Support — Firm1", description=("```\n  Vous rencontrez un problème sur le serveur ?\n  Ouvrez un ticket et notre équipe de support\n  vous répondra dans les meilleurs délais.\n```"), color=COLOR_PRIMARY, timestamp=datetime.datetime.now(datetime.timezone.utc))
    embed.add_field(name="📋 Comment ça fonctionne", value=("**1** Cliquez sur `🎫 Ouvrir un ticket`\n**2** Remplissez le formulaire\n**3** Échangez avec le staff en privé\n**4** Fermez le ticket une fois résolu"), inline=True)
    embed.add_field(name="🔔 Staff de support", value=" ".join(r.mention for r in ping_roles) if ping_roles else "*Aucun rôle configuré*", inline=False)
    embed.add_field(name="📌 Règles importantes", value=("• Un seul ticket actif par membre\n• Soyez précis et respectueux\n• Pas de spam ni d'abus\n• Temps de réponse moyen : **< 2h**"), inline=False)
    embed.set_footer(text=f"Firm1 • {interaction.guild.name}")
    if interaction.guild.icon:
        embed.set_thumbnail(url=interaction.guild.icon.url)
    await interaction.channel.send(embed=embed, view=TicketOpenView())
    await interaction.response.send_message(embed=firm1_embed("✅ Panel envoyé !", "Le panel de tickets a été créé.", color=COLOR_SUCCESS, fields=[("📁 Logs", log_ch.mention if log_ch else "❌ Non configuré", True), ("🔔 Rôles", " ".join(r.mention for r in ping_roles) if ping_roles else "❌ Aucun configuré", True)]), ephemeral=True)


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

@tree.command(name="config-auto-mod", description="[Admin] Voir la config de l'auto-modération")
@app_commands.checks.has_permissions(administrator=True)
async def config_automod(interaction: discord.Interaction):
    cfg         = get_guild_config(interaction.guild.id)
    bad_words   = cfg.get("bad_words", [])
    no_link_ch  = [interaction.guild.get_channel(c) for c in cfg.get("no_link_channels", []) if interaction.guild.get_channel(c)]
    no_image_ch = [interaction.guild.get_channel(c) for c in cfg.get("no_image_channels", []) if interaction.guild.get_channel(c)]
    spam_limit  = cfg.get("spam_limit",  SPAM_LIMIT_DEFAULT)
    spam_window = cfg.get("spam_window", SPAM_WINDOW_DEFAULT)
    spam_mute   = cfg.get("spam_mute",   SPAM_MUTE_DEFAULT)
    spam_active = cfg.get("spam_active", True)
    embed = discord.Embed(title="⚙️ Auto-Modération — Config", color=COLOR_PRIMARY, timestamp=datetime.datetime.now(datetime.timezone.utc))
    embed.add_field(name="🤬 Mots interdits", value=", ".join(f"`{w}`" for w in bad_words) if bad_words else "❌ Aucun", inline=False)
    embed.add_field(name="🔗 Salons sans liens", value=" ".join(c.mention for c in no_link_ch) if no_link_ch else "❌ Aucun", inline=False)
    embed.add_field(name="🖼️ Salons sans images", value=" ".join(c.mention for c in no_image_ch) if no_image_ch else "❌ Aucun", inline=False)
    embed.add_field(name="🚨 Antispam", value=(f"{'🟢 Actif' if spam_active else '🔴 Désactivé'}\n**Seuil :** {spam_limit} msg en {spam_window}s\n**Sanction :** mute {spam_mute} min"), inline=False)
    embed.set_footer(text="Firm1 Bot • Support Gaming")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="config-antispam", description="[Admin] Personnalise les paramètres de l'antispam")
@app_commands.describe(limite="Nb messages avant sanction (2-50)", fenetre="Fenêtre en secondes (1-60)", mute_minutes="Durée du mute en minutes (1-1440)", actif="Activer ou désactiver l'antispam")
@app_commands.checks.has_permissions(administrator=True)
async def config_antispam(interaction: discord.Interaction, limite: int | None = None, fenetre: int | None = None, mute_minutes: int | None = None, actif: bool | None = None):
    if limite is not None:
        if not 2 <= limite <= 50:
            await interaction.response.send_message(embed=firm1_embed("Valeur invalide", "Limite : entre **2** et **50**.", color=COLOR_ERROR), ephemeral=True)
            return
        set_guild_config(interaction.guild.id, "spam_limit", limite)
    if fenetre is not None:
        if not 1 <= fenetre <= 60:
            await interaction.response.send_message(embed=firm1_embed("Valeur invalide", "Fenêtre : entre **1** et **60** secondes.", color=COLOR_ERROR), ephemeral=True)
            return
        set_guild_config(interaction.guild.id, "spam_window", fenetre)
    if mute_minutes is not None:
        if not 1 <= mute_minutes <= 1440:
            await interaction.response.send_message(embed=firm1_embed("Valeur invalide", "Durée : entre **1** et **1440** minutes.", color=COLOR_ERROR), ephemeral=True)
            return
        set_guild_config(interaction.guild.id, "spam_mute", mute_minutes)
    if actif is not None:
        set_guild_config(interaction.guild.id, "spam_active", actif)
    cfg = get_guild_config(interaction.guild.id)
    sl  = cfg.get("spam_limit",  SPAM_LIMIT_DEFAULT)
    sw  = cfg.get("spam_window", SPAM_WINDOW_DEFAULT)
    sm  = cfg.get("spam_mute",   SPAM_MUTE_DEFAULT)
    sa  = cfg.get("spam_active", True)
    await interaction.response.send_message(embed=firm1_embed("🚨 Antispam mis à jour", f"{'🟢 Activé' if sa else '🔴 Désactivé'}", color=COLOR_SUCCESS if sa else COLOR_WARNING, fields=[("📨 Seuil", f"**{sl}** messages", True), ("⏱️ Fenêtre", f"**{sw}** secondes", True), ("🔇 Sanction", f"Mute **{sm}** min", True)]), ephemeral=True)

@tree.command(name="ajouter-badword", description="[Admin] Ajoute un ou plusieurs badwords (séparés par _)")
@app_commands.describe(mot="Un ou plusieurs mots séparés par _ (ex: mot1_mot2)")
@app_commands.checks.has_permissions(administrator=True)
async def add_bad_word(interaction: discord.Interaction, mot: str):
    cfg       = get_guild_config(interaction.guild.id)
    bad_words = cfg.get("bad_words", [])
    nouveaux  = [m.strip().lower() for m in mot.split("_") if m.strip()]
    deja      = [m for m in nouveaux if m in bad_words]
    ajoutes   = [m for m in nouveaux if m not in bad_words]
    if ajoutes:
        bad_words.extend(ajoutes)
        set_guild_config(interaction.guild.id, "bad_words", bad_words)
    fields = [("📊 Total", str(len(bad_words)), True)]
    if ajoutes:
        fields.append(("✅ Ajoutés", ", ".join(f"`{m}`" for m in ajoutes), False))
    if deja:
        fields.append(("⚠️ Déjà présents", ", ".join(f"`{m}`" for m in deja), False))
    await interaction.response.send_message(embed=firm1_embed("✅ Badwords mis à jour" if ajoutes else "⚠️ Aucun mot ajouté", f"**{len(ajoutes)}** ajouté(s), **{len(deja)}** déjà présent(s).", color=COLOR_SUCCESS if ajoutes else COLOR_WARNING, fields=fields), ephemeral=True)

@tree.command(name="retirer-badword", description="[Admin] Retire un badword")
@app_commands.describe(mot="Le mot à retirer")
@app_commands.checks.has_permissions(administrator=True)
async def remove_bad_word(interaction: discord.Interaction, mot: str):
    cfg       = get_guild_config(interaction.guild.id)
    bad_words = cfg.get("bad_words", [])
    mot       = mot.lower()
    if mot not in bad_words:
        await interaction.response.send_message(embed=firm1_embed("Introuvable", f"`{mot}` n'est pas dans la liste.", color=COLOR_WARNING), ephemeral=True)
        return
    bad_words.remove(mot)
    set_guild_config(interaction.guild.id, "bad_words", bad_words)
    await interaction.response.send_message(embed=firm1_embed("✅ Mot retiré", f"`{mot}` n'est plus interdit.", color=COLOR_SUCCESS), ephemeral=True)

@tree.command(name="liste-badwords", description="[Admin] Affiche tous les mots interdits")
@app_commands.checks.has_permissions(administrator=True)
async def list_bad_words(interaction: discord.Interaction):
    cfg       = get_guild_config(interaction.guild.id)
    bad_words = cfg.get("bad_words", [])
    if not bad_words:
        await interaction.response.send_message(embed=firm1_embed("📋 Badwords", "Aucun mot interdit configuré.", color=COLOR_INFO), ephemeral=True)
        return
    mots_text = ", ".join(f"`{w}`" for w in bad_words)
    if len(mots_text) > 1000:
        mots_text = mots_text[:997] + "..."
    await interaction.response.send_message(embed=firm1_embed("📋 Liste des Badwords", mots_text, color=COLOR_WARNING, fields=[("📊 Total", str(len(bad_words)), True)]), ephemeral=True)

@tree.command(name="salon-no-lien", description="[Admin] Toggle interdiction de liens dans un salon")
@app_commands.describe(salon="Le salon concerné (défaut : salon actuel)")
@app_commands.checks.has_permissions(administrator=True)
async def toggle_no_link(interaction: discord.Interaction, salon: discord.TextChannel | None = None):
    target  = salon or interaction.channel
    cfg     = get_guild_config(interaction.guild.id)
    no_link = cfg.get("no_link_channels", [])
    if target.id in no_link:
        no_link.remove(target.id)
        msg   = f"✅ Les liens sont désormais **autorisés** dans {target.mention}."
        color = COLOR_SUCCESS
    else:
        no_link.append(target.id)
        msg   = f"🔗 Les liens sont désormais **interdits** dans {target.mention}."
        color = COLOR_WARNING
    set_guild_config(interaction.guild.id, "no_link_channels", no_link)
    await interaction.response.send_message(embed=firm1_embed("Salon no-lien mis à jour", msg, color=color), ephemeral=True)

@tree.command(name="salon-no-image", description="[Admin] Toggle interdiction d'images dans un salon")
@app_commands.describe(salon="Le salon concerné (défaut : salon actuel)")
@app_commands.checks.has_permissions(administrator=True)
async def toggle_no_image(interaction: discord.Interaction, salon: discord.TextChannel | None = None):
    target   = salon or interaction.channel
    cfg      = get_guild_config(interaction.guild.id)
    no_image = cfg.get("no_image_channels", [])
    if target.id in no_image:
        no_image.remove(target.id)
        msg   = f"✅ Les images sont désormais **autorisées** dans {target.mention}."
        color = COLOR_SUCCESS
    else:
        no_image.append(target.id)
        msg   = f"🖼️ Les images sont désormais **interdites** dans {target.mention}."
        color = COLOR_WARNING
    set_guild_config(interaction.guild.id, "no_image_channels", no_image)
    await interaction.response.send_message(embed=firm1_embed("Salon no-image mis à jour", msg, color=color), ephemeral=True)


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
    {"id": 100, "fr": "Voltorbe"}, {"id": 101, "fr": "Électrode"}, {"id": 102, "fr": "Nœunœuf"},
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
    {"id": 300, "fr": "Skitty"}, {"id": 301, "fr": "Delcatty"}, {"id": 302, "fr": "Mysdibule"},
    {"id": 303, "fr": "Ténéfix"}, {"id": 304, "fr": "Galekid"}, {"id": 305, "fr": "Galegon"},
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
    {"id": 668, "fr": "Némélios"}, {"id": 669, "fr": "Couafarel"}, {"id": 670, "fr": "Flabébé"},
    {"id": 671, "fr": "Floette"}, {"id": 672, "fr": "Florges"}, {"id": 673, "fr": "Cabriolaine"},
    {"id": 674, "fr": "Chevroum"}, {"id": 675, "fr": "Pandespiègle"}, {"id": 676, "fr": "Pandarbare"},
    {"id": 677, "fr": "Psytigri"}, {"id": 678, "fr": "Mistigrix"}, {"id": 679, "fr": "Monorpale"},
    {"id": 680, "fr": "Dimoclès"}, {"id": 681, "fr": "Exagide"}, {"id": 682, "fr": "Sucroquin"},
    {"id": 683, "fr": "Cupcanaille"}, {"id": 684, "fr": "Fluvetin"}, {"id": 685, "fr": "Cocotine"},
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


async def update_pokemon_top_roles(guild: discord.Guild):
    scores = pokemon_scores.get(guild.id, {})
    if not scores:
        return
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top3_uids = [uid for uid, _ in sorted_scores[:3]]
    roles = []
    for nom, couleur, _ in POKEMON_TOP_ROLES:
        role = discord.utils.get(guild.roles, name=nom)
        if not role:
            try:
                role = await guild.create_role(name=nom, color=couleur, hoist=True, reason="Rôle automatique Top Pokémon — Firm1 Bot")
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
                await member.add_roles(roles[i], reason=f"Top {i+1} Pokémon — Firm1 Bot")
            except Exception:
                pass


@tree.command(name="pokemon", description="Quel est ce Pokémon ? Devinez son nom en français !")
async def pokemon_cmd(interaction: discord.Interaction):
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

    embed = discord.Embed(
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
    embed.set_footer(text=f"Pokémon n°{pokemon['id']} • Firm1 Bot")
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

                win_embed = discord.Embed(
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
                win_embed.set_footer(text=f"Pokémon n°{pokemon['id']} • Firm1 Bot")
                await msg.channel.send(embed=win_embed)
                break

    except asyncio.TimeoutError:
        active_pokemon_games.pop(channel_id, None)
        timeout_embed = discord.Embed(
            title="⏰ Temps écoulé !",
            description=f"Personne n'a trouvé... C'était **{pokemon['fr']}** !",
            color=COLOR_ERROR,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        timeout_embed.set_thumbnail(url=image_url)
        timeout_embed.set_footer(text=f"Pokémon n°{pokemon['id']} • Firm1 Bot")
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
    embed = discord.Embed(title="🏆 Classement Pokémon — Meilleurs Dresseurs", description="\n".join(lines), color=COLOR_WARNING, timestamp=datetime.datetime.now(datetime.timezone.utc))
    embed.add_field(name="🎭 Titres du Top 3", value=("🥇 **1er** → Professeur Pokémon\n🥈 **2ème** → Expert du pokédex\n🥉 **3ème** → Grand connaisseur des Pokémon"), inline=False)
    embed.set_footer(text="Firm1 Bot • Support Gaming")
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
        embed = discord.Embed(
            title="👾  Firm1 Bot",
            description=("```\n  Le bot officiel de la communauté Firm1.\n  Support • Modération • Mini-Jeux\n```\nTapez `/help` pour voir toutes les commandes."),
            color=COLOR_PRIMARY,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.add_field(name="📊 Stats sur ce serveur", value=(f"🎫 Catégories tickets : **{len(cfg.get('ticket_categories', []))}**\n🚫 Mots interdits : **{len(cfg.get('bad_words', []))}**\n🔗 Salons sans liens : **{len(cfg.get('no_link_channels', []))}**\n🖼️ Salons sans images : **{len(cfg.get('no_image_channels', []))}**"), inline=True)
        embed.add_field(name="⚡ Fonctionnalités", value=("🎫 Système de tickets\n🔨 Modération complète\n🤖 Auto-modération\n🛡️ Whitelist & Blacklist\n🎮 Mini-jeux"), inline=True)
        embed.set_thumbnail(url=bot.user.display_avatar.url)
        embed.set_footer(text=f"Firm1 Bot • Sur {len(bot.guilds)} serveur(s)")
        await message.reply(embed=embed, mention_author=False)
        return

    cfg       = get_guild_config(message.guild.id)
    content   = message.content.lower()
    bad_words = cfg.get("bad_words", [])
    whitelist = cfg.get("whitelist", [])

    content_spaced = f" {content} "
    for word in bad_words:
        pattern = re.compile(r"(?<![a-zA-ZÀ-ÿ])" + re.escape(word) + r"(?![a-zA-ZÀ-ÿ])", re.IGNORECASE)
        if pattern.search(content_spaced):
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

async def update_pokemon_top_roles(guild: discord.Guild):
    scores = pokemon_scores.get(guild.id, {})
    if not scores:
        return
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top3_uids = [uid for uid, _ in sorted_scores[:3]]
    roles = []
    for nom, couleur, _ in POKEMON_TOP_ROLES:
        role = discord.utils.get(guild.roles, name=nom)
        if not role:
            try:
                role = await guild.create_role(name=nom, color=couleur, hoist=True, reason="Rôle automatique Top Pokémon — Firm1 Bot")
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
                await member.add_roles(roles[i], reason=f"Top {i+1} Pokémon — Firm1 Bot")
            except Exception:
                pass


@tree.command(name="pokemon", description="Quel est ce Pokémon ? Devinez son nom en français !")
async def pokemon_cmd(interaction: discord.Interaction):
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

    embed = discord.Embed(
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
    embed.set_footer(text=f"Pokémon n°{pokemon['id']} • Firm1 Bot")
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

                win_embed = discord.Embed(
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
                win_embed.set_footer(text=f"Pokémon n°{pokemon['id']} • Firm1 Bot")
                await msg.channel.send(embed=win_embed)
                break

    except asyncio.TimeoutError:
        active_pokemon_games.pop(channel_id, None)
        timeout_embed = discord.Embed(
            title="⏰ Temps écoulé !",
            description=f"Personne n'a trouvé... C'était **{pokemon['fr']}** !",
            color=COLOR_ERROR,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        timeout_embed.set_thumbnail(url=image_url)
        timeout_embed.set_footer(text=f"Pokémon n°{pokemon['id']} • Firm1 Bot")
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
        if i == 0:
            role_txt = " — *Professeur Pokémon*"
        elif i == 1:
            role_txt = " — *Expert du pokédex*"
        elif i == 2:
            role_txt = " — *Grand connaisseur des Pokémon*"
        lines.append(f"{medal} **{name}**{role_txt} : {score} bonne(s) réponse(s)")
    embed = discord.Embed(title="🏆 Classement Pokémon — Meilleurs Dresseurs", description="\n".join(lines), color=COLOR_WARNING, timestamp=datetime.datetime.now(datetime.timezone.utc))
    embed.add_field(name="🎭 Titres du Top 3", value=("🥇 **1er** → Professeur Pokémon\n🥈 **2ème** → Expert du pokédex\n🥉 **3ème** → Grand connaisseur des Pokémon"), inline=False)
    embed.set_footer(text="Firm1 Bot • Support Gaming")
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
        embed = discord.Embed(
            title="👾  Firm1 Bot",
            description=(
                "```\n"
                "  Le bot officiel de la communauté Firm1.\n"
                "  Support • Modération • Mini-Jeux\n"
                "```\n"
                "Tapez `/help` pour voir toutes les commandes."
            ),
            color=COLOR_PRIMARY,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.add_field(name="📊 Stats sur ce serveur", value=(f"🎫 Catégories tickets : **{len(cfg.get('ticket_categories', []))}**\n🚫 Mots interdits : **{len(cfg.get('bad_words', []))}**\n🔗 Salons sans liens : **{len(cfg.get('no_link_channels', []))}**\n🖼️ Salons sans images : **{len(cfg.get('no_image_channels', []))}**"), inline=True)
        embed.add_field(name="⚡ Fonctionnalités", value=("🎫 Système de tickets\n🔨 Modération complète\n🤖 Auto-modération\n🛡️ Whitelist & Blacklist\n🎮 Mini-jeux"), inline=True)
        embed.set_thumbnail(url=bot.user.display_avatar.url)
        embed.set_footer(text=f"Firm1 Bot • Sur {len(bot.guilds)} serveur(s)")
        await message.reply(embed=embed, mention_author=False)
        return

    cfg       = get_guild_config(message.guild.id)
    content   = message.content.lower()
    bad_words = cfg.get("bad_words", [])
    whitelist = cfg.get("whitelist", [])

    content_spaced = f" {content} "
    for word in bad_words:
        pattern = re.compile(r"(?<![a-zA-ZÀ-ÿ])" + re.escape(word) + r"(?![a-zA-ZÀ-ÿ])", re.IGNORECASE)
        if pattern.search(content_spaced):
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
