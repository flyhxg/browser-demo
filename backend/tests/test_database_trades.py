import sqlite3

import pytest

from services.database import count_open_positions, init_db, insert_trade, list_open_positions


@pytest.fixture
def fresh_db(monkeypatch, tmp_path):
    """Override services.database.DB_PATH to a tmp file and init the schema."""
    db_file = tmp_path / "test_trades.db"
    monkeypatch.setattr("services.database.DB_PATH", db_file)
    init_db()
    yield db_file


def test_insert_trade_persists_row(fresh_db):
    import sqlite3
    conn = sqlite3.connect(str(fresh_db), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    trade_id = insert_trade(
        conn,
        signal_id=1,
        token="BTC",
        side="buy",
        exchange="binance",
        market_type="futures",
        order_id="ord_123",
        quantity=0.5,
        price=50_000.0,
        tp_price=52_500.0,
        sl_price=48_500.0,
    )
    conn.commit()
    row = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
    assert row["signal_id"] == 1
    assert row["token"] == "BTC"
    assert row["side"] == "buy"
    assert row["exchange"] == "binance"
    assert row["market_type"] == "futures"
    assert row["order_id"] == "ord_123"
    assert row["quantity"] == 0.5
    assert row["price"] == 50_000.0
    assert row["tp_price"] == 52_500.0
    assert row["sl_price"] == 48_500.0
    assert row["status"] == "filled"
    conn.close()


def _open_trade(conn, **overrides):
    base = dict(signal_id=None, token="ETH", side="buy", exchange="binance",
                market_type="futures", order_id="o1", quantity=1.0, price=100.0,
                tp_price=105.0, sl_price=97.0, status="filled")
    base.update(overrides)
    tid = insert_trade(conn, **base)
    conn.commit()
    return tid


def test_count_open_positions_zero_when_empty(fresh_db):
    import sqlite3
    conn = sqlite3.connect(str(fresh_db), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    assert count_open_positions(conn) == 0
    conn.close()


def test_count_open_positions_filters_status(fresh_db):
    import sqlite3
    conn = sqlite3.connect(str(fresh_db), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _open_trade(conn)  # status=filled
    _open_trade(conn, order_id="o2", status="closed")
    _open_trade(conn, order_id="o3", status="filled")
    # 'filled' is the post-fill default; treat as open until closed
    assert count_open_positions(conn) == 2
    conn.close()


def test_list_open_positions_returns_dicts(fresh_db):
    import sqlite3
    conn = sqlite3.connect(str(fresh_db), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _open_trade(conn, token="SOL", order_id="o_sol")
    _open_trade(conn, token="AVAX", order_id="o_avax", status="closed")
    rows = list_open_positions(conn)
    assert len(rows) == 1
    assert rows[0]["token"] == "SOL"
    assert rows[0]["order_id"] == "o_sol"
    conn.close()


def test_count_open_positions_excludes_pending(fresh_db):
    """Schema default status='pending' must NOT count as open."""
    import sqlite3
    conn = sqlite3.connect(str(fresh_db), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Insert directly with default status (which is 'pending' per schema)
    conn.execute(
        "INSERT INTO trades (token, side, quantity) VALUES (?, ?, ?)",
        ("BTC", "buy", 0.1),
    )
    conn.commit()
    assert count_open_positions(conn) == 0
    conn.close()


def test_list_open_positions_orders_by_created_at_desc(fresh_db):
    """list_open_positions must order newest first."""
    import sqlite3
    conn = sqlite3.connect(str(fresh_db), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Insert 3 trades, then backdate them with explicit created_at
    for i, ts in enumerate([1000, 2000, 3000]):
        _open_trade(conn, token=f"T{i}", order_id=f"o{i}")
        conn.execute("UPDATE trades SET created_at = ? WHERE order_id = ?", (ts, f"o{i}"))
    conn.commit()
    rows = list_open_positions(conn)
    assert [r["order_id"] for r in rows] == ["o2", "o1", "o0"]
    conn.close()
