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

# ------------------ ANTI-SPAM POUR LA COMMANDE !ping ------------------
command_cooldown = {}
COOLDOWN_SECONDS = 5

# ------------------ CONFIGURATION ------------------
recent_joins = {}
recent_leaves = {}
SPAM_SECONDS = 10

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

# IDs des salons (vérifie qu'ils sont corrects)
ID_BIENVENUE = 1512009964988661861
ID_AUREVOIR = 1512010175907631104
VIDEO_CHANNEL_ID = 1513174573632454817
LOG_CHANNEL_ID = 1512010693665099876

AUTHORIZED_USER_ID = 1274426216413139007

FOND_BIENVENUE = "IMG_1299.png"
FOND_AUREVOIR = "IMG_1319.png"

# ------------------ FONCTION DE LOG VERS DISCORD ------------------
async def send_log(message: str):
    """Envoie un message texte dans le salon de logs (sans bloquer le bot)."""
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        try:
            # Troncature si trop long
            if len(message) > 1990:
                message = message[:1990] + "..."
            await channel.send(f"📋 {message}")
        except Exception as e:
            print(f"Erreur d'envoi du log Discord : {e}")
    else:
        print(f"Salon logs introuvable (ID {LOG_CHANNEL_ID})")

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
    print("✅ Serveur HTTP sur le port 8080")
    # On attend indéfiniment (le serveur tourne en fond)
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
    now = time.time()
    if member.id in recent_joins and now - recent_joins[member.id] < SPAM_SECONDS:
        await send_log(f"🚫 Ignoré (doublon) arrivée de {member.name}")
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
        embed = discord.Embed(title="🎨 Bienvenue !", description=texte, color=0x000000, timestamp=datetime.now())
        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
        await canal.send(embed=embed, file=discord.File(io.BytesIO(img_bordure), filename="welcome.png"))
        await send_log(f"✅ {member.name} a rejoint le serveur (message dans #{canal.name})")
    except Exception as e:
        await send_log(f"⚠️ Erreur bienvenue pour {member.name} : {e}")
        print(f"Erreur bienvenue: {e}")

# ------------------ AU REVOIR ------------------
@bot.event
async def on_member_remove(member):
    now = time.time()
    if member.id in recent_leaves and now - recent_leaves[member.id] < SPAM_SECONDS:
        await send_log(f"🚫 Ignoré (doublon) départ de {member.name}")
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
        embed = discord.Embed(title="👋 Au revoir...", description=texte, color=0x000000, timestamp=datetime.now())
        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
        await canal.send(embed=embed, file=discord.File(io.BytesIO(img_bordure), filename="goodbye.png"))
        await send_log(f"✅ {member.name} a quitté le serveur (message dans #{canal.name})")
    except Exception as e:
        await send_log(f"⚠️ Erreur au revoir pour {member.name} : {e}")
        print(f"Erreur au revoir: {e}")

# ------------------ REDIRECTION DES LIENS VIDÉO ------------------
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
            # Option : log seulement si besoin (décommente si tu veux)
            # await send_log(f"Vidéo redirigée : {message.content}")
        else:
            await send_log(f"❌ Salon vidéo introuvable (ID {VIDEO_CHANNEL_ID})")

# ------------------ COMMANDE !ping (avec anti-spam) ------------------
@bot.command()
async def ping(ctx):
    user_id = ctx.author.id
    now = time.time()
    if user_id in command_cooldown and now - command_cooldown[user_id] < COOLDOWN_SECONDS:
        await ctx.send("⏳ Attends un peu avant de refaire `!ping` !")
        return
    command_cooldown[user_id] = now
    await ctx.send("Pong !")
    await send_log(f"Commande !ping utilisée par {ctx.author.name} (ID {user_id})")

# ------------------ GESTION DES ERREURS DE COMMANDE ------------------
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    await send_log(f"❌ Erreur dans la commande `{ctx.command}` : {error}")
    print(f"Erreur commande: {error}")

# ------------------ DÉMARRAGE ------------------
@bot.event
async def on_ready():
    print(f"✅ Bot connecté : {bot.user} (ID: {bot.user.id})")
    print(f"📡 Serveurs : {[guild.name for guild in bot.guilds]}")
    await send_log("🚀 Bot démarré (version finale sans duplication)")

    # Vérification des salons (affichage console)
    for guild in bot.guilds:
        for channel in guild.text_channels:
            if channel.id in (ID_BIENVENUE, ID_AUREVOIR, VIDEO_CHANNEL_ID, LOG_CHANNEL_ID):
                print(f"🔗 Salon trouvé : #{channel.name} (ID {channel.id})")

# ------------------ LANCEMENT ------------------
async def main():
    # Lance le serveur HTTP pour Render
    asyncio.create_task(start_http_server())
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ Token Discord manquant dans les variables d'environnement")
        return
    await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())