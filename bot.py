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

# ------------------ ANTI-SPAM COMMANDES ------------------
command_cooldown = {}
COOLDOWN_SECONDS = 5
recent_joins = {}
recent_leaves = {}
SPAM_SECONDS = 10

# ------------------ CONFIGURATION ------------------
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True
intents.voice_states = True
intents.reactions = True
intents.guild_messages = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

# IDs des salons
ID_BIENVENUE = 1512009964988661861
ID_AUREVOIR = 1512010175907631104
VIDEO_CHANNEL_ID = 1513174573632454817
LOG_CHANNEL_ID = 1512010693665099876
AUTHORIZED_USER_ID = 1274426216413139007

FOND_BIENVENUE = "IMG_1299.png"
FOND_AUREVOIR = "IMG_1319.png"

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

# ------------------ BIENVENUE & AU REVOIR ------------------
@bot.event
async def on_member_join(member):
    now = time.time()
    if member.id in recent_joins and now - recent_joins[member.id] < SPAM_SECONDS:
        await send_log(f"🚫 Ignoré doublon arrivée de {member.name}")
        return
    recent_joins[member.id] = now
    canal = bot.get_channel(ID_BIENVENUE)
    if not canal:
        await send_log(f"❌ Salon bienvenue introuvable")
        return
    try:
        img_bytes = await lire_image(FOND_BIENVENUE)
        img_bordure = ajouter_bordure(img_bytes)
        texte = f"Oh ! **{member.display_name}** est un/une potentiel(le) dessinateur/rice et a rejoint ce serveur, bonne visite !"
        embed = discord.Embed(title="🎨 Bienvenue !", description=texte, color=0x000000, timestamp=datetime.now())
        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
        await canal.send(embed=embed, file=discord.File(io.BytesIO(img_bordure), filename="welcome.png"))
        await send_log(f"✅ {member.name} a rejoint le serveur")
    except Exception as e:
        await send_log(f"⚠️ Erreur bienvenue pour {member.name} : {e}")

@bot.event
async def on_member_remove(member):
    now = time.time()
    if member.id in recent_leaves and now - recent_leaves[member.id] < SPAM_SECONDS:
        await send_log(f"🚫 Ignoré doublon départ de {member.name}")
        return
    recent_leaves[member.id] = now
    canal = bot.get_channel(ID_AUREVOIR)
    if not canal:
        await send_log(f"❌ Salon au revoir introuvable")
        return
    try:
        img_bytes = await lire_image(FOND_AUREVOIR)
        img_bordure = ajouter_bordure(img_bytes)
        texte = f"Oh... **{member.display_name}**, un/une potentiel(le) dessinateur/rice, a quitté ce serveur, en espérant que tu deviendras un(e) artiste."
        embed = discord.Embed(title="👋 Au revoir...", description=texte, color=0x000000, timestamp=datetime.now())
        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
        await canal.send(embed=embed, file=discord.File(io.BytesIO(img_bordure), filename="goodbye.png"))
        await send_log(f"✅ {member.name} a quitté le serveur")
    except Exception as e:
        await send_log(f"⚠️ Erreur au revoir pour {member.name} : {e}")

# ------------------ MODIFICATION D'UN MEMBRE (pseudo, rôles, boost, mute) ------------------
@bot.event
async def on_member_update(before, after):
    # Changement de pseudo / surnom
    if before.display_name != after.display_name:
        await send_log(f"✏️ {before.name} a changé de pseudo : **{before.display_name}** → **{after.display_name}**")
    # Ajout ou retrait de rôles
    before_roles = set(before.roles)
    after_roles = set(after.roles)
    added = after_roles - before_roles
    removed = before_roles - after_roles
    for role in added:
        await send_log(f"➕ Rôle `{role.name}` ajouté à {after.name}")
    for role in removed:
        await send_log(f"➖ Rôle `{role.name}` retiré de {after.name}")
    # Début/fin de boost (le rôle "Nitro Booster" est généralement un rôle spécial)
    # On détecte via le boost depuis la timeline ? Non, on utilise le changement de rôle "Nitro Booster".
    # Si le membre a le rôle booster (souvent nommé "Booster"), on peut loguer.
    # Mais on peut aussi se fier à l'attribut premium_since (non fourni dans MemberUpdate). 
    # On va ignorer car complexe. Nous pourrons loguer via un autre événement si besoin.

# ------------------ CHANGEMENT D'AVATAR ------------------
@bot.event
async def on_user_update(before, after):
    if before.avatar != after.avatar:
        await send_log(f"🖼️ {before.name} a changé d'avatar")

# ------------------ SUPPRESSION DE MESSAGE ------------------
@bot.event
async def on_message_delete(message):
    if message.author.bot:
        return
    content = message.content or "[fichier/sans texte]"
    await send_log(f"🗑️ Message supprimé de **{message.author.name}** dans #{message.channel.name} : {content[:500]}")

# ------------------ ÉDITION DE MESSAGE ------------------
@bot.event
async def on_message_edit(before, after):
    if before.author.bot:
        return
    if before.content == after.content:
        return
    await send_log(f"✏️ Message édité par **{before.author.name}** dans #{before.channel.name}\n**Avant :** {before.content[:400]}\n**Après :** {after.content[:400]}")

# ------------------ RÉACTIONS ------------------
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

# ------------------ ÉVÉNEMENTS VOCAUX ------------------
@bot.event
async def on_voice_state_update(member, before, after):
    # Rejoint un salon vocal
    if before.channel is None and after.channel is not None:
        await send_log(f"🔊 {member.name} a rejoint le salon vocal {after.channel.name}")
    # Quitte un salon vocal
    elif before.channel is not None and after.channel is None:
        await send_log(f"🔇 {member.name} a quitté le salon vocal {before.channel.name}")
    # Change de salon vocal
    elif before.channel != after.channel:
        await send_log(f"🔄 {member.name} est passé du salon {before.channel.name} à {after.channel.name}")
    # Début/fin de mute (micro ou casque)
    if before.self_mute != after.self_mute:
        state = "activé" if after.self_mute else "désactivé"
        await send_log(f"🎙️ {member.name} a {state} son micro")
    if before.self_deaf != after.self_deaf:
        state = "activé" if after.self_deaf else "désactivé"
        await send_log(f"🎧 {member.name} a {state} le son du serveur")
    # Début/fin de stream
    if before.self_stream != after.self_stream:
        if after.self_stream:
            await send_log(f"📡 {member.name} a commencé à streamer dans {after.channel.name}")
        else:
            await send_log(f"📡 {member.name} a arrêté de streamer")

# ------------------ ÉPINGLE ------------------
@bot.event
async def on_guild_pins_update(guild, channel, last_pin):
    await send_log(f"📌 Un message a été épinglé/désépinglé dans #{channel.name}")

# ------------------ DÉCONNEXION ET ERREURS ------------------
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
                await send_log(f"❌ Salon vidéo introuvable")
    # Important pour ne pas bloquer les commandes
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

# ------------------ GESTION DES ERREURS DE COMMANDES ------------------
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
    await send_log("🚀 Bot démarré (version complète avec tous les logs)")

async def main():
    asyncio.create_task(start_http_server())
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ Token manquant")
        return
    await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())