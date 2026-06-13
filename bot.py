import discord
from discord.ext import commands
from PIL import Image
import io
import os
from datetime import datetime
import asyncio
from aiohttp import web
import time
import re

# ------------------ CONFIGURATION ------------------
# IDs des salons (à vérifier)
ID_BIENVENUE = 1512009964988661861
ID_AUREVOIR = 1512010175907631104
VIDEO_CHANNEL_ID = 1513174573632454817
LOG_CHANNEL_ID = 1512010693665099876
VERIFICATION_CHANNEL_ID = 1511654306414198805   # salon #‼️règles‼️
RULES_MESSAGE_ID = 1511657834192961598          # message des règles (avec réaction ✅)

# IDs des rôles existants
UNVERIFIED_ROLE_ID = 1513799071029137499        # "Non vérifié"
MEMBER_ROLE_ID = 1512012606435491911            # "Membres"

# ID de la personne autorisée pour les vidéos
AUTHORIZED_USER_ID = 1274426216413139007

# Images de fond
FOND_BIENVENUE = "IMG_1299.png"
FOND_AUREVOIR = "IMG_1319.png"

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
            print(f"Erreur log Discord : {e}")

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

# ------------------ IMAGES ------------------
def ajouter_bordure(image_bytes: bytes, bordure_px: int = 15) -> bytes:
    img = Image.open(io.BytesIO(image_bytes))
    img_bordure = Image.new("RGB", (img.width + 2*bordure_px, img.height + 2*bordure_px), (0,0,0))
    img_bordure.paste(img, (bordure_px, bordure_px))
    with io.BytesIO() as buf:
        img_bordure.save(buf, format="PNG")
        buf.seek(0)
        return buf.getvalue()

async def lire_image(fond_path: str) -> bytes:
    with open(fond_path, "rb") as f:
        return f.read()

# ------------------ CRÉATION AUTO DES RÔLES ------------------
async def ensure_roles(guild):
    """Crée les rôles manquants (Féminin, Masculin, etc.) si besoin."""
    created = []
    required = [
        ("Féminin", discord.Colour.pink()),
        ("Masculin", discord.Colour.blue()),
        ("Majeur", discord.Colour.green()),
        ("Mineur", discord.Colour.gold()),
        ("Dessinateur", discord.Colour.purple()),
        ("Animateur", discord.Colour.orange())
    ]
    for name, colour in required:
        role = discord.utils.get(guild.roles, name=name)
        if not role:
            try:
                role = await guild.create_role(name=name, colour=colour, reason="Création auto pour l'onboarding")
                created.append(name)
            except Exception as e:
                await send_log(f"❌ Erreur création rôle {name} : {e}")
    if created:
        await send_log(f"✅ Rôles créés automatiquement : {', '.join(created)}")

# ------------------ VUE À MENUS POUR LA SÉLECTION ------------------
class RoleSelectView(discord.ui.View):
    def __init__(self, member: discord.Member):
        super().__init__(timeout=300)  # 5 minutes
        self.member = member
        self.gender_selected = None
        self.age_selected = None
        self.creator_selected = None
        self.add_menu()

    def add_menu(self):
        self.gender_menu = discord.ui.Select(
            placeholder="Sélectionne ton genre",
            options=[
                discord.SelectOption(label="Féminin", value="Féminin", emoji="♀️"),
                discord.SelectOption(label="Masculin", value="Masculin", emoji="♂️")
            ]
        )
        self.age_menu = discord.ui.Select(
            placeholder="Sélectionne ta tranche d'âge",
            options=[
                discord.SelectOption(label="Majeur (18+)", value="Majeur", emoji="🔞"),
                discord.SelectOption(label="Mineur (-18)", value="Mineur", emoji="🧒")
            ]
        )
        self.creator_menu = discord.ui.Select(
            placeholder="Sélectionne ton statut créatif",
            options=[
                discord.SelectOption(label="Dessinateur", value="Dessinateur", emoji="✏️"),
                discord.SelectOption(label="Animateur", value="Animateur", emoji="🎬")
            ]
        )
        
        self.gender_menu.callback = self.gender_callback
        self.age_menu.callback = self.age_callback
        self.creator_menu.callback = self.creator_callback
        
        self.add_item(self.gender_menu)
        self.add_item(self.age_menu)
        self.add_item(self.creator_menu)

    async def gender_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.member.id:
            return await interaction.response.send_message("Cette sélection ne vous est pas destinée.", ephemeral=True)
        await self.update_role(interaction, self.gender_menu.values[0], "genre")
        self.gender_selected = self.gender_menu.values[0]
        self.gender_menu.disabled = True
        await interaction.response.edit_message(view=self)
        await self.check_completion(interaction)

    async def age_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.member.id:
            return await interaction.response.send_message("Cette sélection ne vous est pas destinée.", ephemeral=True)
        await self.update_role(interaction, self.age_menu.values[0], "âge")
        self.age_selected = self.age_menu.values[0]
        self.age_menu.disabled = True
        await interaction.response.edit_message(view=self)
        await self.check_completion(interaction)

    async def creator_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.member.id:
            return await interaction.response.send_message("Cette sélection ne vous est pas destinée.", ephemeral=True)
        await self.update_role(interaction, self.creator_menu.values[0], "statut")
        self.creator_selected = self.creator_menu.values[0]
        self.creator_menu.disabled = True
        await interaction.response.edit_message(view=self)
        await self.check_completion(interaction)

    async def update_role(self, interaction: discord.Interaction, role_name: str, category: str):
        guild = interaction.guild
        role = discord.utils.get(guild.roles, name=role_name)
        if not role:
            await interaction.followup.send(f"❌ Le rôle `{role_name}` est introuvable. Contacte un administrateur.", ephemeral=True)
            return
        # Retirer le rôle opposé dans la même catégorie
        opposite_map = {
            ("Féminin", "Masculin"): ("Masculin", "Féminin"),
            ("Majeur", "Mineur"): ("Mineur", "Majeur"),
            ("Dessinateur", "Animateur"): ("Animateur", "Dessinateur")
        }
        for (a, b), (opp_a, opp_b) in opposite_map.items():
            if role_name == a:
                opposite = discord.utils.get(guild.roles, name=b)
            elif role_name == b:
                opposite = discord.utils.get(guild.roles, name=a)
            else:
                continue
            if opposite and opposite in interaction.user.roles:
                await interaction.user.remove_roles(opposite)
            break
        await interaction.user.add_roles(role)
        await send_log(f"🔁 {interaction.user.name} a choisi {role_name} (catégorie {category})")

    async def check_completion(self, interaction: discord.Interaction):
        if self.gender_selected and self.age_selected and self.creator_selected:
            # Retirer le rôle "Non vérifié"
            unverified_role = interaction.guild.get_role(UNVERIFIED_ROLE_ID)
            if unverified_role and unverified_role in interaction.user.roles:
                await interaction.user.remove_roles(unverified_role)
                await send_log(f"🔓 {interaction.user.name} a terminé la sélection, accès aux règles accordé.")
            # Désactiver tous les menus
            for item in self.children:
                item.disabled = True
            await interaction.message.edit(view=self)
            embed_success = discord.Embed(
                title="✅ Parcours terminé !",
                description=f"Rends-toi maintenant dans le salon <#{VERIFICATION_CHANNEL_ID}> et réagis avec {VERIFICATION_EMOJI} sur le message des règles pour accéder au serveur.",
                color=0x00ff00
            )
            await interaction.followup.send(embed=embed_success, ephemeral=True)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if hasattr(self, 'message'):
            try:
                await self.message.edit(view=self)
            except:
                pass

# ------------------ VÉRIFICATION PAR RÉACTION (sur message existant) ------------------
async def setup_verification_reaction():
    channel = bot.get_channel(VERIFICATION_CHANNEL_ID)
    if not channel:
        await send_log(f"❌ Salon des règles introuvable (ID {VERIFICATION_CHANNEL_ID})")
        return
    try:
        message = await channel.fetch_message(RULES_MESSAGE_ID)
        for reaction in message.reactions:
            if str(reaction.emoji) == VERIFICATION_EMOJI:
                return
        await message.add_reaction(VERIFICATION_EMOJI)
        print(f"✅ Réaction {VERIFICATION_EMOJI} ajoutée au message des règles.")
    except discord.NotFound:
        await send_log(f"❌ Message des règles introuvable (ID {RULES_MESSAGE_ID})")
    except Exception as e:
        await send_log(f"❌ Erreur lors de l'ajout de la réaction : {e}")

@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return
    if payload.channel_id != VERIFICATION_CHANNEL_ID or str(payload.emoji) != VERIFICATION_EMOJI or payload.message_id != RULES_MESSAGE_ID:
        return
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    member = guild.get_member(payload.user_id)
    if not member:
        return
    # Vérifier que le membre a bien fait la sélection (n'a plus le rôle "Non vérifié")
    unverified_role = guild.get_role(UNVERIFIED_ROLE_ID)
    if unverified_role and unverified_role in member.roles:
        await send_log(f"⚠️ {member.name} a essayé de réagir aux règles sans avoir fait la sélection de rôles.")
        return
    member_role = guild.get_role(MEMBER_ROLE_ID)
    if member_role:
        await member.add_roles(member_role)
        await send_log(f"✅ {member.name} a réagi aux règles et est devenu Membre.")
        # Retirer la réaction pour éviter les doublons
        try:
            channel = bot.get_channel(VERIFICATION_CHANNEL_ID)
            msg = await channel.fetch_message(payload.message_id)
            await msg.remove_reaction(VERIFICATION_EMOJI, member)
        except:
            pass

# ------------------ BIENVENUE ------------------
@bot.event
async def on_member_join(member):
    # Anti-spam
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

    # Message de bienvenue dans le salon dédié
    canal_bienvenue = bot.get_channel(ID_BIENVENUE)
    if canal_bienvenue:
        try:
            img_bytes = await lire_image(FOND_BIENVENUE)
            img_bordure = ajouter_bordure(img_bytes)
            texte = f"Oh ! **{member.display_name}** est un/une potentiel(le) dessinateur/rice et a rejoint ce serveur, bonne visite !"
            embed_bv = discord.Embed(title="🎨 Bienvenue !", description=texte, color=0x000000, timestamp=datetime.now())
            embed_bv.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
            await canal_bienvenue.send(embed=embed_bv, file=discord.File(io.BytesIO(img_bordure), filename="welcome.png"))
            await send_log(f"✅ Message de bienvenue envoyé pour {member.name}")
        except Exception as e:
            await send_log(f"⚠️ Erreur bienvenue : {e}")

        # Panneau de sélection des rôles (message visible par tous, mais seul le membre peut interagir)
        embed_select = discord.Embed(
            title="🔧 Configuration de ton profil",
            description=(
                "Bienvenue ! Pour accéder au serveur, choisis les options ci-dessous.\n\n"
                "**Genre**\n**Âge**\n**Statut créatif**"
            ),
            color=0x2b2d31  # gris foncé
        )
        view = RoleSelectView(member)
        msg = await canal_bienvenue.send(embed=embed_select, view=view)
        view.message = msg
        await send_log(f"📨 Panneau de sélection envoyé à {member.name} dans {canal_bienvenue.mention}")
    else:
        await send_log(f"❌ Salon de bienvenue introuvable (ID {ID_BIENVENUE})")

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
        try:
            img_bytes = await lire_image(FOND_AUREVOIR)
            img_bordure = ajouter_bordure(img_bytes)
            texte = f"Oh... **{member.display_name}**, un/une potentiel(le) dessinateur/rice, a quitté ce serveur, en espérant que tu deviendras un(e) artiste."
            embed = discord.Embed(title="👋 Au revoir...", description=texte, color=0x000000, timestamp=datetime.now())
            embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
            await canal.send(embed=embed, file=discord.File(io.BytesIO(img_bordure), filename="goodbye.png"))
            await send_log(f"✅ Message d'au revoir envoyé pour {member.name}")
        except Exception as e:
            await send_log(f"⚠️ Erreur au revoir : {e}")

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
    """Recrée les rôles manquants (Féminin, Masculin, etc.)"""
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
    # Créer les rôles manquants sur chaque serveur
    for guild in bot.guilds:
        await ensure_roles(guild)
    await setup_verification_reaction()
    await send_log("🚀 Bot démarré (panneau de sélection dans le serveur, rôles auto-créés)")

async def main():
    asyncio.create_task(start_http_server())
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ Token manquant")
        return
    await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())