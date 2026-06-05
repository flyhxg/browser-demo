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


def test_signals_source_type_backfills_mock_authors():
    """Mock seed authors must be classified 'mock' after init_db(), not 'live'.

    Regression: SQLite's ALTER TABLE ADD COLUMN ... DEFAULT 'live' populates
    existing rows with the default value, not NULL, so a guard of
    `AND source_type IS NULL` would make the backfill a no-op. This test
    inserts a row with source_type='live' (the post-ALTER default state)
    and asserts that init_db() re-classifies the known mock author as 'mock'.
    """
    import uuid

    from services.database import get_db, init_db

    # Use unique source_urls so we don't collide with existing rows.
    suffix = uuid.uuid4().hex[:8]
    authors = ("TraderOne", "CryptoWhale", "BearHunter")
    init_db()
    conn = get_db()
    try:
        for author in authors:
            conn.execute(
                """
                INSERT INTO signals (source, source_url, author, content,
                                     likes, comments, status, source_type)
                VALUES (?, ?, ?, ?, 0, 0, 'pending', 'live')
                """,
                ("mock", f"https://test/{author}/{suffix}", author, f"seed {author}"),
            )
        conn.commit()
        init_db()
        rows = conn.execute(
            "SELECT author, source_type FROM signals WHERE source_url LIKE ?",
            (f"https://test/%/{suffix}",),
        ).fetchall()
        assert len(rows) == 3, f"expected 3 seed rows, got {len(rows)}"
        for r in rows:
            assert r["source_type"] == "mock", (
                f"author {r['author']} should be 'mock' but is {r['source_type']!r}"
            )
    finally:
        conn.execute("DELETE FROM signals WHERE source_url LIKE ?",
                     (f"https://test/%/{suffix}",))
        conn.commit()
        conn.close()


def test_signals_source_url_unique_index_exists():
    """idx_signals_source_url must exist and be unique for dedup to work."""
    from services.database import get_db, init_db
    init_db()
    conn = get_db()
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name='idx_signals_source_url'"
    ).fetchone()
    conn.close()
    assert row is not None, "idx_signals_source_url index missing"
    assert "UNIQUE" in row["sql"], "index is not unique"
    assert "source_url" in row["sql"], "index is not on source_url column"
