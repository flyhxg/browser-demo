"""Database models and connection management."""
import json
import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).parent.parent / "data" / "trading.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# A trade with status='filled' is considered "open" until it transitions to 'closed'.
OPEN_TRADE_STATUS = "filled"


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

    # Migration: add source_type column (idempotent)
    cursor.execute("PRAGMA table_info(signals)")
    sig_cols = {row[1] for row in cursor.fetchall()}
    if "source_type" not in sig_cols:
        cursor.execute("ALTER TABLE signals ADD COLUMN source_type TEXT DEFAULT 'live'")
        # Backfill known mock authors
        cursor.execute(
            "UPDATE signals SET source_type = 'mock' "
            "WHERE author IN ('TraderOne', 'CryptoWhale', 'BearHunter') "
            "AND source_type IS NULL"
        )

    # Dedup existing rows by source_url before adding the unique index.
    # Pre-existing mock data may have repeated (source_url) values that
    # would block index creation. Keep the earliest row per source_url;
    # Task 8's INSERT OR IGNORE prevents this from recurring.
    # Idempotent: a no-op once the table is already deduped.
    cursor.execute(
        """
        DELETE FROM signals
        WHERE id NOT IN (
            SELECT MIN(id) FROM signals
            WHERE source_url IS NOT NULL AND source_url != ''
            GROUP BY source_url
        )
        AND source_url IS NOT NULL AND source_url != ''
        """
    )

    # Unique index on source_url for dedup (idempotent)
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_signals_source_url "
        "ON signals(source_url) WHERE source_url != ''"
    )

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
            scan_interval_minutes INTEGER DEFAULT 30
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

    # ---- Analysis Reports ----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analysis_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            dimensions TEXT,
            timeframe TEXT DEFAULT '24h',
            request_type TEXT DEFAULT 'single',
            raw_data TEXT,
            llm_summary TEXT,
            strengths TEXT,
            risks TEXT,
            confidence REAL,
            recommendation TEXT,
            time_horizon TEXT,
            version INTEGER DEFAULT 1,
            status TEXT DEFAULT 'completed',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analysis_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id INTEGER NOT NULL,
            dimension TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            metric_value REAL,
            metric_unit TEXT,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (report_id) REFERENCES analysis_reports(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS token_memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL UNIQUE,
            first_queried TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_queried TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_interests TEXT,
            key_levels TEXT,
            related_sectors TEXT,
            notes TEXT,
            analysis_history TEXT
        )
    """)

    # Migration: drop dead polymarket SL/TP columns. These were previously
    # editable via /api/polymarket/config but have been hardcoded in
    # RiskConfig.polymarket() (sl_pct=0.15, tp_pct=0.05) since the trading-
    # engine-risk refactor. Idempotent via PRAGMA table_info check.
    cursor.execute("PRAGMA table_info(polymarket_config)")
    poly_cols = {row[1] for row in cursor.fetchall()}
    for col in ("sl_percentage", "tp_percentage"):
        if col in poly_cols:
            cursor.execute(f"ALTER TABLE polymarket_config DROP COLUMN {col}")

    # Migration: drop dead max_positions column. The config_store's
    # max_open_positions is the source-of-truth (read by RiskConfig.from_config_store).
    # The DB column was never read by any runtime code path, only written via
    # /api/trading/config (dead write). Idempotent via PRAGMA table_info check.
    cursor.execute("PRAGMA table_info(trading_config)")
    trade_cols = {row[1] for row in cursor.fetchall()}
    if "max_positions" in trade_cols:
        cursor.execute("ALTER TABLE trading_config DROP COLUMN max_positions")

    # Migration: add scheduler config columns for Phase 2.4 SignalScanScheduler.
    # Defaults: signal_scan_enabled=0 (kill switch off — first-deploy safe),
    # signal_scan_interval_minutes=30 (matches the design's spec default — public
    # scrape cadence, not minute-level).
    # Idempotent via PRAGMA table_info check (same pattern as the
    # max_positions / polymarket SL/TP migrations above).
    if "signal_scan_enabled" not in trade_cols:
        cursor.execute(
            "ALTER TABLE trading_config ADD COLUMN signal_scan_enabled INTEGER DEFAULT 0"
        )
    if "signal_scan_interval_minutes" not in trade_cols:
        cursor.execute(
            "ALTER TABLE trading_config ADD COLUMN signal_scan_interval_minutes INTEGER DEFAULT 30"
        )

    conn.commit()
    conn.close()


def dict_from_row(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a sqlite Row to a dict."""
    return {key: row[key] for key in row.keys()}


def insert_trade(
    conn: sqlite3.Connection,
    signal_id: int | None,
    token: str,
    side: str,
    exchange: str,
    market_type: str,
    order_id: str,
    quantity: float,
    price: float,
    tp_price: float,
    sl_price: float,
    status: str = OPEN_TRADE_STATUS,
) -> int:
    """Insert a trade row, return the new trade id. Caller commits."""
    cursor = conn.execute(
        """
        INSERT INTO trades (signal_id, token, side, exchange, market_type, order_id,
                            quantity, price, tp_price, sl_price, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (signal_id, token, side, exchange, market_type, order_id,
         quantity, price, tp_price, sl_price, status),
    )
    return cursor.lastrowid


def count_open_positions(conn: sqlite3.Connection) -> int:
    """Count trades currently in 'filled' state (i.e. not yet closed)."""
    cursor = conn.execute(
        "SELECT COUNT(*) FROM trades WHERE status = ?",
        (OPEN_TRADE_STATUS,),
    )
    return cursor.fetchone()[0]


def list_open_positions(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return all currently-open positions as dicts."""
    cursor = conn.execute(
        "SELECT * FROM trades WHERE status = ? ORDER BY created_at DESC",
        (OPEN_TRADE_STATUS,),
    )
    return [dict_from_row(row) for row in cursor.fetchall()]
