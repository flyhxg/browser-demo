"""Database models and connection management."""
import json
import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).parent.parent / "data" / "trading.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_db() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize the database with all tables."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            source_url TEXT,
            author TEXT,
            content TEXT NOT NULL,
            likes INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0,
            raw_data TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signal_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id INTEGER NOT NULL,
            token TEXT NOT NULL,
            sentiment TEXT,
            confidence REAL,
            reasoning TEXT,
            llm_model TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (signal_id) REFERENCES signals(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signal_validation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id INTEGER NOT NULL,
            token TEXT NOT NULL,
            cg_market_cap_rank INTEGER,
            cg_price_change_24h REAL,
            okx_funding_rate REAL,
            hyperliquid_funding REAL,
            validation_result TEXT,
            fail_reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (signal_id) REFERENCES signals(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id INTEGER,
            token TEXT NOT NULL,
            side TEXT NOT NULL,
            exchange TEXT DEFAULT 'binance',
            market_type TEXT,
            order_id TEXT,
            quantity REAL,
            price REAL,
            tp_price REAL,
            sl_price REAL,
            status TEXT DEFAULT 'pending',
            pnl REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (signal_id) REFERENCES signals(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trading_config (
            id INTEGER PRIMARY KEY,
            binance_api_key TEXT,
            binance_secret_key TEXT,
            use_testnet INTEGER DEFAULT 1,
            max_position_size_usd REAL DEFAULT 100.0,
            max_positions INTEGER DEFAULT 5,
            tp_percentage REAL DEFAULT 5.0,
            sl_percentage REAL DEFAULT 3.0,
            min_confidence REAL DEFAULT 0.7,
            max_daily_loss REAL DEFAULT 100.0,
            scan_interval_minutes INTEGER DEFAULT 5
        )
    """)

    cursor.execute("SELECT COUNT(*) FROM trading_config")
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            "INSERT INTO trading_config (id) VALUES (1)"
        )

    # ---- Polymarket Prediction Market tables ----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS polymarket_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id TEXT UNIQUE NOT NULL,
            market_slug TEXT NOT NULL,
            question TEXT,
            outcome TEXT NOT NULL,
            side TEXT NOT NULL,
            token_id TEXT NOT NULL,
            condition_id TEXT NOT NULL,
            avg_price REAL,
            total_value REAL DEFAULT 0.0,
            unique_users INTEGER DEFAULT 0,
            confidence REAL DEFAULT 0.0,
            net_inflow REAL DEFAULT 0.0,
            status TEXT DEFAULT 'pending',
            executed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS polymarket_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            position_id TEXT UNIQUE NOT NULL,
            signal_id TEXT,
            token_id TEXT NOT NULL,
            condition_id TEXT NOT NULL,
            market_slug TEXT NOT NULL,
            question TEXT,
            outcome TEXT NOT NULL,
            side TEXT NOT NULL,
            entry_price REAL NOT NULL,
            current_price REAL,
            size REAL NOT NULL,
            entry_amount REAL NOT NULL,
            highest_price REAL,
            lowest_price REAL,
            stop_loss_price REAL,
            take_profit_price REAL,
            status TEXT DEFAULT 'open',
            pnl REAL DEFAULT 0.0,
            pnl_pct REAL DEFAULT 0.0,
            close_price REAL,
            close_reason TEXT,
            opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            closed_at TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS polymarket_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id TEXT UNIQUE NOT NULL,
            signal_id TEXT,
            position_id TEXT,
            token_id TEXT NOT NULL,
            condition_id TEXT NOT NULL,
            market_slug TEXT NOT NULL,
            outcome TEXT NOT NULL,
            side TEXT NOT NULL,
            price REAL NOT NULL,
            size REAL NOT NULL,
            amount REAL NOT NULL,
            fee REAL DEFAULT 0.0,
            status TEXT DEFAULT 'pending',
            order_id TEXT,
            filled_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS polymarket_config (
            id INTEGER PRIMARY KEY,
            api_key TEXT,
            api_secret TEXT,
            api_passphrase TEXT,
            private_key TEXT,
            dry_run INTEGER DEFAULT 1,
            poll_interval INTEGER DEFAULT 60,
            cluster_min_users INTEGER DEFAULT 3,
            cluster_min_value REAL DEFAULT 1000.0,
            min_price REAL DEFAULT 0.01,
            max_price REAL DEFAULT 0.99,
            market_expiry_hours INTEGER DEFAULT 6,
            sl_percentage REAL DEFAULT 0.15,
            tp_percentage REAL DEFAULT 0.05,
            auto_execute_threshold REAL DEFAULT 0.7,
            enabled INTEGER DEFAULT 0
        )
    """)

    cursor.execute("SELECT COUNT(*) FROM polymarket_config")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO polymarket_config (id) VALUES (1)")

    # ---- Hot Tokens tables ----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hot_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            price REAL DEFAULT 0,
            price_change_24h REAL DEFAULT 0,
            volume_24h REAL DEFAULT 0,
            volume_usd REAL DEFAULT 0,
            funding_rate REAL DEFAULT 0,
            long_short_ratio REAL DEFAULT 0,
            open_interest REAL DEFAULT 0,
            liquidation_price REAL DEFAULT 0,
            heat_score REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ---- Chat Sessions ----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            tool_calls TEXT,
            thinking_steps TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
    """)

    conn.commit()
    conn.close()


def dict_from_row(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a sqlite Row to a dict."""
    return {key: row[key] for key in row.keys()}
