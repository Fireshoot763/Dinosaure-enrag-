import discord
from discord.ext import commands
from PIL import Image
import io
import os
from datetime import datetime
import asyncio
from aiohttp import web
import time

# --- Anti-spam : dictionnaire pour mémoriser le dernier événement par membre ---
last_join = {}
last_leave = {}
SPAM_DELAY = 15  # secondes

# --- Configuration des intents ---
intents = discord.Intents.default()
intents.members = True
intents.message_content = False  # pas besoin si pas de commandes

bot = commands.Bot(command_prefix='!', intents=intents)

# --- IDs des salons (À VÉRIFIER !) ---
ID_BIENVENUE = 1512009964988661861
ID_AUREVOIR  = 1512010175907631104

# --- Chemins relatifs des images ---
FOND_BIENVENUE = "IMG_1299.png"
FOND_AUREVOIR  = "IMG_1319.png"

# --- Bordure ---
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

# --- Serveur HTTP (inchangé) ---
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
    await asyncio.Event().wait()

# --- Événement de bienvenue avec anti-spam ---
@bot.event
async def on_member_join(member):
    # Ignorer si le même membre a rejoint il y a moins de SPAM_DELAY secondes
    now = time.time()
    if member.id in last_join and now - last_join[member.id] < SPAM_DELAY:
        print(f"⚠️ Ignoré doublon bienvenue pour {member.display_name}")
        return
    last_join[member.id] = now

    canal = bot.get_channel(ID_BIENVENUE)
    if not canal:
        print(f"❌ Salon bienvenue introuvable (ID {ID_BIENVENUE})")
        # Tentative de récupération par nom (optionnel)
        for guild in bot.guilds:
            for channel in guild.text_channels:
                if channel.id == ID_BIENVENUE:
                    canal = channel
                    break
        if not canal:
            return

    try:
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
        print(f"✅ Bienvenue envoyée pour {member.display_name} dans le salon {canal.name}")
    except Exception as e:
        print(f"Erreur bienvenue : {e}")

# --- Événement d'au revoir avec anti-spam ---
@bot.event
async def on_member_remove(member):
    now = time.time()
    if member.id in last_leave and now - last_leave[member.id] < SPAM_DELAY:
        print(f"⚠️ Ignoré doublon au revoir pour {member.display_name}")
        return
    last_leave[member.id] = now

    canal = bot.get_channel(ID_AUREVOIR)
    if not canal:
        print(f"❌ Salon au revoir introuvable (ID {ID_AUREVOIR})")
        for guild in bot.guilds:
            for channel in guild.text_channels:
                if channel.id == ID_AUREVOIR:
                    canal = channel
                    break
        if not canal:
            return

    try:
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
        print(f"✅ Au revoir envoyé pour {member.display_name} dans le salon {canal.name}")
    except Exception as e:
        print(f"Erreur au revoir : {e}")

# --- Événement de démarrage ---
@bot.event
async def on_ready():
    print(f"✅ {bot.user} est en ligne sur {len(bot.guilds)} serveur(s)")
    # Affiche les salons trouvés (debug)
    for guild in bot.guilds:
        for channel in guild.text_channels:
            if channel.id in (ID_BIENVENUE, ID_AUREVOIR):
                print(f"Salon trouvé : #{channel.name} (ID {channel.id})")

# --- Lancement ---
async def main():
    asyncio.create_task(start_http_server())
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ Token manquant")
        return
    await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())