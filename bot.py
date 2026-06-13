import discord
from discord.ext import commands
import os
import asyncio
from aiohttp import web
import time
from datetime import datetime  # ✅ Correction : import manquant

# ------------------ CONFIGURATION ------------------
ID_BIENVENUE = 1512009964988661861
ID_AUREVOIR = 1512010175907631104
VIDEO_CHANNEL_ID = 1513174573632454817
LOG_CHANNEL_ID = 1512010693665099876
VERIFICATION_CHANNEL_ID = 1511654306414198805   # salon #‼️règles‼️

UNVERIFIED_ROLE_ID = 1513799071029137499        # "Non vérifié"
MEMBER_ROLE_ID = 1512012606435491911            # "Membres"

AUTHORIZED_USER_ID = 1274426216413139007        # personne autorisée pour les vidéos

# Rôles pour la sélection facultative (création auto)
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

# ------------------ VUE À BOUTONS POUR LA SÉLECTION (MP, facultative) ------------------
class RoleSelectView(discord.ui.View):
    def __init__(self, member: discord.Member):
        super().__init__(timeout=300)
        self.member = member
        self.choices = {"gender": None, "age": None, "creator": None}
        self.message = None

    @discord.ui.button(label="Féminin", style=discord.ButtonStyle.secondary, emoji="♀️", custom_id="gender_female")
    async def gender_female(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_choice(interaction, "gender", "Féminin", "Masculin", button)

    @discord.ui.button(label="Masculin", style=discord.ButtonStyle.secondary, emoji="♂️", custom_id="gender_male")
    async def gender_male(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_choice(interaction, "gender", "Masculin", "Féminin", button)

    @discord.ui.button(label="Majeur", style=discord.ButtonStyle.secondary, emoji="🔞", custom_id="age_adult")
    async def age_adult(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_choice(interaction, "age", "Majeur", "Mineur", button)

    @discord.ui.button(label="Mineur", style=discord.ButtonStyle.secondary, emoji="🧒", custom_id="age_minor")
    async def age_minor(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_choice(interaction, "age", "Mineur", "Majeur", button)

    @discord.ui.button(label="Dessinateur", style=discord.ButtonStyle.secondary, emoji="✏️", custom_id="creator_drawer")
    async def creator_drawer(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_choice(interaction, "creator", "Dessinateur", "Animateur", button)

    @discord.ui.button(label="Animateur", style=discord.ButtonStyle.secondary, emoji="🎬", custom_id="creator_animator")
    async def creator_animator(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_choice(interaction, "creator", "Animateur", "Dessinateur", button)

    async def handle_choice(self, interaction: discord.Interaction, category: str, chosen: str, opposite: str, button: discord.ui.Button):
        if interaction.user.id != self.member.id:
            return await interaction.response.send_message("Ce panneau ne vous est pas destiné.", ephemeral=True)
        
        guild = interaction.guild
        role_chosen = discord.utils.get(guild.roles, name=chosen)
        role_opposite = discord.utils.get(guild.roles, name=opposite)
        
        if not role_chosen:
            await interaction.response.send_message(f"❌ Le rôle {chosen} est introuvable. Contacte un admin.", ephemeral=True)
            return
        
        await interaction.user.add_roles(role_chosen)
        await send_log(f"➕ {interaction.user.name} a choisi {chosen}")
        if role_opposite and role_opposite in interaction.user.roles:
            await interaction.user.remove_roles(role_opposite)
        
        self.choices[category] = chosen
        button.disabled = True
        for child in self.children:
            if child.custom_id == f"{category}_{opposite.lower()}":
                child.disabled = True
                break
        
        await interaction.response.edit_message(view=self)
        
        if all(self.choices.values()):
            # Optionnel : retirer le rôle Non vérifié (mais pas obligatoire)
            unverified_role = guild.get_role(UNVERIFIED_ROLE_ID)
            if unverified_role and unverified_role in interaction.user.roles:
                await interaction.user.remove_roles(unverified_role)
                await send_log(f"🔓 {interaction.user.name} a terminé la sélection, rôle Non vérifié retiré.")
            
            for child in self.children:
                child.disabled = True
            await self.message.edit(view=self)
            
            embed_success = discord.Embed(
                title="✅ Rôles sélectionnés !",
                description=f"Tu peux maintenant réagir avec {VERIFICATION_EMOJI} dans le salon <#{VERIFICATION_CHANNEL_ID}> pour accéder au serveur (même si tu n'as pas encore choisi, ce n'est pas obligatoire).",
                color=0x00ff00
            )
            await interaction.followup.send(embed=embed_success, ephemeral=True)
            self.stop()

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass

# ------------------ VÉRIFICATION PAR RÉACTION (ACCÈS DIRECT, SANS CONDITION) ------------------
@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return
    # Vérifie le salon et l'émoji
    if payload.channel_id != VERIFICATION_CHANNEL_ID or str(payload.emoji) != VERIFICATION_EMOJI:
        return
    
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    member = guild.get_member(payload.user_id)
    if not member:
        return
    
    # Donner le rôle Membre (et retirer Non vérifié si présent)
    member_role = guild.get_role(MEMBER_ROLE_ID)
    if member_role:
        await member.add_roles(member_role)
        await send_log(f"✅ {member.name} a réagi aux règles et est devenu Membre.")
    
    unverified_role = guild.get_role(UNVERIFIED_ROLE_ID)
    if unverified_role and unverified_role in member.roles:
        await member.remove_roles(unverified_role)
        await send_log(f"🔓 Rôle 'Non vérifié' retiré à {member.name} (vérification effectuée).")
    
    # Retirer la réaction pour éviter les doublons (optionnel)
    try:
        channel = bot.get_channel(VERIFICATION_CHANNEL_ID)
        msg = await channel.fetch_message(payload.message_id)
        await msg.remove_reaction(VERIFICATION_EMOJI, member)
    except:
        pass

# ------------------ BIENVENUE ------------------
@bot.event
async def on_member_join(member):
    now = time.time()
    if member.id in recent_joins and now - recent_joins[member.id] < SPAM_SECONDS:
        await send_log(f"🚫 Ignoré doublon arrivée de {member.name}")
        return
    recent_joins[member.id] = now

    unverified_role = member.guild.get_role(UNVERIFIED_ROLE_ID)
    if unverified_role:
        try:
            await member.add_roles(unverified_role)
            await send_log(f"🔒 Rôle 'Non vérifié' ajouté à {member.name}")
        except Exception as e:
            await send_log(f"❌ Erreur ajout rôle Non vérifié : {e}")
    else:
        await send_log(f"❌ Rôle Non vérifié (ID {UNVERIFIED_ROLE_ID}) introuvable.")

    # Message public de bienvenue (corrigé avec datetime)
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
    else:
        await send_log(f"❌ Salon bienvenue introuvable (ID {ID_BIENVENUE})")

    # Panneau de sélection facultatif en MP (sans obligation)
    try:
        embed_select = discord.Embed(
            title="🔧 Configuration optionnelle",
            description="Bienvenue ! Tu peux choisir des rôles ci-dessous (ce n'est pas obligatoire).\n\n**Genre**\n**Âge**\n**Statut créatif**",
            color=0x2b2d31
        )
        view = RoleSelectView(member)
        msg = await member.send(embed=embed_select, view=view)
        view.message = msg
        await send_log(f"📨 Panneau de sélection (facultatif) envoyé en MP à {member.name}")
    except discord.Forbidden:
        await send_log(f"⚠️ Impossible d'envoyer un MP à {member.name} (DM fermés).")
    except Exception as e:
        await send_log(f"❌ Erreur envoi MP : {e}")

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
    await send_log("🚀 Bot démarré (vérification par réaction sans condition préalable)")

async def main():
    asyncio.create_task(start_http_server())
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ Token manquant")
        return
    await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())