import time

TELEGRAM_TOKEN = "8349037970:AAHmVMVRI9Zw6mymNQtInlCuXhqEZ8S8xOw"
CHAT_ID = "501795546"

MODES_CONFIG = {
    0: {"nom": "REEL", "AUTH_STRING": None},
    1: {"nom": "DEMO", "AUTH_STRING": None},
    2: {"nom": "TOURNOI", "AUTH_STRING": None}
}

CONFIG = {
    "max_drawdown_target_pct": -20.0,
    "max_profit_target_pct": 10.0,
    "is_running": True,
    "paused": False,
    "restart_requested": False,
    "mode": 1,
    "actif": "EURUSD_otc",
    "preferred_actifs": [
        "EURUSD_otc", "GBPUSD_otc", "AUDUSD_otc", "AUDCAD_otc",
        "EURGBP_otc", "GBPJPY_otc", "USDJPY_otc", "NZDUSD_otc",
        "EURJPY_otc", "GBPAUD_otc"
    ],
    "rotation_groups": [
        ["EURUSD_otc", "GBPUSD_otc", "AUDUSD_otc", "AUDCAD_otc"],
        ["EURGBP_otc", "GBPJPY_otc", "USDJPY_otc", "NZDUSD_otc"],
        ["EURJPY_otc", "GBPAUD_otc", "USDCAD_otc", "USDCHF_otc"]
    ],
    "use_ema_filter": True,
    "use_rsi_filter": False,  
    "rsi_period": 7,
    "ema_period": 7,
    "current_rotation_index": 0,
    "rotation_interval_minutes": 10,
    "last_rotation_time": time.time(),
    "montant_base": 1.0,
    "montant_actuel": 1.0,
    "duree": 5,
    "use_martingale": True,
    "martingale_coeff": 2.2,
    "martingale_steps": 5,
    "martingale_pause_minutes": 10,
    "profit_target_pct": 10.0,
    "multi_assets_enabled": False,
    "last_update_id": 0,
    "waiting_input": None,
    "waiting_session": False,
    "active_strategies": [
        "Pin Bar", "Engulfing", "Breakout", "Three Line Strike",
        "Pin Bar + EMA Filter", "Rejection Wick", "EMA Cross + RSI",
        "Railroad Tracks", "BB Squeeze Break", "Cassure", "Order Block"
    ]
}

STATS = {
    "start_time": time.time(),
    "start_balance": 0.0,
    "current_balance": 0.0,

    "wins": 0,
    "losses": 0,
    "win_streak": 0,
    "loss_streak": 0,

    "total_gross_profit": 0.0,
    "total_gross_loss": 0.0,
    "daily_profit": 0.0,
    "total_turnover": 0.0,
    
    # NOUVEAU : Records Globaux
    "max_win": 0.0,
    "max_loss": 0.0,
    "max_stake": 0.0,

    "ema_val": 0.0,
    "rsi_val": 50.0,
    "max_drawdown": 0.0,
    "max_drawdown_pct": 0.0,

    "first_trade_time": 0,
    "last_trade_time": 0,
    "trade_history": [],

    "strategy_stats": {
        "Pin Bar": {"wins": 0, "losses": 0, "profit": 0.0},
        "Engulfing": {"wins": 0, "losses": 0, "profit": 0.0},
        "Breakout": {"wins": 0, "losses": 0, "profit": 0.0},
        "Three Line Strike": {"wins": 0, "losses": 0, "profit": 0.0},
        "Pin Bar + EMA Filter": {"wins": 0, "losses": 0, "profit": 0.0},
        "Rejection Wick": {"wins": 0, "losses": 0, "profit": 0.0},
        "EMA Cross + RSI": {"wins": 0, "losses": 0, "profit": 0.0},
        "Railroad Tracks": {"wins": 0, "losses": 0, "profit": 0.0},
        "BB Squeeze Break": {"wins": 0, "losses": 0, "profit": 0.0},
        "Cassure": {"wins": 0, "losses": 0, "profit": 0.0},
        "Order Block": {"wins": 0, "losses": 0, "profit": 0.0},
    },

    "assets": {}
}