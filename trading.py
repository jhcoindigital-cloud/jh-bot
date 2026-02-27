import asyncio
import time
import json
import os
from loguru import logger
from config import CONFIG, STATS, MODES_CONFIG
from strategy import SuperStrategy
from telegram_bot import send_tg, get_report_text
from BinaryOptionsToolsV2 import PocketOptionAsync

strat = SuperStrategy()

asset_states = {}

async def trade_single_asset(client, actif):
    state = asset_states.setdefault(actif, {
        'in_trade': False,
        't_end': 0,
        't_start_bal': 0,
        'montant': CONFIG["montant_base"],
        'mart_level': 0,
        'last_tick_time': time.time(),
        'last_regime': "RANGE" # Pour suivre les changements de marché
    })

    o = h = l = c = None
    tf = CONFIG.get("candle_timeframe", CONFIG.get("duree", 5)) # Timeframe dynamique
    next_candle_time = time.time() + (tf - (time.time() % tf))
    current_strategy = None

    try:
        sub = await client.subscribe_symbol(actif)
        if actif not in STATS["assets"]:
            STATS["assets"][actif] = {
                "wins": 0, "losses": 0,
                "total_gross_profit": 0.0, "total_gross_loss": 0.0,
                "max_win": 0.0, "max_loss": 0.0, "max_stake": 0.0, # <-- NOUVEAU
                "strategy_stats": {}
            }
        logger.info(f"Abonnement réussi à {actif}")
        await send_tg(f"✅ Abonnement réussi à {actif}")
    except Exception as e:
        logger.error(f"Échec abonnement {actif}: {e}")
        await send_tg(f"❌ <b>Nom d'actif invalide ou indisponible :</b> {actif}\n\n<i>Le bot est en pause. Utilisez le bouton 'Changer Actif' pour corriger.</i>")
        CONFIG["paused"] = True 
        return

    while CONFIG["is_running"] and not CONFIG["restart_requested"]:
        try:
            tick = await asyncio.wait_for(sub.__anext__(), timeout=60.0)
        except asyncio.TimeoutError:
            logger.warning(f"🔴 Déconnexion silencieuse sur {actif} (pas de prix depuis 60s). Relance...")
            await send_tg(f"⚠️ Perte de connexion réseau détectée sur {actif}. Reconnexion en cours...")
            break 
        except StopAsyncIteration:
            break
        except Exception as e:
            logger.error(f"Erreur de flux {actif}: {e}")
            break

        state['last_tick_time'] = time.time()
        now = time.time()
        price = float(tick.get("close", 0))

        strat.rsi_p = CONFIG["rsi_period"]
        strat.update_indicators(price)

        if o is None: o = h = l = c = price
        h, l, c = max(h, price), min(l, price), price

        if now >= next_candle_time:
            new_candle = {'o': o, 'h': h, 'l': l, 'c': c}
            strat.candles.append(new_candle)
            if len(strat.candles) > 30: strat.candles.pop(0)

            if CONFIG["paused"]:
                o = h = l = c = None
                next_candle_time = now + (tf - (now % tf))
                continue

            # =========================================================
            # DÉTECTION DES CHANGEMENTS DE MARCHÉ (RÉACTIVATION)
            # =========================================================
            current_regime = strat.get_market_regime()
            if current_regime != state['last_regime']:
                if STATS.get("banned_strats"):
                    banned_list = ", ".join(STATS["banned_strats"])
                    await send_tg(f"🔄 <b>Changement de marché détecté !</b> ({state['last_regime']} ➡️ {current_regime})\n✅ Réactivation des stratégies : {banned_list}")
                    
                    STATS["banned_strats"] = []
                    # On réinitialise les compteurs des stratégies pour leur donner une nouvelle chance
                    for s in STATS["strategy_stats"]:
                        STATS["strategy_stats"][s]["start_time"] = time.time()
                        STATS["strategy_stats"][s]["wins"] = 0
                        STATS["strategy_stats"][s]["losses"] = 0
                state['last_regime'] = current_regime

            current_dd_pct = ((STATS["current_balance"] - STATS["start_balance"]) / STATS["start_balance"] * 100) if STATS["start_balance"] > 0 else 0
            dd_target = CONFIG.get("max_drawdown_target_pct", -10.0)
            if current_dd_pct <= dd_target and not CONFIG["paused"]:
                CONFIG["paused"] = True
                pause_msg = f"🚨 **STOP AUTO DRAWDOWN** – {current_dd_pct:.1f}% atteint (seuil : {dd_target} %)\nBot mis en pause."
                await send_tg(pause_msg)
                await send_tg(get_report_text())
                break

            if not state['in_trade'] and len(strat.candles) >= 2:
                res = strat.check_patterns(strat.candles[-2], strat.candles[-1])
                if res:
                    direction, name = res
                    current_strategy = name
                    autorise = True

                    if CONFIG["use_ema_filter"] and STATS.get("ema_val", 0) > 0:
                        if direction == "call" and price < STATS["ema_val"]: autorise = False
                        if direction == "put" and price > STATS["ema_val"]: autorise = False

                    if autorise:
                        success = await (client.buy if direction == "call" else client.sell)(
                            actif, state['montant'], CONFIG["duree"]
                        )
                        if success:
                            state['in_trade'] = True
                            state['t_start_bal'] = float(await client.balance() or 0)
                            state['t_end'] = now + CONFIG["duree"]
                            STATS.setdefault("total_turnover", 0.0)
                            STATS["total_turnover"] += state['montant']

                            await send_tg(f"⚡️ <b>{actif.upper()} SIGNAL {direction.upper()}</b>\n🎯 {name}\n💵 {state['montant']:.2f}$")

            o = h = l = c = None
            next_candle_time = now + (tf - (now % tf))

        if state['in_trade'] and now > state['t_end'] + 3.0:
            try:
                new_bal = float(await client.balance() or 0)
                profit_this_trade = new_bal - state['t_start_bal']

                STATS["current_balance"] = new_bal
                STATS["last_trade_time"] = time.time()

                trade_amount = state['montant']

                trade_info = {
                    'time': time.strftime("%Y-%m-%d %H:%M:%S"),
                    'actif': actif,
                    'direction': direction if 'direction' in locals() else '—',
                    'strategy': current_strategy or "Inconnue",
                    'amount': state['montant'],
                    'profit': profit_this_trade,
                    'outcome': "WIN" if profit_this_trade > 0 else "LOSS",
                    'ema_at_trade': STATS.get("ema_val", 0),
                    'rsi_at_trade': STATS.get("rsi_val", 0)
                }

                if "trade_history" not in STATS: STATS["trade_history"] = []
                STATS["trade_history"].append(trade_info)

                if profit_this_trade > 0:
                    STATS["wins"] = STATS.get("wins", 0) + 1
                    STATS["win_streak"] = STATS.get("win_streak", 0) + 1
                    STATS["loss_streak"] = 0
                    STATS["total_gross_profit"] = STATS.get("total_gross_profit", 0) + profit_this_trade
                    status_text = "✅ <b>WIN</b>"
                    state['mart_level'] = 0
                    state['montant'] = CONFIG["montant_base"]
                else:
                    STATS["losses"] = STATS.get("losses", 0) + 1
                    STATS["loss_streak"] = STATS.get("loss_streak", 0) + 1
                    STATS["win_streak"] = 0
                    STATS["total_gross_loss"] = STATS.get("total_gross_loss", 0) - abs(profit_this_trade)  
                    status_text = "❌ <b>LOSS</b>"

                    if CONFIG["use_martingale"]:
                        state['montant'] *= CONFIG["martingale_coeff"]
                        state['mart_level'] += 1

                asset_stat = STATS["assets"][actif]

                if current_strategy:
                    if current_strategy not in STATS["strategy_stats"]:
                        STATS["strategy_stats"][current_strategy] = {"wins": 0, "losses": 0, "profit": 0.0, "start_time": time.time()}
                    if current_strategy not in asset_stat["strategy_stats"]:
                        asset_stat["strategy_stats"][current_strategy] = {"wins": 0, "losses": 0, "profit": 0.0}

                # --- ENREGISTREMENT DES RECORDS (Mise, Gain, Perte) ---
                asset_stat["max_stake"] = max(asset_stat.get("max_stake", 0.0), trade_amount)
                STATS["max_stake"] = max(STATS.get("max_stake", 0.0), trade_amount)

                if profit_this_trade > 0:
                    asset_stat["wins"] += 1
                    asset_stat["total_gross_profit"] += profit_this_trade
                    asset_stat["max_win"] = max(asset_stat.get("max_win", 0.0), profit_this_trade)
                    STATS["max_win"] = max(STATS.get("max_win", 0.0), profit_this_trade)
                else:
                    asset_stat["losses"] += 1
                    asset_stat["total_gross_loss"] -= abs(profit_this_trade)
                    asset_stat["max_loss"] = min(asset_stat.get("max_loss", 0.0), profit_this_trade) # min() car la perte est négative
                    STATS["max_loss"] = min(STATS.get("max_loss", 0.0), profit_this_trade)
                    # =========================================================
                # 🧠 ALIMENTATION DE L'IA (MÉMOIRE HORAIRE)
                # =========================================================
                trade_gmt_hour = str(time.gmtime().tm_hour)
                if "hourly_memory" not in STATS: STATS["hourly_memory"] = {}
                if trade_gmt_hour not in STATS["hourly_memory"]: STATS["hourly_memory"][trade_gmt_hour] = {}
                if current_strategy not in STATS["hourly_memory"][trade_gmt_hour]:
                    STATS["hourly_memory"][trade_gmt_hour][current_strategy] = {"wins": 0, "losses": 0}
                
                if profit_this_trade > 0:
                    STATS["hourly_memory"][trade_gmt_hour][current_strategy]["wins"] += 1
                else:
                    STATS["hourly_memory"][trade_gmt_hour][current_strategy]["losses"] += 1

                if current_strategy:
                    glob_strat = STATS["strategy_stats"][current_strategy]
                    asset_strat = asset_stat["strategy_stats"][current_strategy]
                    if profit_this_trade > 0:
                        glob_strat["wins"] += 1
                        asset_strat["wins"] += 1
                    else:
                        glob_strat["losses"] += 1
                        asset_strat["losses"] += 1
                    glob_strat["profit"] += profit_this_trade
                    asset_strat["profit"] += profit_this_trade

                    # =========================================================
                    # INTELLIGENCE : AUTO-DÉSACTIVATION DES MAUVAISES STRATÉGIES
                    # =========================================================
                    if "start_time" not in glob_strat:
                        glob_strat["start_time"] = time.time()
                    
                    uptime_strat = time.time() - glob_strat["start_time"]
                    total_strat_trades = glob_strat["wins"] + glob_strat["losses"]
                    strat_winrate = (glob_strat["wins"] / total_strat_trades * 100) if total_strat_trades > 0 else 0
                    
                    # Règle : Si + de 5 minutes (300s) + de 3 trades, et winrate < 45% -> BAN
                    if uptime_strat > 300 and total_strat_trades >= 3 and strat_winrate < 45.0:
                        if "banned_strats" not in STATS: STATS["banned_strats"] = []
                        if current_strategy not in STATS["banned_strats"]:
                            STATS["banned_strats"].append(current_strategy)
                            await send_tg(f"⚠️ <b>Stratégie désactivée : {current_strategy}</b>\nWinrate critique ({strat_winrate:.1f}%) sur les 5 dernières minutes.\n<i>Elle sera réactivée quand le marché changera de comportement.</i>")

                msg = (
                    f"{status_text} sur {actif}\n"
                    f"━━━━━━━━━━━━━━━\n"
                    f"💰 Solde: {new_bal:.2f}$\n"
                    f"📈 Profit: {profit_this_trade:+.2f}$\n"
                    f"Martingale niv: {state['mart_level']}\n"
                    f"Prochaine mise: {state['montant']:.2f}$\n"
                    f"━━━━━━━━━━━━━━━"
                )
                await send_tg(msg)
                state['in_trade'] = False

                profit_target = CONFIG.get("max_profit_target_pct", 20.0)

                if CONFIG.get("multi_assets_enabled", False):
                    asset_profit = asset_stat["total_gross_profit"] + asset_stat["total_gross_loss"]
                    asset_profit_pct = (asset_profit / STATS.get("start_balance", 1)) * 100 if STATS.get("start_balance", 0) > 0 else 0
                    
                    if asset_profit_pct >= profit_target:
                        await send_tg(f"🎯 <b>Objectif atteint sur {actif} !</b> (+{asset_profit_pct:.1f}%)\n🔄 Fermeture de cet actif et recherche d'un remplaçant...")
                        await send_tg(get_report_text(actif=actif)) 
                        if "assets_done" not in STATS: STATS["assets_done"] = []
                        STATS["assets_done"].append(actif) 
                        CONFIG["restart_requested"] = True 
                        break 
                else:
                    current_profit_pct = ((STATS["current_balance"] - STATS["start_balance"]) / STATS["start_balance"] * 100) if STATS.get("start_balance", 0) > 0 else 0
                    if current_profit_pct >= profit_target and not CONFIG["paused"]:
                        CONFIG["paused"] = True
                        await send_tg(f"🎯 **PROFIT CIBLE GLOBAL ATTEINT** : +{current_profit_pct:.1f}% (seuil : {profit_target} %)\nBot mis en pause.")
                        await send_tg(get_report_text())

                try:
                    with open("stats_data.json", "w", encoding="utf-8") as f:
                        json.dump(STATS, f)
                except Exception as e:
                    logger.error(f"Erreur sauvegarde auto : {e}")

            except Exception as e:
                logger.error(f"Erreur résultat trade {actif}: {e}")
                state['in_trade'] = False


async def trading_loop():
    last_connected_mode = None
    retries = 0
    max_retries = 20

    logger.info("🚀 trading_loop démarré – Scanner Global & Cerveau IA activés")

    while CONFIG["is_running"]:
        if CONFIG["restart_requested"]:
            logger.info(f"🔄 Restart forcé détecté")
            last_connected_mode = None
            CONFIG["restart_requested"] = False
            retries = 0
            asset_states.clear()
            await asyncio.sleep(1.5)
            continue

        if MODES_CONFIG[CONFIG["mode"]]["AUTH_STRING"] is None:
            await asyncio.sleep(2)
            continue

        try:
            auth = MODES_CONFIG[CONFIG["mode"]]["AUTH_STRING"]
            mode_nom = MODES_CONFIG[CONFIG["mode"]]["nom"]

            async with PocketOptionAsync(ssid=auth) as client:
                await asyncio.sleep(2)

                balance_val = await client.balance()
                if balance_val is None or float(balance_val) < 0:
                    logger.warning(f"❌ SSID invalide ({mode_nom})")
                    await send_tg(f"⚠️ Session expirée ({mode_nom})")
                    MODES_CONFIG[CONFIG["mode"]]["AUTH_STRING"] = None
                    last_connected_mode = None
                    retries = 0
                    continue

                if STATS.get("start_balance", 0) == 0:
                    STATS["start_balance"] = float(balance_val)
                STATS["current_balance"] = float(balance_val)

                if last_connected_mode is None:
                    await send_tg(f"🚀 Connecté : {mode_nom} - Solde : {balance_val:.2f}$")
                    last_connected_mode = True

                if STATS["current_balance"] <= CONFIG["montant_base"]:
                    CONFIG["paused"] = True
                    await send_tg(f"⚠️ <b>ALERTE SOLDE INSUFFISANT</b> ⚠️\nVotre solde est inférieur à la mise de base. Bot en pause.")

                current_dd_pct = ((STATS["current_balance"] - STATS["start_balance"]) / STATS["start_balance"] * 100) if STATS.get("start_balance", 0) > 0 else 0
                dd_target = CONFIG.get("max_drawdown_target_pct", -10.0)
                if current_dd_pct <= dd_target and not CONFIG["paused"]:
                    CONFIG["paused"] = True
                    await send_tg(f"🚨 **STOP AUTO DRAWDOWN** – {current_dd_pct:.1f}% atteint. Bot en pause.")
                    await asyncio.sleep(60)
                    continue

                # =====================================================================
                # 🧠 L'AMNISTIE HORAIRE & APPRENTISSAGE MACHINE
                # =====================================================================
                current_gmt_hour = time.gmtime().tm_hour
                if STATS.get("last_clear_hour", -1) != current_gmt_hour:
                    is_first_run = (STATS.get("last_clear_hour", -1) == -1)
                    STATS["last_clear_hour"] = current_gmt_hour
                    STATS["assets_done"] = []
                    STATS["banned_strats"] = [] # On libère tout le monde par défaut
                    
                    msg_ia = f"⏰ <b>Nouvelle heure GMT ({current_gmt_hour}h) !</b>\n🔓 Actifs libérés.\n\n"
                    
                    # --- LE CERVEAU IA QUI APPREND DU PASSÉ ---
                    current_hour_str = str(current_gmt_hour)
                    if "hourly_memory" in STATS and current_hour_str in STATS["hourly_memory"]:
                        mem = STATS["hourly_memory"][current_hour_str]
                        strats_bannies_ia = []
                        strats_top_ia = []
                        
                        for strat_name, data in mem.items():
                            tot = data["wins"] + data["losses"]
                            # Il faut au moins 3 trades dans le passé à cette heure pour que l'IA prenne une décision fiable
                            if tot >= 3: 
                                wr = (data["wins"] / tot) * 100
                                if wr < 45.0:
                                    # L'IA bannit préventivement la stratégie pour cette heure !
                                    STATS["banned_strats"].append(strat_name)
                                    strats_bannies_ia.append(f"{strat_name} ({wr:.0f}%)")
                                elif wr >= 65.0:
                                    strats_top_ia.append(f"{strat_name} ({wr:.0f}%)")
                        
                        if strats_bannies_ia:
                            msg_ia += f"🛡️ <b>Filtre IA :</b> J'ai banni <b>{', '.join(strats_bannies_ia)}</b> car elles perdent souvent à cette heure précise.\n"
                        if strats_top_ia:
                            msg_ia += f"⭐ <b>Top Strats recommandées :</b> {', '.join(strats_top_ia)}\n"
                    else:
                        msg_ia += "🧠 <b>IA Apprentissage :</b> Pas encore assez de données historiques pour cette heure, j'observe..."

                    if not is_first_run: 
                        await send_tg(msg_ia)
                    
                    # On remet le profit des actifs à zéro pour qu'ils puissent regagner la cible
                    if "assets" in STATS:
                        for a in STATS["assets"]:
                            STATS["assets"][a]["total_gross_profit"] = 0.0
                            STATS["assets"][a]["total_gross_loss"] = 0.0
                            
                    try:
                        with open("stats_data.json", "w", encoding="utf-8") as f:
                            json.dump(STATS, f)
                    except Exception: pass

                
                # ================= SÉLECTION ACTIFS INTELLIGENTE (RECHERCHE GLOBALE) =================
                actifs_a_surveiller = []
                MIN_PAYOUT = CONFIG.get("min_payout", 91)

                if CONFIG.get("multi_assets_enabled", False):
                    await send_tg(f"🔍 <b>Scan dynamique des marchés en cours...</b>\nRecherche des payouts ≥ {MIN_PAYOUT}%")
                    actifs_dispos = []
                    assets_done = STATS.get("assets_done", [])
                    
                    liste_dynamique = []
                    try:
                        if hasattr(client, 'get_all_assets'): liste_dynamique = await client.get_all_assets()
                        elif hasattr(client, 'assets'): liste_dynamique = client.assets
                        else:
                            liste_dynamique = ["EURUSD_otc", "GBPUSD_otc", "AUDCAD_otc", "NZDUSD_otc", "USDCHF_otc", "AUDUSD_otc", "USDCAD_otc", "EURGBP_otc", "EURJPY_otc", "GBPJPY_otc", "AUDJPY_otc", "CHFJPY_otc", "CADCHF_otc", "CADJPY_otc", "EURAUD_otc", "EURCAD_otc", "EURCHF_otc", "GBPAUD_otc", "GBPCAD_otc", "GBPCHF_otc", "NZDCAD_otc", "NZDJPY_otc", "USDJPY_otc"]
                    except:
                        liste_dynamique = ["EURUSD_otc", "GBPUSD_otc", "AUDCAD_otc", "NZDUSD_otc", "USDCHF_otc", "AUDUSD_otc", "USDCAD_otc"]

                    if isinstance(liste_dynamique, dict):
                        liste_dynamique = list(liste_dynamique.keys())
                    
                    filtre_actuel = CONFIG.get("asset_filter", "OTC")

                    # 2. On scanne les payouts ET on applique le filtre de catégorie
                    for actif_test in liste_dynamique:
                        if actif_test in assets_done: continue
                        
                        actif_str = str(actif_test).upper()
                        
                        # --- FILTRE DE MARCHÉ ---
                        if filtre_actuel == "OTC":
                            if not actif_str.endswith("_OTC") and not actif_str.endswith("OTC"): continue
                            
                        elif filtre_actuel == "CRYPTO":
                            cryptos_connues = ["BTC", "ETH", "LTC", "DASH", "XRP", "BITCOIN", "ETHEREUM"]
                            if not any(c in actif_str for c in cryptos_connues): continue
                            
                        elif filtre_actuel == "FOREX":
                            if "OTC" in actif_str: continue
                            if any(c in actif_str for c in ["BTC", "ETH", "LTC", "DASH", "XRP", "APPLE", "TSLA"]): continue
                            
                        try:
                            payout = 0
                            if hasattr(client, 'get_payout'): payout = await client.get_payout(actif_test)
                            elif hasattr(client, 'get_profit_asset'): payout = await client.get_profit_asset(actif_test)
                            elif hasattr(client, 'check_asset_open'):
                                res = await client.check_asset_open(actif_test)
                                if isinstance(res, tuple) and len(res) > 1: payout = res[1]
                                elif res: payout = 92
                            else: payout = 92
                                
                            if payout >= MIN_PAYOUT:
                                actifs_dispos.append((actif_test, payout))
                        except Exception:
                            continue
                            
                    actifs_dispos.sort(key=lambda x: x[1], reverse=True)
                    top_actifs = actifs_dispos[:3] 
                    
                    if not top_actifs:
                        await send_tg(f"⚠️ <b>Marché peu rentable !</b>\nAucun actif à +{MIN_PAYOUT}% trouvé. Veille de 5 minutes.")
                        await asyncio.sleep(300)
                        continue
                        
                    actifs_a_surveiller = [x[0] for x in top_actifs]
                    msg_scan = "✅ <b>Top Actifs trouvés sur la plateforme :</b>\n" + "\n".join([f"🔸 {a} ({p}%)" for a, p in top_actifs])
                    await send_tg(msg_scan)
                    
                else:
                    actifs_a_surveiller = [str(CONFIG.get("actif", "EURUSD_otc"))]

                tasks = []
                for actif in actifs_a_surveiller:
                    tasks.append(trade_single_asset(client, actif))

                await asyncio.gather(*tasks, return_exceptions=True)

                retries = 0

        except Exception as e:
            retries += 1
            logger.error(f"Erreur trading (tentative {retries}/{max_retries}): {e}")
            await send_tg(f"⚠️ Erreur ({retries}/{max_retries})")

            if retries >= max_retries:
                await send_tg("🔴 Trop d'erreurs – bot en pause")
                CONFIG["paused"] = True
                break

            await asyncio.sleep(min(120, 5 * (2 ** (retries - 1))))

        finally:
            await asyncio.sleep(1)