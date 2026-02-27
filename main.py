import os
import sys
import asyncio
import json
import urllib.request
import time
from loguru import logger

from config import CONFIG, STATS, MODES_CONFIG, TELEGRAM_TOKEN
from telegram_bot import send_tg, main_keyboard, limit_profit_sub_keyboard, strategy_keyboard, ema_filter_sub_keyboard, rsi_filter_sub_keyboard, get_report_text, send_csv, report_sub_keyboard
from trading import trading_loop

logger.add("jhbot_pro.log", rotation="20 MB", level="INFO", encoding="utf-8", backtrace=True, diagnose=True)
logger.info("JHBot PRO démarré – Boutons ON/OFF EMA/RSI supprimés")

def get_updates_sync(offset):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={offset}&timeout=10"
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            return json.loads(response.read().decode())
    except Exception:
        return {"ok": False}

async def telegram_loop():
    offset = 0
    bot_start_time = time.time() 

    while CONFIG["is_running"]:
        try:
            updates = await asyncio.to_thread(get_updates_sync, offset)
            if updates.get("ok"):
                for update in updates.get("result", []):
                    offset = update["update_id"] + 1
                    msg = update.get("message", {})
                    
                    if msg.get("date", 0) != 0 and msg.get("date", 0) < bot_start_time:
                        continue
                    
                    text = msg.get("text", "").strip().lower()
                    
                    if text == "/start" or text == "🏠 retour menu" or text == "retour menu":
                        CONFIG["waiting_input"] = None
                        await send_tg("Bienvenue dans le menu principal", main_keyboard())
                        continue

                    # =========================================================
                    # 1. GESTION DES SAISIES TEXTUELLES (SSID, Actif...)
                    # =========================================================
                    elif CONFIG["waiting_input"] in ["ssid_input", "change_actif"]:
                        saisie_brute = msg.get("text", "").strip() 
                        
                        fichier_session = "session_data.json"
                        if os.path.exists(fichier_session):
                            try:
                                with open(fichier_session, "r", encoding="utf-8") as f:
                                    data = json.load(f)
                            except:
                                data = {"mode": CONFIG["mode"], "ssids": {}}
                        else:
                            data = {"mode": CONFIG["mode"], "ssids": {}}
                        
                        if CONFIG["waiting_input"] == "ssid_input":
                            if "ssids" not in data:
                                data["ssids"] = {}
                            data["ssids"][str(CONFIG["mode"])] = saisie_brute
                            
                            with open(fichier_session, "w", encoding="utf-8") as f:
                                json.dump(data, f)
                                
                            CONFIG["waiting_input"] = None
                            CONFIG["restart_requested"] = True
                            CONFIG["is_running"] = False
                            
                            noms_modes = {0: "REEL", 1: "DEMO", 2: "TOURNOI"}
                            await send_tg(f"✅ <b>SSID sauvegardé pour le mode {noms_modes[CONFIG['mode']]} !</b>\n🔄 Connexion en cours...")
                            continue

                        elif CONFIG["waiting_input"] == "change_actif":
                            actif_propre = saisie_brute.upper().replace("/", "").replace(" ", "")
                            if "_OTC" in actif_propre:
                                actif_propre = actif_propre.replace("_OTC", "_otc")
                            
                            CONFIG["actif"] = actif_propre
                            
                            data["actif"] = CONFIG["actif"]
                            with open(fichier_session, "w", encoding="utf-8") as f:
                                json.dump(data, f)
                                
                            CONFIG["waiting_input"] = None
                            CONFIG["restart_requested"] = True
                            CONFIG["is_running"] = False
                            await send_tg(f"✅ Actif corrigé et changé : <b>{CONFIG['actif']}</b> – Redémarrage...", main_keyboard())
                            continue

                    # =========================================================
                    # 2. GESTION DES SAISIES NUMÉRIQUES
                    # =========================================================
                    elif CONFIG["waiting_input"] and not any(mot in text for mot in ["limite", "drawdown", "profit", "🎯", "rapport", "stratégies", "ema", "rsi", "mode", "payout"]):
                        text_clean = text.replace('%', '').strip()
                        
                        try:
                            val = float(text_clean)
                            
                            if CONFIG["waiting_input"] == "drawdown_target":
                                val = -abs(val)
                                if -50 <= val <= 0:
                                    CONFIG["max_drawdown_target_pct"] = val
                                    CONFIG["waiting_input"] = None
                                    await send_tg(f"✅ Limite DD mise à jour : {val:.1f}%", limit_profit_sub_keyboard())
                                else:
                                    await send_tg("❌ Valeur invalide. Saisissez entre -50 et 0 :", limit_profit_sub_keyboard())
                                    
                            elif CONFIG["waiting_input"] == "profit_target":
                                if 1 <= val <= 100:
                                    CONFIG["max_profit_target_pct"] = val
                                    CONFIG["waiting_input"] = None
                                    await send_tg(f"✅ Limite Profit modifiée : {val:.1f}%", limit_profit_sub_keyboard())
                                else:
                                    await send_tg("❌ Valeur invalide (1 à 100)", limit_profit_sub_keyboard())

                            elif CONFIG["waiting_input"] == "min_payout":
                                if 50 <= val <= 99:
                                    CONFIG["min_payout"] = int(val)
                                    CONFIG["waiting_input"] = None
                                    
                                    # Sauvegarde du payout
                                    fichier_session = "session_data.json"
                                    if os.path.exists(fichier_session):
                                        try:
                                            with open(fichier_session, "r", encoding="utf-8") as f: data = json.load(f)
                                        except: data = {}
                                    else: data = {}
                                    data["min_payout"] = CONFIG["min_payout"]
                                    with open(fichier_session, "w", encoding="utf-8") as f: json.dump(data, f)
                                    
                                    await send_tg(f"✅ Payout minimum mis à jour : {int(val)}%", limit_profit_sub_keyboard())
                                else:
                                    await send_tg("❌ Valeur invalide. Saisissez entre 50 et 99 :", limit_profit_sub_keyboard())

                            elif CONFIG["waiting_input"] == "ema_period":
                                if 5 <= val <= 50:
                                    CONFIG["ema_period"] = int(val)
                                    CONFIG["waiting_input"] = None
                                    await send_tg(f"✅ EMA période : {int(val)}", ema_filter_sub_keyboard())
                                else:
                                    await send_tg("❌ 5 à 50.", ema_filter_sub_keyboard())

                            elif CONFIG["waiting_input"] == "rsi_period":
                                if 5 <= val <= 50:
                                    CONFIG["rsi_period"] = int(val)
                                    CONFIG["waiting_input"] = None
                                    await send_tg(f"✅ RSI période : {int(val)}", rsi_filter_sub_keyboard())
                                else:
                                    await send_tg("❌ 5 à 50.", rsi_filter_sub_keyboard())

                            elif CONFIG["waiting_input"] == "montant_base":
                                if val > 0:
                                    CONFIG["montant_base"] = val
                                    CONFIG["montant_actuel"] = val
                                    CONFIG["waiting_input"] = None
                                    await send_tg(f"✅ Mise modifiée : {val:.2f}$", main_keyboard())
                                else:
                                    await send_tg("❌ Positive.", main_keyboard())

                            elif CONFIG["waiting_input"] == "duree":
                                if val >= 1 and val == int(val):
                                    CONFIG["duree"] = int(val)
                                    CONFIG["waiting_input"] = None
                                    await send_tg(f"✅ Durée modifiée : {int(val)} secondes", main_keyboard())
                                else:
                                    await send_tg("❌ Entrez un entier positif", main_keyboard())

                        except ValueError:
                            await send_tg("❌ Erreur : Veuillez entrer une valeur numérique valide.", main_keyboard())
                            CONFIG["waiting_input"] = None
                            continue

                    # =========================================================
                    # 3. LE RESTE DES COMMANDES CLASSIQUES (Boutons menus)
                    # =========================================================
                    elif "voir liste noire" in text:
                        banned = STATS.get("banned_strats", [])
                        done = STATS.get("assets_done", [])
                        msg = "📊 <b>LISTE NOIRE ACTUELLE</b>\n\n"
                        msg += "🚫 <b>Stratégies désactivées :</b>\n"
                        msg += "\n".join([f"- {s}" for s in banned]) if banned else "- <i>Aucune</i>\n"
                        msg += "\n🎯 <b>Actifs en pause :</b>\n"
                        msg += "\n".join([f"- {a}" for a in done]) if done else "- <i>Aucun</i>\n"
                        msg += "\n<i>(Libération à la prochaine heure GMT)</i>"
                        await send_tg(msg, main_keyboard())
                        continue

                    # --- NOUVEAU : BOUTON CERVEAU IA ---
                    elif "cerveau ia" in text or "🧠" in text:
                        
                        current_gmt = str(time.gmtime().tm_hour)
                        msg = f"🧠 <b>MÉMOIRE IA - HEURE ACTUELLE ({current_gmt}h GMT)</b>\n\n"
                        
                        if "hourly_memory" in STATS and current_gmt in STATS["hourly_memory"]:
                            mem = STATS["hourly_memory"][current_gmt]
                            strats_data = []
                            
                            for s_name, data in mem.items():
                                tot = data["wins"] + data["losses"]
                                if tot > 0:
                                    wr = (data["wins"] / tot) * 100
                                    strats_data.append((s_name, wr, tot, data["wins"], data["losses"]))
                                    
                            if strats_data:
                                # On trie les stratégies de la meilleure à la pire
                                strats_data.sort(key=lambda x: x[1], reverse=True)
                                
                                for s_name, wr, tot, w, l in strats_data:
                                    # Définir l'icône selon l'intelligence du bot
                                    if tot >= 3 and wr < 45.0:
                                        icon = "🚫" # Stratégie bannie pour cette heure
                                    elif wr >= 65.0:
                                        icon = "⭐" # Excellente stratégie
                                    else:
                                        icon = "📊" # Neutre / En cours d'observation
                                        
                                    msg += f"{icon} <b>{s_name}</b> : {wr:.1f}% ({w}W / {l}L)\n"
                                    
                                msg += "\n<i>Règle IA : Au moins 3 trades requis pour qu'une stratégie soit filtrée (🚫).</i>"
                            else:
                                msg += "<i>Aucune stratégie n'a encore été testée à cette heure précise.</i>"
                        else:
                            msg += "<i>L'IA commence tout juste son apprentissage. Base de données vide pour cette heure.</i>"
                            
                        await send_tg(msg, main_keyboard())
                        continue

                    elif "🎮 mode" in text:
                        from telegram_bot import mode_sub_keyboard
                        await send_tg("🎮 <b>Choisissez votre Mode de trading :</b>", mode_sub_keyboard())
                        continue

                    elif "mode :" in text and any(m in text for m in ["reel", "demo", "tournoi"]):
                        mode_choisi = 0 if "reel" in text else (1 if "demo" in text else 2)
                        CONFIG["mode"] = mode_choisi
                        noms_modes = {0: "REEL", 1: "DEMO", 2: "TOURNOI"}
                        
                        fichier_session = "session_data.json"
                        if os.path.exists(fichier_session):
                            try:
                                with open(fichier_session, "r", encoding="utf-8") as f: data = json.load(f)
                            except: data = {"mode": 1, "ssids": {}}
                        else: data = {"mode": 1, "ssids": {}}
                            
                        data["mode"] = mode_choisi
                        with open(fichier_session, "w", encoding="utf-8") as f: json.dump(data, f)
                        
                        CONFIG["restart_requested"] = True
                        CONFIG["is_running"] = False
                        await send_tg(f"✅ <b>Mode {noms_modes[mode_choisi]} sélectionné !</b>\n🔄 Redémarrage...", main_keyboard())
                        continue

                    elif "menu multi-actifs" in text:
                        from telegram_bot import multi_assets_sub_keyboard
                        await send_tg("🌐 <b>Configuration du Scanner Global</b>", multi_assets_sub_keyboard())
                        continue

                    elif "activer multi-actifs" in text:
                        CONFIG["multi_assets_enabled"] = not CONFIG.get("multi_assets_enabled", False)
                        
                        fichier_session = "session_data.json"
                        if os.path.exists(fichier_session):
                            try:
                                with open(fichier_session, "r", encoding="utf-8") as f: data = json.load(f)
                            except: data = {}
                        else: data = {}
                            
                        data["multi_assets"] = CONFIG["multi_assets_enabled"]
                        with open(fichier_session, "w", encoding="utf-8") as f: json.dump(data, f)
                            
                        CONFIG["restart_requested"] = True
                        CONFIG["is_running"] = False
                        continue

                    elif "filtrer :" in text:
                        if "otc" in text: CONFIG["asset_filter"] = "OTC"
                        elif "crypto" in text: CONFIG["asset_filter"] = "CRYPTO"
                        elif "forex" in text: CONFIG["asset_filter"] = "FOREX"
                        elif "tout" in text: CONFIG["asset_filter"] = "TOUT"
                        
                        fichier_session = "session_data.json"
                        if os.path.exists(fichier_session):
                            try:
                                with open(fichier_session, "r", encoding="utf-8") as f: data = json.load(f)
                            except: data = {}
                        else: data = {}
                            
                        data["asset_filter"] = CONFIG["asset_filter"]
                        with open(fichier_session, "w", encoding="utf-8") as f: json.dump(data, f)
                            
                        CONFIG["restart_requested"] = True
                        CONFIG["is_running"] = False
                        await send_tg(f"✅ Filtre appliqué : {CONFIG['asset_filter']}. Redémarrage...")
                        continue

                    elif "min payout" in text:
                        CONFIG["waiting_input"] = "min_payout"
                        current_payout = CONFIG.get("min_payout", 91)
                        await send_tg(f"⚙️ Payout minimum actuel : {current_payout}%\n\nEntrez la nouvelle valeur (entre 50 et 99) :")
                        continue

                    elif "limite dd" in text or "drawdown max" in text:
                        CONFIG["waiting_input"] = "drawdown_target"
                        current = CONFIG.get("max_drawdown_target_pct", -10.0)
                        await send_tg(f"Limite DD actuelle : {current:.1f}%\nEntrez la nouvelle valeur (-50 à 0) :", limit_profit_sub_keyboard())
                        continue

                    elif "limite profit" in text or "gain max" in text:
                        CONFIG["waiting_input"] = "profit_target"
                        current = CONFIG.get("max_profit_target_pct", 20.0)
                        await send_tg(f"Limite Profit actuelle : {current:.1f}%\nEntrez la nouvelle valeur (1 à 100) :", limit_profit_sub_keyboard())
                        continue

                    elif "🎯 limite profit objectif" in text:
                        await send_tg("Sous-menu Limite Profit Objectif :", limit_profit_sub_keyboard())
                        continue

                    elif "rapport" in text and not any(a.lower() in text for a in CONFIG.get("preferred_actifs", [])) and "global" not in text:
                        await send_tg("Choisissez l'actif pour le rapport :", report_sub_keyboard())
                        continue

                    elif "rapport global" in text or "rapport général" in text:
                        await send_tg(get_report_text(), main_keyboard())
                        continue

                    elif "rapport" in text:
                        for actif in CONFIG.get("preferred_actifs", []):
                            if actif.lower() in text:
                                await send_tg(get_report_text(actif=actif), main_keyboard())
                                break
                        continue

                    elif "stratégies" in text:
                        await send_tg("Gestion des stratégies :", strategy_keyboard())
                        continue

                    elif text.startswith("✅ ") or text.startswith("❌ "):
                        displayed_name = text[2:].strip()
                        found_strategy = next((s for s in CONFIG["active_strategies"] if s.lower() == displayed_name.lower()), None)
                        if found_strategy:
                            CONFIG["active_strategies"].remove(found_strategy)
                            await send_tg(f"{found_strategy} désactivée", strategy_keyboard())
                        else:
                            possible_strategy = next((s for s in CONFIG["active_strategies"] if s.lower() == displayed_name.lower()), displayed_name.title())
                            if possible_strategy not in CONFIG["active_strategies"]:
                                CONFIG["active_strategies"].append(possible_strategy)
                            await send_tg(f"{possible_strategy} activée", strategy_keyboard())
                        continue

                    elif "ema filter on/off" in text:
                        CONFIG["use_ema_filter"] = not CONFIG.get("use_ema_filter", True)
                        status = "🟢 ON" if CONFIG["use_ema_filter"] else "🔴 OFF"
                        await send_tg(f"EMA Filter : {status}")
                        await send_tg("Sous-menu EMA Filter :", ema_filter_sub_keyboard())
                        continue

                    elif "ema filter" in text:
                        await send_tg("Sous-menu EMA Filter :", ema_filter_sub_keyboard())
                        continue

                    elif "régler période ema" in text:
                        CONFIG["waiting_input"] = "ema_period"
                        current = CONFIG.get("ema_period", 14)
                        await send_tg(f"Période EMA actuelle : {current}\nEntrez la nouvelle valeur :")
                        continue

                    elif "rsi filter on/off" in text:
                        CONFIG["use_rsi_filter"] = not CONFIG.get("use_rsi_filter", False)
                        status = "🟢 ON" if CONFIG["use_rsi_filter"] else "🔴 OFF"
                        await send_tg(f"RSI Filter : {status}")
                        await send_tg("Sous-menu RSI Filter :", rsi_filter_sub_keyboard())
                        continue

                    elif "rsi filter" in text:
                        await send_tg("Sous-menu RSI Filter :", rsi_filter_sub_keyboard())
                        continue

                    elif "régler période rsi" in text:
                        CONFIG["waiting_input"] = "rsi_period"
                        current = CONFIG.get("rsi_period", 14)
                        await send_tg(f"Période RSI actuelle : {current}\nEntrez la nouvelle valeur :")
                        continue

                    elif "pause" in text or "⏸" in text:
                        CONFIG["paused"] = True
                        await send_tg("⏸ Bot mis en pause", main_keyboard())
                        continue

                    elif "reprendre" in text or "▶️" in text:
                        CONFIG["paused"] = False
                        await send_tg("▶️ Bot repris", main_keyboard())
                        continue

                    elif "stop" in text or "reset" in text or "⏹" in text:
                        if CONFIG["paused"]:
                            await send_tg("📊 <b>Rapport final avant réinitialisation :</b>")
                            await send_tg(get_report_text())
                            
                            CONFIG["is_running"] = False
                            STATS["wins"] = STATS["losses"] = 0
                            STATS["win_streak"] = STATS["loss_streak"] = 0
                            STATS["total_gross_profit"] = STATS["total_gross_loss"] = 0.0
                            STATS["trade_history"] = []
                            STATS["assets"] = {}
                            STATS["assets_done"] = []
                            STATS["start_balance"] = 0 
                            STATS["strategy_stats"] = {s: {"wins": 0, "losses": 0, "profit": 0.0} for s in CONFIG["active_strategies"]}
                            
                            try:
                                with open("stats_data.json", "w", encoding="utf-8") as f: json.dump(STATS, f)
                            except: pass

                            await send_tg("⏹ Bot arrêté et statistiques effacées.\nPour relancer : redémarrez le script.", main_keyboard())
                        else:
                            await send_tg("⏹ Stop & Reset disponible uniquement en pause.", main_keyboard())
                        continue
                    
                    elif "restart" in text:
                        await send_tg("🔄 <b>Redémarrage du bot en cours...</b>")
                        CONFIG["restart_requested"] = True
                        CONFIG["is_running"] = False 
                        continue

                    elif "effacer mémoire" in text or "json" in text:
                        for f_name in ["session_data.json", "stats_data.json"]:
                            if os.path.exists(f_name):
                                try: os.remove(f_name)
                                except Exception: pass
                                
                        await send_tg("🗑️ <b>Mémoires effacées avec succès !</b>\n🔄 Redémarrage...")
                        CONFIG["restart_requested"] = True
                        CONFIG["is_running"] = False
                        continue

                    elif "exporter" in text or "csv" in text:
                        await send_csv()
                        continue

                    elif "changer actif" in text:
                        CONFIG["waiting_input"] = "change_actif"
                        await send_tg("Entrez le nom exact de l’actif (ex: EURUSD_otc) :", main_keyboard())
                        continue

                    elif "modifier mise" in text or "💰" in text:
                        CONFIG["waiting_input"] = "montant_base"
                        await send_tg(f"Mise actuelle : {CONFIG['montant_base']:.2f}$\nEntrez la nouvelle mise :", main_keyboard())
                        continue

                    # --- GESTIONNAIRE DE TIMEFRAME INTELLIGENT ---
                    elif "durée trade" in text or "⏱️" in text:
                        from telegram_bot import timeframe_sub_keyboard
                        msg = (
                            "⏱️ <b>Configuration du Timeframe & Expiration</b>\n\n"
                            "Choisissez votre mode de trading. Le bot se reconfigurera automatiquement :\n"
                            "- Synchronisation de la taille des bougies\n"
                            "- Ajustement des paramètres EMA et RSI"
                        )
                        await send_tg(msg, timeframe_sub_keyboard())
                        continue

                    elif any(d in text for d in ["5 secondes", "15 secondes", "1 minute", "5 minutes"]):
                        if "5 secondes" in text:
                            tf = 5
                            ema = 7
                            rsi = 7
                        elif "15 secondes" in text:
                            tf = 15
                            ema = 9
                            rsi = 9
                        elif "1 minute" in text:
                            tf = 60
                            ema = 14
                            rsi = 14
                        elif "5 minutes" in text:
                            tf = 300
                            ema = 21
                            rsi = 14

                        CONFIG["duree"] = tf
                        CONFIG["candle_timeframe"] = tf
                        CONFIG["ema_period"] = ema
                        CONFIG["rsi_period"] = rsi

                        # Sauvegarde de la configuration
                        fichier_session = "session_data.json"
                        if os.path.exists(fichier_session):
                            try:
                                with open(fichier_session, "r", encoding="utf-8") as f: data = json.load(f)
                            except: data = {}
                        else: data = {}
                            
                        data["duree"] = tf
                        data["candle_timeframe"] = tf
                        with open(fichier_session, "w", encoding="utf-8") as f: json.dump(data, f)

                        CONFIG["restart_requested"] = True
                        CONFIG["is_running"] = False
                        
                        nom_tf = "1 Minute" if tf == 60 else ("5 Minutes" if tf == 300 else f"{tf} Secondes")
                        await send_tg(
                            f"✅ <b>Mode de Trading mis à jour : {nom_tf}</b>\n\n"
                            f"📊 <b>Nouveaux Paramètres :</b>\n"
                            f"- Expiration : {tf}s\n"
                            f"- Bougies : {tf}s\n"
                            f"- Période EMA : {ema}\n"
                            f"- Période RSI : {rsi}\n\n"
                            f"🔄 <i>Redémarrage en cours...</i>", 
                            main_keyboard()
                        )
                        continue

        except Exception as e:
            logger.error(f"Erreur Telegram: {e}")
            await asyncio.sleep(5)

async def main():
    logger.success("========================================")
    logger.success("     POCKET OPTION BOT PRO - DEMARRAGE      ")
    logger.success("========================================")

    # ---> NOUVEAUTÉ : CHARGEMENT DES STATS SAUVEGARDÉES <---
    fichier_stats = "stats_data.json"
    if os.path.exists(fichier_stats):
        try:
            with open(fichier_stats, "r", encoding="utf-8") as f:
                saved_stats = json.load(f)
                STATS.update(saved_stats)
                logger.info("Données de trading (Stats) restaurées avec succès.")
        except Exception as e:
            logger.error(f"Erreur chargement STATS : {e}")

    fichier_session = "session_data.json"
    session_data = {"mode": 1, "ssids": {}}
    # ... (la suite de ta fonction main ne change pas)

    # 1. On lit le trousseau de clés (et les paramètres) s'il existe
    if os.path.exists(fichier_session):
        try:
            with open(fichier_session, "r", encoding="utf-8") as f:
                saved_data = json.load(f)
                
                if "ssid" in saved_data and "ssids" not in saved_data:
                    session_data["mode"] = saved_data.get("mode", 1)
                    session_data["ssids"][str(session_data["mode"])] = saved_data["ssid"]
                else:
                    session_data["mode"] = saved_data.get("mode", 1)
                    session_data["ssids"] = saved_data.get("ssids", {})
                
                # ---> NOUVEAUTÉ ICI : Chargement de l'actif sauvegardé
                if "actif" in saved_data:
                    CONFIG["actif"] = saved_data["actif"]
                if "multi_assets" in saved_data:
                    CONFIG["multi_assets_enabled"] = saved_data["multi_assets"]
                
                if "asset_filter" in saved_data:
                    CONFIG["asset_filter"] = saved_data["asset_filter"]
                
                if "min_payout" in saved_data: # <--- AJOUTE ÇA ICI
                    CONFIG["min_payout"] = saved_data["min_payout"]
                    
            CONFIG["mode"] = session_data["mode"]
        except Exception as e:
            logger.error(f"Erreur de lecture de la session : {e}")

    # 2. On vérifie si on a le SSID pour le mode sélectionné
    mode_str = str(CONFIG["mode"])
    nom_du_mode = MODES_CONFIG[CONFIG["mode"]]["nom"]
    ssid = session_data["ssids"].get(mode_str, "")

    # 3. SI LE SSID EST MANQUANT -> On demande sur Telegram
    if not ssid:
        logger.warning(f"--- SSID MANQUANT POUR LE MODE {nom_du_mode} ---")
        CONFIG["waiting_input"] = "ssid_input"
        
        await send_tg(
            f"⚠️ <b>Connexion au mode {nom_du_mode} impossible</b>\n\n"
            f"Le SSID est manquant. Veuillez envoyer votre SSID complet (commençant par 42...) <b>directement ici dans le chat :</b>"
        )
        
        await telegram_loop()
        
    else:
        logger.success(f"🔄 Reconnexion automatique au mode {nom_du_mode} avec le SSID sauvegardé !")
        MODES_CONFIG[CONFIG["mode"]]["AUTH_STRING"] = ssid
        logger.success("========================================\n")
        logger.success(f"✅ SSID {nom_du_mode} JHBot pro prêt. Lancement...")
        logger.success("========================================\n")

        await asyncio.gather(telegram_loop(), trading_loop())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Arrêt manuel du bot.")
    finally:
        if CONFIG.get("restart_requested"):
            logger.warning("🔄 Redémarrage en cours...")
            os.execv(sys.executable, ['python'] + sys.argv)