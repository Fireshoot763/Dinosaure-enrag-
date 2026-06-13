import discord
from discord.ext import commands
import os
import asyncio
from aiohttp import web
import time
from datetime import datetime

# ------------------ CONFIGURATION ------------------
# IDs des salons
ID_BIENVENUE = 1512009964988661861  # salon public de bienvenue (optionnel)
ID_AUREVOIR = 1512010175907631104
VIDEO_CHANNEL_ID = 1513174573632454817
LOG_CHANNEL_ID = 1512010693665099876
ONBOARDING_CHANNEL_ID = 1512009964988661861  # à remplacer par l'ID du salon #choix-roles (ou créer un nouveau)
RULES_CHANNEL_ID = 1511654306414198805       # salon #‼️règles‼️

# IDs des rôles
ROLE_NEW_ID = 1513799071029137499          # "Non vérifié" (sera utilisé comme rôle "Nouveau")
ROLE_VERIFYING_ID = 0                      # à créer : rôle "En attente" (donner ID)
ROLE_MEMBER_ID = 1512012606435491911       # "Membres"

AUTHORIZED_USER_ID = 1274426216413139007   # personne autorisée pour les vidéos

# Rôles optionnels (créés automatiquement si besoin)
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
    # Vérifier aussi les rôles système
    if not guild.get_role(ROLE_VERIFYING_ID):
        await send_log(f"⚠️ Rôle 'En attente' (ID {ROLE_VERIFYING_ID}) introuvable. Crée-le manuellement.")

# ------------------ VUE AVEC MENUS ET BOUTON VALIDER ------------------
class OnboardingView(discord.ui.View):
    def __init__(self, member: discord.Member):
        super().__init__(timeout=600)  # 10 minutes
        self.member = member
        self.gender = None
        self.age = None
        self.creator = None
        self.anonymous = False
        self.message = None

        # Menu Genre
        self.gender_menu = discord.ui.Select(
            placeholder="Genre (optionnel)",
            options=[
                discord.SelectOption(label="Féminin", value="Féminin", emoji="♀️"),
                discord.SelectOption(label="Masculin", value="Masculin", emoji="♂️"),
                discord.SelectOption(label="Anonyme", value="anonyme_gender", emoji="🤐")
            ]
        )
        self.gender_menu.callback = self.gender_callback
        self.add_item(self.gender_menu)

        # Menu Âge
        self.age_menu = discord.ui.Select(
            placeholder="Âge (optionnel)",
            options=[
                discord.SelectOption(label="Majeur (18+)", value="Majeur", emoji="🔞"),
                discord.SelectOption(label="Mineur (-18)", value="Mineur", emoji="🧒"),
                discord.SelectOption(label="Anonyme", value="anonyme_age", emoji="🤐")
            ]
        )
        self.age_menu.callback = self.age_callback
        self.add_item(self.age_menu)

        # Menu Statut
        self.creator_menu = discord.ui.Select(
            placeholder="Statut créatif (optionnel)",
            options=[
                discord.SelectOption(label="Dessinateur", value="Dessinateur", emoji="✏️"),
                discord.SelectOption(label="Animateur", value="Animateur", emoji="🎬"),
                discord.SelectOption(label="Anonyme", value="anonyme_creator", emoji="🤐")
            ]
        )
        self.creator_menu.callback = self.creator_callback
        self.add_item(self.creator_menu)

        # Bouton Valider
        validate = discord.ui.Button(label="✅ Valider", style=discord.ButtonStyle.success, custom_id="validate")
        validate.callback = self.validate_callback
        self.add_item(validate)

    async def gender_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.member.id:
            return await interaction.response.send_message("Ce panneau ne vous est pas destiné.", ephemeral=True)
        value = self.gender_menu.values[0]
        if value == "anonyme_gender":
            self.gender = None
            await interaction.response.send_message("✅ Genre anonyme (aucun rôle attribué)", ephemeral=True)
        else:
            self.gender = value
            await self.assign_role(interaction, value, "Féminin", "Masculin")
        self.gender_menu.disabled = True
        await interaction.followup.edit_message(interaction.message.id, view=self)

    async def age_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.member.id:
            return await interaction.response.send_message("Ce panneau ne vous est pas destiné.", ephemeral=True)
        value = self.age_menu.values[0]
        if value == "anonyme_age":
            self.age = None
            await interaction.response.send_message("✅ Âge anonyme (aucun rôle attribué)", ephemeral=True)
        else:
            self.age = value
            await self.assign_role(interaction, value, "Majeur", "Mineur")
        self.age_menu.disabled = True
        await interaction.followup.edit_message(interaction.message.id, view=self)

    async def creator_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.member.id:
            return await interaction.response.send_message("Ce panneau ne vous est pas destiné.", ephemeral=True)
        value = self.creator_menu.values[0]
        if value == "anonyme_creator":
            self.creator = None
            await interaction.response.send_message("✅ Statut anonyme (aucun rôle attribué)", ephemeral=True)
        else:
            self.creator = value
            await self.assign_role(interaction, value, "Dessinateur", "Animateur")
        self.creator_menu.disabled = True
        await interaction.followup.edit_message(interaction.message.id, view=self)

    async def assign_role(self, interaction, chosen, role1, role2):
        guild = interaction.guild
        role = discord.utils.get(guild.roles, name=chosen)
        opposite = discord.utils.get(guild.roles, name=role1 if chosen == role2 else role2)
        if role:
            await interaction.user.add_roles(role)
            await send_log(f"➕ {interaction.user.name} a choisi {chosen}")
        if opposite and opposite in interaction.user.roles:
            await interaction.user.remove_roles(opposite)

    async def validate_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.member.id:
            return await interaction.response.send_message("Ce panneau ne vous est pas destiné.", ephemeral=True)
        # Désactiver tous les composants
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

        # Changer les rôles : retirer "Nouveau" (ROLE_NEW) et ajouter "En attente" (ROLE_VERIFYING)
        guild = interaction.guild
        new_role = guild.get_role(ROLE_NEW_ID)
        verifying_role = guild.get_role(ROLE_VERIFYING_ID)
        if new_role:
            await interaction.user.remove_roles(new_role)
        if verifying_role:
            await interaction.user.add_roles(verifying_role)
        await send_log(f"🔁 {interaction.user.name} a validé son onboarding → rôle 'En attente'")

        # Envoyer un message de confirmation (éphémère)
        await interaction.followup.send(
            f"✅ Parcours validé ! Rends-toi maintenant dans le salon <#{RULES_CHANNEL_ID}> "
            f"et réagis avec {VERIFICATION_EMOJI} pour accéder au serveur.",
            ephemeral=True
        )
        self.stop()

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass

# ------------------ VÉRIFICATION PAR RÉACTION (salon règles) ------------------
@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return
    if payload.channel_id != RULES_CHANNEL_ID or str(payload.emoji) != VERIFICATION_EMOJI:
        return

    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    member = guild.get_member(payload.user_id)
    if not member:
        return

    # Vérifier que le membre a le rôle "En attente" (et non "Nouveau")
    verifying_role = guild.get_role(ROLE_VERIFYING_ID)
    if not verifying_role or verifying_role not in member.roles:
        await send_log(f"⚠️ {member.name} a réagi aux règles sans avoir le bon rôle.")
        return

    # Donner le rôle Membre et retirer En attente
    member_role = guild.get_role(ROLE_MEMBER_ID)
    if member_role:
        await member.add_roles(member_role)
        await send_log(f"✅ {member.name} a réagi aux règles → devient Membre.")
    if verifying_role:
        await member.remove_roles(verifying_role)

    # Retirer la réaction pour éviter les doublons
    try:
        channel = bot.get_channel(RULES_CHANNEL_ID)
        msg = await channel.fetch_message(payload.message_id)
        await msg.remove_reaction(VERIFICATION_EMOJI, member)
    except:
        pass

# ------------------ BIENVENUE (arrivée) ------------------
@bot.event
async def on_member_join(member):
    now = time.time()
    if member.id in recent_joins and now - recent_joins[member.id] < SPAM_SECONDS:
        await send_log(f"🚫 Ignoré doublon arrivée de {member.name}")
        return
    recent_joins[member.id] = now

    # Ajouter le rôle "Nouveau"
    new_role = member.guild.get_role(ROLE_NEW_ID)
    if new_role:
        try:
            await member.add_roles(new_role)
            await send_log(f"🔒 Rôle 'Nouveau' ajouté à {member.name}")
        except Exception as e:
            await send_log(f"❌ Erreur ajout rôle Nouveau : {e}")
    else:
        await send_log(f"❌ Rôle Nouveau introuvable (ID {ROLE_NEW_ID})")

    # Message public de bienvenue (dans un salon public si tu veux)
    canal_bienvenue = bot.get_channel(ID_BIENVENUE)
    if canal_bienvenue:
        embed_bv = discord.Embed(
            title="🎨 Bienvenue !",
            description=f"Oh ! **{member.display_name}** a rejoint le serveur !",
            color=0x000000,
            timestamp=datetime.now()
        )
        if member.avatar:
            embed_bv.set_thumbnail(url=member.avatar.url)
        await canal_bienvenue.send(embed=embed_bv)

    # Envoyer le panneau d'onboarding dans le salon dédié
    onboarding_channel = bot.get_channel(ONBOARDING_CHANNEL_ID)
    if not onboarding_channel:
        await send_log(f"❌ Salon d'onboarding introuvable (ID {ONBOARDING_CHANNEL_ID})")
        return

    embed = discord.Embed(
        title="🔧 Configuration de ton profil",
        description=(
            "Bienvenue ! Choisis les options ci-dessous (ou reste anonyme).\n"
            "Une fois que tu as fait tes choix (ou non), clique sur **Valider**.\n\n"
            "*Tu pourras modifier tes rôles plus tard avec la commande `/reroll`.*"
        ),
        color=0x2b2d31
    )
    view = OnboardingView(member)
    msg = await onboarding_channel.send(embed=embed, view=view)
    view.message = msg
    await send_log(f"📨 Panneau d'onboarding envoyé à {member.name} dans {onboarding_channel.mention}")

# ------------------ COMMANDE POUR MODIFIER LES RÔLES (optionnelle) ------------------
@bot.command()
@commands.has_any_role(ROLE_MEMBER_ID, ROLE_VERIFYING_ID)  # accessible aux membres déjà vérifiés ou en attente
async def reroll(ctx):
    """Permet de modifier tes rôles (réouvre le salon d'onboarding)."""
    # Pour simplifier, on pourrait réattribuer le rôle "Nouveau" temporairement, mais cela nécessite de bien gérer les permissions.
    # On va plutôt envoyer un message privé avec les menus (plus simple).
    # Je laisse cette commande en suggestion ; tu pourras l'implémenter plus tard.
    await ctx.send("Commande en développement. Pour l'instant, contacte un admin.")

# ------------------ AUTRES FONCTIONS (au revoir, vidéos, ping) ------------------
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
            description=f"Oh... {member.display_name} a quitté le serveur.",
            color=0x000000,
            timestamp=datetime.now()
        )
        await canal.send(embed=embed)

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

@bot.command()
async def ping(ctx):
    user_id = ctx.author.id
    now = time.time()
    if user_id in command_cooldown and now - command_cooldown[user_id] < COOLDOWN_SECONDS:
        await ctx.send("⏳ Attends un peu...")
        return
    command_cooldown[user_id] = now
    await ctx.send("Pong !")
    await send_log(f"!ping par {ctx.author.name}")

@bot.tree.command(name="ping", description="Vérifie la latence")
async def slash_ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong ! {round(bot.latency*1000)}ms")

@bot.command()
@commands.has_permissions(administrator=True)
async def setup_roles(ctx):
    await ensure_roles(ctx.guild)
    await ctx.send("✅ Rôles optionnels créés.", ephemeral=True)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    await send_log(f"❌ Erreur commande {ctx.command}: {error}")

@bot.event
async def on_ready():
    print(f"✅ Bot connecté : {bot.user}")
    await bot.tree.sync()
    print("✅ Commandes slash synchronisées")
    for guild in bot.guilds:
        await ensure_roles(guild)
    await send_log("🚀 Bot démarré (onboarding avec salon dédié)")

async def main():
    asyncio.create_task(start_http_server())
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ Token manquant")
        return
    await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())