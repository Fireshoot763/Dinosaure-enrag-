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
# IDs des salons
ID_BIENVENUE = 1512009964988661861
ID_AUREVOIR = 1512010175907631104
VIDEO_CHANNEL_ID = 1513174573632454817
LOG_CHANNEL_ID = 1512010693665099876
VERIFICATION_CHANNEL_ID = 1511654306414198805   # salon #‼️règles‼️

# IDs des rôles
UNVERIFIED_ROLE_ID = 1513799071029137499        # rôle "Non vérifié"
MEMBER_ROLE_ID = 1512012606435491911            # rôle "Membres"

# ID de la personne autorisée pour les vidéos
AUTHORIZED_USER_ID = 1274426216413139007

# Images de fond
FOND_BIENVENUE = "IMG_1299.png"
FOND_AUREVOIR = "IMG_1319.png"

# Anti-spam commandes
command_cooldown = {}
COOLDOWN_SECONDS = 5

# Anti-spam pour les événements join/leave
recent_joins = {}
recent_leaves = {}
SPAM_SECONDS = 10

# Émoji de vérification
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

# ------------------ SYSTÈME DE VÉRIFICATION ------------------
async def setup_verification_message():
    """Crée ou recycle le message de vérification dans le salon #règles."""
    channel = bot.get_channel(VERIFICATION_CHANNEL_ID)
    if not channel:
        print("Salon de vérification introuvable.")
        return

    # Supprimer les anciens messages du bot dans ce salon
    async for message in channel.history(limit=100):
        if message.author == bot.user:
            await message.delete()

    # Envoyer le nouveau message
    embed = discord.Embed(
        title="🔐 Vérification requise",
        description=(
            "Bienvenue sur le serveur ! Pour accéder aux salons, vous devez accepter les règles.\n\n"
            f"Réagissez avec {VERIFICATION_EMOJI} pour être vérifié."
        ),
        color=discord.Color.blue()
    )
    msg = await channel.send(embed=embed)
    await msg.add_reaction(VERIFICATION_EMOJI)
    print("Message de vérification créé.")
    return msg

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.user_id == bot.user.id:
        return

    # Vérifier que c'est dans le bon salon et la bonne réaction
    if payload.channel_id != VERIFICATION_CHANNEL_ID:
        return
    if str(payload.emoji) != VERIFICATION_EMOJI:
        return

    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    member = guild.get_member(payload.user_id)
    if not member:
        return

    unverified_role = guild.get_role(UNVERIFIED_ROLE_ID)
    member_role = guild.get_role(MEMBER_ROLE_ID)
    if not unverified_role or not member_role:
        await send_log("❌ Rôles de vérification introuvables.")
        return

    # Échanger les rôles
    await member.add_roles(member_role)
    await member.remove_roles(unverified_role)
    await send_log(f"✅ {member.name} a été vérifié et a reçu le rôle Membre.")

    # Retirer la réaction pour éviter de multiples validations
    try:
        channel = bot.get_channel(VERIFICATION_CHANNEL_ID)
        msg = await channel.fetch_message(payload.message_id)
        await msg.remove_reaction(VERIFICATION_EMOJI, member)
    except:
        pass

# ------------------ BIENVENUE (MP + rôle non vérifié) ------------------
@bot.event
async def on_member_join(member):
    # Anti-spam
    now = time.time()
    if member.id in recent_joins and now - recent_joins[member.id] < SPAM_SECONDS:
        await send_log(f"🚫 Ignoré doublon arrivée de {member.name}")
        return
    recent_joins[member.id] = now

    # 1. Envoyer un message privé au nouveau membre
    try:
        mp_message = (
            "Salut ! Pour pouvoir interagir avec le serveur, tu devras réagir avec ✅ "
            f"dans le salon <#{VERIFICATION_CHANNEL_ID}> (règles)."
        )
        await member.send(mp_message)
        await send_log(f"📨 MP envoyé à {member.name} pour la vérification.")
    except discord.Forbidden:
        await send_log(f"⚠️ Impossible d'envoyer un MP à {member.name} (bloqué).")

    # 2. Ajouter le rôle "Non vérifié"
    unverified_role = member.guild.get_role(UNVERIFIED_ROLE_ID)
    if unverified_role:
        await member.add_roles(unverified_role)
        await send_log(f"🔒 Rôle 'Non vérifié' ajouté à {member.name}")
    else:
        await send_log("❌ Rôle 'Non vérifié' introuvable. La vérification ne fonctionnera pas.")

    # 3. Envoyer le message de bienvenue classique dans le salon dédié
    canal = bot.get_channel(ID_BIENVENUE)
    if canal:
        try:
            img_bytes = await lire_image(FOND_BIENVENUE)
            img_bordure = ajouter_bordure(img_bytes)
            texte = (f"Oh ! **{member.display_name}** est un/une potentiel(le) dessinateur/rice et a rejoint ce serveur, "
                     f"bonne visite !")
            embed = discord.Embed(title="🎨 Bienvenue !", description=texte, color=0x000000, timestamp=datetime.now())
            embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
            await canal.send(embed=embed, file=discord.File(io.BytesIO(img_bordure), filename="welcome.png"))
            await send_log(f"✅ Message de bienvenue envoyé pour {member.name}")
        except Exception as e:
            await send_log(f"⚠️ Erreur bienvenue pour {member.name} : {e}")
    else:
        await send_log("❌ Salon de bienvenue introuvable.")

# ------------------ AU REVOIR (inchangé) ------------------
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
            texte = (f"Oh... **{member.display_name}**, un/une potentiel(le) dessinateur/rice, a quitté ce serveur, "
                     f"en espérant que tu deviendras un(e) artiste.")
            embed = discord.Embed(title="👋 Au revoir...", description=texte, color=0x000000, timestamp=datetime.now())
            embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
            await canal.send(embed=embed, file=discord.File(io.BytesIO(img_bordure), filename="goodbye.png"))
            await send_log(f"✅ Message d'au revoir envoyé pour {member.name}")
        except Exception as e:
            await send_log(f"⚠️ Erreur au revoir : {e}")
    else:
        await send_log("❌ Salon d'au revoir introuvable.")

# ------------------ AUTRES ÉVÉNEMENTS (logs complets) ------------------
@bot.event
async def on_member_update(before, after):
    if before.display_name != after.display_name:
        await send_log(f"✏️ {before.name} a changé de pseudo : {before.display_name} → {after.display_name}")
    before_roles = set(before.roles)
    after_roles = set(after.roles)
    added = after_roles - before_roles
    removed = before_roles - after_roles
    for role in added:
        await send_log(f"➕ Rôle `{role.name}` ajouté à {after.name}")
    for role in removed:
        await send_log(f"➖ Rôle `{role.name}` retiré de {after.name}")

@bot.event
async def on_user_update(before, after):
    if before.avatar != after.avatar:
        await send_log(f"🖼️ {before.name} a changé d'avatar")

@bot.event
async def on_message_delete(message):
    if message.author.bot:
        return
    content = message.content or "[fichier/sans texte]"
    await send_log(f"🗑️ Message supprimé de {message.author.name} dans #{message.channel.name} : {content[:500]}")

@bot.event
async def on_message_edit(before, after):
    if before.author.bot or before.content == after.content:
        return
    await send_log(f"✏️ Message édité par {before.author.name} dans #{before.channel.name}\nAvant : {before.content[:400]}\nAprès : {after.content[:400]}")

@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return
    await send_log(f"➕ {user.name} a réagi avec {reaction.emoji} dans #{reaction.message.channel.name}")

@bot.event
async def on_reaction_remove(reaction, user):
    if user.bot:
        return
    await send_log(f"➖ {user.name} a retiré la réaction {reaction.emoji} dans #{reaction.message.channel.name}")

@bot.event
async def on_voice_state_update(member, before, after):
    if before.channel is None and after.channel is not None:
        await send_log(f"🔊 {member.name} a rejoint le salon vocal {after.channel.name}")
    elif before.channel is not None and after.channel is None:
        await send_log(f"🔇 {member.name} a quitté le salon vocal {before.channel.name}")
    elif before.channel != after.channel:
        await send_log(f"🔄 {member.name} est passé du salon {before.channel.name} à {after.channel.name}")
    if before.self_mute != after.self_mute:
        state = "activé" if after.self_mute else "désactivé"
        await send_log(f"🎙️ {member.name} a {state} son micro")
    if before.self_deaf != after.self_deaf:
        state = "activé" if after.self_deaf else "désactivé"
        await send_log(f"🎧 {member.name} a {state} le son du serveur")
    if before.self_stream != after.self_stream:
        if after.self_stream:
            await send_log(f"📡 {member.name} a commencé à streamer dans {after.channel.name}")
        else:
            await send_log(f"📡 {member.name} a arrêté de streamer")

@bot.event
async def on_guild_pins_update(guild, channel, last_pin):
    await send_log(f"📌 Un message a été épinglé/désépinglé dans #{channel.name}")

@bot.event
async def on_disconnect():
    await send_log("⚠️ Le bot s'est déconnecté de Discord")

@bot.event
async def on_error(event, *args, **kwargs):
    await send_log(f"❌ Une erreur s'est produite dans l'événement {event}")

# ------------------ REDIRECTION VIDÉOS ------------------
@bot.listen('on_message')
async def on_message_listener(message):
    if message.author == bot.user:
        return
    if message.author.id == AUTHORIZED_USER_ID:
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
    await setup_verification_message()   # Crée le message de vérification
    await send_log("🚀 Bot démarré (vérification par réaction incluse)")

async def main():
    asyncio.create_task(start_http_server())
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ Token manquant")
        return
    await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())