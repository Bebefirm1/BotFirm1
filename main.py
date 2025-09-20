import os
import json
import asyncio
import discord
import re
import random
import aiohttp
from datetime import datetime
from dotenv import load_dotenv
from discord.ext import commands, tasks
from typing import Optional, Dict, List, Union
from abc import ABC, abstractmethod
from bs4 import BeautifulSoup

from keep_alive import keep_alive
load_dotenv()
token = os.getenv('Token_bot')

# --- Configuration des Intents et du Bot ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

    # --- Constantes pour les fichiers de données ---
DATA_FILE = "products.json"
CONFIG_FILE = "config.json"
CUSTOM_SITES_FILE = "custom_sites.json"
PRICE_HISTORY_FILE = "price_history.json"

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

        async def get_product_price(self, url: str) -> Optional[float]:
            """Récupère le prix actuel du produit (simulation pour l'instant)"""
            # Simulation - Dans un cas réel, vous devriez faire du web scraping
            # Pour la démonstration, on retourne un prix aléatoire
            return round(random.uniform(50, 500), 2)

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
            self._price_selector = config.get("price_selector", "")

        @property
        def aliases(self) -> List[str]: return self._aliases
        @property
        def name(self) -> str: return self._name
        @property
        def description(self) -> str: return self._description
        @property
        def price_selector(self) -> str: return self._price_selector

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
def load_config(): return load_json_file(CONFIG_FILE, {"monitoring_enabled": False, "notification_role": None, "check_interval": 60})
def save_config(config): save_json_file(CONFIG_FILE, config)
def load_custom_sites(): return load_json_file(CUSTOM_SITES_FILE, {})
def save_custom_sites(sites): save_json_file(CUSTOM_SITES_FILE, sites)
def load_price_history(): return load_json_file(PRICE_HISTORY_FILE, {})
def save_price_history(history): save_json_file(PRICE_HISTORY_FILE, history)

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

reload_providers()  # Chargement initial

    # --- Fonction de vérification des prix ---
async def check_product_price(product_name: str, product_info: dict) -> Optional[float]:
        """Vérifie le prix actuel d'un produit (simulation améliorée)"""
        # Simulation de récupération du prix
        # Dans une implémentation réelle, vous devriez faire du web scraping ici

        # Récupération du provider si disponible
        if "source" in product_info and product_info["source"].get("kind") == "site":
            site_key = product_info["source"]["site_key"]
            provider = get_provider_by_alias(site_key)
            if provider:
                # Simulation de prix avec variation
                base_price = product_info["prix_cible"]
                variation = random.uniform(-50, 100)
                current_price = max(10, base_price + variation)

                # Enregistrer dans l'historique
                history = load_price_history()
                if product_name not in history:
                    history[product_name] = []
                history[product_name].append({
                    "price": round(current_price, 2),
                    "timestamp": datetime.now().isoformat()
                })
                # Garder seulement les 100 derniers prix
                history[product_name] = history[product_name][-100:]
                save_price_history(history)

                return round(current_price, 2)

        # Fallback pour les URLs directes
        return round(random.uniform(50, 500), 2)

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
                  "`!checkprice <nom>` - Vérifie manuellement le prix d'un produit.\n"
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
                  "`!setrole <@rôle|off>` - Définit ou retire le rôle pour les notifications.\n"
                  "`!setinterval <secondes>` - Définit l'intervalle de vérification (min: 30s).",
            inline=False
        )

        embed.add_field(
            name="📊 Statistiques",
            value="`!stats` - Affiche les statistiques globales de surveillance.",
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
            # Mode URL classique
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
            # Mode site + ID
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
            source_info = {
                "kind": "site", 
                "site_key": site_alias, 
                "product_id": product_id, 
                "provider_name": provider.name
            }

        if not nom.strip():
            await send_error(ctx, "Le nom du produit ne peut pas être vide.")
            return

        nom = nom.strip()
        autobuy_enabled = autobuy.lower() in ["on", "true"]

        data["products"][nom] = {
            "url": url, 
            "prix_cible": prix_cible, 
            "autobuy": autobuy_enabled,
            "actif": True, 
            "added_by": ctx.author.id, 
            "source": source_info,
            "date_added": datetime.now().isoformat(),
            "last_check": None,
            "notifications_sent": 0
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
        embed.set_footer(text="La surveillance commence immédiatement si elle est activée.")
        await ctx.send(embed=embed)

@bot.command(name='checkprice')
async def check_price_manual(ctx, *, nom: str):
        """Vérifie manuellement le prix d'un produit."""
        data = load_data()
        if nom not in data["products"]:
            await send_error(ctx, f"Aucun produit trouvé avec le nom : **{nom}**")
            return

        product_info = data["products"][nom]
        embed = discord.Embed(
            title="🔍 Vérification du prix...",
            description=f"Recherche du prix actuel pour **{nom}**...",
            color=discord.Color.blue()
        )
        msg = await ctx.send(embed=embed)

        # Simulation de vérification
        await asyncio.sleep(2)
        current_price = await check_product_price(nom, product_info)

        if current_price:
            prix_cible = product_info["prix_cible"]
            diff = current_price - prix_cible

            if current_price <= prix_cible:
                embed = discord.Embed(
                    title="🎉 Prix intéressant !",
                    description=f"**{nom}** est disponible à un bon prix !",
                    color=discord.Color.green()
                )
                embed.add_field(name="Prix actuel", value=f"{current_price}€", inline=True)
                embed.add_field(name="Prix cible", value=f"{prix_cible}€", inline=True)
                embed.add_field(name="Économie", value=f"{abs(diff):.2f}€", inline=True)
            else:
                embed = discord.Embed(
                    title="💰 Prix actuel",
                    description=f"**{nom}** est au-dessus du prix cible.",
                    color=discord.Color.orange()
                )
                embed.add_field(name="Prix actuel", value=f"{current_price}€", inline=True)
                embed.add_field(name="Prix cible", value=f"{prix_cible}€", inline=True)
                embed.add_field(name="Différence", value=f"+{diff:.2f}€", inline=True)

            embed.add_field(name="URL", value=f"[Voir le produit]({product_info['url']})", inline=False)

            # Mise à jour de last_check
            data["products"][nom]["last_check"] = datetime.now().isoformat()
            save_data(data)
        else:
            embed = discord.Embed(
                title="❌ Erreur",
                description="Impossible de récupérer le prix actuel.",
                color=discord.Color.red()
            )

        await msg.edit(embed=embed)

@bot.command(name='stats')
async def show_stats(ctx):
        """Affiche les statistiques de surveillance."""
        data = load_data()
        config = load_config()

        total_products = len(data["products"])
        active_products = sum(1 for p in data["products"].values() if p.get("actif", True))
        autobuy_products = sum(1 for p in data["products"].values() if p["autobuy"])

        embed = discord.Embed(
            title="📊 Statistiques de surveillance",
            color=discord.Color.blue()
        )

        embed.add_field(name="Total produits", value=str(total_products), inline=True)
        embed.add_field(name="Produits actifs", value=str(active_products), inline=True)
        embed.add_field(name="AutoBuy activé", value=str(autobuy_products), inline=True)

        status = "🟢 Activée" if config.get("monitoring_enabled", False) else "🔴 Désactivée"
        embed.add_field(name="Surveillance", value=status, inline=True)

        interval = config.get("check_interval", 60)
        embed.add_field(name="Intervalle", value=f"{interval}s", inline=True)

        # Notifications totales envoyées
        total_notifs = sum(p.get("notifications_sent", 0) for p in data["products"].values())
        embed.add_field(name="Notifications envoyées", value=str(total_notifs), inline=True)

        await ctx.send(embed=embed)

@bot.command(name='setinterval')
@commands.has_permissions(manage_guild=True)
async def set_check_interval(ctx, seconds: int):
        """Définit l'intervalle de vérification des prix."""
        if seconds < 30:
            await send_error(ctx, "L'intervalle minimum est de 30 secondes.")
            return

        config = load_config()
        config["check_interval"] = seconds
        save_config(config)

        # Redémarrer la tâche avec le nouvel intervalle
        if price_monitor.is_running():
            price_monitor.cancel()
            price_monitor.change_interval(seconds=seconds)
            price_monitor.start()

        await send_success(ctx, "⏱️ Intervalle mis à jour", f"Les prix seront vérifiés toutes les {seconds} secondes.")

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

        for nom, info in list(products.items())[:25]:  # Limite à 25 pour éviter de dépasser la limite Discord
            status = "🟢" if info.get("actif", True) else "🔴"
            autobuy = "🛒" if info["autobuy"] else "👀"
            last_check = info.get("last_check", "Jamais")
            if last_check != "Jamais":
                last_check = datetime.fromisoformat(last_check).strftime("%d/%m %H:%M")

            value = f"{status} {autobuy} Prix: {info['prix_cible']}€\n"
            value += f"📅 Vérifié: {last_check}\n"
            value += f"[Lien]({info['url']})"

            embed.add_field(name=f"**{nom}**", value=value, inline=True)

        if len(products) > 25:
            embed.set_footer(text=f"Affichage limité aux 25 premiers produits sur {len(products)}")

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

@bot.command(name='setrole')
@commands.has_permissions(manage_guild=True)
async def set_notification_role(ctx, *, args: str):
        """Définit ou retire le rôle à mentionner pour les notifications."""
        config = load_config()
        parts = args.split()

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

        if len(parts) == 1 and parts[0].lower() == 'off':
            if config.get("notification_role") is None:
                await send_error(ctx, "Aucun rôle de notification n'est actuellement configuré.")
                return

            config["notification_role"] = None
            save_config(config)
            await send_success(ctx, "🔕 Rôle de notification retiré", "Aucun rôle ne sera plus mentionné pour les notifications.")
            return

        await send_error(ctx, "Commande invalide. Usage : `!setrole <@rôle|off>`")

class AutoBuyView(discord.ui.View):
        def __init__(self, product_url: str):
            super().__init__(timeout=3600)  # 1 heure
            self.add_item(discord.ui.Button(label='🛒 Acheter maintenant', style=discord.ButtonStyle.link, url=product_url))

@tasks.loop(seconds=60)
async def price_monitor():
        """Surveille les prix des produits"""
        config = load_config()
        if not config.get("monitoring_enabled", False):
            return

        data = load_data()
        products_to_check = [
            (nom, info) for nom, info in data["products"].items() 
            if info.get("actif", True)
        ]

        for nom, info in products_to_check:
            try:
                current_price = await check_product_price(nom, info)

                if current_price and current_price <= info["prix_cible"]:
                    # Prix cible atteint !
                    for guild in bot.guilds:
                        channel = guild.system_channel or next(
                            (c for c in guild.text_channels if c.permissions_for(guild.me).send_messages), 
                            None
                        )
                        if not channel: 
                            continue

                        # Créer l'embed de notification
                        if info["autobuy"]:
                            embed = discord.Embed(
                                title="🚨 Prix cible atteint - AutoBuy !",
                                description=f"**{nom}** est disponible à {current_price}€ (cible: {info['prix_cible']}€)",
                                color=0xff6600
                            )
                            view = AutoBuyView(info["url"])
                        else:
                            embed = discord.Embed(
                                title="📢 Prix cible atteint !",
                                description=f"**{nom}** est disponible à {current_price}€ (cible: {info['prix_cible']}€)",
                                color=discord.Color.green()
                            )
                            embed.add_field(name="Lien", value=f"[Voir le produit]({info['url']})")
                            view = None

                        # Ajouter les détails du site si disponible
                        if "source" in info and info["source"].get("kind") == "site":
                            embed.add_field(
                                name="Site",
                                value=f"{info['source']['provider_name']} (ID: {info['source']['product_id']})",
                                inline=True
                            )

                        embed.add_field(name="Économie", value=f"{info['prix_cible'] - current_price:.2f}€", inline=True)
                        embed.set_footer(text=f"Vérifié le {datetime.now().strftime('%d/%m/%Y à %H:%M')}")

                        # Mention du rôle si configuré
                        content = ""
                        if config.get("notification_role"):
                            role = guild.get_role(config["notification_role"])
                            if role: 
                                content = f"{role.mention}"

                        # Envoyer la notification
                        if view:
                            await channel.send(content=content, embed=embed, view=view)
                        else:
                            await channel.send(content=content, embed=embed)

                        # Mise à jour des statistiques
                        data["products"][nom]["actif"] = False  # Désactiver pour éviter le spam
                        data["products"][nom]["notifications_sent"] = data["products"][nom].get("notifications_sent", 0) + 1
                        data["products"][nom]["last_notification"] = datetime.now().isoformat()
                        save_data(data)

                        print(f"✅ Notification envoyée pour {nom} - Prix: {current_price}€")
                        break  # Ne notifier qu'un seul canal par guilde

                # Mise à jour du last_check même si le prix n'est pas atteint
                data["products"][nom]["last_check"] = datetime.now().isoformat()
                save_data(data)

            except Exception as e:
                print(f"Erreur lors de la vérification de {nom}: {e}")
                continue

    # Gestion des erreurs pour les commandes
@add_product.error
async def add_product_error(ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await send_error(ctx, "Vous devez avoir la permission 'Gérer le serveur' pour utiliser cette commande.")

@remove_product.error
async def remove_product_error(ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await send_error(ctx, "Vous devez avoir la permission 'Gérer le serveur' pour utiliser cette commande.")

@toggle_autobuy.error
async def toggle_autobuy_error(ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await send_error(ctx, "Vous devez avoir la permission 'Gérer le serveur' pour utiliser cette commande.")

@enable_monitoring.error
async def enable_monitoring_error(ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await send_error(ctx, "Vous devez avoir la permission 'Gérer le serveur' pour utiliser cette commande.")

@disable_monitoring.error
async def disable_monitoring_error(ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await send_error(ctx, "Vous devez avoir la permission 'Gérer le serveur' pour utiliser cette commande.")

@set_notification_role.error
async def set_notification_role_error(ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await send_error(ctx, "Vous devez avoir la permission 'Gérer le serveur' pour utiliser cette commande.")

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
        try: 
            re.compile(id_regex)
        except re.error:
            await send_error(ctx, "Expression régulière (regex) invalide.")
            return

        custom_sites = load_custom_sites()
        custom_sites[alias] = {
            "aliases": [alias], 
            "name": name.strip(), 
            "url_pattern": url_pattern.strip(),
            "id_regex": id_regex.strip(), 
            "description": description.strip(), 
            "added_by": ctx.author.id,
            "added_date": datetime.now().isoformat()
        }
        save_custom_sites(custom_sites)
        reload_providers()

        embed = discord.Embed(
            title="🌐 Site personnalisé ajouté !", 
            description=f"Le site **{name}** a été ajouté avec succès.",
            color=discord.Color.green()
        )
        embed.add_field(name="Alias", value=f"`{alias}`", inline=True)
        embed.add_field(name="Pattern URL", value=f"`{url_pattern}`", inline=False)
        embed.add_field(name="Validation ID (Regex)", value=f"`{id_regex}`", inline=False)
        if description:
            embed.add_field(name="Description", value=description, inline=False)
        embed.set_footer(text=f"Utilisez `!add {alias} <id> <prix> [autobuy] <nom>` pour surveiller un produit.")
        await ctx.send(embed=embed)

@add_custom_site.error
async def add_custom_site_error(ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await send_error(ctx, "Vous devez avoir la permission 'Gérer le serveur' pour utiliser cette commande.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await send_error(ctx, "Argument manquant. Usage: `!addsite <alias> <nom> <url_pattern> <regex> [description]`")

@bot.command(name='listsite')
async def list_custom_sites(ctx):
        """Lister tous les sites (intégrés + personnalisés)"""
        embed = discord.Embed(
            title="🌐 Sites supportés", 
            color=discord.Color.blue()
        )

        builtin = get_builtin_providers()
        if builtin:
            builtin_text = "\n".join([f"• **{p.name}** (`{p.aliases[0]}`)" for p in builtin])
            embed.add_field(name="🏗️ Sites intégrés", value=builtin_text, inline=False)

        custom = get_custom_providers()
        if custom:
            custom_text = "\n".join([
                f"• **{p.name}** (`{p.aliases[0]}`)" + (f" - *{p.description}*" if p.description else "") 
                for p in custom
            ])
            embed.add_field(name="🔧 Sites personnalisés", value=custom_text, inline=False)
        else:
            embed.add_field(
                name="🔧 Sites personnalisés", 
                value="Aucun site personnalisé n'a été ajouté.", 
                inline=False
            )

        embed.set_footer(text="Ajoutez un site avec !addsite | Voir l'aide avec !help")
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

            embed = discord.Embed(
                title="🗑️ Site supprimé", 
                description=f"Le site personnalisé **{site_name}** (`{alias}`) a été supprimé.", 
                color=discord.Color.orange()
            )
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
        embed = discord.Embed(
            title="📋 Aide - Commande `!add`", 
            description="Comment ajouter un produit à la surveillance.", 
            color=0x0099ff
        )
        embed.add_field(
            name="🔗 Mode 1 : Avec URL complète",
            value="```!add <url> <prix> [autobuy] <nom>```\n"
                  "**Exemple:** `!add https://amazon.fr/dp/B0ABC123 299.99 on Console PS5`", 
            inline=False
        )
        embed.add_field(
            name="🏪 Mode 2 : Avec Site + ID",
            value="```!add <site> <id> <prix> [autobuy] <nom>```\n"
                  "**Exemple:** `!add amazon B0ABC12345 299.99 on Console PS5`", 
            inline=False
        )
        embed.add_field(
            name="🌐 Sites supportés", 
            value=get_supported_sites(), 
            inline=False
        )
        embed.add_field(
            name="⚙️ Argument `[autobuy]`",
            value="`on` : Active la notification avec bouton d'achat.\n"
                  "`off` : Simple notification (par défaut si omis).", 
            inline=False
        )
        embed.add_field(
            name="💡 Conseil",
            value="Pour les sites personnalisés, utilisez l'alias défini avec `!addsite`.\n"
                  "Les produits seront surveillés automatiquement si la surveillance est activée.",
            inline=False
        )
        await ctx.send(embed=embed)

@bot.command(name='reactive')
@commands.has_permissions(manage_guild=True)
async def reactivate_product(ctx, *, nom: str):
        """Réactive un produit après qu'il ait trouvé un prix"""
        data = load_data()
        if nom not in data["products"]:
            await send_error(ctx, f"Aucun produit trouvé avec le nom : **{nom}**")
            return

        data["products"][nom]["actif"] = True
        save_data(data)

        embed = discord.Embed(
            title="♻️ Produit réactivé",
            description=f"**{nom}** est de nouveau sous surveillance active.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

@bot.command(name='history')
async def show_price_history(ctx, *, nom: str):
        """Affiche l'historique des prix d'un produit"""
        history = load_price_history()
        if nom not in history or not history[nom]:
            await send_error(ctx, f"Aucun historique de prix pour **{nom}**")
            return

        product_history = history[nom][-10:]  # Derniers 10 prix

        embed = discord.Embed(
            title=f"📈 Historique des prix - {nom}",
            color=discord.Color.blue()
        )

        for entry in product_history:
            timestamp = datetime.fromisoformat(entry["timestamp"]).strftime("%d/%m %H:%M")
            embed.add_field(
                name=timestamp,
                value=f"{entry['price']}€",
                inline=True
            )

        # Calcul des statistiques
        prices = [entry["price"] for entry in product_history]
        avg_price = sum(prices) / len(prices)
        min_price = min(prices)
        max_price = max(prices)

        embed.add_field(
            name="📊 Statistiques",
            value=f"Moyenne: {avg_price:.2f}€\nMin: {min_price}€\nMax: {max_price}€",
            inline=False
        )

        await ctx.send(embed=embed)

    # Changement de l'intervalle de la loop au démarrage
@price_monitor.before_loop
async def before_price_monitor():
        await bot.wait_until_ready()
        config = load_config()
        interval = config.get("check_interval", 60)
        price_monitor.change_interval(seconds=interval)

keep_alive()
    # Lancement du bot
try:
        token = os.environ['Token_bot']
        bot.run(token)
except KeyError:
    print("Erreur: Le token du bot n'est pas défini dans les variables d'environnement.")
    print("Veuillez définir la variable d'environnement 'Token_bot'.")
