import discord
from discord.ext import commands
import os
import asyncio
from aiohttp import web
import time
from datetime import datetime

# ------------------ CONFIGURATION ------------------
ID_BIENVENUE = 1512009964988661861
ID_AUREVOIR = 1512010175907631104
VIDEO_CHANNEL_ID = 1513174573632454817
LOG_CHANNEL_ID = 1512010693665099876
VERIFICATION_CHANNEL_ID = 1511654306414198805   # salon #‼️règles‼️

UNVERIFIED_ROLE_ID = 1513799071029137499        # "Non vérifié"
MEMBER_ROLE_ID = 1512012606435491911            # "Membres"

AUTHORIZED_USER_ID = 1274426216413139007        # personne autorisée pour les vidéos

# Rôles pour la sélection (facultative)
ROLES_TO_CREATE = [
    ("Féminin", discord.Colour.pink()),
    ("Masculin", discord.Colour.blue()),
    ("Majeur", discord.Colour.green()),
    ("Mineur", discord.Colour.gold()),
    ("Dessinateur", discord.Colour.purple()),
    ("Animateur", discord.Colour.orange())
]

# Anti-spam
command_cooldown = {}
COOLDOWN_SECONDS = 5
recent_joins = {}
recent_leaves = {}
SPAM_SECONDS = 10

VERIFICATION_EMOJI = "✅"

# ------------------ INTENTS ------------------
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True
intents.voice_states = True
intents.reactions = True
intents.guild_messages = True

bot = commands.Bot(command_prefix='!', intents=intents)

# ------------------ LOGS ------------------
async def send_log(message: str):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        try:
            if len(message) > 1990:
                message = message[:1990] + "..."
            await channel.send(f"📋 {message}")
        except Exception as e:
            print(f"Erreur log : {e}")
    else:
        print(f"Log (salon introuvable) : {message}")

# ------------------ SERVEUR HTTP ------------------
async def handle_health(request):
    return web.Response(text="OK")

async def start_http_server():
    app = web.Application()
    app.router.add_get('/', handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    print("✅ Serveur HTTP sur le port 8080")

# ------------------ CRÉATION AUTO DES RÔLES ------------------
async def ensure_roles(guild):
    created = []
    for name, colour in ROLES_TO_CREATE:
        role = discord.utils.get(guild.roles, name=name)
        if not role:
            try:
                role = await guild.create_role(name=name, colour=colour, reason="Création auto onboarding")
                created.append(name)
            except Exception as e:
                await send_log(f"❌ Erreur création rôle {name} : {e}")
    if created:
        await send_log(f"✅ Rôles créés : {', '.join(created)}")

# ------------------ VUE À MENUS (SELECT MENUS) POUR LE PANNEAU ÉPHÉMÈRE ------------------
class RoleSelectView(discord.ui.View):
    def __init__(self, member: discord.Member):
        super().__init__(timeout=300)
        self.member = member
        self.choices = {"gender": None, "age": None, "creator": None}
        self.message = None

        # Menu Genre
        self.gender_menu = discord.ui.Select(
            placeholder="Choisis ton genre",
            options=[
                discord.SelectOption(label="Féminin", value="Féminin", emoji="♀️"),
                discord.SelectOption(label="Masculin", value="Masculin", emoji="♂️")
            ]
        )
        self.gender_menu.callback = self.gender_callback
        self.add_item(self.gender_menu)

        # Menu Âge
        self.age_menu = discord.ui.Select(
            placeholder="Choisis ta tranche d'âge",
            options=[
                discord.SelectOption(label="Majeur (18+)", value="Majeur", emoji="🔞"),
                discord.SelectOption(label="Mineur (-18)", value="Mineur", emoji="🧒")
            ]
        )
        self.age_menu.callback = self.age_callback
        self.add_item(self.age_menu)

        # Menu Statut créatif
        self.creator_menu = discord.ui.Select(
            placeholder="Choisis ton statut",
            options=[
                discord.SelectOption(label="Dessinateur", value="Dessinateur", emoji="✏️"),
                discord.SelectOption(label="Animateur", value="Animateur", emoji="🎬")
            ]
        )
        self.creator_menu.callback = self.creator_callback
        self.add_item(self.creator_menu)

    async def gender_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.member.id:
            return await interaction.response.send_message("Ce panneau ne vous est pas destiné.", ephemeral=True)
        value = self.gender_menu.values[0]
        await self.update_role(interaction, value, "genre", self.gender_menu)

    async def age_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.member.id:
            return await interaction.response.send_message("Ce panneau ne vous est pas destiné.", ephemeral=True)
        value = self.age_menu.values[0]
        await self.update_role(interaction, value, "âge", self.age_menu)

    async def creator_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.member.id:
            return await interaction.response.send_message("Ce panneau ne vous est pas destiné.", ephemeral=True)
        value = self.creator_menu.values[0]
        await self.update_role(interaction, value, "statut", self.creator_menu)

    async def update_role(self, interaction: discord.Interaction, role_name: str, category: str, menu: discord.ui.Select):
        guild = interaction.guild
        role = discord.utils.get(guild.roles, name=role_name)
        if not role:
            await interaction.response.send_message(f"❌ Le rôle {role_name} est introuvable.", ephemeral=True)
            return

        # Retirer le rôle opposé dans la même catégorie
        opposite_map = {
            "Féminin": "Masculin",
            "Masculin": "Féminin",
            "Majeur": "Mineur",
            "Mineur": "Majeur",
            "Dessinateur": "Animateur",
            "Animateur": "Dessinateur"
        }
        opposite_name = opposite_map.get(role_name)
        if opposite_name:
            opposite_role = discord.utils.get(guild.roles, name=opposite_name)
            if opposite_role and opposite_role in interaction.user.roles:
                await interaction.user.remove_roles(opposite_role)

        await interaction.user.add_roles(role)
        await send_log(f"➕ {interaction.user.name} a choisi {role_name} (catégorie {category})")
        
        # Désactiver le menu après choix
        menu.disabled = True
        await interaction.response.edit_message(view=self)
        
        # Vérifier si tous les choix sont faits (optionnel, pas de suppression du rôle Non vérifié ici)
        # On ne fait rien de spécial, les menus deviennent juste grisés.

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass

# ------------------ VÉRIFICATION PAR RÉACTION (ACCÈS FINAL) ------------------
@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return
    if payload.channel_id != VERIFICATION_CHANNEL_ID or str(payload.emoji) != VERIFICATION_EMOJI:
        return

    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    member = guild.get_member(payload.user_id)
    if not member:
        return

    # Donner le rôle Membre et retirer Non vérifié
    member_role = guild.get_role(MEMBER_ROLE_ID)
    if member_role:
        await member.add_roles(member_role)
        await send_log(f"✅ {member.name} a réagi aux règles et est devenu Membre.")

    unverified_role = guild.get_role(UNVERIFIED_ROLE_ID)
    if unverified_role and unverified_role in member.roles:
        await member.remove_roles(unverified_role)
        await send_log(f"🔓 Rôle 'Non vérifié' retiré à {member.name} (vérification effectuée).")

    # Retirer la réaction pour éviter les doublons
    try:
        channel = bot.get_channel(VERIFICATION_CHANNEL_ID)
        msg = await channel.fetch_message(payload.message_id)
        await msg.remove_reaction(VERIFICATION_EMOJI, member)
    except:
        pass

# ------------------ BIENVENUE (message éphémère dans le salon) ------------------
@bot.event
async def on_member_join(member):
    now = time.time()
    if member.id in recent_joins and now - recent_joins[member.id] < SPAM_SECONDS:
        await send_log(f"🚫 Ignoré doublon arrivée de {member.name}")
        return
    recent_joins[member.id] = now

    # Ajouter le rôle "Non vérifié"
    unverified_role = member.guild.get_role(UNVERIFIED_ROLE_ID)
    if unverified_role:
        try:
            await member.add_roles(unverified_role)
            await send_log(f"🔒 Rôle 'Non vérifié' ajouté à {member.name}")
        except Exception as e:
            await send_log(f"❌ Erreur ajout rôle Non vérifié : {e}")
    else:
        await send_log(f"❌ Rôle Non vérifié (ID {UNVERIFIED_ROLE_ID}) introuvable.")

    # Message public de bienvenue (classique)
    canal_bienvenue = bot.get_channel(ID_BIENVENUE)
    if canal_bienvenue:
        try:
            embed_bv = discord.Embed(
                title="🎨 Bienvenue !",
                description=f"Oh ! **{member.display_name}** a rejoint le serveur ! Bonne visite !",
                color=0x000000,
                timestamp=datetime.now()
            )
            if member.avatar:
                embed_bv.set_thumbnail(url=member.avatar.url)
            await canal_bienvenue.send(embed=embed_bv)
            await send_log(f"✅ Message public de bienvenue pour {member.name}")
        except Exception as e:
            await send_log(f"⚠️ Erreur bienvenue publique : {e}")

        # Envoi du panneau de sélection éphémère (visible uniquement par le nouveau membre)
        embed_select = discord.Embed(
            title="🔧 Configuration optionnelle de ton profil",
            description=(
                "Bienvenue ! Tu peux choisir des rôles ci-dessous (ce n'est pas obligatoire).\n\n"
                "**Genre**\n**Âge**\n**Statut créatif**\n\n"
                "Une fois ces choix faits (ou non), rends-toi dans le salon <#{}> "
                "et réagis avec {} pour accéder au serveur."
            ).format(VERIFICATION_CHANNEL_ID, VERIFICATION_EMOJI),
            color=0x2b2d31  # gris foncé / noir
        )
        view = RoleSelectView(member)
        # ephemeral=True : message visible uniquement par le membre
        msg = await canal_bienvenue.send(embed=embed_select, view=view, ephemeral=True)
        view.message = msg
        await send_log(f"📨 Panneau de sélection (éphémère) envoyé à {member.name} dans {canal_bienvenue.mention}")
    else:
        await send_log(f"❌ Salon bienvenue introuvable (ID {ID_BIENVENUE})")

# ------------------ AU REVOIR ------------------
@bot.event
async def on_member_remove(member):
    now = time.time()
    if member.id in recent_leaves and now - recent_leaves[member.id] < SPAM_SECONDS:
        await send_log(f"🚫 Ignoré doublon départ de {member.name}")
        return
    recent_leaves[member.id] = now
    canal = bot.get_channel(ID_AUREVOIR)
    if canal:
        embed = discord.Embed(
            title="👋 Au revoir...",
            description=f"Oh... {member.display_name} a quitté le serveur, en espérant qu'il/elle deviendra un(e) artiste.",
            color=0x000000,
            timestamp=datetime.now()
        )
        await canal.send(embed=embed)
        await send_log(f"✅ Message d'au revoir pour {member.name}")

# ------------------ REDIRECTION VIDÉOS ------------------
@bot.listen('on_message')
async def on_message_listener(message):
    if message.author == bot.user or message.author.id != AUTHORIZED_USER_ID:
        return
    content = message.content.lower()
    if "youtube.com" in content or "youtu.be" in content or "tiktok.com" in content:
        video_channel = bot.get_channel(VIDEO_CHANNEL_ID)
        if video_channel:
            await video_channel.send(f"📹 **{message.author.display_name}** a partagé :\n{message.content}")
        else:
            await send_log("❌ Salon vidéo introuvable")
    await bot.process_commands(message)

# ------------------ COMMANDES ------------------
@bot.command()
async def ping(ctx):
    user_id = ctx.author.id
    now = time.time()
    if user_id in command_cooldown and now - command_cooldown[user_id] < COOLDOWN_SECONDS:
        await ctx.send("⏳ Attends un peu avant de refaire `!ping` !")
        return
    command_cooldown[user_id] = now
    await ctx.send("Pong !")
    await send_log(f"Commande !ping utilisée par {ctx.author.name}")

@bot.tree.command(name="ping", description="Vérifie la latence du bot")
async def slash_ping(interaction: discord.Interaction):
    user_id = interaction.user.id
    now = time.time()
    if user_id in command_cooldown and now - command_cooldown[user_id] < COOLDOWN_SECONDS:
        await interaction.response.send_message("⏳ Attends un peu avant de refaire `/ping` !", ephemeral=True)
        return
    command_cooldown[user_id] = now
    await interaction.response.send_message(f"Pong ! Latence : {round(bot.latency * 1000)}ms")
    await send_log(f"Commande /ping utilisée par {interaction.user.name}")

@bot.command()
@commands.has_permissions(administrator=True)
async def setup_roles(ctx):
    await ensure_roles(ctx.guild)
    await ctx.send("✅ Vérification/création des rôles effectuée.", ephemeral=True)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    await send_log(f"❌ Erreur dans la commande `{ctx.command}` : {error}")

# ------------------ DÉMARRAGE ------------------
@bot.event
async def on_ready():
    print(f"✅ Bot connecté : {bot.user}")
    await bot.tree.sync()
    print("✅ Commandes slash synchronisées")
    for guild in bot.guilds:
        await ensure_roles(guild)
    await send_log("🚀 Bot démarré (panneau éphémère dans le salon de bienvenue)")

async def main():
    asyncio.create_task(start_http_server())
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ Token manquant")
        return
    await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())