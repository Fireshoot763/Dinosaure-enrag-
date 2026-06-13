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
    ("Féminin", discord.Colour.pink(), "♀️"),
    ("Masculin", discord.Colour.blue(), "♂️"),
    ("Majeur", discord.Colour.green(), "🔞"),
    ("Mineur", discord.Colour.gold(), "🧒"),
    ("Dessinateur", discord.Colour.purple(), "✏️"),
    ("Animateur", discord.Colour.orange(), "🎬")
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

# ------------------ MESSAGE UNIQUE AVEC RÉACTIONS ------------------
async def create_onboarding_message(guild):
    """Crée un message unique avec des réactions pour le choix des rôles."""
    channel = discord.utils.get(guild.text_channels, name="choix-roles")
    if not channel:
        await send_log("❌ Salon #choix-roles introuvable.")
        return False

    # Supprimer les anciens messages du bot
    async for message in channel.history(limit=200):
        if message.author == bot.user:
            await message.delete()

    embed = discord.Embed(
        title="🔧 Choisis tes rôles",
        description=(
            "Clique sur les réactions ci-dessous pour obtenir des rôles (optionnels) :\n\n"
            "♀️ – Féminin\n"
            "♂️ – Masculin\n"
            "🔞 – Majeur (18+)\n"
            "🧒 – Mineur\n"
            "✏️ – Dessinateur\n"
            "🎬 – Animateur\n"
            "🤐 – Rester anonyme (ne donne aucun rôle)\n\n"
            "Une fois tes choix faits (ou non), clique sur **✅** pour valider ton parcours."
        ),
        color=0x2b2d31
    )
    message = await channel.send(embed=embed)

    # Ajouter toutes les réactions
    emojis = ["♀️", "♂️", "🔞", "🧒", "✏️", "🎬", "🤐", "✅"]
    for emoji in emojis:
        await message.add_reaction(emoji)

    await send_log("✅ Message d'onboarding avec réactions créé.")
    return True

# ------------------ GESTION DES RÉACTIONS ------------------
async def assign_role(member, role_name):
    guild = member.guild
    role = discord.utils.get(guild.roles, name=role_name)
    if role:
        await member.add_roles(role)
        await send_log(f"➕ {member.name} a obtenu le rôle {role_name}")
        return True
    return False

async def remove_role(member, role_name):
    guild = member.guild
    role = discord.utils.get(guild.roles, name=role_name)
    if role and role in member.roles:
        await member.remove_roles(role)
        await send_log(f"➖ {member.name} a perdu le rôle {role_name}")

@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return

    # Vérifier que la réaction est dans le salon #choix-roles
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    channel = guild.get_channel(payload.channel_id)
    if not channel or channel.name != "choix-roles":
        return

    member = guild.get_member(payload.user_id)
    if not member:
        return

    # Vérifier que le membre a le rôle "Nouveau"
    new_role = guild.get_role(ROLE_NEW_ID)
    if not new_role or new_role not in member.roles:
        # L'utilisateur n'est pas en onboarding, on ignore
        return

    emoji = str(payload.emoji)
    # Gestion des rôles selon l'emoji
    if emoji == "♀️":
        await assign_role(member, "Féminin")
        await remove_role(member, "Masculin")
    elif emoji == "♂️":
        await assign_role(member, "Masculin")
        await remove_role(member, "Féminin")
    elif emoji == "🔞":
        await assign_role(member, "Majeur")
        await remove_role(member, "Mineur")
    elif emoji == "🧒":
        await assign_role(member, "Mineur")
        await remove_role(member, "Majeur")
    elif emoji == "✏️":
        await assign_role(member, "Dessinateur")
        await remove_role(member, "Animateur")
    elif emoji == "🎬":
        await assign_role(member, "Animateur")
        await remove_role(member, "Dessinateur")
    elif emoji == "🤐":
        # Anonyme : ne rien faire (juste un message de confirmation)
        await member.send("Tu as choisi de rester anonyme. Aucun rôle ne t'a été attribué.")
        await send_log(f"🤐 {member.name} a choisi l'anonymat.")
    elif emoji == "✅":
        # Validation : passage du rôle Nouveau à En attente
        verifying_role = discord.utils.get(guild.roles, name="En attente")
        if verifying_role:
            await member.remove_roles(new_role)
            await member.add_roles(verifying_role)
            await send_log(f"🔁 {member.name} a validé son onboarding → rôle 'En attente'")
            await member.send(
                f"✅ Parcours validé ! Rends-toi dans <#{RULES_CHANNEL_ID}> et réagis avec {VERIFICATION_EMOJI} pour accéder au serveur."
            )
    else:
        return

    # Retirer la réaction de l'utilisateur (pour éviter l'encombrement)
    try:
        msg = await channel.fetch_message(payload.message_id)
        await msg.remove_reaction(emoji, member)
    except:
        pass

# ------------------ VÉRIFICATION FINALE PAR RÉACTION DANS #règles ------------------
@bot.event
async def on_raw_reaction_add_rules(payload):
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

    # Retirer la réaction pour éviter les doublons
    try:
        channel = bot.get_channel(RULES_CHANNEL_ID)
        msg = await channel.fetch_message(payload.message_id)
        await msg.remove_reaction(VERIFICATION_EMOJI, member)
    except:
        pass

# On remplace l'ancien on_raw_reaction_add par les deux fonctions ci-dessus
# Pour éviter les conflits, on va les enregistrer séparément. Discord.py appelle tous les événements.
# Mais il faut éviter de dupliquer. Je vais fusionner dans un seul `on_raw_reaction_add` avec des conditions.

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
    await create_onboarding_message(ctx.guild)
    await ctx.send("✅ Message d'onboarding recréé.", ephemeral=True)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    await send_log(f"❌ Erreur commande {ctx.command}: {error}")

async def create_optional_roles(guild):
    for name, colour, _ in ROLES_TO_CREATE:
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
        await create_onboarding_message(guild)
    await send_log("🚀 Bot démarré avec système de réactions (plus robuste)")

async def main():
    asyncio.create_task(start_http_server())
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ Token manquant")
        return
    await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())