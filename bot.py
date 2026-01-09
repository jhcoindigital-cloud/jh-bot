import asyncio
import json
import os
import time
import websockets
from threading import Thread
from flask import Flask

import pandas as pd
import ta

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# ================= CONFIG =================
TOKEN = os.getenv("BOT_TOKEN", "REMPLACE_PAR_TON_TOKEN")
ADMIN_CHAT_ID = os.getenv("CHAT_ID", "REMPLACE_PAR_TON_CHAT_ID")

last_price = "⏳ Connexion..."
binance_status = "❌ Déconnecté"
render_status = "✅ Actif"

prices = []

# ================= SERVEUR WEB (RENDER) =================
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot Telegram actif ✅"

def run_web():
    app.run(host="0.0.0.0", port=10000)

# ================= TELEGRAM =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Bot en ligne\n\n"
        "/status – État des connexions\n"
        "/price – Dernier prix\n"
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📡 **ÉTAT DU BOT**\n\n"
        f"🌐 Render : {render_status}\n"
        f"📈 Binance : {binance_status}\n"
        f"💰 EUR/USDT : `{last_price}`",
        parse_mode="Markdown"
    )

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"💰 EUR/USDT : `{last_price}`",
        parse_mode="Markdown"
    )

# ================= NOTIFICATION DEPLOIEMENT =================
async def notify_deploy(app):
    try:
        await app.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text="🚀 Bot déployé / redémarré avec succès sur Render"
        )
    except Exception as e:
        print("Erreur notification :", e)

# ================= BINANCE WEBSOCKET =================
async def binance_ws():
    global last_price, binance_status, prices

    uri = "wss://stream.binance.com:443/ws/eurusdt@trade"

    while True:
        try:
            async with websockets.connect(uri) as ws:
                binance_status = "✅ Connecté"
                while True:
                    data = json.loads(await ws.recv())
                    price = float(data["p"])
                    last_price = f"{price:.5f}"

                    prices.append(price)
                    if len(prices) > 200:
                        prices.pop(0)

        except Exception:
            binance_status = "❌ Déconnecté"
            await asyncio.sleep(5)

# ================= STRATEGIE RSI / EMA =================
def analyze_market():
    if len(prices) < 50:
        return None

    df = pd.DataFrame(prices, columns=["close"])

    df["rsi"] = ta.momentum.RSIIndicator(df["close"], 14).rsi()
    df["ema_fast"] = ta.trend.EMAIndicator(df["close"], 9).ema_indicator()
    df["ema_slow"] = ta.trend.EMAIndicator(df["close"], 21).ema_indicator()

    rsi = df["rsi"].iloc[-1]
    ema_fast = df["ema_fast"].iloc[-1]
    ema_slow = df["ema_slow"].iloc[-1]

    if rsi < 30 and ema_fast > ema_slow:
        return "📈 ACHAT"
    elif rsi > 70 and ema_fast < ema_slow:
        return "📉 VENTE"
    return None

# ================= SIGNAUX AUTOMATIQUES =================
async def auto_signals(app):
    while True:
        signal = analyze_market()
        if signal:
            try:
                await app.bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text=(
                        f"📊 **SIGNAL AUTOMATIQUE**\n\n"
                        f"💱 Paire : EUR/USD OTC\n"
                        f"🎯 Signal : {signal}\n"
                        f"⏱ Timeframe : 1 min\n"
                        f"💰 Prix : {last_price}"
                    ),
                    parse_mode="Markdown"
                )
                await asyncio.sleep(60)  # anti-spam
            except Exception as e:
                print("Erreur signal :", e)

        await asyncio.sleep(10)

# ================= MAIN =================
def main():
    Thread(target=run_web, daemon=True).start()

    app_tg = Application.builder().token(TOKEN).build()

    app_tg.add_handler(CommandHandler("start", start))
    app_tg.add_handler(CommandHandler("status", status))
    app_tg.add_handler(CommandHandler("price", price))

    loop = asyncio.get_event_loop()
    loop.create_task(binance_ws())
    loop.create_task(auto_signals(app_tg))
    loop.create_task(notify_deploy(app_tg))

    print("🚀 Bot prêt sur Render")
    app_tg.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
