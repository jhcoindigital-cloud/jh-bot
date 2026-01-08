import asyncio, json, websockets, os, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from flask import Flask
from threading import Thread
from collections import deque

# ================= WEB SERVER (RENDER) =================
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is alive"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# ================= CONFIG =================
TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = 501795546

prices = deque(maxlen=200)
last_price = "Récupération..."
last_signal_time = 0

# ================= INDICATORS =================
def EMA(data, period):
    k = 2 / (period + 1)
    ema = data[0]
    for price in data[1:]:
        ema = price * k + ema * (1 - k)
    return ema

def RSI(data, period=14):
    gains, losses = 0, 0
    for i in range(1, period + 1):
        diff = data[-i] - data[-i - 1]
        if diff > 0:
            gains += diff
        else:
            losses -= diff
    if losses == 0:
        return 100
    rs = gains / losses
    return 100 - (100 / (1 + rs))

# ================= TELEGRAM =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("💰 Prix", callback_data="price")],
        [InlineKeyboardButton("📊 Signal", callback_data="signal")]
    ]
    await update.message.reply_text(
        "🤖 Bot Trading actif",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "price":
        await query.edit_message_text(
            f"💰 *EUR/USD* : `{last_price}`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔄 Actualiser", callback_data="price")]]
            )
        )

    elif query.data == "signal":
        if len(prices) < 30:
            msg = "⏳ Analyse en cours..."
        else:
            rsi = RSI(list(prices))
            ema9 = EMA(list(prices)[-20:], 9)
            ema21 = EMA(list(prices)[-40:], 21)
            msg = (
                f"📊 *Analyse EUR/USD*\n"
                f"RSI : `{round(rsi,2)}`\n"
                f"EMA9 : `{round(ema9,5)}`\n"
                f"EMA21 : `{round(ema21,5)}`"
            )

        await query.edit_message_text(
            msg,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔄 Actualiser", callback_data="signal")]]
            )
        )

# ================= SIGNAL ENGINE =================
async def check_signal(app):
    global last_signal_time

    if len(prices) < 50:
        return

    rsi = RSI(list(prices))
    ema9_now = EMA(list(prices)[-20:], 9)
    ema21_now = EMA(list(prices)[-40:], 21)

    # Anti-spam : 1 signal / minute
    if time.time() - last_signal_time < 60:
        return

    if rsi < 30 and ema9_now > ema21_now:
        await app.bot.send_message(
            chat_id=CHAT_ID,
            text="🟢 *SIGNAL BUY EUR/USD*\nRSI bas + croisement EMA",
            parse_mode="Markdown"
        )
        last_signal_time = time.time()

    elif rsi > 70 and ema9_now < ema21_now:
        await app.bot.send_message(
            chat_id=CHAT_ID,
            text="🔴 *SIGNAL SELL EUR/USD*\nRSI haut + croisement EMA",
            parse_mode="Markdown"
        )
        last_signal_time = time.time()

# ================= BINANCE =================
async def binance_ws(app):
    global last_price
    uri = "wss://stream.binance.com/ws/eurusdt@kline_1m"

    while True:
        try:
            async with websockets.connect(uri) as ws:
                async for msg in ws:
                    data = json.loads(msg)
                    price = float(data["k"]["c"])
                    last_price = price
                    prices.append(price)
                    await check_signal(app)
        except Exception as e:
            print("Binance reconnect:", e)
            await asyncio.sleep(5)

# ================= MAIN =================
def main():
    Thread(target=run_web, daemon=True).start()

    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(buttons))

    application.post_init = lambda app: asyncio.create_task(binance_ws(app))

    print("🚀 BOT TRADING ACTIF (RENDER)")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
