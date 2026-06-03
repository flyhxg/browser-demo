import pytest
from services.database import get_db, init_db


def test_analysis_reports_table_exists():
    init_db()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='analysis_reports'"
    )
    assert cursor.fetchone() is not None
    conn.close()


def test_analysis_metrics_table_exists():
    init_db()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='analysis_metrics'"
    )
    assert cursor.fetchone() is not None
    conn.close()


def test_token_memories_table_exists():
    init_db()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='token_memories'"
    )
    assert cursor.fetchone() is not None
    conn.close()


def test_analysis_reports_insert_and_read():
    init_db()
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO analysis_reports (
            symbol, dimensions, timeframe, request_type, raw_data,
            llm_summary, strengths, risks, confidence, recommendation,
            time_horizon, version, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "BTCUSDT",
        "price,volume,liquidity",
        "24h",
        "single",
        '{"price": 65000}',
        "Bullish momentum building.",
        "Strong uptrend, high volume.",
        "Possible correction after rally.",
        0.85,
        "buy",
        "medium",
        1,
        "completed",
    ))

    report_id = cursor.lastrowid
    conn.commit()

    cursor.execute(
        "SELECT * FROM analysis_reports WHERE id = ?", (report_id,)
    )
    row = cursor.fetchone()
    assert row is not None
    assert row["symbol"] == "BTCUSDT"
    assert row["dimensions"] == "price,volume,liquidity"
    assert row["timeframe"] == "24h"
    assert row["request_type"] == "single"
    assert row["raw_data"] == '{"price": 65000}'
    assert row["llm_summary"] == "Bullish momentum building."
    assert row["strengths"] == "Strong uptrend, high volume."
    assert row["risks"] == "Possible correction after rally."
    assert row["confidence"] == 0.85
    assert row["recommendation"] == "buy"
    assert row["time_horizon"] == "medium"
    assert row["version"] == 1
    assert row["status"] == "completed"
    assert row["created_at"] is not None

    conn.close()
