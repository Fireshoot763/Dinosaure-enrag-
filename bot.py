import discord
from discord.ext import commands
from PIL import Image
import io
import os
import sys
import logging
import traceback
from datetime import datetime
import asyncio
from aiohttp import web
import time
import re

# ------------------ CONFIGURATION DES LOGS ------------------
discord_log_queue = asyncio.Queue()
bot_instance = None
_logging_initialized = False  # pour éviter les doublons

class DiscordLogHandler(logging.Handler):
    def emit(self, record):
        if bot_instance is None:
            return
        msg = self.format(record)
        asyncio.run_coroutine_threadsafe(send_log(msg), bot_instance.loop)

async def send_log(message: str):
    if bot_instance is None:
        return
    channel = bot_instance.get_channel(LOG_CHANNEL_ID)
    if channel:
        try:
            if len(message) > 1990:
                message = message[:1990] + "..."
            await channel.send(f"📋 {message}")
        except Exception as e:
            print(f"Erreur log : {e}")
    else:
        print(f"Salon logs introuvable (ID {LOG_CHANNEL_ID})")

def setup_logging():
    global _logging_initialized
    if _logging_initialized:
        return
    _logging_initialized = True
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    console.setFormatter(formatter)
    logger.addHandler(console)
    discord_handler = DiscordLogHandler()
    discord_handler.setLevel(logging.INFO)
    discord_handler.setFormatter(formatter)
    logger.addHandler(discord_handler)
    
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.critical("Exception non gérée", exc_info=(exc_type, exc_value, exc_traceback))
    sys.excepthook = handle_exception

# ------------------ ANTI-SPAM COMMANDES ------------------
command_cooldown = {}
COOLDOWN_SECONDS = 5

# ------------------ CONFIGURATION BOT ------------------
recent_joins = {}
recent_leaves = {}
SPAM_SECONDS = 10

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)
bot_instance = bot

# IDs
ID_BIENVENUE = 1512009964988661861
ID_AUREVOIR  = 1512010175907631104
VIDEO_CHANNEL_ID = 1513174573632454817
LOG_CHANNEL_ID  = 1512010693665099876
AUTHORIZED_USER_ID = 1274426216413139007

FOND_BIENVENUE = "IMG_1299.png"
FOND_AUREVOIR  = "IMG_1319.png"

# ------------------ IMAGES & SERVEUR HTTP ------------------
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

async def handle_health(request):
    return web.Response(text="OK")

async def start_http_server():
    app = web.Application()
    app.router.add_get('/', handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    logging.info("✅ Serveur HTTP sur port 8080")
    await asyncio.Event().wait()

# ------------------ BIENVENUE ------------------
@bot.event
async def on_member_join(member):
    now = time.time()
    if member.id in recent_joins and now - recent_joins[member.id] < SPAM_SECONDS:
        logging.info(f"🚫 Ignoré doublon arrivée de {member.name}")
        return
    recent_joins[member.id] = now
    canal = bot.get_channel(ID_BIENVENUE)
    if not canal:
        logging.error(f"Salon bienvenue introuvable")
        return
    try:
        img_bytes = await lire_image(FOND_BIENVENUE)
        img_bordure = ajouter_bordure(img_bytes)
        texte = (f"Oh ! **{member.display_name}** est un/une potentiel(le) dessinateur/rice et a rejoint ce serveur, bonne visite !")
        embed = discord.Embed(title="🎨 Bienvenue !", description=texte, color=0x000000, timestamp=datetime.now())
        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
        await canal.send(embed=embed, file=discord.File(io.BytesIO(img_bordure), filename="welcome.png"))
        logging.info(f"✅ {member.name} a rejoint")
    except Exception as e:
        logging.error(f"Erreur bienvenue {member.name}: {e}", exc_info=True)

@bot.event
async def on_member_remove(member):
    now = time.time()
    if member.id in recent_leaves and now - recent_leaves[member.id] < SPAM_SECONDS:
        logging.info(f"🚫 Ignoré doublon départ de {member.name}")
        return
    recent_leaves[member.id] = now
    canal = bot.get_channel(ID_AUREVOIR)
    if not canal:
        logging.error(f"Salon au revoir introuvable")
        return
    try:
        img_bytes = await lire_image(FOND_AUREVOIR)
        img_bordure = ajouter_bordure(img_bytes)
        texte = (f"Oh... **{member.display_name}**, un/une potentiel(le) dessinateur/rice, a quitté ce serveur, en espérant que tu deviendras un(e) artiste.")
        embed = discord.Embed(title="👋 Au revoir...", description=texte, color=0x000000, timestamp=datetime.now())
        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
        await canal.send(embed=embed, file=discord.File(io.BytesIO(img_bordure), filename="goodbye.png"))
        logging.info(f"✅ {member.name} a quitté")
    except Exception as e:
        logging.error(f"Erreur au revoir {member.name}: {e}", exc_info=True)

# ------------------ REDIRECTION VIDÉOS ------------------
@bot.listen('on_message')
async def on_message_listener(message):
    if message.author == bot.user:
        return
    if message.author.id != AUTHORIZED_USER_ID:
        return
    content = message.content.lower()
    if "youtube.com" in content or "youtu.be" in content or "tiktok.com" in content:
        video_channel = bot.get_channel(VIDEO_CHANNEL_ID)
        if video_channel:
            await video_channel.send(f"📹 **{message.author.display_name}** a partagé :\n{message.content}")
            logging.info(f"Vidéo redirigée: {message.content}")
        else:
            logging.error(f"Salon vidéo introuvable")

# ------------------ COMMANDE PING AVEC ANTI-SPAM ------------------
@bot.command()
async def ping(ctx):
    # Anti-spam par utilisateur
    user_id = ctx.author.id
    now = time.time()
    if user_id in command_cooldown and now - command_cooldown[user_id] < COOLDOWN_SECONDS:
        await ctx.send("⏳ Attend un peu avant de refaire `!ping` !")
        return
    command_cooldown[user_id] = now
    await ctx.send("Pong !")
    logging.info(f"Commande !ping utilisée par {ctx.author.name}")

# ------------------ GESTION DES ERREURS ------------------
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    logging.error(f"Erreur commande {ctx.command}: {error}", exc_info=True)

# ------------------ DÉMARRAGE ------------------
@bot.event
async def on_ready():
    logging.info(f"✅ Bot connecté : {bot.user} (ID: {bot.user.id})")
    logging.info(f"📡 Serveurs : {[guild.name for guild in bot.guilds]}")
    for guild in bot.guilds:
        for channel in guild.text_channels:
            if channel.id in (ID_BIENVENUE, ID_AUREVOIR, VIDEO_CHANNEL_ID, LOG_CHANNEL_ID):
                logging.info(f"🔗 Salon trouvé : #{channel.name} (ID {channel.id})")

async def main():
    setup_logging()
    asyncio.create_task(start_http_server())
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        logging.error("Token manquant")
        return
    await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())