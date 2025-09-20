import os
import json
import asyncio
import discord
import re
from dotenv import load_dotenv
from discord.ext import commands, tasks
from typing import Optional, Dict, List, Union
from abc import ABC, abstractmethod

# keep_alive est souvent utilisé sur des plateformes comme Replit,
# s'il n'est pas utilisé, cette ligne peut être commentée ou supprimée.
from keep_alive import keep_alive
load_dotenv()
token = os.getenv('Token_bot')

    # --- Configuration des Intents et du Bot ---
intents = discord.Intents.default()
intents.message_content = True
    # On désactive la commande d'aide par défaut pour en créer une personnalisée
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

    # --- Constantes pour les fichiers de données ---
DATA_FILE = "products.json"
CONFIG_FILE = "config.json"
CUSTOM_SITES_FILE = "custom_sites.json"


    # --- Fonctions d'aide pour les Embeds ---
async def send_error(ctx, message: str):
        """Envoie un message d'erreur standardisé dans un embed."""
        embed = discord.Embed(
            title="❌ Erreur",
            description=message,
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

async def send_success(ctx, title: str, message: str):
        """Envoie un message de succès standardisé dans un embed."""
        embed = discord.Embed(
            title=title,
            description=message,
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)


    # --- Classes de Providers pour les sites ---
class Provider(ABC):
        """Classe de base pour les providers de sites"""
        @property
        @abstractmethod
        def aliases(self) -> List[str]:
            """Liste des alias acceptés pour ce site"""
            pass

        @property
        @abstractmethod
        def name(self) -> str:
            """Nom du provider"""
            pass

        @abstractmethod
        def validate_product_ref(self, ref: str) -> bool:
            """Valide que la référence produit est correcte pour ce site"""
            pass

        @abstractmethod
        def build_product_url(self, ref: str) -> str:
            """Construit l'URL complète du produit à partir de sa référence"""
            pass

class AmazonProvider(Provider):
        @property
        def aliases(self) -> List[str]: return ["amazon", "amazon.fr", "amazon.com"]
        @property
        def name(self) -> str: return "Amazon"
        def validate_product_ref(self, ref: str) -> bool: return bool(re.match(r'^[A-Z0-9]{10}$', ref.upper()))
        def build_product_url(self, ref: str) -> str: return f"https://amazon.fr/dp/{ref.upper()}"

class AliExpressProvider(Provider):
        @property
        def aliases(self) -> List[str]: return ["aliexpress", "ali"]
        @property
        def name(self) -> str: return "AliExpress"
        def validate_product_ref(self, ref: str) -> bool: return bool(re.match(r'^\d{8,12}$', ref))
        def build_product_url(self, ref: str) -> str: return f"https://fr.aliexpress.com/item/{ref}.html"

class VintedProvider(Provider):
        @property
        def aliases(self) -> List[str]: return ["vinted"]
        @property
        def name(self) -> str: return "Vinted"
        def validate_product_ref(self, ref: str) -> bool: return bool(re.match(r'^\d{8,10}$', ref))
        def build_product_url(self, ref: str) -> str: return f"https://vinted.fr/items/{ref}"

class CustomProvider(Provider):
        """Provider configurable pour les sites personnalisés"""
        def __init__(self, config: dict):
            self._aliases = config["aliases"]
            self._name = config["name"]
            self._url_pattern = config["url_pattern"]
            self._id_regex = config["id_regex"]
            self._description = config.get("description", "")

        @property
        def aliases(self) -> List[str]: return self._aliases
        @property
        def name(self) -> str: return self._name
        @property
        def description(self) -> str: return self._description
        def validate_product_ref(self, ref: str) -> bool:
            try: return bool(re.match(self._id_regex, ref))
            except re.error: return False
        def build_product_url(self, ref: str) -> str: return self._url_pattern.replace("{id}", ref)


    # --- Fonctions de gestion des données et des providers ---
def load_json_file(filename: str, default_data: dict):
        """Charge un fichier JSON ou retourne les données par défaut."""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return default_data

def save_json_file(filename: str, data: dict):
        """Sauvegarde des données dans un fichier JSON."""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

def load_data(): return load_json_file(DATA_FILE, {"products": {}})
def save_data(data): save_json_file(DATA_FILE, data)
def load_config(): return load_json_file(CONFIG_FILE, {"monitoring_enabled": False, "notification_role": None})
def save_config(config): save_json_file(CONFIG_FILE, config)
def load_custom_sites(): return load_json_file(CUSTOM_SITES_FILE, {})
def save_custom_sites(sites): save_json_file(CUSTOM_SITES_FILE, sites)

def reload_providers():
        """Recharge tous les providers (built-in + personnalisés)"""
        global SITE_PROVIDERS, _providers
        builtin_providers = [AmazonProvider(), AliExpressProvider(), VintedProvider()]
        custom_sites = load_custom_sites()
        custom_providers = [CustomProvider(config) for site_id, config in custom_sites.items()]
        _providers = builtin_providers + custom_providers
        SITE_PROVIDERS = {alias.lower(): provider for provider in _providers for alias in provider.aliases}

def get_provider_by_alias(alias: str) -> Optional[Provider]: return SITE_PROVIDERS.get(alias.lower())
def get_supported_sites() -> str:
        sites = {provider.name: provider.aliases[0] for provider in _providers}
        return ", ".join(f"{name} (`{alias}`)" for name, alias in sorted(sites.items()))
def get_builtin_providers() -> List[Provider]: return [p for p in _providers if not isinstance(p, CustomProvider)]
def get_custom_providers() -> List[CustomProvider]: return [p for p in _providers if isinstance(p, CustomProvider)]

reload_providers() # Chargement initial


    # --- Événements du Bot ---
@bot.event
async def on_ready():
        print(f'{bot.user} has connected to Discord!')
        print('Bot is ready and online!')
        config = load_config()
        if config.get("monitoring_enabled", False) and not price_monitor.is_running():
            price_monitor.start()
            print("Price monitoring started automatically")


    # --- Commandes du Bot ---

@bot.command(name='help')
async def custom_help(ctx):
        """Affiche ce message d'aide."""
        embed = discord.Embed(
            title="📚 Aide du Bot de Surveillance",
            description="Voici la liste des commandes disponibles.",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="📦 Gestion des Produits",
            value="`!add` - Ajoute un produit à surveiller.\n"
                  "`!remove <nom>` - Supprime un produit.\n"
                  "`!list` - Liste tous les produits surveillés.\n"
                  "`!autobuy <nom> <on/off>` - Gère l'AutoBuy pour un produit.\n"
                  "`!help_add` - Aide détaillée pour la commande `!add`.",
            inline=False
        )

        embed.add_field(
            name="🌐 Gestion des Sites",
            value="`!addsite` - Ajoute un site personnalisé.\n"
                  "`!removesite <alias>` - Supprime un site personnalisé.\n"
                  "`!listsite` - Liste tous les sites supportés.",
            inline=False
        )

        embed.add_field(
            name="⚙️ Configuration du Bot",
            value="`!enable` - Active la surveillance des prix.\n"
                  "`!disable` - Désactive la surveillance des prix.\n"
                  "`!setrole <@rôle|off>` - Définit ou retire le rôle pour les notifications.",
            inline=False
        )

        embed.add_field(
            name="👋 Autres",
            value="`!bonjour` - Le bot vous dit bonjour.",
            inline=False
        )

        embed.set_footer(text="Les commandes de gestion nécessitent la permission 'Gérer le serveur'.")
        await ctx.send(embed=embed)


@bot.command(name='add')
@commands.has_permissions(manage_guild=True)
async def add_product(ctx, *, args: str):
        """Ajouter un produit à surveiller."""
        parts = args.split()
        if len(parts) < 3:
            await send_error(ctx, "Pas assez d'arguments. Utilisez `!help_add` pour voir les exemples.")
            return

        data = load_data()

        # Déterminer le mode d'utilisation
        if parts[0].startswith(('http://', 'https://')):
            # Mode URL classique: !add <url> <prix> [autobuy] <nom...>
            url = parts[0]
            try: prix_cible = float(parts[1])
            except ValueError:
                await send_error(ctx, "Prix invalide. Le prix doit être un nombre.")
                return

            if len(parts) > 3 and parts[2].lower() in ["on", "off", "true", "false"]:
                autobuy = parts[2]
                nom = " ".join(parts[3:])
            else:
                autobuy = "off"
                nom = " ".join(parts[2:])
            source_info = {"kind": "url"}
        else:
            # Mode site + ID: !add <site> <product_id> <prix> [autobuy] <nom...>
            if len(parts) < 4:
                await send_error(ctx, "Mode site+ID requiert au moins 4 arguments. Utilisez `!help_add`.")
                return

            site_alias = parts[0].lower()
            product_id = parts[1]
            try: prix_cible = float(parts[2])
            except ValueError:
                await send_error(ctx, "Prix invalide. Le prix doit être un nombre.")
                return

            provider = get_provider_by_alias(site_alias)
            if not provider:
                supported = get_supported_sites()
                await send_error(ctx, f"Site non supporté: `{site_alias}`\n**Sites supportés**: {supported}")
                return

            if not provider.validate_product_ref(product_id):
                await send_error(ctx, f"ID produit invalide pour {provider.name}: `{product_id}`")
                return

            if len(parts) > 4 and parts[3].lower() in ["on", "off", "true", "false"]:
                autobuy = parts[3]
                nom = " ".join(parts[4:])
            else:
                autobuy = "off"
                nom = " ".join(parts[3:])

            url = provider.build_product_url(product_id)
            source_info = {"kind": "site", "site_key": site_alias, "product_id": product_id, "provider_name": provider.name}

        if not nom.strip():
            await send_error(ctx, "Le nom du produit ne peut pas être vide.")
            return

        nom = nom.strip()
        autobuy_enabled = autobuy.lower() in ["on", "true"]

        data["products"][nom] = {
            "url": url, "prix_cible": prix_cible, "autobuy": autobuy_enabled,
            "actif": True, "added_by": ctx.author.id, "source": source_info
        }
        save_data(data)

        embed = discord.Embed(
            title="✅ Produit ajouté",
            description=f"**{nom}** a été ajouté à la surveillance.",
            color=discord.Color.green()
        )
        embed.add_field(name="Prix cible", value=f"{prix_cible}€", inline=True)
        embed.add_field(name="AutoBuy", value="✅ Activé" if autobuy_enabled else "❌ Désactivé", inline=True)
        if source_info["kind"] == "site":
            embed.add_field(name="Site", value=f"{source_info['provider_name']} (ID: {source_info['product_id']})", inline=False)
        embed.add_field(name="URL", value=f"[Lien vers le produit]({url})", inline=False)
        await ctx.send(embed=embed)

@add_product.error
async def add_product_error(ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await send_error(ctx, "Vous devez avoir la permission 'Gérer le serveur' pour utiliser cette commande.")

@bot.command(name='remove')
@commands.has_permissions(manage_guild=True)
async def remove_product(ctx, *, nom: str):
        """Supprimer un produit de la surveillance"""
        data = load_data()
        if nom in data["products"]:
            del data["products"][nom]
            save_data(data)
            embed = discord.Embed(
                title="🗑️ Produit supprimé",
                description=f"**{nom}** a été retiré de la surveillance.",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
        else:
            await send_error(ctx, f"Aucun produit trouvé avec le nom : **{nom}**")

@remove_product.error
async def remove_product_error(ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await send_error(ctx, "Vous devez avoir la permission 'Gérer le serveur' pour utiliser cette commande.")


@bot.command(name='list')
async def list_products(ctx):
        """Lister tous les produits surveillés"""
        products = load_data()["products"]
        if not products:
            embed = discord.Embed(
                title="📭 Aucun produit surveillé",
                description="La liste est vide. Ajoutez un produit avec `!add`.",
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)
            return

        embed = discord.Embed(
            title="📋 Produits surveillés",
            description=f"Total: {len(products)} produit(s)",
            color=discord.Color.blue()
        )
        for nom, info in products.items():
            status = "🟢 Actif" if info.get("actif", True) else "🔴 Inactif"
            autobuy = "🛒 AutoBuy ON" if info["autobuy"] else "👀 Surveillance"
            embed.add_field(
                name=f"**{nom}**",
                value=f"{status} | {autobuy}\n"
                      f"💰 Prix cible: {info['prix_cible']}€\n"
                      f"[Voir le produit]({info['url']})",
                inline=True
            )
        await ctx.send(embed=embed)


@bot.command(name='autobuy')
@commands.has_permissions(manage_guild=True)
async def toggle_autobuy(ctx, *, args: str):
        """Activer/désactiver l'autoBuy pour un produit"""
        try:
            nom, action = args.rsplit(maxsplit=1)
        except ValueError:
            await send_error(ctx, "Usage : `!autobuy <nom du produit> <on/off>`")
            return

        data = load_data()
        if nom not in data["products"]:
            await send_error(ctx, f"Aucun produit trouvé avec le nom : **{nom}**")
            return

        if action.lower() in ["on", "true", "1", "yes"]:
            data["products"][nom]["autobuy"] = True
            status = "✅ activé"
        elif action.lower() in ["off", "false", "0", "no"]:
            data["products"][nom]["autobuy"] = False
            status = "❌ désactivé"
        else:
            await send_error(ctx, "Action invalide. Utilisez `on` ou `off`.")
            return

        save_data(data)
        await send_success(ctx, "🛒 AutoBuy mis à jour", f"L'AutoBuy pour **{nom}** est maintenant {status}.")

@toggle_autobuy.error
async def toggle_autobuy_error(ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await send_error(ctx, "Vous devez avoir la permission 'Gérer le serveur' pour utiliser cette commande.")

@bot.command(name='enable')
@commands.has_permissions(manage_guild=True)
async def enable_monitoring(ctx):
        """Activer la surveillance automatique"""
        config = load_config()
        config["monitoring_enabled"] = True
        save_config(config)
        if not price_monitor.is_running():
            price_monitor.start()
        await send_success(ctx, "🟢 Surveillance activée", "La vérification automatique des prix est maintenant active.")

@enable_monitoring.error
async def enable_monitoring_error(ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await send_error(ctx, "Vous devez avoir la permission 'Gérer le serveur' pour utiliser cette commande.")

@bot.command(name='disable')
@commands.has_permissions(manage_guild=True)
async def disable_monitoring(ctx):
        """Désactiver la surveillance automatique"""
        config = load_config()
        config["monitoring_enabled"] = False
        save_config(config)
        if price_monitor.is_running():
            price_monitor.cancel()
        embed = discord.Embed(
            title="🔴 Surveillance désactivée",
            description="La vérification automatique des prix est inactive.",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)

@disable_monitoring.error
async def disable_monitoring_error(ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await send_error(ctx, "Vous devez avoir la permission 'Gérer le serveur' pour utiliser cette commande.")


@bot.command(name='setrole')
@commands.has_permissions(manage_guild=True)
async def set_notification_role(ctx, *, args: str):
        """Définit ou retire le rôle à mentionner pour les notifications."""
        config = load_config()
        parts = args.split()

        # --- Cas 1 : !setrole @Role ---
        # Pour définir ou changer le rôle de notification.
        if len(parts) == 1 and parts[0].lower() != 'off':
            try:
                role_to_set = await commands.RoleConverter().convert(ctx, parts[0])
                if role_to_set.is_default():
                    await send_error(ctx, "Vous ne pouvez pas utiliser le rôle @everyone pour les notifications.")
                    return

                config["notification_role"] = role_to_set.id
                save_config(config)
                await send_success(ctx, "🔔 Rôle de notification défini", f"Le rôle {role_to_set.mention} sera désormais notifié.")
            except commands.RoleNotFound:
                await send_error(ctx, "Rôle introuvable. Assurez-vous de mentionner un rôle valide.")
            return

        # --- Cas 2 : !setrole off ---
        # Pour retirer le rôle actuellement configuré, quel qu'il soit.
        if len(parts) == 1 and parts[0].lower() == 'off':
            if config.get("notification_role") is None:
                await send_error(ctx, "Aucun rôle de notification n'est actuellement configuré.")
                return

            config["notification_role"] = None
            save_config(config)
            await send_success(ctx, "🔕 Rôle de notification retiré", "Aucun rôle ne sera plus mentionné pour les notifications.")
            return

        # --- Cas 3 : !setrole @Role off ---
        # Pour retirer un rôle UNIQUEMENT s'il correspond au rôle configuré.
        if len(parts) == 2 and parts[1].lower() == 'off':
            try:
                role_to_remove = await commands.RoleConverter().convert(ctx, parts[0])
                current_role_id = config.get("notification_role")

                if current_role_id is None:
                    await send_error(ctx, "Aucun rôle de notification n'est configuré. Il n'y a donc rien à retirer.")
                    return

                if role_to_remove.id == current_role_id:
                    config["notification_role"] = None
                    save_config(config)
                    await send_success(ctx, "🔕 Rôle de notification retiré", f"Le rôle {role_to_remove.mention} ne sera plus notifié.")
                else:
                    current_role = ctx.guild.get_role(current_role_id)
                    await send_error(ctx, f"Action impossible. Le rôle {role_to_remove.mention} n'est pas le rôle de notification actuel ({current_role.mention if current_role else 'ID inconnu'}).")

            except commands.RoleNotFound:
                await send_error(ctx, "Rôle introuvable. Mentionnez le rôle que vous souhaitez retirer.")
            return

        # --- Cas d'erreur ---
        await send_error(ctx, "Commande invalide. Usage : `!setrole <@rôle|off>` ou `!setrole <@rôle> off`")

@set_notification_role.error
async def set_notification_role_error(ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await send_error(ctx, "Vous devez avoir la permission 'Gérer le serveur' pour utiliser cette commande.")


class AutoBuyView(discord.ui.View):
        def __init__(self, product_url: str):
            super().__init__(timeout=3600)  # 1 heure
            self.add_item(discord.ui.Button(label='🛒 Acheter maintenant', style=discord.ButtonStyle.link, url=product_url))

@tasks.loop(seconds=3)
async def price_monitor():
        """Surveille les prix des produits (simulation)"""
        config = load_config()
        if not config.get("monitoring_enabled", False):
            return

        data = load_data()
        # Utilisation de .copy() pour éviter les problèmes de modification pendant l'itération
        for nom, info in data["products"].copy().items():
            if not info.get("actif", True):
                continue

            # Simulation: 1% de chance de trouver un bon prix
            import random
            if random.random() < 0.01:
                for guild in bot.guilds:
                    channel = guild.system_channel or next((c for c in guild.text_channels if c.permissions_for(guild.me).send_messages), None)
                    if not channel: continue

                    if info["autobuy"]:
                        embed = discord.Embed(title="🚨 Prix cible atteint - AutoBuy !",
                                              description=f"**{nom}** est à {info['prix_cible']}€ ou moins !",
                                              color=0xff6600)
                        view = AutoBuyView(info["url"])
                        content = ""
                        if config.get("notification_role"):
                            role = guild.get_role(config["notification_role"])
                            if role: content = f"{role.mention}"
                        await channel.send(content=content, embed=embed, view=view)
                    else:
                        # --- DÉBUT DE L'AJOUT ---
                        # On prépare le message de notification avec la mention du rôle,
                        # comme demandé.
                        content = ""
                        if config.get("notification_role"):
                            role = guild.get_role(config["notification_role"])
                            if role:
                                content = role.mention

                        # On crée un embed clair pour l'alerte de disponibilité.
                        embed = discord.Embed(
                            title="📢 Alerte : Produit Disponible !",
                            description=f"Le produit **{nom}** est disponible au prix que vous souhaitiez !",
                            color=discord.Color.blue()
                        )
                        embed.add_field(name="Prix Cible Atteint", value=f"**{info['prix_cible']}€**", inline=True)
                        embed.add_field(name="Lien vers l'article", value=f"[🛒 Voir le produit]({info['url']})", inline=True)

                        # On envoie le message avec la mention et l'embed.
                        await channel.send(content=content, embed=embed)
                        # --- FIN DE L'AJOUT ---


                    # Désactiver le produit pour éviter le spam de notifications
                    data["products"][nom]["actif"] = False
                    save_data(data)
                    break # Notifier un seul canal par guilde

@bot.command(name='bonjour')
async def hello(ctx):
        """Le bot vous dit bonjour"""
        embed = discord.Embed(
            description=f"👋 Bonjour, {ctx.author.mention} !",
            color=discord.Color.blurple()
        )
        await ctx.send(embed=embed)


    # ... Commandes de gestion de site (addsite, listsite, removesite, help_add) ...
    # Elles utilisent déjà majoritairement des embeds, les erreurs seront gérées par le décorateur.

@bot.command(name='addsite')
@commands.has_permissions(manage_guild=True)
async def add_custom_site(ctx, alias: str, name: str, url_pattern: str, id_regex: str, *, description: str = ""):
        """Ajouter un nouveau site personnalisé à surveiller."""
        alias = alias.lower().strip()
        if get_provider_by_alias(alias):
            await send_error(ctx, f"Un site avec l'alias `{alias}` existe déjà.")
            return
        if "{id}" not in url_pattern:
            await send_error(ctx, "Le pattern d'URL doit contenir `{id}`.")
            return
        try: re.compile(id_regex)
        except re.error:
            await send_error(ctx, "Expression régulière (regex) invalide.")
            return

        custom_sites = load_custom_sites()
        custom_sites[alias] = {
            "aliases": [alias], "name": name.strip(), "url_pattern": url_pattern.strip(),
            "id_regex": id_regex.strip(), "description": description.strip(), "added_by": ctx.author.id
        }
        save_custom_sites(custom_sites)
        reload_providers()

        embed = discord.Embed(title="🌐 Site personnalisé ajouté !", description=f"Le site **{name}** a été ajouté.", color=discord.Color.green())
        embed.add_field(name="Alias", value=f"`{alias}`", inline=True)
        embed.add_field(name="Pattern URL", value=f"`{url_pattern}`", inline=False)
        embed.add_field(name="Validation ID (Regex)", value=f"`{id_regex}`", inline=False)
        if description:
            embed.add_field(name="Description", value=description, inline=False)
        embed.set_footer(text=f"Utilisez `!add {alias} <id> ...` pour l'ajouter.")
        await ctx.send(embed=embed)

@add_custom_site.error
async def add_custom_site_error(ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await send_error(ctx, "Vous devez avoir la permission 'Gérer le serveur' pour utiliser cette commande.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await send_error(ctx, "Argument manquant. Usage: `!addsite <alias> <nom> <url> <regex> [description]`")

@bot.command(name='listsite')
async def list_custom_sites(ctx):
        """Lister tous les sites (intégrés + personnalisés)"""
        embed = discord.Embed(title="🌐 Sites supportés", color=discord.Color.blue())
        builtin = get_builtin_providers()
        if builtin:
            embed.add_field(name="🏗️ Sites intégrés", value="\n".join([f"• **{p.name}** (`{p.aliases[0]}`)" for p in builtin]), inline=False)

        custom = get_custom_providers()
        if custom:
            custom_text = "\n".join([f"• **{p.name}** (`{p.aliases[0]}`)" + (f" - *{p.description}*" if p.description else "") for p in custom])
            embed.add_field(name="🔧 Sites personnalisés", value=custom_text, inline=False)
        else:
            embed.add_field(name="🔧 Sites personnalisés", value="Aucun site personnalisé n'a été ajouté.", inline=False)

        embed.set_footer(text="Ajoutez un site avec !addsite.")
        await ctx.send(embed=embed)

@bot.command(name='removesite')
@commands.has_permissions(manage_guild=True)
async def remove_custom_site(ctx, alias: str):
        """Supprimer un site personnalisé"""
        alias = alias.lower().strip()
        provider = get_provider_by_alias(alias)
        if not provider:
            await send_error(ctx, f"Aucun site trouvé avec l'alias `{alias}`.")
            return
        if not isinstance(provider, CustomProvider):
            await send_error(ctx, f"`{alias}` est un site intégré et ne peut pas être supprimé.")
            return

        custom_sites = load_custom_sites()
        if alias in custom_sites:
            site_name = custom_sites[alias]["name"]
            del custom_sites[alias]
            save_custom_sites(custom_sites)
            reload_providers()
            embed = discord.Embed(title="🗑️ Site supprimé", description=f"Le site personnalisé **{site_name}** (`{alias}`) a été supprimé.", color=discord.Color.orange())
            await ctx.send(embed=embed)
        else:
            await send_error(ctx, f"Incohérence : le site `{alias}` existe mais n'est pas dans le fichier de configuration.")

@remove_custom_site.error
async def remove_custom_site_error(ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await send_error(ctx, "Vous devez avoir la permission 'Gérer le serveur' pour utiliser cette commande.")


@bot.command(name='help_add')
async def help_add_command(ctx):
        """Aide pour la commande !add"""
        embed = discord.Embed(title="📋 Aide - Commande `!add`", description="Comment ajouter un produit à la surveillance.", color=0x0099ff)
        embed.add_field(name="🔗 Mode 1 : Avec URL complète",
                          value="```!add <url> <prix> [autobuy] <nom>```\n"
                                "**Exemple:** `!add https://amazon.fr/dp/B0ABC123 299.99 on Console PS5`", inline=False)
        embed.add_field(name="🏪 Mode 2 : Avec Site + ID",
                          value="```!add <site> <id> <prix> [autobuy] <nom>```\n"
                                "**Exemple:** `!add amazon B0ABC12345 299.99 on Console PS5`", inline=False)
        embed.add_field(name="🌐 Sites supportés (alias)", value=get_supported_sites(), inline=False)
        embed.add_field(name="⚙️ Argument `[autobuy]`",
                          value="`on` : Active la notification avec bouton d'achat.\n`off` : Simple notification (par défaut si omis).", inline=False)
        await ctx.send(embed=embed)


keep_alive()
# Lancement du bot
try:
        token = os.environ['Token_bot']
        bot.run(token)
except KeyError:
        print("Erreur: Le token du bot n'est pas défini dans les variables d'environnement.")
        print("Veuillez définir la variable d'environnement 'Token_bot'.")
