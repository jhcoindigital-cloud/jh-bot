import asyncio
import json
import os
import websockets
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

# ================= CONFIGURATION =================
TOKEN = os.getenv("BOT_TOKEN", "REMPLACE_PAR_TON_TOKEN")
ADMIN_CHAT_ID = os.getenv("CHAT_ID", "REMPLACE_PAR_TON_CHAT_ID")

last_price = "⏳ Connexion..."
current_strategy = "FRACTALE_3"
high_precedent = 0.0
highs_history = []
signal_envoye = False
binance_status = "❌ Déconnecté"

# ================= SERVEUR WEB (KEEP-ALIVE) =================
app = Flask(__name__)
@app.route("/")
def home(): return "Bot Actif ✅"

def run_web(): app.run(host="0.0.0.0", port=10000)

# ================= LOGIQUE D'ANTICIPATION =================
def calculer_anticipation(prix_actuel, niveau_casse, strategie):
    ecart = ((prix_actuel - niveau_casse) / niveau_casse) * 100
    if strategie == "FRACTALE_5":
        exp, conf = "3-5 MIN", "ÉLEVÉE" if ecart > 0.02 else "MOYENNE"
    elif strategie == "FRACTALE_3":
        exp, conf = "2 MIN", "MOYENNE" if ecart > 0.01 else "FAIBLE"
    else:
        exp, conf = "1 MIN", "FAIBLE"
    return exp, conf, ecart

# ================= FONCTIONS ASYNCHRONES =================

async def binance_ws(app_tg):
    global last_price, binance_status, high_precedent, signal_envoye, highs_history
    uri = "wss://stream.binance.com:443/ws/eurusdt@kline_1m"
    while True:
        try:
            async with websockets.connect(uri) as ws:
                binance_status = "✅ Connecté"
                while True:
                    data = json.loads(await ws.recv())
                    k = data['k']
                    price_actuel = float(k['c'])
                    last_price = f"{price_actuel:.5f}"
                    
                    if k['x']: # Bougie Fermée
                        val_high = float(k['h'])
                        highs_history.append(val_high)
                        if len(highs_history) > 5: highs_history.pop(0)

                        if current_strategy == "SIMPLE":
                            high_precedent = val_high
                        elif current_strategy == "FRACTALE_3" and len(highs_history) >= 3:
                            h = highs_history[-3:]
                            if h[1] > h[0] and h[1] > h[2]: high_precedent = h[1]
                        elif current_strategy == "FRACTALE_5" and len(highs_history) == 5:
                            h = highs_history
                            if h[2] > h[0] and h[2] > h[1] and h[2] > h[3] and h[2] > h[4]: high_precedent = h[2]
                        signal_envoye = False

                    if high_precedent > 0 and price_actuel > high_precedent and not signal_envoye:
                        exp, conf, pwr = calculer_anticipation(price_actuel, high_precedent, current_strategy)
                        msg = (f"🔔 **SIGNAL ACHAT**\nStratégie : `{current_strategy}`\n"
                               f"🎯 Niveau : `{high_precedent:.5f}`\n💰 Prix : `{price_actuel:.5f}`\n"
                               f"⏳ Expiration : **{exp}** ({conf})")
                        await app_tg.bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg, parse_mode="Markdown")
                        signal_envoye = True
        except Exception as e:
            binance_status = "❌ Déconnecté"
            await asyncio.sleep(5)

async def post_init(application: Application):
    """ Lance les tâches dès que le bot démarre """
    asyncio.create_task(binance_ws(application))
    try:
        await application.bot.send_message(chat_id=ADMIN_CHAT_ID, text="🚀 **Bot déployé sur Render !**")
    except: pass

# ================= HANDLERS TELEGRAM =================

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🚀 Simple (1m)", callback_data='S_SIMPLE')],
        [InlineKeyboardButton("💎 Fractale 3 (2m)", callback_data='S_3')],
        [InlineKeyboardButton("🏆 Fractale 5 (3-5m)", callback_data='S_5')]
    ]
    await update.message.reply_text("⚙️ **Réglages stratégie :**", 
                                  reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_strategy, signal_envoye
    query = update.callback_query
    await query.answer()
    mapping = {'S_SIMPLE': "SIMPLE", 'S_3': "FRACTALE_3", 'S_5': "FRACTALE_5"}
    current_strategy = mapping.get(query.data, "FRACTALE_3")
    signal_envoye = False
    await query.edit_message_text(text=f"✅ Stratégie : *{current_strategy}*")

# ================= LANCEMENT =================

def main():
    # Serveur Flask en tâche de fond
    Thread(target=run_web, daemon=True).start()

    # Configuration du Bot
    builder = Application.builder().token(TOKEN)
    builder.post_init(post_init) # <--- C'est ici qu'on lance les tâches proprement
    app_tg = builder.build()

    app_tg.add_handler(CommandHandler("start", lambda u,c: u.message.reply_text("Bot actif. /settings")))
    app_tg.add_handler(CommandHandler("settings", settings))
    app_tg.add_handler(CallbackQueryHandler(button_handler))

    print("🚀 Démarrage du bot...")
    app_tg.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
