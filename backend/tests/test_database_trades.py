import sqlite3

import pytest

from services.database import init_db, insert_trade


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
