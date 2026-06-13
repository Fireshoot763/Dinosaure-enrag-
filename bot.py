import discord
from discord.ext import commands
import os
import asyncio
from aiohttp import web
import time
from datetime import datetime

# ------------------ CONFIGURATION ------------------
WELCOME_CHANNEL_ID = 1512009964988661861
GOODBYE_CHANNEL_ID = 1512010175907631104
VIDEO_CHANNEL_ID = 1513174573632454817
LOG_CHANNEL_ID = 1512010693665099876
RULES_CHANNEL_ID = 1511654306414198805

ROLE_NEW_ID = 1513799071029137499
ROLE_MEMBER_ID = 1512012606435491911

AUTHORIZED_USER_ID = 1274426216413139007

ROLES_TO_CREATE = [
    ("Féminin", discord.Colour.pink()),
    ("Masculin", discord.Colour.blue()),
    ("Majeur", discord.Colour.green()),
    ("Mineur", discord.Colour.gold()),
    ("Dessinateur", discord.Colour.purple()),
    ("Animateur", discord.Colour.orange())
]

command_cooldown = {}
COOLDOWN_SECONDS = 5
recent_joins = {}
recent_leaves = {}
SPAM_SECONDS = 10
VERIFICATION_EMOJI = "✅"

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
        print(f"Log : {message}")

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

# ------------------ GESTION DES PERMISSIONS ------------------
async def fix_channel_permissions(guild):
    new_role = guild.get_role(ROLE_NEW_ID)
    member_role = guild.get_role(ROLE_MEMBER_ID)
    verifying_role = discord.utils.get(guild.roles, name="En attente")
    if not new_role or not member_role or not verifying_role:
        await send_log("❌ Rôles manquants pour configurer les permissions.")
        return

    onboarding_channel = discord.utils.get(guild.text_channels, name="choix-roles")
    if onboarding_channel:
        await onboarding_channel.set_permissions(guild.default_role, view_channel=False)
        await onboarding_channel.set_permissions(new_role, view_channel=True, send_messages=True, read_messages=True)
        await onboarding_channel.set_permissions(verifying_role, view_channel=False)
        await onboarding_channel.set_permissions(member_role, view_channel=False)
        await send_log("✅ Permissions #choix-roles OK")

    rules_channel = guild.get_channel(RULES_CHANNEL_ID)
    if rules_channel:
        await rules_channel.set_permissions(guild.default_role, view_channel=False)
        await rules_channel.set_permissions(new_role, view_channel=False)
        await rules_channel.set_permissions(verifying_role, view_channel=True, send_messages=True, read_messages=True)
        await rules_channel.set_permissions(member_role, view_channel=True)
        await send_log("✅ Permissions #règles OK")

    for channel in guild.channels:
        if channel.id == (onboarding_channel.id if onboarding_channel else None) or channel.id == rules_channel.id:
            continue
        await channel.set_permissions(guild.default_role, view_channel=False)
        await channel.set_permissions(new_role, view_channel=False)
        await channel.set_permissions(verifying_role, view_channel=False)
        await channel.set_permissions(member_role, view_channel=True)
        if isinstance(channel, discord.VoiceChannel):
            await channel.set_permissions(member_role, connect=True, speak=True)
        if isinstance(channel, discord.CategoryChannel):
            await send_log(f"✅ Catégorie {channel.name} configurée")
    await send_log("✅ Permissions mises à jour")

# ------------------ CRÉATION AUTO DES RÔLES ET SALON ------------------
async def ensure_onboarding(guild):
    verifying_role = discord.utils.get(guild.roles, name="En attente")
    if not verifying_role:
        try:
            verifying_role = await guild.create_role(name="En attente", colour=discord.Colour.greyple(), reason="Création auto onboarding")
            await send_log(f"✅ Rôle 'En attente' créé (ID: {verifying_role.id})")
        except Exception as e:
            await send_log(f"❌ Erreur création rôle 'En attente' : {e}")
            return None, None

    onboarding_channel = discord.utils.get(guild.text_channels, name="choix-roles")
    if not onboarding_channel:
        new_role = guild.get_role(ROLE_NEW_ID)
        if not new_role:
            await send_log(f"❌ Rôle 'Nouveau' (ID {ROLE_NEW_ID}) introuvable.")
            return verifying_role, None
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            new_role: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True)
        }
        try:
            onboarding_channel = await guild.create_text_channel("choix-roles", overwrites=overwrites)
            await send_log(f"✅ Salon 'choix-roles' créé (ID: {onboarding_channel.id})")
        except Exception as e:
            await send_log(f"❌ Erreur création salon : {e}")
            return verifying_role, None
    else:
        await send_log(f"ℹ️ Salon 'choix-roles' déjà existant (ID: {onboarding_channel.id})")
    return verifying_role, onboarding_channel

# ------------------ VUE PERSISTANTE (MESSAGE UNIQUE) ------------------
class OnboardingView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

        self.gender_menu = discord.ui.Select(
            placeholder="Genre (optionnel)",
            options=[
                discord.SelectOption(label="Féminin", value="Féminin", emoji="♀️"),
                discord.SelectOption(label="Masculin", value="Masculin", emoji="♂️")
            ]
        )
        self.gender_menu.callback = self.gender_callback
        self.add_item(self.gender_menu)

        self.age_menu = discord.ui.Select(
            placeholder="Âge (optionnel)",
            options=[
                discord.SelectOption(label="Majeur (18+)", value="Majeur", emoji="🔞"),
                discord.SelectOption(label="Mineur (-18)", value="Mineur", emoji="🧒")
            ]
        )
        self.age_menu.callback = self.age_callback
        self.add_item(self.age_menu)

        self.creator_menu = discord.ui.Select(
            placeholder="Statut (optionnel)",
            options=[
                discord.SelectOption(label="Dessinateur", value="Dessinateur", emoji="✏️"),
                discord.SelectOption(label="Animateur", value="Animateur", emoji="🎬")
            ]
        )
        self.creator_menu.callback = self.creator_callback
        self.add_item(self.creator_menu)

        self.anonymous = discord.ui.Button(label="🤐 Rester anonyme", style=discord.ButtonStyle.secondary, custom_id="anonymous")
        self.anonymous.callback = self.anonymous_callback
        self.add_item(self.anonymous)

        self.validate = discord.ui.Button(label="✅ Valider", style=discord.ButtonStyle.success, custom_id="validate")
        self.validate.callback = self.validate_callback
        self.add_item(self.validate)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        new_role = interaction.guild.get_role(ROLE_NEW_ID)
        if not new_role or new_role not in interaction.user.roles:
            await interaction.response.send_message("Tu n'es pas autorisé à utiliser ce panneau (tu as déjà validé ou tu n'es pas nouveau).", ephemeral=True)
            return False
        return True

    async def gender_callback(self, interaction: discord.Interaction):
        value = self.gender_menu.values[0]
        await self.assign_role(interaction, value, "Féminin", "Masculin")
        await interaction.response.send_message(f"✅ Genre {value} enregistré.", ephemeral=True)

    async def age_callback(self, interaction: discord.Interaction):
        value = self.age_menu.values[0]
        await self.assign_role(interaction, value, "Majeur", "Mineur")
        await interaction.response.send_message(f"✅ Âge {value} enregistré.", ephemeral=True)

    async def creator_callback(self, interaction: discord.Interaction):
        value = self.creator_menu.values[0]
        await self.assign_role(interaction, value, "Dessinateur", "Animateur")
        await interaction.response.send_message(f"✅ Statut {value} enregistré.", ephemeral=True)

    async def assign_role(self, interaction, chosen, role1, role2):
        role = discord.utils.get(interaction.guild.roles, name=chosen)
        opposite = discord.utils.get(interaction.guild.roles, name=role1 if chosen == role2 else role2)
        if role:
            await interaction.user.add_roles(role)
            await send_log(f"➕ {interaction.user.name} a choisi {chosen}")
        if opposite and opposite in interaction.user.roles:
            await interaction.user.remove_roles(opposite)

    async def finalize(self, interaction: discord.Interaction):
        new_role = interaction.guild.get_role(ROLE_NEW_ID)
        verifying_role = discord.utils.get(interaction.guild.roles, name="En attente")
        if new_role:
            await interaction.user.remove_roles(new_role)
        if verifying_role:
            await interaction.user.add_roles(verifying_role)
        await send_log(f"🔁 {interaction.user.name} a validé → rôle 'En attente'")
        await interaction.response.send_message(
            f"✅ Parcours validé ! Rends-toi dans <#{RULES_CHANNEL_ID}> et réagis avec {VERIFICATION_EMOJI} pour accéder au serveur.",
            ephemeral=True
        )

    async def validate_callback(self, interaction: discord.Interaction):
        await self.finalize(interaction)

    async def anonymous_callback(self, interaction: discord.Interaction):
        await self.finalize(interaction)

# ------------------ MESSAGE D'ONBOARDING UNIQUE ------------------
async def create_onboarding_message(guild):
    """Supprime tous les anciens messages du bot dans #choix-roles et en crée un nouveau."""
    channel = discord.utils.get(guild.text_channels, name="choix-roles")
    if not channel:
        await send_log("❌ Salon #choix-roles introuvable.")
        return False
    # Nettoyage
    async for message in channel.history(limit=200):
        if message.author == bot.user:
            await message.delete()
    # Création
    embed = discord.Embed(
        title="🔧 Configuration de ton profil",
        description=(
            "Bienvenue ! Choisis des rôles ci-dessous (ou clique sur **Rester anonyme**).\n"
            "Une fois tes choix faits (ou non), clique sur **Valider**.\n\n"
            "*Tu pourras modifier tes rôles plus tard.*"
        ),
        color=0x2b2d31
    )
    view = OnboardingView()
    await channel.send(embed=embed, view=view)
    await send_log("✅ Message d'onboarding unique créé (anciens supprimés).")
    return True

# ------------------ VÉRIFICATION PAR RÉACTION ------------------
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

    verifying_role = discord.utils.get(guild.roles, name="En attente")
    if not verifying_role or verifying_role not in member.roles:
        await send_log(f"⚠️ {member.name} a réagi sans le rôle 'En attente'.")
        return

    member_role = guild.get_role(ROLE_MEMBER_ID)
    if member_role:
        await member.add_roles(member_role)
        await send_log(f"✅ {member.name} a réagi → devient Membre.")
    if verifying_role:
        await member.remove_roles(verifying_role)

    try:
        channel = bot.get_channel(RULES_CHANNEL_ID)
        msg = await channel.fetch_message(payload.message_id)
        await msg.remove_reaction(VERIFICATION_EMOJI, member)
    except:
        pass

# ------------------ ARRIVÉE D'UN MEMBRE ------------------
@bot.event
async def on_member_join(member):
    now = time.time()
    if member.id in recent_joins and now - recent_joins.get(member.id, 0) < SPAM_SECONDS:
        await send_log(f"🚫 Ignoré doublon arrivée de {member.name}")
        return
    recent_joins[member.id] = now

    new_role = member.guild.get_role(ROLE_NEW_ID)
    if new_role:
        try:
            await member.add_roles(new_role)
            await send_log(f"🔒 Rôle 'Nouveau' ajouté à {member.name}")
        except Exception as e:
            await send_log(f"❌ Erreur ajout rôle Nouveau : {e}")
    else:
        await send_log(f"❌ Rôle 'Nouveau' (ID {ROLE_NEW_ID}) introuvable.")

    welcome_channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if welcome_channel:
        embed = discord.Embed(
            title="🎨 Bienvenue !",
            description=f"Oh ! **{member.display_name}** a rejoint le serveur !",
            color=0x000000,
            timestamp=datetime.now()
        )
        if member.avatar:
            embed.set_thumbnail(url=member.avatar.url)
        await welcome_channel.send(embed=embed)

    # Pas besoin d'envoyer de nouveau message d'onboarding : il existe déjà

# ------------------ AUTRES ÉVÉNEMENTS ------------------
@bot.event
async def on_member_remove(member):
    now = time.time()
    if member.id in recent_leaves and now - recent_leaves.get(member.id, 0) < SPAM_SECONDS:
        await send_log(f"🚫 Ignoré doublon départ de {member.name}")
        return
    recent_leaves[member.id] = now
    channel = bot.get_channel(GOODBYE_CHANNEL_ID)
    if channel:
        embed = discord.Embed(
            title="👋 Au revoir...",
            description=f"Oh... {member.display_name} a quitté le serveur.",
            color=0x000000,
            timestamp=datetime.now()
        )
        await channel.send(embed=embed)

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
    if user_id in command_cooldown and now - command_cooldown.get(user_id, 0) < COOLDOWN_SECONDS:
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
    await ensure_onboarding(ctx.guild)
    await ctx.send("✅ Éléments d'onboarding vérifiés/créés.", ephemeral=True)

@bot.command()
@commands.has_permissions(administrator=True)
async def setup_perms(ctx):
    await ensure_onboarding(ctx.guild)
    await fix_channel_permissions(ctx.guild)
    await ctx.send("✅ Permissions des salons et catégories mises à jour.", ephemeral=True)

@bot.command()
@commands.has_permissions(administrator=True)
async def create_onboarding_message(ctx):
    """Recrée le message d'onboarding unique (nettoyage + nouveau)."""
    await create_onboarding_message(ctx.guild)
    await ctx.send("✅ Message d'onboarding recréé.", ephemeral=True)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    await send_log(f"❌ Erreur commande {ctx.command}: {error}")

async def create_optional_roles(guild):
    for name, colour in ROLES_TO_CREATE:
        if not discord.utils.get(guild.roles, name=name):
            try:
                await guild.create_role(name=name, colour=colour, reason="Création auto")
                await send_log(f"✅ Rôle optionnel '{name}' créé.")
            except Exception as e:
                await send_log(f"❌ Erreur création rôle {name} : {e}")

@bot.event
async def on_ready():
    print(f"✅ Bot connecté : {bot.user}")
    await bot.tree.sync()
    print("✅ Commandes slash synchronisées")
    for guild in bot.guilds:
        await create_optional_roles(guild)
        await ensure_onboarding(guild)
        await fix_channel_permissions(guild)
        await create_onboarding_message(guild)   # <-- force la recréation du message interactif
    await send_log("🚀 Bot redémarré avec message d'onboarding unique et interactif")

async def main():
    asyncio.create_task(start_http_server())
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ Token manquant")
        return
    await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())