import discord
from discord.ext import commands
from PIL import Image
import io
import os
from datetime import datetime
import asyncio
from aiohttp import web

# --- Configuration des intents ---
intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# --- IDs des salons ---
ID_BIENVENUE = 1512009964988661861
ID_AUREVOIR  = 1512010175907631104

# --- Chemins relatifs des images (dans le même dossier) ---
FOND_BIENVENUE = "IMG_1299.png"
FOND_AUREVOIR  = "IMG_1319.png"

# --- Fonction pour ajouter une bordure noire ---
def ajouter_bordure(image_bytes: bytes, bordure_px: int = 15) -> bytes:
    img = Image.open(io.BytesIO(image_bytes))
    img_bordure = Image.new("RGB", (img.width + 2*bordure_px, img.height + 2*bordure_px), (0,0,0))
    img_bordure.paste(img, (bordure_px, bordure_px))
    with io.BytesIO() as buf:
        img_bordure.save(buf, format="PNG")
        buf.seek(0)
        return buf.getvalue()

# --- Lecture d'une image depuis le disque ---
async def lire_image(fond_path: str) -> bytes:
    with open(fond_path, "rb") as f:
        return f.read()

# --- Serveur HTTP asynchrone (aiohttp) ---
async def handle_health(request):
    return web.Response(text="OK")

async def start_http_server():
    app = web.Application()
    app.router.add_get('/', handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    print("✅ Serveur HTTP asynchrone démarré sur le port 8080")
    # On maintient le serveur ouvert indéfiniment
    await asyncio.Event().wait()

# --- Événement de démarrage du bot ---
@bot.event
async def on_ready():
    print(f"✅ {bot.user} est en ligne !")

# --- Bienvenue ---
@bot.event
async def on_member_join(member):
    canal = bot.get_channel(ID_BIENVENUE)
    if not canal:
        print("Salon de bienvenue introuvable")
        return

    image_bytes = await lire_image(FOND_BIENVENUE)
    image_avec_bordure = ajouter_bordure(image_bytes)

    texte = (f"Oh ! **{member.display_name}** est un/une potentiel(le) dessinateur/rice et a rejoint ce serveur, "
             f"bonne visite !")

    embed = discord.Embed(
        title="🎨 Bienvenue !",
        description=texte,
        color=0x000000,
        timestamp=datetime.now()
    )
    embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)

    await canal.send(embed=embed, file=discord.File(io.BytesIO(image_avec_bordure), filename="welcome.png"))

# --- Au revoir ---
@bot.event
async def on_member_remove(member):
    canal = bot.get_channel(ID_AUREVOIR)
    if not canal:
        print("Salon d'au revoir introuvable")
        return

    image_bytes = await lire_image(FOND_AUREVOIR)
    image_avec_bordure = ajouter_bordure(image_bytes)

    texte = (f"Oh... **{member.display_name}**, un/une potentiel(le) dessinateur/rice, a quitté ce serveur, "
             f"en espérant que tu deviendras un(e) artiste.")

    embed = discord.Embed(
        title="👋 Au revoir...",
        description=texte,
        color=0x000000,
        timestamp=datetime.now()
    )
    embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)

    await canal.send(embed=embed, file=discord.File(io.BytesIO(image_avec_bordure), filename="goodbye.png"))

# --- Point d'entrée principal : lancement du serveur HTTP et du bot ensemble ---
async def main():
    # Lancer le serveur HTTP en arrière‑plan
    asyncio.create_task(start_http_server())
    # Démarrer le bot Discord (utilise bot.start, une coroutine)
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("Erreur : la variable d'environnement DISCORD_TOKEN n'est pas définie.")
        return
    await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())