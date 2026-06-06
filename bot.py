import discord
from discord.ext import commands
from PIL import Image
import io
from datetime import datetime
import os

# Configuration des intents
intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# --- IDs des salons (à vérifier) ---
ID_BIENVENUE = 1512009964988661861
ID_AUREVOIR  = 1512010175907631104

# --- Chemins des images de fond ---
FOND_BIENVENUE = "IMG_1299.png"
FOND_AUREVOIR  = "IMG_1319.png"

# --- Fonction pour ajouter une bordure noire à une image ---
def ajouter_bordure(image_bytes: bytes, bordure_px: int = 15) -> bytes:
    img = Image.open(io.BytesIO(image_bytes))
    img_bordure = Image.new("RGB", (img.width + 2*bordure_px, img.height + 2*bordure_px), (0,0,0))
    img_bordure.paste(img, (bordure_px, bordure_px))
    with io.BytesIO() as buf:
        img_bordure.save(buf, format="PNG")
        buf.seek(0)
        return buf.getvalue()

# --- Fonction pour lire une image depuis le disque ---
async def lire_image(fond_path: str) -> bytes:
    with open(fond_path, "rb") as f:
        return f.read()

# --- Événement quand le bot est prêt ---
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

    # Lecture de l'image de fond
    image_bytes = await lire_image(FOND_BIENVENUE)
    image_avec_bordure = ajouter_bordure(image_bytes, bordure_px=15)

    # Message personnalisé avec le pseudo
    texte_bienvenue = (f"Oh ! **{member.display_name}** est un/une potentiel(le) dessinateur/rice et a rejoint ce serveur, "
                       f"bonne visite !")

    # Création de l'embed (cadre noir)
    embed = discord.Embed(
        title="🎨 Bienvenue !",
        description=texte_bienvenue,
        color=0x000000,
        timestamp=datetime.now()
    )
    # Miniature : avatar du membre
    embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)

    # Envoi du message (embed + image attachée)
    await canal.send(embed=embed, file=discord.File(io.BytesIO(image_avec_bordure), filename="welcome.png"))

# --- Au revoir ---
@bot.event
async def on_member_remove(member):
    canal = bot.get_channel(ID_AUREVOIR)
    if not canal:
        print("Salon d'au revoir introuvable")
        return

    image_bytes = await lire_image(FOND_AUREVOIR)
    image_avec_bordure = ajouter_bordure(image_bytes, bordure_px=15)

    texte_aurevoir = (f"Oh... **{member.display_name}**, un/une potentiel(le) dessinateur/rice, a quitté ce serveur, "
                      f"en espérant que tu deviendras un(e) artiste.")

    embed = discord.Embed(
        title="👋 Au revoir...",
        description=texte_aurevoir,
        color=0x000000,
        timestamp=datetime.now()
    )
    embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)

    await canal.send(embed=embed, file=discord.File(io.BytesIO(image_avec_bordure), filename="goodbye.png"))

# --- Lancement du bot avec lecture sécurisée du token ---
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("Erreur : La variable d'environnement DISCORD_TOKEN n'est pas définie.")
    else:
        bot.run(token)