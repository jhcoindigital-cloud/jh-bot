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
target_high = 0.0
target_low = 0.0
highs_history = []
lows_history = []
signal_envoye_call = False
signal_envoye_put = False

# ================= SERVEUR WEB =================
app = Flask(__name__)
@app.route("/")
def home(): return "Bot Réactif Actif ✅"

def run_web(): app.run(host="0.0.0.0", port=10000)

# ================= LOGIQUE DE DÉTECTION =================
async def analyser_marche(app_tg, prix_actuel):
    global target_high, target_low, signal_envoye_call, signal_envoye_put
    
    # SIGNAL CALL
    if target_high > 0 and prix_actuel > target_high and not signal_envoye_call:
        exp = "1m" if current_strategy == "SIMPLE" else "2m" if current_strategy == "FRACTALE_3" else "5m"
        msg = f"🟢 **SIGNAL CALL ({current_strategy})**\n🎯 Niveau : `{target_high:.5f}`\n💰 Prix : `{prix_actuel:.5f}`\n⏳ Exp : **{exp}**"
        await app_tg.bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg, parse_mode="Markdown")
        signal_envoye_call = True

    # SIGNAL PUT
    if target_low > 0 and prix_actuel < target_low and not signal_envoye_put:
        exp = "1m" if current_strategy == "SIMPLE" else "2m" if current_strategy == "FRACTALE_3" else "5m"
        msg = f"🔴 **SIGNAL PUT ({current_strategy})**\n🎯 Niveau : `{target_low:.5f}`\n💰 Prix : `{prix_actuel:.5f}`\n⏳ Exp : **{exp}**"
        await app_tg.bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg, parse_mode="Markdown")
        signal_envoye_put = True

# ================= BINANCE WEBSOCKET =================
async def binance_ws(app_tg):
    global last_price, target_high, target_low, highs_history, lows_history
    global signal_envoye_call, signal_envoye_put

    uri = "wss://stream.binance.com:443/ws/eurusdt@kline_1m"
    async with websockets.connect(uri) as ws:
        while True:
            data = json.loads(await ws.recv())
            k = data['k']
            prix_actuel = float(k['c'])
            last_price = f"{prix_actuel:.5f}"
            
            if k['x']: # Bougie fermée
                highs_history.append(float(k['h']))
                lows_history.append(float(k['l']))
                if len(highs_history) > 5: highs_history.pop(0)

                # RE-CALCUL DES CIBLES IMMÉDIAT
                if current_strategy == "SIMPLE" and len(highs_history) >= 1:
                    target_high, target_low = highs_history[-1], lows_history[-1]
                
                elif current_strategy == "FRACTALE_3" and len(highs_history) >= 3:
                    h, l = highs_history[-3:], lows_history[-3:]
                    if h[1] > h[0] and h[1] > h[2]: target_high = h[1]
                    if l[1] < l[0] and l[1] < l[2]: target_low = l[1]
                
                elif current_strategy == "FRACTALE_5" and len(highs_history) >= 5:
                    h, l = highs_history[-5:], lows_history[-5:]
                    if h[2] > h[0] and h[2] > h[1] and h[2] > h[3] and h[2] > h[4]: target_high = h[2]
                    if l[2] < l[0] and l[2] < l[1] and l[2] < l[3] and l[2] < l[4]: target_low = l[2]
                
                signal_envoye_call = signal_envoye_put = False
                print(f"DEBUG: {current_strategy} | High: {target_high} | Low: {target_low}")

            await analyser_marche(app_tg, prix_actuel)

# ================= COMMANDES TELEGRAM =================
async def test_signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ Commande pour tester si le bot envoie bien des messages """
    await update.message.reply_text("🧪 **Test de connexion...**")
    await update.message.reply_text("✅ Si tu reçois ce message, ton bot fonctionne et peut t'envoyer des signaux !", parse_mode="Markdown")

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🚀 Simple", callback_data='S_S')],
                [InlineKeyboardButton("💎 Fractale 3", callback_data='S_3')],
                [InlineKeyboardButton("🏆 Fractale 5", callback_data='S_5')]]
    await update.message.reply_text(f"Mode actuel: {current_strategy}\nCible High: {target_high}\nCible Low: {target_low}", 
                                  reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_strategy, signal_envoye_call, signal_envoye_put
    query = update.callback_query
    await query.answer()
    mapping = {'S_S': "SIMPLE", 'S_3': "FRACTALE_3", 'S_5': "FRACTALE_5"}
    current_strategy = mapping.get(query.data)
    signal_envoye_call = signal_envoye_put = False
    await query.edit_message_text(text=f"✅ Stratégie changée pour : **{current_strategy}**\nAnalyse en cours...", parse_mode="Markdown")

async def post_init(application: Application):
    asyncio.create_task(binance_ws(application))
    await application.bot.send_message(chat_id=ADMIN_CHAT_ID, text="🚀 **Bot opérationnel !**\nUtilise /test pour vérifier la connexion ou /settings pour changer de mode.")

def main():
    Thread(target=run_web, daemon=True).start()
    app_tg = Application.builder().token(TOKEN).post_init(post_init).build()
    app_tg.add_handler(CommandHandler("settings", settings))
    app_tg.add_handler(CommandHandler("test", test_signal))
    app_tg.add_handler(CallbackQueryHandler(button_handler))
    app_tg.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
