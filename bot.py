import asyncio
import json
import os
import websockets
from threading import Thread
from flask import Flask
from collections import deque
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ================= CONFIG =================
TOKEN = os.getenv("BOT_TOKEN", "8553165413:AAE8CUjph44w-nmkpcRnlnz53EFk-V4vEOM")
ADMIN_CHAT_ID = int(os.getenv("CHAT_ID", "501795546"))

prices = deque(maxlen=100)
binance_status = "❌ Déconnecté"
last_signal = None

# ================= SERVEUR WEB =================
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot Telegram actif ✅"

def run_web():
    app.run(host="0.0.0.0", port=10000)

# ================= INDICATEURS =================
def ema(values, period):
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    ema_val = values[0]
    for v in values[1:]:
        ema_val = v * k + ema_val * (1 - k)
    return ema_val

def rsi(values, period=14):
    if len(values) < period + 1:
        return None
    gains, losses = 0, 0
    for i in range(-period, -1):
        diff = values[i + 1] - values[i]
        if diff > 0:
            gains += diff
        else:
            losses -= diff
    if losses == 0:
        return 100
    rs = gains / losses
    return 100 - (100 / (1 + rs))

# ================= STRATÉGIE =================
def generate_signal():
    values = list(prices)
    ema9 = ema(values[-9:], 9)
    ema21 = ema(values[-21:], 21)
    rsi14 = rsi(values)

    if not ema9 or not ema21 or not rsi14:
        return None

    if ema9 > ema21 and rsi14 < 30:
        return "BUY"
    elif ema9 < ema21 and rsi14 > 70:
        return "SELL"
    return None

def build_trade(signal, price):
    if signal == "BUY":
        tp = price + 0.0005
        sl = price - 0.0003
    else:
        tp = price - 0.0005
        sl = price + 0.0003

    return {
        "signal": signal,
        "price": price,
        "tp": round(tp, 5),
        "sl": round(sl, 5),
        "expire": (datetime.utcnow() + timedelta(minutes=1)).strftime("%H:%M:%S UTC")
    }

# ================= MENU =================
def menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Signal EUR/USD", callback_data="signal")],
        [InlineKeyboardButton("📊 Signal EUR/USD OTC", callback_data="signal_otc")],
        [InlineKeyboardButton("📡 Statut", callback_data="status")],
    ])

# ================= TELEGRAM =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot prêt\nChoisis 👇", reply_markup=menu())

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data.startswith("signal"):
        signal = generate_signal()
        if not signal:
            txt = "⏳ Pas de signal valide pour le moment"
        else:
            price = prices[-1]
            trade = build_trade(signal, price)
            pair = "EUR/USD OTC" if "otc" in q.data else "EUR/USD"
            txt = (
                f"📊 **SIGNAL {pair}**\n\n"
                f"📌 Action : **{trade['signal']}**\n"
                f"💰 Entrée : `{trade['price']}`\n"
                f"🎯 TP : `{trade['tp']}`\n"
                f"🛑 SL : `{trade['sl']}`\n"
                f"⏱ Expiration : **1 min**\n"
                f"⏰ Fin : `{trade['expire']}`"
            )
        await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=menu())

    elif q.data == "status":
        await q.edit_message_text(
            f"🌐 Render : ✅\n📈 Binance : {binance_status}",
            reply_markup=menu()
        )

# ================= BINANCE =================
async def binance_ws():
    global binance_status
    uri = "wss://stream.binance.com:443/ws/eurusdt@trade"
    while True:
        try:
            async with websockets.connect(uri) as ws:
                binance_status = "✅ Connecté"
                while True:
                    data = json.loads(await ws.recv())
                    prices.append(float(data["p"]))
        except:
            binance_status = "❌ Déconnecté"
            await asyncio.sleep(5)

# ================= SIGNAUX AUTO =================
async def auto_signals(app):
    global last_signal
    while True:
        signal = generate_signal()
        if signal and signal != last_signal:
            trade = build_trade(signal, prices[-1])
            msg = (
                f"🔔 **SIGNAL AUTOMATIQUE**\n\n"
                f"📊 EUR/USD & OTC\n"
                f"📌 Action : **{trade['signal']}**\n"
                f"💰 Entrée : `{trade['price']}`\n"
                f"🎯 TP : `{trade['tp']}`\n"
                f"🛑 SL : `{trade['sl']}`\n"
                f"⏱ Expiration : **1 min**"
            )
            await app.bot.send_message(ADMIN_CHAT_ID, msg, parse_mode="Markdown")
            last_signal = signal

        await asyncio.sleep(60)  # SAFE POUR RENDER FREE

# ================= MAIN =================
def main():
    Thread(target=run_web, daemon=True).start()

    tg = Application.builder().token(TOKEN).build()
    tg.add_handler(CommandHandler("start", start))
    tg.add_handler(CallbackQueryHandler(buttons))

    loop = asyncio.get_event_loop()
    loop.create_task(binance_ws())
    loop.create_task(auto_signals(tg))

    print("🚀 Bot Pocket Option prêt (Render free safe)")
    tg.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
