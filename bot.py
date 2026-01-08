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
TOKEN = os.getenv("BOT_TOKEN")          # Mets ton token dans Render (ENV VAR)
ADMIN_CHAT_ID = os.getenv("CHAT_ID")    # Ton ID Telegram (ENV VAR)

last_price = "⏳ Connexion en cours..."
binance_status = "❌ Déconnecté"

# ================= SERVEUR WEB (RENDER) =================
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot Telegram actif ✅"

def run_web():
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
    uri = "wss://stream.binance.com:9443/ws/eurusdt@trade"

    while True:
        try:
            async with websockets.connect(uri) as ws:
                binance_status = "✅ Connecté"
                while True:
                    data = json.loads(await ws.recv())
                    last_price = data["p"]
        except Exception:
            binance_status = "❌ Déconnecté"
            await asyncio.sleep(5)

# ================= MESSAGE AU DÉPLOIEMENT =================
async def notify_deploy(application: Application):
    try:
        await application.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text="🚀 Bot déployé et connecté avec succès sur Render"
        )
    except Exception as e:
        print("Erreur notification Telegram :", e)

# ================= MAIN =================
async def main():
    # Lancer le serveur web (Render)
    Thread(target=run_web, daemon=True).start()

    # Telegram app
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("price", price))

    await application.initialize()
    await notify_deploy(application)
    await application.start()

    # Lancer Binance en tâche parallèle
    asyncio.create_task(binance_ws())

    # Polling Telegram
    await application.run_polling()

# ================= RUN =================
if __name__ == "__main__":
    asyncio.run(main())
