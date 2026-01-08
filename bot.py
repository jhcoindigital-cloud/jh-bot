import asyncio
import json
import os
import websockets
from threading import Thread
from flask import Flask

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# ================= CONFIG =================
# Si tu n'as pas encore mis les ENV VAR sur Render, remplace direct ici pour tester
TOKEN = os.getenv("BOT_TOKEN", "8553165413:AAE8CUjph44w-nmkpcRnlnz53EFk-V4vEOM")
ADMIN_CHAT_ID = os.getenv("CHAT_ID", "501795546")

last_price = "⏳ Connexion en cours..."
binance_status = "❌ Déconnecté"

# ================= SERVEUR WEB (RENDER) =================
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot Telegram actif ✅"

def run_web():
    # Render utilise le port 10000 par défaut
    app.run(host="0.0.0.0", port=10000)

# ================= TELEGRAM COMMANDES =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Bot en ligne !\n"
        "📌 Commandes disponibles :\n"
        "/status – État des connexions\n"
        "/price – Prix EUR/USDT"
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📡 **État du bot**\n\n"
        f"🌐 Serveur Render : ✅ Connecté\n"
        f"📈 Binance : {binance_status}\n"
        f"💰 Dernier prix EUR/USDT : `{last_price}`",
        parse_mode="Markdown"
    )

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"💰 EUR/USDT : `{last_price}`", parse_mode="Markdown")

# ================= BINANCE WEBSOCKET =================
async def binance_ws():
    global last_price, binance_status
    # Changement du port 9443 vers 443 pour Render
    uri = "wss://stream.binance.com:443/ws/eurusdt@trade"

    while True:
        try:
            async with websockets.connect(uri) as ws:
                binance_status = "✅ Connecté"
                while True:
                    data = json.loads(await ws.recv())
                    # Formatage du prix pour n'avoir que 4 décimales
                    last_price = f"{float(data['p']):.4f}"
        except Exception:
            binance_status = "❌ Déconnecté"
            await asyncio.sleep(5)

# ================= MAIN =================
def main():
    # 1. Lancer le serveur web
    Thread(target=run_web, daemon=True).start()

    # 2. Configurer l'application Telegram
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("price", price))

    # 3. Lancer Binance en arrière-plan AVANT le polling
    loop = asyncio.get_event_loop()
    loop.create_task(binance_ws())

    # 4. Lancement propre avec nettoyage du conflit (drop_pending_updates)
    print("🚀 Bot prêt sur Render")
    
    # run_polling gère l'initialisation et le démarrage proprement
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
