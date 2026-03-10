"""
╔══════════════════════════════════════════════════════════╗
║           🎮 FIRM1 — Bot de Gestion Discord             ║
║          Tickets • Support • Mini-Jeux • Utilitaires     ║
╚══════════════════════════════════════════════════════════╝

Firm1 est le bot officiel de gestion de la communauté gaming Firm1.
Il centralise le support via un système de tickets structuré,
propose des mini-jeux et des outils d'administration.

Dépendances :
    pip install discord.py python-dotenv flask

Configuration :
    Créez un fichier .env avec :  Token_bot=VOTRE_TOKEN_ICI
    Utilisez /config-tickets pour personnaliser le salon de logs et les rôles pingés.
    Aucun rôle ni salon n'est requis par défaut — tout est configurable via les commandes.
"""

import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
try:
    from keep_alive import keep_alive
    KEEP_ALIVE_AVAILABLE = True
except ImportError:
    KEEP_ALIVE_AVAILABLE = False
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

# Couleurs de la palette Firm1
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
def firm1_embed(
    title: str,
    description: str,
    color: int = COLOR_PRIMARY,
    footer: str | None = None,
    thumbnail: str | None = None,
    fields: list[tuple[str, str, bool]] | None = None,
) -> discord.Embed:
    """Crée un embed stylisé aux couleurs de Firm1."""
    embed = discord.Embed(
        title=f"✦ {title}",
        description=description,
        color=color,
        timestamp=datetime.datetime.utcnow(),
    )
    embed.set_footer(
        text=footer or "Firm1 Bot • Support Gaming",
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
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="🎮 /help • Support Firm1"
        )
    )
    print(f"✅ Firm1 connecté en tant que {bot.user} (ID: {bot.user.id})")
    print(f"📋 Serveurs : {len(bot.guilds)}")
    # Sync global
    await tree.sync()
    print("✅ Sync global effectué.")
    # Sync instantané par serveur (commandes visibles immédiatement)
    for guild in bot.guilds:
        try:
            await tree.sync(guild=guild)
            print(f"✅ Commandes sync sur : {guild.name}")
        except Exception as e:
            print(f"⚠️ Sync échoué sur {guild.name} : {e}")


@bot.event
async def on_guild_join(guild: discord.Guild):
    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            embed = firm1_embed(
                title="Firm1 Bot est opérationnel !",
                description=(
                    "**Firm1** est désormais actif sur ce serveur. 🎮\n\n"
                    "Utilisez `/help` pour consulter toutes les commandes disponibles.\n"
                    "Configurez le système de tickets avec `/config-tickets`."
                ),
                color=COLOR_SUCCESS,
            )
            await channel.send(embed=embed)
            break


# ─────────────────────────────────────────────
#  COMMANDES GÉNÉRALES
# ─────────────────────────────────────────────

# ─────────────────────────────────────────────
#  DICTIONNAIRE COMPLET DES COMMANDES (pour /help <commande>)
# ─────────────────────────────────────────────
COMMANDS_DETAIL = {
    # Tickets
    "ticket": {
        "usage": "/ticket <raison>",
        "description": "Ouvre un ticket de support privé. Un salon dédié est créé avec les permissions appropriées.",
        "args": [("raison", "Optionnel", "Décrit votre problème ou demande.")],
        "perms": "Tout le monde",
        "category": "🎫 Tickets",
    },
    "fermer": {
        "usage": "/fermer",
        "description": "Ferme le ticket actuel. Une confirmation est demandée avant la suppression du salon (5s).",
        "args": [],
        "perms": "Tout le monde (dans un ticket)",
        "category": "🎫 Tickets",
    },
    "ajouter": {
        "usage": "/ajouter <@user>",
        "description": "Ajoute un membre au ticket actuel pour qu'il puisse lire et écrire dedans.",
        "args": [("@user", "Requis", "Le membre à ajouter.")],
        "perms": "Tout le monde (dans un ticket)",
        "category": "🎫 Tickets",
    },
    "retirer": {
        "usage": "/retirer <@user>",
        "description": "Retire les permissions d'un membre dans le ticket actuel.",
        "args": [("@user", "Requis", "Le membre à retirer.")],
        "perms": "Tout le monde (dans un ticket)",
        "category": "🎫 Tickets",
    },
    "panel-tickets": {
        "usage": "/panel-tickets",
        "description": "Envoie le panel d'ouverture de tickets dans le salon actuel avec un bouton interactif.",
        "args": [],
        "perms": "Administrateur",
        "category": "🎫 Tickets",
    },
    "config-tickets": {
        "usage": "/config-tickets",
        "description": "Affiche la configuration actuelle du système de tickets : salon de logs, rôles pingés, catégories.",
        "args": [],
        "perms": "Administrateur",
        "category": "🎫 Tickets",
    },
    "set-log-tickets": {
        "usage": "/set-log-tickets <#salon>",
        "description": "Définit le salon qui recevra les logs d'ouverture et fermeture de tickets.",
        "args": [("#salon", "Requis", "Le salon texte cible.")],
        "perms": "Administrateur",
        "category": "🎫 Tickets",
    },
    "ajouter-role-ticket": {
        "usage": "/ajouter-role-ticket <@role>",
        "description": "Ajoute un rôle à pinger automatiquement à l'ouverture de chaque ticket.",
        "args": [("@role", "Requis", "Le rôle à ajouter.")],
        "perms": "Administrateur",
        "category": "🎫 Tickets",
    },
    "retirer-role-ticket": {
        "usage": "/retirer-role-ticket <@role>",
        "description": "Retire un rôle de la liste des pings automatiques.",
        "args": [("@role", "Requis", "Le rôle à retirer.")],
        "perms": "Administrateur",
        "category": "🎫 Tickets",
    },
    "ajouter-categorie-ticket": {
        "usage": "/ajouter-categorie-ticket <label> <categorie_discord> [description] [emoji]",
        "description": "Ajoute une catégorie au menu de sélection des tickets. Les tickets de cette catégorie seront créés dans la catégorie Discord choisie.",
        "args": [
            ("label", "Requis", "Nom affiché (ex: Support, Bug)."),
            ("categorie_discord", "Requis", "Catégorie Discord cible."),
            ("description", "Optionnel", "Courte description."),
            ("emoji", "Optionnel", "Emoji affiché (défaut: 🎫)."),
        ],
        "perms": "Administrateur",
        "category": "🎫 Tickets",
    },
    "retirer-categorie-ticket": {
        "usage": "/retirer-categorie-ticket <label>",
        "description": "Supprime une catégorie du menu de sélection des tickets.",
        "args": [("label", "Requis", "Nom exact de la catégorie à supprimer.")],
        "perms": "Administrateur",
        "category": "🎫 Tickets",
    },
    "reset-config-tickets": {
        "usage": "/reset-config-tickets",
        "description": "Réinitialise toute la configuration des tickets (logs, rôles, catégories).",
        "args": [],
        "perms": "Administrateur",
        "category": "🎫 Tickets",
    },
    # Modération
    "ban": {
        "usage": "/ban <@user> [raison]",
        "description": "Bannit définitivement un membre du serveur. Un MP est envoyé à l'utilisateur avec la raison.",
        "args": [("@user", "Requis", "Le membre à bannir."), ("raison", "Optionnel", "Raison du bannissement.")],
        "perms": "Bannir des membres",
        "category": "🔨 Modération",
    },
    "kick": {
        "usage": "/kick <@user> [raison]",
        "description": "Expulse un membre du serveur (il peut revenir). Un MP lui est envoyé.",
        "args": [("@user", "Requis", "Le membre à expulser."), ("raison", "Optionnel", "Raison.")],
        "perms": "Expulser des membres",
        "category": "🔨 Modération",
    },
    "mute": {
        "usage": "/mute <@user> <durée> [raison]",
        "description": "Met un membre en sourdine via le timeout natif Discord. Durée : `10s`, `5m`, `2h`, `1j`. Max 28 jours.",
        "args": [("@user", "Requis", "Le membre à mute."), ("durée", "Requis", "Durée : 10s, 5m, 2h, 1j…"), ("raison", "Optionnel", "Raison.")],
        "perms": "Modérer les membres",
        "category": "🔨 Modération",
    },
    "unmute": {
        "usage": "/unmute <@user>",
        "description": "Retire le timeout d'un membre avant son expiration.",
        "args": [("@user", "Requis", "Le membre à unmute.")],
        "perms": "Modérer les membres",
        "category": "🔨 Modération",
    },
    "warn": {
        "usage": "/warn <@user> <raison>",
        "description": "Envoie un avertissement à un membre. L'historique est sauvegardé et consultable avec `/warns`.",
        "args": [("@user", "Requis", "Le membre à avertir."), ("raison", "Requis", "Raison de l'avertissement.")],
        "perms": "Expulser des membres",
        "category": "🔨 Modération",
    },
    "warns": {
        "usage": "/warns <@user>",
        "description": "Affiche l'historique complet des avertissements d'un membre.",
        "args": [("@user", "Requis", "Le membre à consulter.")],
        "perms": "Expulser des membres",
        "category": "🔨 Modération",
    },
    "clear": {
        "usage": "/clear <nombre>",
        "description": "Supprime en masse les derniers messages du salon. Maximum 100 messages à la fois.",
        "args": [("nombre", "Requis", "Nombre de messages à supprimer (1–100).")],
        "perms": "Gérer les messages",
        "category": "🔨 Modération",
    },
    # Auto-mod
    "config-antispam": {
        "usage": "/config-antispam [limite] [fenetre] [mute_minutes] [actif]",
        "description": "Personnalise les paramètres de l'antispam par serveur. Chaque argument est optionnel — seuls les paramètres fournis sont modifiés.",
        "args": [
            ("limite",       "Optionnel", "Nombre de messages avant sanction (2–50, défaut : 5)."),
            ("fenetre",      "Optionnel", "Fenêtre de temps en secondes (1–60, défaut : 5)."),
            ("mute_minutes", "Optionnel", "Durée du mute en minutes (1–1440, défaut : 5)."),
            ("actif",        "Optionnel", "true pour activer, false pour désactiver."),
        ],
        "perms": "Administrateur",
        "category": "🤖 Auto-Modération",
    },
    "config-auto-mod": {
        "usage": "/config-auto-mod",
        "description": "Affiche la configuration complète de l'auto-modération : mots interdits, salons restreints, antispam.",
        "args": [],
        "perms": "Administrateur",
        "category": "🤖 Auto-Modération",
    },
    "ajouter-mot-interdit": {
        "usage": "/ajouter-mot-interdit <mot>",
        "description": "Ajoute un mot à la liste noire. Tout message contenant ce mot sera supprimé automatiquement.",
        "args": [("mot", "Requis", "Le mot à interdire (insensible à la casse).")],
        "perms": "Administrateur",
        "category": "🤖 Auto-Modération",
    },
    "retirer-mot-interdit": {
        "usage": "/retirer-mot-interdit <mot>",
        "description": "Retire un mot de la liste noire.",
        "args": [("mot", "Requis", "Le mot à retirer.")],
        "perms": "Administrateur",
        "category": "🤖 Auto-Modération",
    },
    "salon-no-lien": {
        "usage": "/salon-no-lien [#salon]",
        "description": "Active ou désactive (toggle) l'interdiction de liens dans un salon. Les liens postés seront supprimés.",
        "args": [("#salon", "Optionnel", "Le salon concerné (défaut : salon actuel).")],
        "perms": "Administrateur",
        "category": "🤖 Auto-Modération",
    },
    "salon-no-image": {
        "usage": "/salon-no-image [#salon]",
        "description": "Active ou désactive (toggle) l'interdiction d'images et pièces jointes dans un salon.",
        "args": [("#salon", "Optionnel", "Le salon concerné (défaut : salon actuel).")],
        "perms": "Administrateur",
        "category": "🤖 Auto-Modération",
    },
    # Whitelist & Blacklist
    "whitelist-ajouter": {
        "usage": "/whitelist-ajouter <@user>",
        "description": "Ajoute un membre à la whitelist. Il sera ignoré par toute l'auto-modération (mots, liens, images, antispam).",
        "args": [("@user", "Requis", "Le membre à whitelister.")],
        "perms": "Administrateur",
        "category": "🛡️ Whitelist & Blacklist",
    },
    "whitelist-retirer": {
        "usage": "/whitelist-retirer <@user>",
        "description": "Retire un membre de la whitelist. Il sera à nouveau soumis à l'auto-modération.",
        "args": [("@user", "Requis", "Le membre à retirer.")],
        "perms": "Administrateur",
        "category": "🛡️ Whitelist & Blacklist",
    },
    "whitelist-liste": {
        "usage": "/whitelist-liste",
        "description": "Affiche tous les membres actuellement whitelistés sur ce serveur.",
        "args": [],
        "perms": "Administrateur",
        "category": "🛡️ Whitelist & Blacklist",
    },
    "blacklist-ajouter": {
        "usage": "/blacklist-ajouter <@user> [raison]",
        "description": "Blackliste un membre : il est expulsé immédiatement et expulsé automatiquement s'il tente de revenir.",
        "args": [("@user", "Requis", "Le membre à blacklister."), ("raison", "Optionnel", "Raison.")],
        "perms": "Administrateur",
        "category": "🛡️ Whitelist & Blacklist",
    },
    "blacklist-retirer": {
        "usage": "/blacklist-retirer <@user>",
        "description": "Retire un membre de la blacklist. Il peut à nouveau rejoindre le serveur.",
        "args": [("@user", "Requis", "Le membre à retirer (peut ne plus être sur le serveur).")],
        "perms": "Administrateur",
        "category": "🛡️ Whitelist & Blacklist",
    },
    "blacklist-liste": {
        "usage": "/blacklist-liste",
        "description": "Affiche tous les membres actuellement blacklistés sur ce serveur.",
        "args": [],
        "perms": "Administrateur",
        "category": "🛡️ Whitelist & Blacklist",
    },
    # Mini-jeux
    "pile-ou-face": {
        "usage": "/pile-ou-face",
        "description": "Lance une pièce et affiche le résultat (Pile ou Face).",
        "args": [],
        "perms": "Tout le monde",
        "category": "🎮 Mini-Jeux",
    },
    "dé": {
        "usage": "/dé [faces]",
        "description": "Lance un dé avec le nombre de faces choisi (défaut : 6).",
        "args": [("faces", "Optionnel", "Nombre de faces (min 2, défaut 6).")],
        "perms": "Tout le monde",
        "category": "🎮 Mini-Jeux",
    },
    "rps": {
        "usage": "/rps <choix>",
        "description": "Joue à Pierre-Papier-Ciseaux contre le bot.",
        "args": [("choix", "Requis", "pierre, papier ou ciseaux.")],
        "perms": "Tout le monde",
        "category": "🎮 Mini-Jeux",
    },
    "nombre": {
        "usage": "/nombre [max]",
        "description": "Le bot choisit un nombre secret. Devinez-le en 30 secondes avec des indices chaud/froid.",
        "args": [("max", "Optionnel", "Valeur maximale (défaut : 100).")],
        "perms": "Tout le monde",
        "category": "🎮 Mini-Jeux",
    },
    "8ball": {
        "usage": "/8ball <question>",
        "description": "Posez une question à la boule magique. Elle répondra par oui, non ou peut-être.",
        "args": [("question", "Requis", "Votre question.")],
        "perms": "Tout le monde",
        "category": "🎮 Mini-Jeux",
    },
    "trivia": {
        "usage": "/trivia",
        "description": "Pose une question de culture générale (QCM). Répondez A/B/C/D en 20 secondes.",
        "args": [],
        "perms": "Tout le monde",
        "category": "🎮 Mini-Jeux",
    },
    # Utilitaires
    "ping": {
        "usage": "/ping",
        "description": "Affiche la latence WebSocket du bot en millisecondes.",
        "args": [],
        "perms": "Tout le monde",
        "category": "🛠️ Utilitaires",
    },
    "info-serveur": {
        "usage": "/info-serveur",
        "description": "Affiche les informations du serveur : propriétaire, membres, salons, rôles, niveau de vérification.",
        "args": [],
        "perms": "Tout le monde",
        "category": "🛠️ Utilitaires",
    },
    "info-user": {
        "usage": "/info-user [@user]",
        "description": "Affiche les informations d'un membre : date de création, date d'arrivée, rôles.",
        "args": [("@user", "Optionnel", "Le membre à inspecter (défaut : vous-même).")],
        "perms": "Tout le monde",
        "category": "🛠️ Utilitaires",
    },
    "avatar": {
        "usage": "/avatar [@user]",
        "description": "Affiche l'avatar d'un membre en haute résolution avec un lien direct.",
        "args": [("@user", "Optionnel", "Le membre (défaut : vous-même).")],
        "perms": "Tout le monde",
        "category": "🛠️ Utilitaires",
    },
    "say": {
        "usage": "/say <message> [#salon]",
        "description": "Fait envoyer un message par le bot dans le salon actuel ou un salon choisi.",
        "args": [("message", "Requis", "Le message à envoyer."), ("#salon", "Optionnel", "Salon cible (défaut : salon actuel).")],
        "perms": "Administrateur",
        "category": "🛠️ Utilitaires",
    },
    "renommer-bot": {
        "usage": "/renommer-bot <nom>",
        "description": "Change le pseudo du bot sur ce serveur uniquement. Limité à 2 changements par heure (limite Discord).",
        "args": [("nom", "Requis", "Nouveau pseudo (max 32 caractères).")],
        "perms": "Administrateur",
        "category": "🛠️ Utilitaires",
    },
    "help": {
        "usage": "/help [commande]",
        "description": "Affiche l'aide paginée du bot. Si une commande est précisée, affiche ses détails complets.",
        "args": [("commande", "Optionnel", "Nom d'une commande pour plus de détails.")],
        "perms": "Tout le monde",
        "category": "🛠️ Utilitaires",
    },
}


@tree.command(name="help", description="Affiche l'aide complète ou les détails d'une commande")
@app_commands.describe(commande="Nom d'une commande pour plus de détails (optionnel)")
async def help_cmd(interaction: discord.Interaction, commande: str | None = None):

    # ── Mode détail : /help <commande> ──
    if commande:
        key = commande.lstrip("/").lower()
        info = COMMANDS_DETAIL.get(key)
        if not info:
            await interaction.response.send_message(
                embed=firm1_embed(
                    "Commande introuvable",
                    f"Aucune commande nommée `/{key}`.\nUtilisez `/help` pour voir toutes les commandes.",
                    color=COLOR_ERROR,
                ),
                ephemeral=True,
            )
            return

        args_text = "\n".join(
            f"`{a}` — **{req}** — {desc}" for a, req, desc in info["args"]
        ) if info["args"] else "*Aucun argument*"

        embed = discord.Embed(
            title=f"📖  /{key}",
            description=info["description"],
            color=COLOR_PRIMARY,
            timestamp=datetime.datetime.utcnow(),
        )
        embed.add_field(name="📝 Utilisation",   value=f"`{info['usage']}`",  inline=False)
        embed.add_field(name="📂 Catégorie",      value=info["category"],      inline=True)
        embed.add_field(name="🔒 Permission",     value=info["perms"],         inline=True)
        embed.add_field(name="⚙️ Arguments",      value=args_text,             inline=False)
        embed.set_footer(text="Firm1 Bot • Support Gaming")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # ── Mode paginé : /help ──
    pages = [
        firm1_embed(
            title="Firm1 Bot — 🎫 Tickets (1/5)",
            description="Système de tickets de support.\nℹ️ `/help <commande>` pour plus de détails.",
            color=COLOR_PRIMARY,
            fields=[
                ("📩 Membres", (
                    "`/ticket [raison]` — Ouvrir un ticket\n"
                    "`/fermer` — Fermer votre ticket\n"
                    "`/ajouter <@user>` — Ajouter un membre\n"
                    "`/retirer <@user>` — Retirer un membre"
                ), False),
                ("⚙️ Administration *(admin)*", (
                    "`/panel-tickets` — Envoyer le panel\n"
                    "`/config-tickets` — Voir la configuration\n"
                    "`/set-log-tickets <#salon>` — Salon de logs\n"
                    "`/ajouter-role-ticket <@role>` — Ajouter rôle ping\n"
                    "`/retirer-role-ticket <@role>` — Retirer rôle ping\n"
                    "`/ajouter-categorie-ticket` — Ajouter une catégorie\n"
                    "`/retirer-categorie-ticket` — Supprimer une catégorie\n"
                    "`/reset-config-tickets` — Réinitialiser la config"
                ), False),
            ],
        ),
        firm1_embed(
            title="Firm1 Bot — 🔨 Modération (2/5)",
            description="Commandes de modération manuelle.\nℹ️ `/help <commande>` pour plus de détails.",
            color=COLOR_ERROR,
            fields=[
                ("👮 Sanctions *(modo)*", (
                    "`/ban <@user> [raison]` — Bannir\n"
                    "`/kick <@user> [raison]` — Expulser\n"
                    "`/mute <@user> <durée> [raison]` — Mute (10s/5m/2h/1j)\n"
                    "`/unmute <@user>` — Retirer le mute\n"
                    "`/warn <@user> <raison>` — Avertir\n"
                    "`/warns <@user>` — Voir les avertissements\n"
                    "`/clear <1-100>` — Supprimer des messages"
                ), False),
            ],
        ),
        firm1_embed(
            title="Firm1 Bot — 🤖 Auto-Modération (3/5)",
            description="Modération automatique configurable.\nℹ️ `/help <commande>` pour plus de détails.",
            color=COLOR_WARNING,
            fields=[
                ("⚙️ Configuration *(admin)*", (
                    "`/config-auto-mod` — Voir toute la config\n"
                    "`/config-antispam` — Personnaliser l'antispam\n"
                    "`/ajouter-mot-interdit <mot>` — Ajouter un mot interdit\n"
                    "`/retirer-mot-interdit <mot>` — Retirer un mot interdit\n"
                    "`/salon-no-lien [#salon]` — Toggle interdiction liens\n"
                    "`/salon-no-image [#salon]` — Toggle interdiction images"
                ), False),
                ("🚨 Automatique", (
                    "• **Mots interdits** → suppression + MP\n"
                    "• **Liens interdits** → suppression par salon\n"
                    "• **Images interdites** → suppression par salon\n"
                    "• **Antispam** → 5 msg/5s → mute 5min auto"
                ), False),
            ],
        ),
        firm1_embed(
            title="Firm1 Bot — 🛡️ Whitelist & Blacklist (4/5)",
            description="Gestion des accès membres.\nℹ️ `/help <commande>` pour plus de détails.",
            color=COLOR_INFO,
            fields=[
                ("✅ Whitelist *(admin)* — bypass auto-mod", (
                    "`/whitelist-ajouter <@user>` — Ajouter\n"
                    "`/whitelist-retirer <@user>` — Retirer\n"
                    "`/whitelist-liste` — Voir la liste"
                ), False),
                ("⛔ Blacklist *(admin)* — expulsion auto", (
                    "`/blacklist-ajouter <@user> [raison]` — Blacklister\n"
                    "`/blacklist-retirer <@user>` — Retirer\n"
                    "`/blacklist-liste` — Voir la liste"
                ), False),
            ],
        ),
        firm1_embed(
            title="Firm1 Bot — 🎮 Mini-Jeux & Utilitaires (5/5)",
            description="Jeux et outils divers.\nℹ️ `/help <commande>` pour plus de détails.",
            color=COLOR_SUCCESS,
            fields=[
                ("🎮 Mini-Jeux", (
                    "`/pile-ou-face` — Lancer une pièce\n"
                    "`/dé [faces]` — Lancer un dé\n"
                    "`/rps <choix>` — Pierre-Papier-Ciseaux\n"
                    "`/nombre [max]` — Deviner un nombre\n"
                    "`/8ball <question>` — Boule magique\n"
                    "`/trivia` — Question de culture générale"
                ), False),
                ("🛠️ Utilitaires", (
                    "`/ping` — Latence du bot\n"
                    "`/info-serveur` — Infos sur le serveur\n"
                    "`/info-user [@user]` — Infos sur un membre\n"
                    "`/avatar [@user]` — Avatar d'un membre\n"
                    "`/say <message> [#salon]` — Parler à la place du bot *(admin)*\n"
                    "`/renommer-bot <nom>` — Changer le pseudo *(admin)*\n"
                    "`/help [commande]` — Cette aide"
                ), False),
            ],
        ),
    ]

    class HelpView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=120)
            self.page = 0
            self._update_buttons()

        def _update_buttons(self):
            self.prev_btn.disabled = self.page == 0
            self.next_btn.disabled = self.page == len(pages) - 1
            self.page_btn.label    = f"{self.page + 1} / {len(pages)}"

        @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
        async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.page -= 1
            self._update_buttons()
            await interaction.response.edit_message(embed=pages[self.page], view=self)

        @discord.ui.button(label="1 / 5", style=discord.ButtonStyle.primary, disabled=True)
        async def page_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
            pass

        @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
        async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.page += 1
            self._update_buttons()
            await interaction.response.edit_message(embed=pages[self.page], view=self)

    view = HelpView()
    await interaction.response.send_message(embed=pages[0], view=view, ephemeral=True)



@tree.command(name="ping", description="Affiche la latence du bot")
async def ping_cmd(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    color = COLOR_SUCCESS if latency < 100 else (COLOR_WARNING if latency < 200 else COLOR_ERROR)
    status = "🟢 Excellent" if latency < 100 else ("🟡 Correct" if latency < 200 else "🔴 Élevé")
    embed = firm1_embed(
        title="Pong !",
        description=f"**Latence WebSocket :** `{latency} ms`\n**Statut :** {status}",
        color=color,
    )
    await interaction.response.send_message(embed=embed)


@tree.command(name="info-serveur", description="Informations sur le serveur")
async def server_info(interaction: discord.Interaction):
    guild = interaction.guild
    embed = firm1_embed(
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
    embed = firm1_embed(
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
    embed = firm1_embed(
        title=f"Avatar de {membre.display_name}",
        description=f"[Ouvrir en plein écran]({membre.display_avatar.url})",
        color=COLOR_INFO,
    )
    embed.set_image(url=membre.display_avatar.url)
    await interaction.response.send_message(embed=embed)


@tree.command(name="say", description="[Admin] Fait parler le bot à sa place")
@app_commands.describe(
    message="Le message à envoyer",
    salon="Le salon où envoyer le message (optionnel, défaut : salon actuel)",
)
@app_commands.checks.has_permissions(administrator=True)
async def say_cmd(interaction: discord.Interaction, message: str, salon: discord.TextChannel | None = None):
    target = salon or interaction.channel
    try:
        await target.send(message)
        embed = firm1_embed(
            title="✅ Message envoyé",
            description=f"Message envoyé dans {target.mention}.",
            color=COLOR_SUCCESS,
            fields=[("📝 Contenu", message[:1024], False)],
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message(
            embed=firm1_embed("Erreur", f"Je n'ai pas la permission d'envoyer des messages dans {target.mention}.", color=COLOR_ERROR),
            ephemeral=True,
        )


@tree.command(name="renommer-bot", description="[Admin] Change le pseudo du bot sur ce serveur")
@app_commands.describe(nom="Le nouveau pseudo du bot (max 32 caractères)")
@app_commands.checks.has_permissions(administrator=True)
async def rename_bot(interaction: discord.Interaction, nom: str):
    if len(nom) > 32:
        await interaction.response.send_message(
            embed=firm1_embed("Erreur", "Le pseudo ne peut pas dépasser **32 caractères**.", color=COLOR_ERROR),
            ephemeral=True,
        )
        return
    try:
        await interaction.guild.me.edit(nick=nom)
        embed = firm1_embed(
            title="✅ Pseudo mis à jour",
            description=f"Le bot s'appelle désormais **{nom}** sur ce serveur.",
            color=COLOR_SUCCESS,
            fields=[("⚠️ Limite Discord", "Maximum 2 changements de pseudo par heure.", False)],
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except discord.HTTPException as e:
        if e.status == 429:
            await interaction.response.send_message(
                embed=firm1_embed("Limite atteinte", "Trop de changements de pseudo. Réessayez dans **1 heure**.", color=COLOR_WARNING),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                embed=firm1_embed("Erreur", f"Impossible de changer le pseudo : `{e}`", color=COLOR_ERROR),
                ephemeral=True,
            )


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
    """Modal pour saisir la raison après avoir choisi la catégorie."""

    raison = discord.ui.TextInput(
        label="Raison de votre demande",
        placeholder="Décrivez brièvement votre problème ou question…",
        style=discord.TextStyle.paragraph,
        max_length=300,
        required=True,
    )

    def __init__(self, categorie_label: str, category_id: int | None):
        super().__init__(title=f"📋 Ticket — {categorie_label}")
        self.categorie_label = categorie_label
        self.category_id     = category_id

    async def on_submit(self, interaction: discord.Interaction):
        raison_text = f"[{self.categorie_label}] {self.raison.value}"
        await _creer_ticket(interaction, raison=raison_text, category_id=self.category_id)


class TicketCategorySelect(discord.ui.Select):
    """Menu déroulant pour choisir la catégorie du ticket."""

    def __init__(self, categories: list[dict]):
        options = [
            discord.SelectOption(
                label=cat["label"],
                description=cat.get("description", "")[:100],
                emoji=cat.get("emoji", "🎫"),
                value=str(i),
            )
            for i, cat in enumerate(categories)
        ]
        super().__init__(
            placeholder="Choisissez une catégorie…",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="ticket_category_select",
        )
        self.categories = categories

    async def callback(self, interaction: discord.Interaction):
        idx = int(self.values[0])
        cat = self.categories[idx]
        category_id = cat.get("discord_category_id")
        modal = TicketReasonModal(
            categorie_label=cat["label"],
            category_id=category_id,
        )
        await interaction.response.send_modal(modal)


class TicketCategoryView(discord.ui.View):
    """Vue éphémère avec le select de catégorie."""

    def __init__(self, categories: list[dict]):
        super().__init__(timeout=60)
        self.add_item(TicketCategorySelect(categories))


class TicketCloseConfirmView(discord.ui.View):
    """Vue de confirmation avant fermeture."""

    def __init__(self):
        super().__init__(timeout=30)

    @discord.ui.button(label="✅ Confirmer la fermeture", style=discord.ButtonStyle.danger, custom_id="confirm_close")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _fermer_ticket(interaction)

    @discord.ui.button(label="❌ Annuler", style=discord.ButtonStyle.secondary, custom_id="cancel_close")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = firm1_embed("Fermeture annulée", "Le ticket reste ouvert.", color=COLOR_SUCCESS)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        self.stop()


class TicketCloseView(discord.ui.View):
    """Boutons de gestion affichés dans le ticket."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Fermer le ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = firm1_embed(
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
                embed=firm1_embed("Accès refusé", "Seul le staff (rôles configurés ou admin) peut revendiquer un ticket.", color=COLOR_ERROR),
                ephemeral=True,
            )
            return
        embed = firm1_embed(
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
        cfg        = get_guild_config(interaction.guild.id)
        categories = cfg.get("ticket_categories", [])

        if not categories:
            # Aucune catégorie configurée → modal direct sans choix
            modal = TicketReasonModal(categorie_label="Support général", category_id=None)
            await interaction.response.send_modal(modal)
        else:
            # Affiche le select de catégories en éphémère
            embed = firm1_embed(
                title="Choisissez une catégorie",
                description="Sélectionnez la catégorie correspondant à votre demande.",
                color=COLOR_INFO,
            )
            view = TicketCategoryView(categories)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(
        label="📖 Comment ça marche ?",
        style=discord.ButtonStyle.secondary,
        custom_id="ticket_info_btn",
        row=0,
    )
    async def info_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = firm1_embed(
            title="Comment ouvrir un ticket ?",
            description=(
                "**1.** Cliquez sur **🎫 Ouvrir un ticket**\n"
                "**2.** Choisissez la catégorie de votre demande\n"
                "**3.** Remplissez le formulaire (raison)\n"
                "**4.** Un salon privé sera créé pour vous\n"
                "**5.** Le staff vous répondra dès que possible\n\n"
                "⚠️ *Un seul ticket par utilisateur. Merci d'être précis.*"
            ),
            color=COLOR_INFO,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def _creer_ticket(interaction: discord.Interaction, raison: str = "Non spécifiée", category_id: int | None = None):
    guild = interaction.guild
    user  = interaction.user
    cfg   = get_guild_config(guild.id)

    # Vérifie si un ticket est déjà ouvert
    if user.id in open_tickets:
        ch = guild.get_channel(open_tickets[user.id]["channel_id"])
        if ch:
            embed = firm1_embed(
                title="Ticket déjà ouvert",
                description=f"Vous avez déjà un ticket ouvert : {ch.mention}",
                color=COLOR_WARNING,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

    # Catégorie Discord cible
    # 1. Catégorie choisie par l'utilisateur (discord_category_id lié à la catégorie de ticket)
    # 2. Sinon, catégorie par défaut "🎫 Tickets"
    category = None
    if category_id:
        category = guild.get_channel(category_id)
    if not category:
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
    embed.set_footer(text="Firm1 • Support")
    view = TicketCloseView()

    # Ping du staff + embed
    ping_content = " ".join(ping_mentions) if ping_mentions else ""
    await channel.send(content=f"{user.mention} {ping_content}".strip(), embed=embed, view=view)

    # Confirmation ephemeral
    confirm = firm1_embed(
        title="Ticket créé !",
        description=f"Votre ticket est disponible ici : {channel.mention}",
        color=COLOR_SUCCESS,
    )
    await interaction.response.send_message(embed=confirm, ephemeral=True)

    # Log dans le salon configuré
    log_channel_id = cfg.get("log_channel_id")
    log_channel = guild.get_channel(log_channel_id) if log_channel_id else None
    if log_channel:
        log_embed = firm1_embed(
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
        embed = firm1_embed("Erreur", "Ce salon n'est pas un ticket.", color=COLOR_ERROR)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    embed = firm1_embed(
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
        log_embed = firm1_embed(
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
            embed=firm1_embed("Erreur", "Cette commande doit être utilisée dans un ticket.", color=COLOR_ERROR),
            ephemeral=True,
        )
        return
    await channel.set_permissions(membre, read_messages=True, send_messages=True)
    embed = firm1_embed(
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
            embed=firm1_embed("Erreur", "Cette commande doit être utilisée dans un ticket.", color=COLOR_ERROR),
            ephemeral=True,
        )
        return
    await channel.set_permissions(membre, overwrite=None)
    embed = firm1_embed(
        title="Utilisateur retiré",
        description=f"{membre.mention} a été retiré de ce ticket.",
        color=COLOR_WARNING,
    )
    await interaction.response.send_message(embed=embed)


# ── Configuration des tickets ──────────────────

@tree.command(name="config-tickets", description="[Admin] Configure les rôles, le salon et les catégories de tickets")
@app_commands.checks.has_permissions(administrator=True)
async def config_tickets(interaction: discord.Interaction):
    cfg        = get_guild_config(interaction.guild.id)
    log_ch_id  = cfg.get("log_channel_id")
    ping_ids   = cfg.get("ping_roles", [])
    categories = cfg.get("ticket_categories", [])
    log_ch     = interaction.guild.get_channel(log_ch_id) if log_ch_id else None
    ping_roles = [interaction.guild.get_role(rid) for rid in ping_ids if interaction.guild.get_role(rid)]

    cats_value = ""
    for cat in categories:
        emoji    = cat.get("emoji", "🎫")
        label    = cat["label"]
        disc_cat = interaction.guild.get_channel(cat.get("discord_category_id")) if cat.get("discord_category_id") else None
        cats_value += f"{emoji} **{label}** → {disc_cat.mention if disc_cat else '`🎫 Tickets` (défaut)'}\n"

    embed = discord.Embed(
        title="⚙️  Configuration — Tickets",
        description="Personnalisez le système de tickets. Les changements persistent au redémarrage.",
        color=COLOR_PRIMARY,
        timestamp=datetime.datetime.utcnow(),
    )
    embed.add_field(
        name="📋  Salon de logs",
        value=log_ch.mention if log_ch else "❌ Non configuré — `/set-log-tickets #salon`",
        inline=False,
    )
    embed.add_field(
        name="🔔  Rôles pingés",
        value=" ".join(r.mention for r in ping_roles) if ping_roles else "❌ Aucun — `/ajouter-role-ticket @role`",
        inline=False,
    )
    embed.add_field(
        name="🗂️  Catégories de tickets",
        value=cats_value if cats_value else "❌ Aucune — `/ajouter-categorie-ticket`",
        inline=False,
    )
    embed.add_field(
        name="🛠️  Commandes disponibles",
        value=(
            "`/set-log-tickets #salon` — Salon de logs\n"
            "`/ajouter-role-ticket @role` — Ajouter un rôle ping\n"
            "`/retirer-role-ticket @role` — Retirer un rôle ping\n"
            "`/ajouter-categorie-ticket` — Ajouter une catégorie de ticket\n"
            "`/retirer-categorie-ticket` — Supprimer une catégorie de ticket\n"
            "`/reset-config-tickets` — Tout réinitialiser"
        ),
        inline=False,
    )
    embed.set_footer(text=f"Firm1 • Config de {interaction.guild.name}")
    embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(name="set-log-tickets", description="[Admin] Définit le salon de logs des tickets")
@app_commands.describe(salon="Le salon texte qui recevra les logs de tickets")
@app_commands.checks.has_permissions(administrator=True)
async def set_log_tickets(interaction: discord.Interaction, salon: discord.TextChannel):
    set_guild_config(interaction.guild.id, "log_channel_id", salon.id)
    embed = firm1_embed(
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
            embed=firm1_embed(
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
    embed = firm1_embed(
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
            embed=firm1_embed(
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
    embed = firm1_embed(
        title="✅ Rôle ping retiré",
        description=f"{role.mention} ne sera plus pingé à l'ouverture d'un ticket.",
        color=COLOR_SUCCESS,
        fields=[
            ("🔔 Liste restante",
             " ".join(r.mention for r in all_roles) if all_roles else "Aucun rôle configuré", False),
        ],
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(name="ajouter-categorie-ticket", description="[Admin] Ajoute une categorie de ticket")
@app_commands.describe(
    label="Nom affiche dans le menu (ex: Support, Bug)",
    categorie_discord="La categorie Discord cible pour ces tickets",
    description="Description courte (optionnel)",
    emoji="Emoji (optionnel)",
)
@app_commands.checks.has_permissions(administrator=True)
async def add_ticket_category(
    interaction: discord.Interaction,
    label: str,
    categorie_discord: discord.CategoryChannel,
    description: str = "",
    emoji: str = "🎫",
):
    cfg        = get_guild_config(interaction.guild.id)
    categories = cfg.get("ticket_categories", [])
    if any(c["label"].lower() == label.lower() for c in categories):
        await interaction.response.send_message(
            embed=firm1_embed("Deja existant", f"Une categorie **{label}** existe deja.", color=COLOR_WARNING),
            ephemeral=True,
        )
        return
    if len(categories) >= 25:
        await interaction.response.send_message(
            embed=firm1_embed("Limite atteinte", "Maximum 25 categories.", color=COLOR_ERROR),
            ephemeral=True,
        )
        return
    categories.append({"label": label, "description": description, "emoji": emoji, "discord_category_id": categorie_discord.id})
    set_guild_config(interaction.guild.id, "ticket_categories", categories)
    embed = firm1_embed(
        title="Categorie ajoutee",
        description=f"{emoji} **{label}** vers {categorie_discord.mention}",
        color=COLOR_SUCCESS,
        fields=[("Total", str(len(categories)), True), ("Description", description or "Aucune", True)],
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(name="retirer-categorie-ticket", description="[Admin] Supprime une categorie de ticket")
@app_commands.describe(label="Nom exact de la categorie a supprimer")
@app_commands.checks.has_permissions(administrator=True)
async def remove_ticket_category(interaction: discord.Interaction, label: str):
    cfg        = get_guild_config(interaction.guild.id)
    categories = cfg.get("ticket_categories", [])
    new_cats   = [c for c in categories if c["label"].lower() != label.lower()]
    if len(new_cats) == len(categories):
        await interaction.response.send_message(
            embed=firm1_embed("Introuvable", f"Aucune categorie nommee **{label}**.", color=COLOR_WARNING),
            ephemeral=True,
        )
        return
    set_guild_config(interaction.guild.id, "ticket_categories", new_cats)
    embed = firm1_embed(
        title="Categorie supprimee",
        description=f"**{label}** a ete retiree du menu.",
        color=COLOR_SUCCESS,
        fields=[("Restantes", str(len(new_cats)), True)],
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
    embed = firm1_embed(
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
        title="🎫  Support — Firm1",
        description=(
            "```\n"
            "  Vous rencontrez un problème sur le serveur ?\n"
            "  Ouvrez un ticket et notre équipe de support\n"
            "  vous répondra dans les meilleurs délais.\n"
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
    embed.set_footer(text=f"Firm1 • {interaction.guild.name}")
    embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)

    view = TicketOpenView()
    await interaction.channel.send(embed=embed, view=view)

    # Résumé de config pour l'admin
    confirm_embed = firm1_embed(
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
    embed = firm1_embed(
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
            embed=firm1_embed("Erreur", "Le dé doit avoir au moins 2 faces.", color=COLOR_ERROR),
            ephemeral=True,
        )
        return
    result = random.randint(1, faces)
    embed = firm1_embed(
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

    embed = firm1_embed(
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
    embed = firm1_embed(
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
        embed = firm1_embed("Partie en cours", "Une partie est déjà en cours dans ce salon.", color=COLOR_WARNING)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    number = random.randint(1, maximum)
    active_guess_games[channel_id] = number

    embed = firm1_embed(
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
                win_embed = firm1_embed(
                    title="🎉 Bonne réponse !",
                    description=f"{msg.author.mention} a trouvé le nombre **{number}** !",
                    color=COLOR_SUCCESS,
                )
                await msg.channel.send(embed=win_embed)
                break
            elif guess < number:
                hint = firm1_embed("💡 Trop petit !", f"Le nombre est **plus grand** que {guess}.", color=COLOR_WARNING)
                await msg.channel.send(embed=hint, delete_after=5)
            else:
                hint = firm1_embed("💡 Trop grand !", f"Le nombre est **plus petit** que {guess}.", color=COLOR_WARNING)
                await msg.channel.send(embed=hint, delete_after=5)

    except asyncio.TimeoutError:
        if channel_id in active_guess_games:
            del active_guess_games[channel_id]
        timeout_embed = firm1_embed(
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

    embed = firm1_embed(
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
            result_embed = firm1_embed(
                title="✅ Bonne réponse !",
                description=f"La réponse était bien **{q['options'][q['correct']]}** ! 🎉",
                color=COLOR_SUCCESS,
            )
        else:
            result_embed = firm1_embed(
                title="❌ Mauvaise réponse !",
                description=f"La bonne réponse était **{q['options'][q['correct']]}**.",
                color=COLOR_ERROR,
            )
        await interaction.channel.send(embed=result_embed)

    except asyncio.TimeoutError:
        timeout_embed = firm1_embed(
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
        embed = firm1_embed(
            title="Permission refusée",
            description="Vous n'avez pas les permissions nécessaires.",
            color=COLOR_ERROR,
        )
    elif isinstance(error, app_commands.CommandOnCooldown):
        embed = firm1_embed(
            title="Cooldown",
            description=f"Attendez encore **{error.retry_after:.1f}s** avant de réutiliser cette commande.",
            color=COLOR_WARNING,
        )
    else:
        embed = firm1_embed(
            title="Erreur inattendue",
            description=f"```{str(error)[:200]}```",
            color=COLOR_ERROR,
        )
    try:
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except discord.InteractionResponded:
        await interaction.followup.send(embed=embed, ephemeral=True)


# ─────────────────────────────────────────────
#  MODÉRATION
# ─────────────────────────────────────────────

# Stockage warns en mémoire (persisté dans guild_config)
import re
from discord.ext import tasks

# ── Helpers ───────────────────────────────────

def parse_duration(duration: str) -> int | None:
    """Convertit '10m', '2h', '1j' en secondes. Retourne None si invalide."""
    match = re.fullmatch(r"(\d+)(s|m|h|j)", duration.lower())
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2)
    return value * {"s": 1, "m": 60, "h": 3600, "j": 86400}[unit]

def get_warns(guild_id: int, user_id: int) -> list:
    cfg = get_guild_config(guild_id)
    return cfg.get("warns", {}).get(str(user_id), [])

def add_warn(guild_id: int, user_id: int, raison: str, moderator: str):
    cfg  = get_guild_config(guild_id)
    warns = cfg.get("warns", {})
    uid  = str(user_id)
    if uid not in warns:
        warns[uid] = []
    warns[uid].append({"raison": raison, "by": moderator, "at": datetime.datetime.utcnow().isoformat()})
    set_guild_config(guild_id, "warns", warns)
    return len(warns[uid])

# ── Commandes de modération ────────────────────

@tree.command(name="ban", description="[Modo] Bannir un membre du serveur")
@app_commands.describe(membre="Le membre à bannir", raison="Raison du ban")
@app_commands.checks.has_permissions(ban_members=True)
async def ban_cmd(interaction: discord.Interaction, membre: discord.Member, raison: str = "Aucune raison fournie"):
    if membre.top_role >= interaction.user.top_role:
        await interaction.response.send_message(
            embed=firm1_embed("Erreur", "Vous ne pouvez pas bannir un membre avec un rôle supérieur ou égal au vôtre.", color=COLOR_ERROR),
            ephemeral=True,
        )
        return
    try:
        await membre.send(embed=firm1_embed("🔨 Vous avez été banni", f"**Serveur :** {interaction.guild.name}\n**Raison :** {raison}", color=COLOR_ERROR))
    except Exception:
        pass
    await membre.ban(reason=raison)
    await interaction.response.send_message(embed=firm1_embed(
        "🔨 Membre banni",
        f"{membre.mention} a été banni.",
        color=COLOR_ERROR,
        fields=[("👤 Membre", str(membre), True), ("📝 Raison", raison, True), ("🛡️ Modérateur", interaction.user.mention, True)],
    ))


@tree.command(name="kick", description="[Modo] Expulser un membre du serveur")
@app_commands.describe(membre="Le membre à expulser", raison="Raison du kick")
@app_commands.checks.has_permissions(kick_members=True)
async def kick_cmd(interaction: discord.Interaction, membre: discord.Member, raison: str = "Aucune raison fournie"):
    if membre.top_role >= interaction.user.top_role:
        await interaction.response.send_message(
            embed=firm1_embed("Erreur", "Vous ne pouvez pas expulser un membre avec un rôle supérieur ou égal au vôtre.", color=COLOR_ERROR),
            ephemeral=True,
        )
        return
    try:
        await membre.send(embed=firm1_embed("👢 Vous avez été expulsé", f"**Serveur :** {interaction.guild.name}\n**Raison :** {raison}", color=COLOR_WARNING))
    except Exception:
        pass
    await membre.kick(reason=raison)
    await interaction.response.send_message(embed=firm1_embed(
        "👢 Membre expulsé",
        f"{membre.mention} a été expulsé.",
        color=COLOR_WARNING,
        fields=[("👤 Membre", str(membre), True), ("📝 Raison", raison, True), ("🛡️ Modérateur", interaction.user.mention, True)],
    ))


@tree.command(name="mute", description="[Modo] Rendre muet un membre (ex: 10m, 2h, 1j)")
@app_commands.describe(membre="Le membre à mute", duree="Durée : 10m, 2h, 1j…", raison="Raison")
@app_commands.checks.has_permissions(moderate_members=True)
async def mute_cmd(interaction: discord.Interaction, membre: discord.Member, duree: str, raison: str = "Aucune raison fournie"):
    secondes = parse_duration(duree)
    if secondes is None:
        await interaction.response.send_message(
            embed=firm1_embed("Format invalide", "Utilisez un format valide : `10s`, `5m`, `2h`, `1j`.", color=COLOR_ERROR),
            ephemeral=True,
        )
        return
    if secondes > 2419200:  # 28 jours max (limite Discord)
        await interaction.response.send_message(
            embed=firm1_embed("Durée trop longue", "La durée maximale est **28 jours**.", color=COLOR_ERROR),
            ephemeral=True,
        )
        return
    until = discord.utils.utcnow() + datetime.timedelta(seconds=secondes)
    await membre.timeout(until, reason=raison)
    try:
        await membre.send(embed=firm1_embed("🔇 Vous avez été mis en sourdine", f"**Serveur :** {interaction.guild.name}\n**Durée :** {duree}\n**Raison :** {raison}", color=COLOR_WARNING))
    except Exception:
        pass
    await interaction.response.send_message(embed=firm1_embed(
        "🔇 Membre mis en sourdine",
        f"{membre.mention} est muet pendant **{duree}**.",
        color=COLOR_WARNING,
        fields=[("📝 Raison", raison, True), ("🛡️ Modérateur", interaction.user.mention, True), ("⏰ Fin", f"<t:{int(until.timestamp())}:R>", True)],
    ))


@tree.command(name="unmute", description="[Modo] Retirer le mute d'un membre")
@app_commands.describe(membre="Le membre à unmute")
@app_commands.checks.has_permissions(moderate_members=True)
async def unmute_cmd(interaction: discord.Interaction, membre: discord.Member):
    await membre.timeout(None)
    await interaction.response.send_message(embed=firm1_embed(
        "🔊 Mute retiré",
        f"{membre.mention} peut à nouveau s'exprimer.",
        color=COLOR_SUCCESS,
        fields=[("🛡️ Modérateur", interaction.user.mention, True)],
    ))


@tree.command(name="warn", description="[Modo] Avertir un membre")
@app_commands.describe(membre="Le membre à avertir", raison="Raison de l'avertissement")
@app_commands.checks.has_permissions(kick_members=True)
async def warn_cmd(interaction: discord.Interaction, membre: discord.Member, raison: str):
    total = add_warn(interaction.guild.id, membre.id, raison, str(interaction.user))
    try:
        await membre.send(embed=firm1_embed(
            "⚠️ Avertissement reçu",
            f"**Serveur :** {interaction.guild.name}\n**Raison :** {raison}\n**Total :** {total} avertissement(s)",
            color=COLOR_WARNING,
        ))
    except Exception:
        pass
    await interaction.response.send_message(embed=firm1_embed(
        "⚠️ Membre averti",
        f"{membre.mention} a reçu un avertissement.",
        color=COLOR_WARNING,
        fields=[("📝 Raison", raison, True), ("🛡️ Modérateur", interaction.user.mention, True), ("📊 Total warns", str(total), True)],
    ))


@tree.command(name="warns", description="Voir les avertissements d'un membre")
@app_commands.describe(membre="Le membre à consulter")
@app_commands.checks.has_permissions(kick_members=True)
async def warns_cmd(interaction: discord.Interaction, membre: discord.Member):
    warns = get_warns(interaction.guild.id, membre.id)
    if not warns:
        await interaction.response.send_message(
            embed=firm1_embed("📋 Avertissements", f"{membre.mention} n'a aucun avertissement.", color=COLOR_SUCCESS),
            ephemeral=True,
        )
        return
    desc = "\n".join(f"**{i+1}.** {w['raison']} — *par {w['by']}*" for i, w in enumerate(warns))
    await interaction.response.send_message(embed=firm1_embed(
        f"⚠️ Avertissements de {membre.display_name}",
        desc,
        color=COLOR_WARNING,
        fields=[("📊 Total", str(len(warns)), True)],
    ), ephemeral=True)


@tree.command(name="clear", description="[Modo] Supprimer des messages dans le salon")
@app_commands.describe(nombre="Nombre de messages à supprimer (1-100)")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear_cmd(interaction: discord.Interaction, nombre: int):
    if not 1 <= nombre <= 100:
        await interaction.response.send_message(
            embed=firm1_embed("Erreur", "Le nombre doit être entre **1** et **100**.", color=COLOR_ERROR),
            ephemeral=True,
        )
        return
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=nombre)
    await interaction.followup.send(embed=firm1_embed(
        "🗑️ Messages supprimés",
        f"**{len(deleted)}** message(s) supprimé(s).",
        color=COLOR_SUCCESS,
    ), ephemeral=True)


# ── Auto-modération ────────────────────────────

# Antispam : {guild_id: {user_id: [timestamps]}}
spam_tracker: dict[int, dict[int, list]] = {}
# Valeurs par défaut (overridables par serveur via /config-antispam)
SPAM_LIMIT_DEFAULT  = 5    # messages
SPAM_WINDOW_DEFAULT = 5    # secondes
SPAM_MUTE_DEFAULT   = 5    # minutes de mute

@tree.command(name="config-auto-mod", description="[Admin] Voir la configuration de l'auto-modération")
@app_commands.checks.has_permissions(administrator=True)
async def config_automod(interaction: discord.Interaction):
    cfg         = get_guild_config(interaction.guild.id)
    bad_words   = cfg.get("bad_words", [])
    no_link     = cfg.get("no_link_channels", [])
    no_image    = cfg.get("no_image_channels", [])
    no_link_ch  = [interaction.guild.get_channel(c) for c in no_link if interaction.guild.get_channel(c)]
    no_image_ch = [interaction.guild.get_channel(c) for c in no_image if interaction.guild.get_channel(c)]
    spam_limit  = cfg.get("spam_limit",  SPAM_LIMIT_DEFAULT)
    spam_window = cfg.get("spam_window", SPAM_WINDOW_DEFAULT)
    spam_mute   = cfg.get("spam_mute",   SPAM_MUTE_DEFAULT)
    spam_active = cfg.get("spam_active", True)

    embed = discord.Embed(title="⚙️ Auto-Modération — Config", color=COLOR_PRIMARY, timestamp=datetime.datetime.utcnow())
    embed.add_field(name="🤬 Mots interdits", value=", ".join(f"`{w}`" for w in bad_words) if bad_words else "❌ Aucun", inline=False)
    embed.add_field(name="🔗 Salons sans liens", value=" ".join(c.mention for c in no_link_ch) if no_link_ch else "❌ Aucun", inline=False)
    embed.add_field(name="🖼️ Salons sans images", value=" ".join(c.mention for c in no_image_ch) if no_image_ch else "❌ Aucun", inline=False)
    embed.add_field(
        name="🚨 Antispam",
        value=(
            f"{'🟢 Actif' if spam_active else '🔴 Désactivé'}\n"
            f"**Seuil :** {spam_limit} messages en {spam_window}s\n"
            f"**Sanction :** mute {spam_mute} minute(s)\n"
            f"*Modifiez avec `/config-antispam`*"
        ),
        inline=False,
    )
    embed.add_field(name="🛠️ Commandes", value=(
        "`/ajouter-mot-interdit <mot>` — Ajouter un mot interdit\n"
        "`/retirer-mot-interdit <mot>` — Retirer un mot interdit\n"
        "`/salon-no-lien [#salon]` — Toggle liens\n"
        "`/salon-no-image [#salon]` — Toggle images\n"
        "`/config-antispam` — Configurer l'antispam"
    ), inline=False)
    embed.set_footer(text="Firm1 Bot • Support Gaming")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(name="config-antispam", description="[Admin] Personnalise les paramètres de l'antispam")
@app_commands.describe(
    limite="Nombre de messages avant sanction (défaut : 5)",
    fenetre="Fenêtre de temps en secondes (défaut : 5)",
    mute_minutes="Durée du mute en minutes (défaut : 5)",
    actif="Activer ou désactiver l'antispam",
)
@app_commands.checks.has_permissions(administrator=True)
async def config_antispam(
    interaction: discord.Interaction,
    limite:       int  | None = None,
    fenetre:      int  | None = None,
    mute_minutes: int  | None = None,
    actif:        bool | None = None,
):
    cfg = get_guild_config(interaction.guild.id)

    # Appliquer uniquement les valeurs fournies
    if limite is not None:
        if not 2 <= limite <= 50:
            await interaction.response.send_message(
                embed=firm1_embed("Valeur invalide", "La limite doit être entre **2** et **50** messages.", color=COLOR_ERROR),
                ephemeral=True,
            )
            return
        set_guild_config(interaction.guild.id, "spam_limit", limite)

    if fenetre is not None:
        if not 1 <= fenetre <= 60:
            await interaction.response.send_message(
                embed=firm1_embed("Valeur invalide", "La fenêtre doit être entre **1** et **60** secondes.", color=COLOR_ERROR),
                ephemeral=True,
            )
            return
        set_guild_config(interaction.guild.id, "spam_window", fenetre)

    if mute_minutes is not None:
        if not 1 <= mute_minutes <= 1440:
            await interaction.response.send_message(
                embed=firm1_embed("Valeur invalide", "La durée de mute doit être entre **1** et **1440** minutes (24h).", color=COLOR_ERROR),
                ephemeral=True,
            )
            return
        set_guild_config(interaction.guild.id, "spam_mute", mute_minutes)

    if actif is not None:
        set_guild_config(interaction.guild.id, "spam_active", actif)

    # Lire la config finale
    cfg         = get_guild_config(interaction.guild.id)
    spam_limit  = cfg.get("spam_limit",  SPAM_LIMIT_DEFAULT)
    spam_window = cfg.get("spam_window", SPAM_WINDOW_DEFAULT)
    spam_mute   = cfg.get("spam_mute",   SPAM_MUTE_DEFAULT)
    spam_active = cfg.get("spam_active", True)

    embed = firm1_embed(
        title="🚨 Antispam — Configuration mise à jour",
        description=f"{'🟢 Antispam **activé**' if spam_active else '🔴 Antispam **désactivé**'}",
        color=COLOR_SUCCESS if spam_active else COLOR_WARNING,
        fields=[
            ("📨 Seuil",    f"**{spam_limit}** messages",     True),
            ("⏱️ Fenêtre",  f"**{spam_window}** secondes",    True),
            ("🔇 Sanction", f"Mute **{spam_mute}** minute(s)", True),
            ("💡 Exemple",  f"Si un membre envoie **{spam_limit}+ messages** en moins de **{spam_window}s**, il est muet **{spam_mute} min**.", False),
        ],
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@app_commands.describe(mot="Le mot à interdire")
@app_commands.checks.has_permissions(administrator=True)
async def add_bad_word(interaction: discord.Interaction, mot: str):
    cfg       = get_guild_config(interaction.guild.id)
    bad_words = cfg.get("bad_words", [])
    mot       = mot.lower()
    if mot in bad_words:
        await interaction.response.send_message(
            embed=firm1_embed("Déjà présent", f"`{mot}` est déjà dans la liste.", color=COLOR_WARNING),
            ephemeral=True,
        )
        return
    bad_words.append(mot)
    set_guild_config(interaction.guild.id, "bad_words", bad_words)
    await interaction.response.send_message(
        embed=firm1_embed("✅ Mot ajouté", f"`{mot}` est désormais interdit.", color=COLOR_SUCCESS, fields=[("📊 Total", str(len(bad_words)), True)]),
        ephemeral=True,
    )


@tree.command(name="ajouter-mot-interdit", description="[Admin] Ajoute un ou plusieurs mots interdits (séparés par _)")
@app_commands.describe(mot="Un ou plusieurs mots séparés par _ (ex: mot1_mot2_mot3)")
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

    await interaction.response.send_message(
        embed=firm1_embed(
            "✅ Mots interdits mis à jour" if ajoutes else "⚠️ Aucun mot ajouté",
            f"**{len(ajoutes)}** mot(s) ajouté(s), **{len(deja)}** déjà présent(s).",
            color=COLOR_SUCCESS if ajoutes else COLOR_WARNING,
            fields=fields,
        ),
        ephemeral=True,
    )


@tree.command(name="retirer-mot-interdit", description="[Admin] Retire un mot interdit")
@app_commands.describe(mot="Le mot à retirer")
@app_commands.checks.has_permissions(administrator=True)
async def remove_bad_word(interaction: discord.Interaction, mot: str):
    cfg       = get_guild_config(interaction.guild.id)
    bad_words = cfg.get("bad_words", [])
    mot       = mot.lower()
    if mot not in bad_words:
        await interaction.response.send_message(
            embed=firm1_embed("Introuvable", f"`{mot}` n'est pas dans la liste.", color=COLOR_WARNING),
            ephemeral=True,
        )
        return
    bad_words.remove(mot)
    set_guild_config(interaction.guild.id, "bad_words", bad_words)
    await interaction.response.send_message(
        embed=firm1_embed("✅ Mot retiré", f"`{mot}` n'est plus interdit.", color=COLOR_SUCCESS),
        ephemeral=True,
    )


@tree.command(name="salon-no-lien", description="[Admin] Active/désactive l'interdiction de liens dans un salon")
@app_commands.describe(salon="Le salon concerné (défaut : salon actuel)")
@app_commands.checks.has_permissions(administrator=True)
async def toggle_no_link(interaction: discord.Interaction, salon: discord.TextChannel | None = None):
    target    = salon or interaction.channel
    cfg       = get_guild_config(interaction.guild.id)
    no_link   = cfg.get("no_link_channels", [])
    if target.id in no_link:
        no_link.remove(target.id)
        set_guild_config(interaction.guild.id, "no_link_channels", no_link)
        await interaction.response.send_message(
            embed=firm1_embed("✅ Liens autorisés", f"Les liens sont à nouveau autorisés dans {target.mention}.", color=COLOR_SUCCESS),
            ephemeral=True,
        )
    else:
        no_link.append(target.id)
        set_guild_config(interaction.guild.id, "no_link_channels", no_link)
        await interaction.response.send_message(
            embed=firm1_embed("🔗 Liens interdits", f"Les liens sont désormais interdits dans {target.mention}.", color=COLOR_WARNING),
            ephemeral=True,
        )


@tree.command(name="salon-no-image", description="[Admin] Active/désactive l'interdiction d'images dans un salon")
@app_commands.describe(salon="Le salon concerné (défaut : salon actuel)")
@app_commands.checks.has_permissions(administrator=True)
async def toggle_no_image(interaction: discord.Interaction, salon: discord.TextChannel | None = None):
    target    = salon or interaction.channel
    cfg       = get_guild_config(interaction.guild.id)
    no_image  = cfg.get("no_image_channels", [])
    if target.id in no_image:
        no_image.remove(target.id)
        set_guild_config(interaction.guild.id, "no_image_channels", no_image)
        await interaction.response.send_message(
            embed=firm1_embed("✅ Images autorisées", f"Les images sont à nouveau autorisées dans {target.mention}.", color=COLOR_SUCCESS),
            ephemeral=True,
        )
    else:
        no_image.append(target.id)
        set_guild_config(interaction.guild.id, "no_image_channels", no_image)
        await interaction.response.send_message(
            embed=firm1_embed("🖼️ Images interdites", f"Les images sont désormais interdites dans {target.mention}.", color=COLOR_WARNING),
            ephemeral=True,
        )


# ── Listener auto-mod (on_message) ────────────

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    # ── Ping / mention du bot → carte de présentation ──
    if bot.user in message.mentions and message.content.strip() in (f"<@{bot.user.id}>", f"<@!{bot.user.id}>"):
        cfg        = get_guild_config(message.guild.id)
        categories = cfg.get("ticket_categories", [])
        bad_words  = cfg.get("bad_words", [])
        no_link    = cfg.get("no_link_channels", [])
        no_image   = cfg.get("no_image_channels", [])

        embed = discord.Embed(
            title="👾  Firm1 Bot",
            description=(
                "```\n"
                "  Le bot officiel de la communauté Firm1.\n"
                "  Support • Modération • Mini-Jeux\n"
                "```\n"
                "Tapez `/help` pour voir toutes les commandes.\n"
                "Tapez `/help <commande>` pour les détails d'une commande."
            ),
            color=COLOR_PRIMARY,
            timestamp=datetime.datetime.utcnow(),
        )

        # Stats du serveur
        embed.add_field(
            name="📊 Stats sur ce serveur",
            value=(
                f"🎫 Catégories tickets : **{len(categories)}**\n"
                f"🚫 Mots interdits : **{len(bad_words)}**\n"
                f"🔗 Salons sans liens : **{len(no_link)}**\n"
                f"🖼️ Salons sans images : **{len(no_image)}**"
            ),
            inline=True,
        )

        # Fonctionnalités
        embed.add_field(
            name="⚡ Fonctionnalités",
            value=(
                "🎫 Système de tickets\n"
                "🔨 Modération complète\n"
                "🤖 Auto-modération\n"
                "🛡️ Whitelist & Blacklist\n"
                "🎮 Mini-jeux"
            ),
            inline=True,
        )

        embed.add_field(
            name="🔗 Commandes rapides",
            value=(
                "`/help` — Aide complète\n"
                "`/panel-tickets` — Panel support\n"
                "`/config-tickets` — Config tickets\n"
                "`/config-auto-mod` — Auto-mod"
            ),
            inline=False,
        )

        embed.set_thumbnail(url=bot.user.display_avatar.url)
        embed.set_footer(text=f"Firm1 Bot • Sur {len(bot.guilds)} serveur(s)")
        await message.reply(embed=embed, mention_author=False)
        return

    cfg = get_guild_config(message.guild.id)
    whitelist = cfg.get("whitelist", [])

    # ── Whitelist : bypass total de l'auto-mod ──
    if message.author.id in whitelist:
        await bot.process_commands(message)
        return

    bad_words = cfg.get("bad_words", [])
    no_link   = cfg.get("no_link_channels", [])
    no_image  = cfg.get("no_image_channels", [])
    content   = message.content.lower()

    # ── Mots interdits ──
    for word in bad_words:
        if word in content:
            await message.delete()
            try:
                await message.author.send(embed=firm1_embed(
                    "🚫 Message supprimé",
                    f"Votre message dans **{message.guild.name}** contient un mot interdit.",
                    color=COLOR_ERROR,
                ))
            except Exception:
                pass
            return

    # ── Liens interdits ──
    url_pattern = re.compile(r"https?://\S+|discord\.gg/\S+", re.IGNORECASE)
    if message.channel.id in no_link and url_pattern.search(message.content):
        await message.delete()
        warn_msg = await message.channel.send(
            embed=firm1_embed("🔗 Lien interdit", f"{message.author.mention}, les liens sont interdits dans ce salon.", color=COLOR_ERROR),
        )
        await asyncio.sleep(5)
        await warn_msg.delete()
        return

    # ── Images interdites ──
    if message.channel.id in no_image and (message.attachments or any(e.image for e in message.embeds)):
        await message.delete()
        warn_msg = await message.channel.send(
            embed=firm1_embed("🖼️ Image interdite", f"{message.author.mention}, les images sont interdites dans ce salon.", color=COLOR_ERROR),
        )
        await asyncio.sleep(5)
        await warn_msg.delete()
        return

    # ── Antispam ──
    guild_id    = message.guild.id
    user_id     = message.author.id
    now         = datetime.datetime.utcnow().timestamp()
    whitelist   = cfg.get("whitelist", [])
    spam_active = cfg.get("spam_active", True)

    # Les membres en whitelist ignorent l'antispam aussi
    if user_id not in whitelist and spam_active:
        spam_limit  = cfg.get("spam_limit",  SPAM_LIMIT_DEFAULT)
        spam_window = cfg.get("spam_window", SPAM_WINDOW_DEFAULT)
        spam_mute   = cfg.get("spam_mute",   SPAM_MUTE_DEFAULT)

        if guild_id not in spam_tracker:
            spam_tracker[guild_id] = {}
        if user_id not in spam_tracker[guild_id]:
            spam_tracker[guild_id][user_id] = []

        timestamps = spam_tracker[guild_id][user_id]
        timestamps.append(now)
        spam_tracker[guild_id][user_id] = [t for t in timestamps if now - t < spam_window]

        if len(spam_tracker[guild_id][user_id]) >= spam_limit:
            spam_tracker[guild_id][user_id] = []
            try:
                until = discord.utils.utcnow() + datetime.timedelta(minutes=spam_mute)
                await message.author.timeout(until, reason="Antispam automatique")
                await message.channel.send(embed=firm1_embed(
                    "🚨 Spam détecté",
                    f"{message.author.mention} a été mis en sourdine **{spam_mute} minute(s)** pour spam.",
                    color=COLOR_ERROR,
                ))
            except Exception:
                pass

    await bot.process_commands(message)


# ── Blacklist : kick automatique à l'arrivée ──

@bot.event
async def on_member_join(member: discord.Member):
    cfg       = get_guild_config(member.guild.id)
    blacklist = cfg.get("blacklist", [])
    if member.id in blacklist:
        try:
            await member.send(embed=firm1_embed(
                "⛔ Accès refusé",
                f"Vous êtes sur la blacklist du serveur **{member.guild.name}** et ne pouvez pas le rejoindre.",
                color=COLOR_ERROR,
            ))
        except Exception:
            pass
        await member.kick(reason="Membre blacklisté")


# ─────────────────────────────────────────────
#  WHITELIST & BLACKLIST
# ─────────────────────────────────────────────

@tree.command(name="whitelist-ajouter", description="[Admin] Ajoute un membre à la whitelist (bypass auto-mod)")
@app_commands.describe(membre="Le membre à whitelister")
@app_commands.checks.has_permissions(administrator=True)
async def whitelist_add(interaction: discord.Interaction, membre: discord.Member):
    cfg       = get_guild_config(interaction.guild.id)
    whitelist = cfg.get("whitelist", [])
    if membre.id in whitelist:
        await interaction.response.send_message(
            embed=firm1_embed("Déjà présent", f"{membre.mention} est déjà dans la whitelist.", color=COLOR_WARNING),
            ephemeral=True,
        )
        return
    whitelist.append(membre.id)
    set_guild_config(interaction.guild.id, "whitelist", whitelist)
    await interaction.response.send_message(embed=firm1_embed(
        "✅ Whitelist — Membre ajouté",
        f"{membre.mention} peut désormais contourner toutes les restrictions de l'auto-modération.",
        color=COLOR_SUCCESS,
        fields=[
            ("👤 Membre", f"{membre} (`{membre.id}`)", True),
            ("📊 Total whitelist", str(len(whitelist)), True),
        ],
    ), ephemeral=True)


@tree.command(name="whitelist-retirer", description="[Admin] Retire un membre de la whitelist")
@app_commands.describe(membre="Le membre à retirer")
@app_commands.checks.has_permissions(administrator=True)
async def whitelist_remove(interaction: discord.Interaction, membre: discord.Member):
    cfg       = get_guild_config(interaction.guild.id)
    whitelist = cfg.get("whitelist", [])
    if membre.id not in whitelist:
        await interaction.response.send_message(
            embed=firm1_embed("Introuvable", f"{membre.mention} n'est pas dans la whitelist.", color=COLOR_WARNING),
            ephemeral=True,
        )
        return
    whitelist.remove(membre.id)
    set_guild_config(interaction.guild.id, "whitelist", whitelist)
    await interaction.response.send_message(embed=firm1_embed(
        "✅ Whitelist — Membre retiré",
        f"{membre.mention} est soumis à nouveau aux restrictions de l'auto-modération.",
        color=COLOR_SUCCESS,
    ), ephemeral=True)


@tree.command(name="whitelist-liste", description="[Admin] Affiche tous les membres whitelistés")
@app_commands.checks.has_permissions(administrator=True)
async def whitelist_list(interaction: discord.Interaction):
    cfg       = get_guild_config(interaction.guild.id)
    whitelist = cfg.get("whitelist", [])
    membres   = [interaction.guild.get_member(uid) for uid in whitelist]
    membres   = [m for m in membres if m]
    if not membres:
        await interaction.response.send_message(
            embed=firm1_embed("📋 Whitelist", "Aucun membre whitelisté.", color=COLOR_INFO),
            ephemeral=True,
        )
        return
    desc = "\n".join(f"• {m.mention} — `{m.id}`" for m in membres)
    await interaction.response.send_message(embed=firm1_embed(
        "📋 Whitelist",
        desc,
        color=COLOR_INFO,
        fields=[("📊 Total", str(len(membres)), True)],
    ), ephemeral=True)


@tree.command(name="blacklist-ajouter", description="[Admin] Ajoute un membre à la blacklist (expulsé automatiquement)")
@app_commands.describe(membre="Le membre à blacklister", raison="Raison")
@app_commands.checks.has_permissions(administrator=True)
async def blacklist_add(interaction: discord.Interaction, membre: discord.Member, raison: str = "Aucune raison fournie"):
    cfg       = get_guild_config(interaction.guild.id)
    blacklist = cfg.get("blacklist", [])
    if membre.id in blacklist:
        await interaction.response.send_message(
            embed=firm1_embed("Déjà présent", f"{membre.mention} est déjà dans la blacklist.", color=COLOR_WARNING),
            ephemeral=True,
        )
        return
    blacklist.append(membre.id)
    set_guild_config(interaction.guild.id, "blacklist", blacklist)
    # Kick immédiat si déjà sur le serveur
    try:
        await membre.send(embed=firm1_embed(
            "⛔ Vous avez été blacklisté",
            f"Vous avez été ajouté à la blacklist de **{interaction.guild.name}**.\n**Raison :** {raison}",
            color=COLOR_ERROR,
        ))
    except Exception:
        pass
    await membre.kick(reason=f"Blacklist : {raison}")
    await interaction.response.send_message(embed=firm1_embed(
        "⛔ Blacklist — Membre ajouté",
        f"{membre.mention} a été blacklisté et expulsé. Il sera automatiquement expulsé s'il tente de revenir.",
        color=COLOR_ERROR,
        fields=[
            ("👤 Membre", f"{membre} (`{membre.id}`)", True),
            ("📝 Raison", raison, True),
            ("📊 Total blacklist", str(len(blacklist)), True),
        ],
    ), ephemeral=True)


@tree.command(name="blacklist-retirer", description="[Admin] Retire un membre de la blacklist")
@app_commands.describe(membre="Le membre à retirer (peut ne plus être sur le serveur)")
@app_commands.checks.has_permissions(administrator=True)
async def blacklist_remove(interaction: discord.Interaction, membre: discord.User):
    cfg       = get_guild_config(interaction.guild.id)
    blacklist = cfg.get("blacklist", [])
    if membre.id not in blacklist:
        await interaction.response.send_message(
            embed=firm1_embed("Introuvable", f"{membre.mention} n'est pas dans la blacklist.", color=COLOR_WARNING),
            ephemeral=True,
        )
        return
    blacklist.remove(membre.id)
    set_guild_config(interaction.guild.id, "blacklist", blacklist)
    await interaction.response.send_message(embed=firm1_embed(
        "✅ Blacklist — Membre retiré",
        f"**{membre}** peut à nouveau rejoindre le serveur.",
        color=COLOR_SUCCESS,
    ), ephemeral=True)


@tree.command(name="blacklist-liste", description="[Admin] Affiche tous les membres blacklistés")
@app_commands.checks.has_permissions(administrator=True)
async def blacklist_list(interaction: discord.Interaction):
    cfg       = get_guild_config(interaction.guild.id)
    blacklist = cfg.get("blacklist", [])
    if not blacklist:
        await interaction.response.send_message(
            embed=firm1_embed("📋 Blacklist", "Aucun membre blacklisté.", color=COLOR_INFO),
            ephemeral=True,
        )
        return
    desc = "\n".join(f"• `{uid}`" for uid in blacklist)
    await interaction.response.send_message(embed=firm1_embed(
        "📋 Blacklist",
        desc,
        color=COLOR_ERROR,
        fields=[("📊 Total", str(len(blacklist)), True)],
    ), ephemeral=True)



if __name__ == "__main__":
    # keep_alive() uniquement si le module est disponible (Replit)
    # Sur Render, le process tourne nativement en continu — inutile
    if KEEP_ALIVE_AVAILABLE:
        keep_alive()
    # Lancement du bot
    try:
        token = os.environ['Token_bot']
        bot.run(token)
    except KeyError:
        print("❌ Token introuvable ! Ajoutez Token_bot dans les variables d'environnement Render.")
    except discord.LoginFailure:
        print("❌ Token invalide ! Vérifiez votre token Discord.")
