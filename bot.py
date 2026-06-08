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

# ------------------ ANTI-SPAM ------------------
command_cooldown = {}
COOLDOWN_SECONDS = 5
recent_joins = {}
recent_leaves = {}
SPAM_SECONDS = 10

# ------------------ CONFIGURATION ------------------
intents = discord.Intents.default()
intents.members = True
intents.message_content = True  # Nécessaire pour lire les messages (commandes !)

bot = commands.Bot(command_prefix='!', intents=intents)

# IDs des salons (vérifie qu'ils sont corrects)
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

# ------------------ SERVEUR HTTP (NON BLOQUANT) ------------------
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

# ------------------ BIENVENUE ------------------
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
        await send_log(f"✅ {member.name} a rejoint")
    except Exception as e:
        await send_log(f"⚠️ Erreur bienvenue : {e}")

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
        await send_log(f"✅ {member.name} a quitté")
    except Exception as e:
        await send_log(f"⚠️ Erreur au revoir : {e}")

# ------------------ REDIRECTION VIDÉOS (avec passage des commandes) ------------------
@bot.listen('on_message')
async def on_message_listener(message):
    # Ne pas traiter les messages du bot
    if message.author == bot.user:
        return

    # Si c'est l'utilisateur autorisé, rediriger les liens vidéo
    if message.author.id == AUTHORIZED_USER_ID:
        content = message.content.lower()
        if "youtube.com" in content or "youtu.be" in content or "tiktok.com" in content:
            video_channel = bot.get_channel(VIDEO_CHANNEL_ID)
            if video_channel:
                await video_channel.send(f"📹 **{message.author.display_name}** a partagé :\n{message.content}")
            else:
                await send_log(f"❌ Salon vidéo introuvable")

    # Toujours permettre le traitement des commandes (comme !ping)
    await bot.process_commands(message)

# ------------------ COMMANDE TEXTE !ping ------------------
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

# ------------------ COMMANDE SLASH /ping ------------------
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

# ------------------ DÉMARRAGE ------------------
@bot.event
async def on_ready():
    print(f"✅ Bot connecté : {bot.user}")
    # Synchronisation des commandes slash
    await bot.tree.sync()
    print("✅ Commandes slash synchronisées")
    await send_log("🚀 Bot démarré (avec !ping et /ping)")

async def main():
    asyncio.create_task(start_http_server())
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ Token manquant")
        return
    await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())