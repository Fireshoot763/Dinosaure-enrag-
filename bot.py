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
# Anti-spam pour les événements join/leave
recent_joins = {}
recent_leaves = {}
SPAM_SECONDS = 10

# Intents Discord
intents = discord.Intents.default()
intents.members = True          # Pour détecter les arrivées/départs
intents.message_content = True  # Pour lire les liens vidéo

bot = commands.Bot(command_prefix='!', intents=intents)

# IDs des salons (à vérifier sur votre serveur)
ID_BIENVENUE = 1512009964988661861
ID_AUREVOIR  = 1512010175907631104
VIDEO_CHANNEL_ID = 1513174573632454817
LOG_CHANNEL_ID  = 1512012141312475229   # <-- NOUVEAU : salon pour les logs

# ID de la personne autorisée à partager des vidéos
AUTHORIZED_USER_ID = 1274426216413139007

# Chemins des images de fond (dans le même dossier)
FOND_BIENVENUE = "IMG_1299.png"
FOND_AUREVOIR  = "IMG_1319.png"

# ------------------ FONCTIONS D'AIDE ------------------
async def send_log(message: str):
    """Envoie un message texte dans le salon de logs."""
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        try:
            await channel.send(message)
            print(f"[LOG] {message}")  # aussi dans la console
        except Exception as e:
            print(f"Erreur lors de l'envoi du log : {e}")
    else:
        print(f"⚠️ Salon de logs introuvable (ID {LOG_CHANNEL_ID})")

# ------------------ SERVEUR HTTP POUR RENDER ------------------
async def handle_health(request):
    return web.Response(text="OK")

async def start_http_server():
    app = web.Application()
    app.router.add_get('/', handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    print("✅ Serveur HTTP démarré sur le port 8080")
    await asyncio.Event().wait()

# ------------------ FONCTIONS POUR LES IMAGES ------------------
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

# ------------------ BIENVENUE ------------------
@bot.event
async def on_member_join(member):
    # Anti-spam
    now = time.time()
    if member.id in recent_joins and now - recent_joins[member.id] < SPAM_SECONDS:
        await send_log(f"🚫 Ignoré doublon bienvenue pour {member.name}")
        return
    recent_joins[member.id] = now

    canal = bot.get_channel(ID_BIENVENUE)
    if not canal:
        await send_log(f"❌ Salon bienvenue introuvable (ID {ID_BIENVENUE})")
        return

    try:
        img_bytes = await lire_image(FOND_BIENVENUE)
        img_bordure = ajouter_bordure(img_bytes)

        texte = (f"Oh ! **{member.display_name}** est un/une potentiel(le) dessinateur/rice et a rejoint ce serveur, "
                 f"bonne visite !")

        embed = discord.Embed(
            title="🎨 Bienvenue !",
            description=texte,
            color=0x000000,
            timestamp=datetime.now()
        )
        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)

        await canal.send(embed=embed, file=discord.File(io.BytesIO(img_bordure), filename="welcome.png"))
        await send_log(f"✅ {member.name} a rejoint le serveur (message envoyé dans #{canal.name})")
    except Exception as e:
        await send_log(f"⚠️ Erreur bienvenue pour {member.name} : {e}")

# ------------------ AU REVOIR ------------------
@bot.event
async def on_member_remove(member):
    now = time.time()
    if member.id in recent_leaves and now - recent_leaves[member.id] < SPAM_SECONDS:
        await send_log(f"🚫 Ignoré doublon au revoir pour {member.name}")
        return
    recent_leaves[member.id] = now

    canal = bot.get_channel(ID_AUREVOIR)
    if not canal:
        await send_log(f"❌ Salon au revoir introuvable (ID {ID_AUREVOIR})")
        return

    try:
        img_bytes = await lire_image(FOND_AUREVOIR)
        img_bordure = ajouter_bordure(img_bytes)

        texte = (f"Oh... **{member.display_name}**, un/une potentiel(le) dessinateur/rice, a quitté ce serveur, "
                 f"en espérant que tu deviendras un(e) artiste.")

        embed = discord.Embed(
            title="👋 Au revoir...",
            description=texte,
            color=0x000000,
            timestamp=datetime.now()
        )
        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)

        await canal.send(embed=embed, file=discord.File(io.BytesIO(img_bordure), filename="goodbye.png"))
        await send_log(f"✅ {member.name} a quitté le serveur (message envoyé dans #{canal.name})")
    except Exception as e:
        await send_log(f"⚠️ Erreur au revoir pour {member.name} : {e}")

# ------------------ REDIRECTION VIDÉOS (YouTube/TikTok) ------------------
@bot.listen('on_message')
async def on_message_listener(message):
    if message.author == bot.user:
        return

    if message.author.id != AUTHORIZED_USER_ID:
        return

    # Détection simple des liens YouTube/TikTok
    content = message.content.lower()
    is_youtube = "youtube.com" in content or "youtu.be" in content
    is_tiktok = "tiktok.com" in content

    if is_youtube or is_tiktok:
        video_channel = bot.get_channel(VIDEO_CHANNEL_ID)
        if video_channel:
            await video_channel.send(f"📹 **{message.author.display_name}** a partagé :\n{message.content}")
            await send_log(f"📹 Lien { 'YouTube' if is_youtube else 'TikTok' } redirigé vers #{video_channel.name} : {message.content}")
        else:
            await send_log(f"❌ Salon vidéo introuvable (ID {VIDEO_CHANNEL_ID})")

# ------------------ DÉMARRAGE ------------------
@bot.event
async def on_ready():
    print(f"✅ Bot connecté : {bot.user} (ID: {bot.user.id})")
    print(f"📡 Serveurs : {[guild.name for guild in bot.guilds]}")
    await send_log(f"🚀 Bot démarré (version avec logs)")

    # Vérification des salons (debug)
    for guild in bot.guilds:
        for channel in guild.text_channels:
            if channel.id in (ID_BIENVENUE, ID_AUREVOIR, VIDEO_CHANNEL_ID, LOG_CHANNEL_ID):
                print(f"🔗 Salon trouvé : #{channel.name} (ID {channel.id})")

async def main():
    # Lancer le serveur HTTP pour Render
    asyncio.create_task(start_http_server())
    # Démarrer le bot
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ Erreur : La variable d'environnement DISCORD_TOKEN n'est pas définie.")
        return
    await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())