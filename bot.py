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

# --- CONFIGURATION ---

# Anti-spam bienvenue/départ
recent_joins = {}
recent_leaves = {}
SPAM_SECONDS = 10

# Intents Discord
intents = discord.Intents.default()
intents.members = True
intents.message_content = True  # Nécessaire pour lire les liens

bot = commands.Bot(command_prefix='!', intents=intents)

# --- IDs des salons ---
ID_BIENVENUE = 1512009964988661861
ID_AUREVOIR  = 1512010175907631104
VIDEO_CHANNEL_ID = 1513174573632454817

# --- ID de la personne autorisée à poster des vidéos ---
AUTHORIZED_USER_ID = 1274426216413139007   # <- ton ID

# --- Images de fond (chemins relatifs) ---
FOND_BIENVENUE = "IMG_1299.png"
FOND_AUREVOIR  = "IMG_1319.png"

# --- Serveur HTTP factice pour Render ---
async def handle_health(request):
    return web.Response(text="OK")

async def start_http_server():
    app = web.Application()
    app.router.add_get('/', handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    print("✅ Serveur HTTP sur port 8080")
    await asyncio.Event().wait()

# --- Fonctions pour les images de bienvenue ---
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

# --- Événement de bienvenue ---
@bot.event
async def on_member_join(member):
    now = time.time()
    if member.id in recent_joins and now - recent_joins[member.id] < SPAM_SECONDS:
        print(f"🚫 Ignoré doublon bienvenue pour {member.name}")
        return
    recent_joins[member.id] = now

    canal = bot.get_channel(ID_BIENVENUE)
    if not canal:
        print(f"❌ Salon bienvenue introuvable (ID {ID_BIENVENUE})")
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
        print(f"✅ Bienvenue envoyée pour {member.name}")
    except Exception as e:
        print(f"⚠️ Erreur bienvenue : {e}")

# --- Événement d'au revoir ---
@bot.event
async def on_member_remove(member):
    now = time.time()
    if member.id in recent_leaves and now - recent_leaves[member.id] < SPAM_SECONDS:
        print(f"🚫 Ignoré doublon au revoir pour {member.name}")
        return
    recent_leaves[member.id] = now

    canal = bot.get_channel(ID_AUREVOIR)
    if not canal:
        print(f"❌ Salon au revoir introuvable (ID {ID_AUREVOIR})")
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
        print(f"✅ Au revoir envoyé pour {member.name}")
    except Exception as e:
        print(f"⚠️ Erreur au revoir : {e}")

# --- REDIRECTION DES LIENS VIDÉO (YouTube / TikTok) ---
@bot.event
async def on_message(message):
    # Ignorer les messages du bot lui-même
    if message.author == bot.user:
        return

    # Vérifier si l'auteur est la personne autorisée
    if message.author.id != AUTHORIZED_USER_ID:
        await bot.process_commands(message)
        return

    # Regex pour détecter les URLs YouTube et TikTok
    url_pattern = re.compile(r'https?://(?:www\.)?(youtube\.com/watch\?v=|youtu\.be/|tiktok\.com/)[^\s]+', re.IGNORECASE)
    match = url_pattern.search(message.content)

    if match:
        video_channel = bot.get_channel(VIDEO_CHANNEL_ID)
        if video_channel:
            await video_channel.send(f"**{message.author.display_name}** a partagé une vidéo :\n{message.content}")
            print(f"✅ Vidéo redirigée : {message.content}")
        else:
            print(f"❌ Salon vidéo introuvable (ID {VIDEO_CHANNEL_ID})")

    # Laisser passer les commandes du bot si besoin
    await bot.process_commands(message)

# --- Démarrage du bot ---
@bot.event
async def on_ready():
    print(f"✅ Bot connecté : {bot.user} (ID: {bot.user.id})")
    print(f"📡 Serveurs : {[guild.name for guild in bot.guilds]}")

async def main():
    asyncio.create_task(start_http_server())
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ Token non défini dans l'environnement")
        return
    await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())