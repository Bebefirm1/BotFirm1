"""
╔══════════════════════════════════════════════════════════╗
║          🤖 MOUREN — Discord Multi-Fonctions          ║
║     Tickets • Mini-Jeux • Modération • Embeds stylés     ║
╚══════════════════════════════════════════════════════════╝

Dépendances :
    pip install discord.py python-dotenv

Configuration :
    Créez un fichier .env avec :  Token_bot=VOTRE_TOKEN_ICI
    Placez keep_alive.py dans le même dossier (optionnel pour Replit).
    Utilisez /config-tickets pour personnaliser le salon de logs et les rôles pingés.
    Aucun rôle ni salon n'est requis par défaut — tout est configurable via les commandes.
"""

import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from keep_alive import keep_alive
import random
import asyncio
import datetime
import json
import os

load_dotenv()
token = os.getenv('Token_bot')

# ─────────────────────────────────────────────
#  Configuration
# ─────────────────────────────────────────────

TICKET_CATEGORY_NAME = "🎫 Tickets"   # Nom de la catégorie créée automatiquement

# Couleurs de la palette Mouren
COLOR_PRIMARY   = 0x5865F2   # Blurple Discord
COLOR_SUCCESS   = 0x57F287   # Vert
COLOR_WARNING   = 0xFEE75C   # Jaune
COLOR_ERROR     = 0xED4245   # Rouge
COLOR_INFO      = 0x00B0FF   # Bleu clair

# ─────────────────────────────────────────────
#  Intents & Bot
# ─────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="/", intents=intents)   # Toutes les commandes sont des slash commands (/)
tree = bot.tree

# Stockage simple des tickets (en mémoire)
open_tickets: dict[int, dict] = {}   # user_id -> {channel_id, created_at, reason}

# ─────────────────────────────────────────────
#  Helpers Embed
# ─────────────────────────────────────────────
def mouren_embed(
    title: str,
    description: str,
    color: int = COLOR_PRIMARY,
    footer: str | None = None,
    thumbnail: str | None = None,
    fields: list[tuple[str, str, bool]] | None = None,
) -> discord.Embed:
    """Crée un embed stylisé aux couleurs de Mouren."""
    embed = discord.Embed(
        title=f"✦ {title}",
        description=description,
        color=color,
        timestamp=datetime.datetime.utcnow(),
    )
    embed.set_footer(
        text=footer or "Mouren • mouren.bot",
        icon_url="https://cdn.discordapp.com/emojis/1234567890.png",  # Remplacez par votre icône
    )
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
    return embed


# ─────────────────────────────────────────────
#  Événements
# ─────────────────────────────────────────────
@bot.event
async def on_ready():
    await tree.sync()
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="⚡ /help pour commencer"
        )
    )
    print(f"✅ Mouren connecté en tant que {bot.user} (ID: {bot.user.id})")
    print(f"📋 Serveurs : {len(bot.guilds)}")


@bot.event
async def on_guild_join(guild: discord.Guild):
    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            embed = mouren_embed(
                title="Mouren est arrivé !",
                description=(
                    "Merci de m'avoir invité sur ce serveur ✨\n\n"
                    "Tapez `/help` pour voir toutes les commandes disponibles.\n"
                    "Configurez les permissions du rôle **Support** pour gérer les tickets."
                ),
                color=COLOR_SUCCESS,
            )
            await channel.send(embed=embed)
            break


# ─────────────────────────────────────────────
#  COMMANDES GÉNÉRALES
# ─────────────────────────────────────────────
@tree.command(name="help", description="Affiche l'aide complète de Mouren")
async def help_cmd(interaction: discord.Interaction):
    embed = mouren_embed(
        title="Aide — Mouren",
        description="Voici toutes les commandes disponibles, classées par catégorie.",
        color=COLOR_PRIMARY,
        fields=[
            ("🎫 **Tickets**", (
                "`/ticket <raison>` — Ouvrir un ticket\n"
                "`/fermer` — Fermer votre ticket\n"
                "`/ajouter <@user>` — Ajouter un utilisateur au ticket\n"
                "`/retirer <@user>` — Retirer un utilisateur du ticket"
            ), False),
            ("⚙️ **Config Tickets** *(Admin)*", (
                "`/config-tickets` — Voir la configuration actuelle\n"
                "`/set-log-tickets #salon` — Définir le salon de logs\n"
                "`/ajouter-role-ticket @role` — Ajouter un rôle ping\n"
                "`/retirer-role-ticket @role` — Retirer un rôle ping\n"
                "`/reset-config-tickets` — Réinitialiser la config\n"
                "`/panel-tickets` — Envoyer le panel"
            ), False),
            ("🎮 **Mini-Jeux**", (
                "`/pile-ou-face` — Lancer une pièce\n"
                "`/dé [faces]` — Lancer un dé\n"
                "`/rps <choix>` — Pierre-papier-ciseaux\n"
                "`/nombre [max]` — Deviner un nombre\n"
                "`/8ball <question>` — Boule magique\n"
                "`/trivia` — Question de culture générale"
            ), False),
            ("🛠️ **Utilitaires**", (
                "`/ping` — Latence du bot\n"
                "`/info-serveur` — Infos sur le serveur\n"
                "`/info-user [@user]` — Infos sur un utilisateur\n"
                "`/avatar [@user]` — Avatar d'un utilisateur"
            ), False),
        ],
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(name="ping", description="Affiche la latence du bot")
async def ping_cmd(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    color = COLOR_SUCCESS if latency < 100 else (COLOR_WARNING if latency < 200 else COLOR_ERROR)
    status = "🟢 Excellent" if latency < 100 else ("🟡 Correct" if latency < 200 else "🔴 Élevé")
    embed = mouren_embed(
        title="Pong !",
        description=f"**Latence WebSocket :** `{latency} ms`\n**Statut :** {status}",
        color=color,
    )
    await interaction.response.send_message(embed=embed)


@tree.command(name="info-serveur", description="Informations sur le serveur")
async def server_info(interaction: discord.Interaction):
    guild = interaction.guild
    embed = mouren_embed(
        title=f"Serveur — {guild.name}",
        description=guild.description or "Aucune description.",
        color=COLOR_INFO,
        thumbnail=guild.icon.url if guild.icon else None,
        fields=[
            ("👑 Propriétaire",    str(guild.owner), True),
            ("👥 Membres",         str(guild.member_count), True),
            ("📁 Salons",          str(len(guild.channels)), True),
            ("🎭 Rôles",           str(len(guild.roles)), True),
            ("🔒 Vérification",    str(guild.verification_level).title(), True),
            ("📅 Créé le",
             f"<t:{int(guild.created_at.timestamp())}:D>", True),
        ],
    )
    await interaction.response.send_message(embed=embed)


@tree.command(name="info-user", description="Informations sur un utilisateur")
@app_commands.describe(membre="L'utilisateur à inspecter (optionnel)")
async def user_info(interaction: discord.Interaction, membre: discord.Member | None = None):
    membre = membre or interaction.user
    roles = [r.mention for r in membre.roles if r.name != "@everyone"]
    embed = mouren_embed(
        title=f"Utilisateur — {membre.display_name}",
        description=f"**Tag :** {membre}\n**ID :** `{membre.id}`",
        color=COLOR_INFO,
        thumbnail=membre.display_avatar.url,
        fields=[
            ("📅 Compte créé", f"<t:{int(membre.created_at.timestamp())}:D>", True),
            ("📥 A rejoint le", f"<t:{int(membre.joined_at.timestamp())}:D>", True),
            ("🎭 Rôles", " ".join(roles) if roles else "Aucun", False),
        ],
    )
    await interaction.response.send_message(embed=embed)


@tree.command(name="avatar", description="Affiche l'avatar d'un utilisateur")
@app_commands.describe(membre="L'utilisateur (optionnel)")
async def avatar_cmd(interaction: discord.Interaction, membre: discord.Member | None = None):
    membre = membre or interaction.user
    embed = mouren_embed(
        title=f"Avatar de {membre.display_name}",
        description=f"[Ouvrir en plein écran]({membre.display_avatar.url})",
        color=COLOR_INFO,
    )
    embed.set_image(url=membre.display_avatar.url)
    await interaction.response.send_message(embed=embed)


# ─────────────────────────────────────────────
#  CONFIGURATION TICKETS (persistante par serveur)
# ─────────────────────────────────────────────
CONFIG_FILE = "ticket_config.json"

def _load_config() -> dict:
    """Charge la configuration depuis le fichier JSON."""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def _save_config(data: dict):
    """Sauvegarde la configuration dans le fichier JSON."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_guild_config(guild_id: int) -> dict:
    """Retourne la config du serveur, avec valeurs par défaut."""
    cfg = _load_config()
    gid = str(guild_id)
    if gid not in cfg:
        cfg[gid] = {}
    return cfg.get(gid, {})

def set_guild_config(guild_id: int, key: str, value):
    """Met à jour une clé de config pour un serveur."""
    cfg = _load_config()
    gid = str(guild_id)
    if gid not in cfg:
        cfg[gid] = {}
    cfg[gid][key] = value
    _save_config(cfg)

# ─────────────────────────────────────────────
#  SYSTÈME DE TICKETS
# ─────────────────────────────────────────────

class TicketReasonModal(discord.ui.Modal, title="📋 Ouvrir un ticket"):
    """Modal pour saisir la raison du ticket."""

    raison = discord.ui.TextInput(
        label="Raison de votre demande",
        placeholder="Décrivez brièvement votre problème ou question…",
        style=discord.TextStyle.paragraph,
        max_length=300,
        required=True,
    )

    categorie = discord.ui.TextInput(
        label="Catégorie",
        placeholder="Support, Bug, Question, Autre…",
        max_length=50,
        required=False,
        default="Support général",
    )

    async def on_submit(self, interaction: discord.Interaction):
        raison_text = f"[{self.categorie.value or 'Support général'}] {self.raison.value}"
        await _creer_ticket(interaction, raison=raison_text)


class TicketCloseConfirmView(discord.ui.View):
    """Vue de confirmation avant fermeture."""

    def __init__(self):
        super().__init__(timeout=30)

    @discord.ui.button(label="✅ Confirmer la fermeture", style=discord.ButtonStyle.danger, custom_id="confirm_close")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _fermer_ticket(interaction)

    @discord.ui.button(label="❌ Annuler", style=discord.ButtonStyle.secondary, custom_id="cancel_close")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = mouren_embed("Fermeture annulée", "Le ticket reste ouvert.", color=COLOR_SUCCESS)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        self.stop()


class TicketCloseView(discord.ui.View):
    """Boutons de gestion affichés dans le ticket."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Fermer le ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = mouren_embed(
            title="Confirmation",
            description="Êtes-vous sûr de vouloir fermer ce ticket ?",
            color=COLOR_WARNING,
        )
        view = TicketCloseConfirmView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="📌 Revendiquer", style=discord.ButtonStyle.success, custom_id="claim_ticket")
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = get_guild_config(interaction.guild.id)
        ping_role_ids: list = cfg.get("ping_roles", [])
        is_staff = interaction.user.guild_permissions.administrator
        if not is_staff:
            member_role_ids = [r.id for r in interaction.user.roles]
            is_staff = any(rid in member_role_ids for rid in ping_role_ids)
        if not is_staff:
            await interaction.response.send_message(
                embed=mouren_embed("Accès refusé", "Seul le staff (rôles configurés ou admin) peut revendiquer un ticket.", color=COLOR_ERROR),
                ephemeral=True,
            )
            return
        embed = mouren_embed(
            title="Ticket revendiqué 📌",
            description=f"Ce ticket est maintenant géré par {interaction.user.mention}.",
            color=COLOR_SUCCESS,
        )
        button.disabled = True
        button.label = f"📌 {interaction.user.display_name}"
        await interaction.message.edit(view=self)
        await interaction.response.send_message(embed=embed)


class TicketOpenView(discord.ui.View):
    """Panel principal d'ouverture de tickets."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🎫 Ouvrir un ticket",
        style=discord.ButtonStyle.primary,
        custom_id="open_ticket_btn",
        row=0,
    )
    async def open_ticket_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = TicketReasonModal()
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="📖 Comment ça marche ?",
        style=discord.ButtonStyle.secondary,
        custom_id="ticket_info_btn",
        row=0,
    )
    async def info_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = mouren_embed(
            title="Comment ouvrir un ticket ?",
            description=(
                "**1.** Cliquez sur **🎫 Ouvrir un ticket**\n"
                "**2.** Remplissez le formulaire (raison + catégorie)\n"
                "**3.** Un salon privé sera créé pour vous\n"
                "**4.** Le staff vous répondra dès que possible\n\n"
                "⚠️ *Un seul ticket par utilisateur. Merci d'être précis.*"
            ),
            color=COLOR_INFO,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def _creer_ticket(interaction: discord.Interaction, raison: str = "Non spécifiée"):
    guild = interaction.guild
    user  = interaction.user
    cfg   = get_guild_config(guild.id)

    # Vérifie si un ticket est déjà ouvert
    if user.id in open_tickets:
        ch = guild.get_channel(open_tickets[user.id]["channel_id"])
        if ch:
            embed = mouren_embed(
                title="Ticket déjà ouvert",
                description=f"Vous avez déjà un ticket ouvert : {ch.mention}",
                color=COLOR_WARNING,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

    # Catégorie tickets
    category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME)
    if not category:
        category = await guild.create_category(TICKET_CATEGORY_NAME)

    # Permissions de base
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        user:               discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me:           discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
    }

    # ── Rôles configurés (ping_roles) ──
    ping_role_ids: list = cfg.get("ping_roles", [])
    ping_mentions: list[str] = []
    for rid in ping_role_ids:
        role = guild.get_role(rid)
        if role:
            overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            ping_mentions.append(role.mention)

    # Création du salon
    ticket_name = f"ticket-{user.name.lower().replace(' ', '-')}"
    channel = await category.create_text_channel(ticket_name, overwrites=overwrites)

    open_tickets[user.id] = {
        "channel_id": channel.id,
        "created_at": datetime.datetime.utcnow().isoformat(),
        "reason":     raison,
    }

    # Message de bienvenue dans le ticket
    embed = discord.Embed(
        title="🎫  Ticket ouvert",
        description=(
            f"Bienvenue {user.mention} !\n\n"
            f"> {raison}\n\n"
            "Le staff va vous répondre dès que possible.\n"
            "Merci de **décrire votre problème en détail** dès maintenant."
        ),
        color=COLOR_SUCCESS,
        timestamp=datetime.datetime.utcnow(),
    )
    embed.add_field(name="👤 Demandeur",  value=user.mention, inline=True)
    embed.add_field(name="🆔 ID",         value=f"`{user.id}`", inline=True)
    embed.add_field(name="📅 Ouvert le",  value=f"<t:{int(datetime.datetime.utcnow().timestamp())}:F>", inline=False)
    if ping_mentions:
        embed.add_field(name="🔔 Staff notifié", value=" ".join(ping_mentions), inline=False)
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.set_footer(text="Mouren • Support")
    view = TicketCloseView()

    # Ping du staff + embed
    ping_content = " ".join(ping_mentions) if ping_mentions else ""
    await channel.send(content=f"{user.mention} {ping_content}".strip(), embed=embed, view=view)

    # Confirmation ephemeral
    confirm = mouren_embed(
        title="Ticket créé !",
        description=f"Votre ticket est disponible ici : {channel.mention}",
        color=COLOR_SUCCESS,
    )
    await interaction.response.send_message(embed=confirm, ephemeral=True)

    # Log dans le salon configuré
    log_channel_id = cfg.get("log_channel_id")
    log_channel = guild.get_channel(log_channel_id) if log_channel_id else None
    if log_channel:
        log_embed = mouren_embed(
            title="📥 Nouveau ticket ouvert",
            description=f"**Canal :** {channel.mention}\n**Raison :** {raison}",
            color=COLOR_INFO,
            fields=[
                ("👤 Utilisateur", f"{user} (`{user.id}`)", True),
                ("🔔 Rôles notifiés", " ".join(ping_mentions) if ping_mentions else "Aucun", True),
            ],
        )
        await log_channel.send(embed=log_embed)


async def _fermer_ticket(interaction: discord.Interaction):
    channel = interaction.channel
    guild   = interaction.guild
    cfg     = get_guild_config(guild.id)
    user_id = None

    for uid, data in open_tickets.items():
        if data["channel_id"] == channel.id:
            user_id = uid
            break

    if user_id is None:
        embed = mouren_embed("Erreur", "Ce salon n'est pas un ticket.", color=COLOR_ERROR)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    embed = mouren_embed(
        title="Ticket en cours de fermeture…",
        description="Ce salon sera supprimé dans **5 secondes**.",
        color=COLOR_WARNING,
    )
    await interaction.response.send_message(embed=embed)

    # Log de fermeture
    log_channel_id = cfg.get("log_channel_id")
    log_channel = guild.get_channel(log_channel_id) if log_channel_id else None
    if log_channel:
        opener = guild.get_member(user_id)
        log_embed = mouren_embed(
            title="📤 Ticket fermé",
            description=f"**Canal :** #{channel.name}\n**Fermé par :** {interaction.user.mention}",
            color=COLOR_ERROR,
            fields=[("👤 Demandeur initial", str(opener) if opener else f"ID {user_id}", True)],
        )
        await log_channel.send(embed=log_embed)

    del open_tickets[user_id]
    await asyncio.sleep(5)
    await channel.delete(reason=f"Ticket fermé par {interaction.user}")


# ── Commandes tickets ──────────────────────────

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
    channel = interaction.channel
    is_ticket = any(d["channel_id"] == channel.id for d in open_tickets.values())
    if not is_ticket:
        await interaction.response.send_message(
            embed=mouren_embed("Erreur", "Cette commande doit être utilisée dans un ticket.", color=COLOR_ERROR),
            ephemeral=True,
        )
        return
    await channel.set_permissions(membre, read_messages=True, send_messages=True)
    embed = mouren_embed(
        title="Utilisateur ajouté",
        description=f"{membre.mention} a été ajouté à ce ticket.",
        color=COLOR_SUCCESS,
    )
    await interaction.response.send_message(embed=embed)


@tree.command(name="retirer", description="Retire un utilisateur du ticket actuel")
@app_commands.describe(membre="L'utilisateur à retirer")
async def retirer_cmd(interaction: discord.Interaction, membre: discord.Member):
    channel = interaction.channel
    is_ticket = any(d["channel_id"] == channel.id for d in open_tickets.values())
    if not is_ticket:
        await interaction.response.send_message(
            embed=mouren_embed("Erreur", "Cette commande doit être utilisée dans un ticket.", color=COLOR_ERROR),
            ephemeral=True,
        )
        return
    await channel.set_permissions(membre, overwrite=None)
    embed = mouren_embed(
        title="Utilisateur retiré",
        description=f"{membre.mention} a été retiré de ce ticket.",
        color=COLOR_WARNING,
    )
    await interaction.response.send_message(embed=embed)


# ── Configuration des tickets ──────────────────

@tree.command(name="config-tickets", description="[Admin] Configure les rôles et le salon des tickets")
@app_commands.checks.has_permissions(administrator=True)
async def config_tickets(interaction: discord.Interaction):
    """Affiche le menu interactif de configuration des tickets."""
    cfg = get_guild_config(interaction.guild.id)

    # Résumé actuel
    log_ch_id   = cfg.get("log_channel_id")
    ping_ids    = cfg.get("ping_roles", [])
    log_ch      = interaction.guild.get_channel(log_ch_id) if log_ch_id else None
    ping_roles  = [interaction.guild.get_role(rid) for rid in ping_ids if interaction.guild.get_role(rid)]

    embed = discord.Embed(
        title="⚙️  Configuration — Tickets",
        description=(
            "Utilisez les commandes ci-dessous pour personnaliser le système de tickets.\n"
            "Les changements sont **sauvegardés automatiquement** et persistent au redémarrage."
        ),
        color=COLOR_PRIMARY,
        timestamp=datetime.datetime.utcnow(),
    )
    embed.add_field(
        name="📋  Salon de logs actuel",
        value=log_ch.mention if log_ch else "❌ Non configuré — utilisez `/set-log-tickets #salon`",
        inline=False,
    )
    embed.add_field(
        name="🔔  Rôles pingés à l'ouverture",
        value=" ".join(r.mention for r in ping_roles) if ping_roles else "❌ Aucun — utilisez `/ajouter-role-ticket @role`",
        inline=False,
    )
    embed.add_field(
        name="🛠️  Commandes disponibles",
        value=(
            "`/set-log-tickets #salon` — Définir le salon de logs\n"
            "`/ajouter-role-ticket @role` — Ajouter un rôle pingSon\n"
            "`/retirer-role-ticket @role` — Retirer un rôle ping\n"
            "`/reset-config-tickets` — Remettre la config par défaut"
        ),
        inline=False,
    )
    embed.set_footer(text=f"Mouren • Config de {interaction.guild.name}")
    embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(name="set-log-tickets", description="[Admin] Définit le salon de logs des tickets")
@app_commands.describe(salon="Le salon texte qui recevra les logs de tickets")
@app_commands.checks.has_permissions(administrator=True)
async def set_log_tickets(interaction: discord.Interaction, salon: discord.TextChannel):
    set_guild_config(interaction.guild.id, "log_channel_id", salon.id)
    embed = mouren_embed(
        title="✅ Salon de logs mis à jour",
        description=f"Les logs de tickets seront désormais envoyés dans {salon.mention}.",
        color=COLOR_SUCCESS,
        fields=[("📁 Salon configuré", salon.mention, True)],
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(name="ajouter-role-ticket", description="[Admin] Ajoute un rôle à pinger lors de l'ouverture d'un ticket")
@app_commands.describe(role="Le rôle à ajouter à la liste des pings")
@app_commands.checks.has_permissions(administrator=True)
async def add_ping_role(interaction: discord.Interaction, role: discord.Role):
    cfg      = get_guild_config(interaction.guild.id)
    ping_ids = cfg.get("ping_roles", [])
    if role.id in ping_ids:
        await interaction.response.send_message(
            embed=mouren_embed(
                "Déjà présent",
                f"{role.mention} est déjà dans la liste des rôles pingés.",
                color=COLOR_WARNING,
            ),
            ephemeral=True,
        )
        return
    ping_ids.append(role.id)
    set_guild_config(interaction.guild.id, "ping_roles", ping_ids)

    # Afficher la liste complète mise à jour
    all_roles = [interaction.guild.get_role(rid) for rid in ping_ids if interaction.guild.get_role(rid)]
    embed = mouren_embed(
        title="✅ Rôle ping ajouté",
        description=f"{role.mention} sera désormais pingé à chaque nouveau ticket.",
        color=COLOR_SUCCESS,
        fields=[
            ("🔔 Liste complète des rôles pingés",
             " ".join(r.mention for r in all_roles), False),
        ],
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(name="retirer-role-ticket", description="[Admin] Retire un rôle de la liste des pings tickets")
@app_commands.describe(role="Le rôle à retirer")
@app_commands.checks.has_permissions(administrator=True)
async def remove_ping_role(interaction: discord.Interaction, role: discord.Role):
    cfg      = get_guild_config(interaction.guild.id)
    ping_ids = cfg.get("ping_roles", [])
    if role.id not in ping_ids:
        await interaction.response.send_message(
            embed=mouren_embed(
                "Introuvable",
                f"{role.mention} n'est pas dans la liste des rôles pingés.",
                color=COLOR_WARNING,
            ),
            ephemeral=True,
        )
        return
    ping_ids.remove(role.id)
    set_guild_config(interaction.guild.id, "ping_roles", ping_ids)

    all_roles = [interaction.guild.get_role(rid) for rid in ping_ids if interaction.guild.get_role(rid)]
    embed = mouren_embed(
        title="✅ Rôle ping retiré",
        description=f"{role.mention} ne sera plus pingé à l'ouverture d'un ticket.",
        color=COLOR_SUCCESS,
        fields=[
            ("🔔 Liste restante",
             " ".join(r.mention for r in all_roles) if all_roles else "Aucun rôle configuré", False),
        ],
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(name="reset-config-tickets", description="[Admin] Remet la configuration des tickets par défaut")
@app_commands.checks.has_permissions(administrator=True)
async def reset_config_tickets(interaction: discord.Interaction):
    cfg = _load_config()
    gid = str(interaction.guild.id)
    if gid in cfg:
        del cfg[gid]
        _save_config(cfg)
    embed = mouren_embed(
        title="🔄 Configuration réinitialisée",
        description=(
            "La configuration des tickets a été remise à zéro.\n\n"
            "• Salon de logs → ❌ Non configuré\n"
            "• Rôles pingés → ❌ Aucun\n\n"
            "Utilisez `/set-log-tickets` et `/ajouter-role-ticket` pour reconfigurer."
        ),
        color=COLOR_WARNING,
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(name="panel-tickets", description="[Admin] Envoie le panneau d'ouverture de tickets")
@app_commands.checks.has_permissions(administrator=True)
async def panel_tickets(interaction: discord.Interaction):
    cfg        = get_guild_config(interaction.guild.id)
    ping_ids   = cfg.get("ping_roles", [])
    ping_roles = [interaction.guild.get_role(rid) for rid in ping_ids if interaction.guild.get_role(rid)]
    log_ch_id  = cfg.get("log_channel_id")
    log_ch     = interaction.guild.get_channel(log_ch_id) if log_ch_id else None

    embed = discord.Embed(
        title="🎫  Centre de Support — Mouren",
        description=(
            "```\n"
            "  Besoin d'aide ? Notre équipe est là pour vous.\n"
            "  Cliquez sur le bouton ci-dessous pour créer\n"
            "  votre ticket de support privé.\n"
            "```"
        ),
        color=COLOR_PRIMARY,
        timestamp=datetime.datetime.utcnow(),
    )
    embed.add_field(
        name="📋  Comment ça fonctionne",
        value=(
            "**①** Cliquez sur `🎫 Ouvrir un ticket`\n"
            "**②** Remplissez le formulaire\n"
            "**③** Échangez avec le staff en privé\n"
            "**④** Fermez le ticket une fois résolu"
        ),
        inline=True,
    )
    embed.add_field(
        name="⏰  Disponibilité",
        value=(
            "🟢 **Lun — Ven**\n`09h00 → 22h00`\n\n"
            "🟡 **Sam — Dim**\n`12h00 → 20h00`"
        ),
        inline=True,
    )
    embed.add_field(
        name="🔔  Staff de support",
        value=(
            " ".join(r.mention for r in ping_roles)
            if ping_roles else "*Aucun rôle configuré*"
        ),
        inline=False,
    )
    embed.add_field(
        name="📌  Règles importantes",
        value=(
            "• Un seul ticket actif par membre\n"
            "• Soyez précis et respectueux\n"
            "• Pas de spam ni d'abus\n"
            "• Temps de réponse moyen : **< 2h**"
        ),
        inline=False,
    )
    embed.set_footer(text=f"Mouren • {interaction.guild.name}")
    embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)

    view = TicketOpenView()
    await interaction.channel.send(embed=embed, view=view)

    # Résumé de config pour l'admin
    confirm_embed = mouren_embed(
        title="✅ Panel envoyé !",
        description="Le panel de tickets a été créé avec succès.",
        color=COLOR_SUCCESS,
        fields=[
            ("📁 Logs", log_ch.mention if log_ch else "❌ Non configuré", True),
            ("🔔 Rôles pingés",
             " ".join(r.mention for r in ping_roles) if ping_roles else "❌ Aucun configuré", True),
        ],
    )
    await interaction.response.send_message(embed=confirm_embed, ephemeral=True)


# ─────────────────────────────────────────────
#  MINI-JEUX
# ─────────────────────────────────────────────

# Pile ou Face
@tree.command(name="pile-ou-face", description="Lance une pièce")
async def coin_flip(interaction: discord.Interaction):
    result = random.choice(["🪙 Pile", "🪙 Face"])
    embed = mouren_embed(
        title="Pile ou Face ?",
        description=f"La pièce a atterri sur… **{result}** !",
        color=random.choice([COLOR_SUCCESS, COLOR_WARNING]),
    )
    await interaction.response.send_message(embed=embed)


# Dé
@tree.command(name="dé", description="Lance un dé")
@app_commands.describe(faces="Nombre de faces du dé (défaut : 6)")
async def dice_roll(interaction: discord.Interaction, faces: int = 6):
    if faces < 2:
        await interaction.response.send_message(
            embed=mouren_embed("Erreur", "Le dé doit avoir au moins 2 faces.", color=COLOR_ERROR),
            ephemeral=True,
        )
        return
    result = random.randint(1, faces)
    embed = mouren_embed(
        title=f"🎲 Dé à {faces} faces",
        description=f"Résultat : **{result}**",
        color=COLOR_INFO,
    )
    await interaction.response.send_message(embed=embed)


# Pierre-Papier-Ciseaux
RPS_CHOICES = {"pierre": "🪨", "papier": "📄", "ciseaux": "✂️"}
RPS_WINS    = {"pierre": "ciseaux", "papier": "pierre", "ciseaux": "papier"}

@tree.command(name="rps", description="Pierre-Papier-Ciseaux contre le bot")
@app_commands.describe(choix="Votre choix")
@app_commands.choices(choix=[
    app_commands.Choice(name="🪨 Pierre",  value="pierre"),
    app_commands.Choice(name="📄 Papier",  value="papier"),
    app_commands.Choice(name="✂️ Ciseaux", value="ciseaux"),
])
async def rps(interaction: discord.Interaction, choix: app_commands.Choice[str]):
    player = choix.value
    bot_choice = random.choice(list(RPS_CHOICES.keys()))

    if player == bot_choice:
        result, color = "Égalité !", COLOR_WARNING
    elif RPS_WINS[player] == bot_choice:
        result, color = "Vous gagnez ! 🎉", COLOR_SUCCESS
    else:
        result, color = "Vous perdez… 😢", COLOR_ERROR

    embed = mouren_embed(
        title="Pierre-Papier-Ciseaux",
        description=result,
        color=color,
        fields=[
            ("Vous",  f"{RPS_CHOICES[player]} {player.title()}", True),
            ("Bot",   f"{RPS_CHOICES[bot_choice]} {bot_choice.title()}", True),
        ],
    )
    await interaction.response.send_message(embed=embed)


# 8-Ball
EIGHTBALL_REPLIES = [
    ("✅ C'est certain.", COLOR_SUCCESS),
    ("✅ Oui, définitivement.", COLOR_SUCCESS),
    ("✅ Sans aucun doute.", COLOR_SUCCESS),
    ("✅ Oui, absolument.", COLOR_SUCCESS),
    ("✅ Vous pouvez compter là-dessus.", COLOR_SUCCESS),
    ("🟡 Demandez à nouveau plus tard.", COLOR_WARNING),
    ("🟡 Il vaut mieux ne pas répondre maintenant.", COLOR_WARNING),
    ("🟡 Impossible de prédire pour l'instant.", COLOR_WARNING),
    ("❌ N'y comptez pas.", COLOR_ERROR),
    ("❌ Ma réponse est non.", COLOR_ERROR),
    ("❌ Les perspectives ne sont pas bonnes.", COLOR_ERROR),
    ("❌ Très douteux.", COLOR_ERROR),
]

@tree.command(name="8ball", description="Posez une question à la boule magique")
@app_commands.describe(question="Votre question")
async def eightball(interaction: discord.Interaction, question: str):
    answer, color = random.choice(EIGHTBALL_REPLIES)
    embed = mouren_embed(
        title="🎱 Boule Magique",
        description=answer,
        color=color,
        fields=[("❓ Question", question, False)],
    )
    await interaction.response.send_message(embed=embed)


# Devine un nombre
active_guess_games: dict[int, int] = {}   # channel_id -> number

@tree.command(name="nombre", description="Devinez le nombre secret !")
@app_commands.describe(maximum="Valeur maximale (défaut : 100)")
async def guess_number(interaction: discord.Interaction, maximum: int = 100):
    channel_id = interaction.channel_id
    if channel_id in active_guess_games:
        embed = mouren_embed("Partie en cours", "Une partie est déjà en cours dans ce salon.", color=COLOR_WARNING)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    number = random.randint(1, maximum)
    active_guess_games[channel_id] = number

    embed = mouren_embed(
        title="🔢 Devinez le nombre !",
        description=(
            f"J'ai choisi un nombre entre **1** et **{maximum}**.\n"
            "Envoyez votre réponse dans ce salon. Vous avez **30 secondes** !"
        ),
        color=COLOR_INFO,
    )
    await interaction.response.send_message(embed=embed)

    def check(m: discord.Message):
        return m.channel.id == channel_id and m.content.isdigit()

    try:
        while True:
            msg = await bot.wait_for("message", timeout=30.0, check=check)
            guess = int(msg.content)

            if guess == number:
                del active_guess_games[channel_id]
                win_embed = mouren_embed(
                    title="🎉 Bonne réponse !",
                    description=f"{msg.author.mention} a trouvé le nombre **{number}** !",
                    color=COLOR_SUCCESS,
                )
                await msg.channel.send(embed=win_embed)
                break
            elif guess < number:
                hint = mouren_embed("💡 Trop petit !", f"Le nombre est **plus grand** que {guess}.", color=COLOR_WARNING)
                await msg.channel.send(embed=hint, delete_after=5)
            else:
                hint = mouren_embed("💡 Trop grand !", f"Le nombre est **plus petit** que {guess}.", color=COLOR_WARNING)
                await msg.channel.send(embed=hint, delete_after=5)

    except asyncio.TimeoutError:
        if channel_id in active_guess_games:
            del active_guess_games[channel_id]
        timeout_embed = mouren_embed(
            title="⏰ Temps écoulé !",
            description=f"Le nombre était **{number}**. Retentez votre chance !",
            color=COLOR_ERROR,
        )
        await interaction.channel.send(embed=timeout_embed)


# Trivia (questions françaises)
TRIVIA_QUESTIONS = [
    {
        "question": "Quelle est la capitale de la France ?",
        "answer":   "paris",
        "options":  ["Paris", "Lyon", "Marseille", "Bordeaux"],
        "correct":  0,
    },
    {
        "question": "Combien y a-t-il de planètes dans le système solaire ?",
        "answer":   "8",
        "options":  ["7", "8", "9", "10"],
        "correct":  1,
    },
    {
        "question": "Qui a peint la Joconde ?",
        "answer":   "léonard de vinci",
        "options":  ["Michel-Ange", "Raphaël", "Léonard de Vinci", "Botticelli"],
        "correct":  2,
    },
    {
        "question": "En quelle année a eu lieu la Révolution française ?",
        "answer":   "1789",
        "options":  ["1776", "1789", "1800", "1815"],
        "correct":  1,
    },
    {
        "question": "Quelle est la formule chimique de l'eau ?",
        "answer":   "h2o",
        "options":  ["CO2", "H2O", "O2", "NaCl"],
        "correct":  1,
    },
    {
        "question": "Quel est le plus grand océan du monde ?",
        "answer":   "pacifique",
        "options":  ["Atlantique", "Indien", "Pacifique", "Arctique"],
        "correct":  2,
    },
    {
        "question": "Combien de cordes a une guitare standard ?",
        "answer":   "6",
        "options":  ["4", "5", "6", "7"],
        "correct":  2,
    },
    {
        "question": "Quel pays a inventé les spaghettis ?",
        "answer":   "italie",
        "options":  ["France", "Chine", "Italie", "Espagne"],
        "correct":  2,
    },
]

@tree.command(name="trivia", description="Question de culture générale")
async def trivia(interaction: discord.Interaction):
    q = random.choice(TRIVIA_QUESTIONS)
    letters = ["🇦", "🇧", "🇨", "🇩"]
    options_text = "\n".join(f"{letters[i]} {opt}" for i, opt in enumerate(q["options"]))

    embed = mouren_embed(
        title="🧠 Trivia !",
        description=f"**{q['question']}**\n\n{options_text}\n\nRépondez avec **A**, **B**, **C** ou **D**. Vous avez **20 secondes** !",
        color=COLOR_INFO,
    )
    await interaction.response.send_message(embed=embed)

    def check(m: discord.Message):
        return (
            m.channel.id == interaction.channel_id
            and m.author.id == interaction.user.id
            and m.content.upper() in ["A", "B", "C", "D"]
        )

    try:
        msg = await bot.wait_for("message", timeout=20.0, check=check)
        user_index = ["A", "B", "C", "D"].index(msg.content.upper())

        if user_index == q["correct"]:
            result_embed = mouren_embed(
                title="✅ Bonne réponse !",
                description=f"La réponse était bien **{q['options'][q['correct']]}** ! 🎉",
                color=COLOR_SUCCESS,
            )
        else:
            result_embed = mouren_embed(
                title="❌ Mauvaise réponse !",
                description=f"La bonne réponse était **{q['options'][q['correct']]}**.",
                color=COLOR_ERROR,
            )
        await interaction.channel.send(embed=result_embed)

    except asyncio.TimeoutError:
        timeout_embed = mouren_embed(
            title="⏰ Temps écoulé !",
            description=f"La bonne réponse était **{q['options'][q['correct']]}**.",
            color=COLOR_ERROR,
        )
        await interaction.channel.send(embed=timeout_embed)


# ─────────────────────────────────────────────
#  Gestion des erreurs globales
# ─────────────────────────────────────────────
@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        embed = mouren_embed(
            title="Permission refusée",
            description="Vous n'avez pas les permissions nécessaires.",
            color=COLOR_ERROR,
        )
    elif isinstance(error, app_commands.CommandOnCooldown):
        embed = mouren_embed(
            title="Cooldown",
            description=f"Attendez encore **{error.retry_after:.1f}s** avant de réutiliser cette commande.",
            color=COLOR_WARNING,
        )
    else:
        embed = mouren_embed(
            title="Erreur inattendue",
            description=f"```{str(error)[:200]}```",
            color=COLOR_ERROR,
        )
    try:
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except discord.InteractionResponded:
        await interaction.followup.send(embed=embed, ephemeral=True)


# ─────────────────────────────────────────────
#  Lancement
# ─────────────────────────────────────────────
if __name__ == "__main__":
    keep_alive()
    # Lancement du bot
    try:
        token = os.environ['Token_bot']
        bot.run(token)
    except KeyError:
        print("❌ Token introuvable ! Vérifiez votre fichier .env ou vos secrets Replit.")
    except discord.LoginFailure:
        print("❌ Token invalide ! Vérifiez votre token Discord.")
