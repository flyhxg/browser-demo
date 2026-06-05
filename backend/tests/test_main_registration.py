"""Verify main.py's module-level code registers both schedulers.

main.py constructs `SignalScanScheduler` and (after Task 6) `PolymarketScheduler`
at import time and calls `register()` on each. This is the wiring that lets
`api/workflow.py` and `api/polymarket.py` look up the schedulers via the
registry. If main.py ever stops registering one of them, the operator's
`/api/polymarket/start` will 503 silently.

Approach: import the `main` module to trigger its module-level code, then
introspect the registry. Each test starts with `_reset_registry()` and
restores it on teardown so the test is hermetic w.r.t. the order pytest
collects tests in.

The test is intentionally small: anything fancier (mocking out the scraper,
replacing `handle_cluster_signal`, etc.) is not needed because main.py's
module-level code is cheap:
  - `BinanceSquareScraper()` is a no-op class — no I/O.
  - `SignalScanScheduler(...)` and `PolymarketScheduler(...)` constructors
    only stash their args; no network calls.
  - `init_db()` runs idempotent schema migrations on the SQLite file.
  - `get_config()` reads `config.json` (or returns defaults).
None of these block on a live network or DB roundtrip.
"""
import importlib
import sys

import pytest

from services.scheduler import (
    _reset_registry,
    get_scheduler,
    get_schedulers,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    """Reset the scheduler registry around each test.

    The registry is a module-level list in `services.scheduler`. Without
    this fixture, tests run in alphabetical order, so a test that imports
    `main` would leak its registered schedulers into the next test.
    """
    _reset_registry()
    yield
    _reset_registry()


def _fresh_main():
    """Import main.py, bypassing any cached module from a prior test.

    pytest's import caching means a second `import main` returns the
    same module object without re-running its module-level code. We need
    the module-level registration to actually fire for each test, so we
    drop the cached entry first.
    """
    sys.modules.pop("main", None)
    return importlib.import_module("main")


def test_main_module_registers_both_schedulers():
    """Importing main.py must register both SignalScanScheduler and PolymarketScheduler.

    The registry must contain exactly two entries (SignalScanScheduler,
    PolymarketScheduler). It must NOT contain duplicates — `register()` is
    idempotent by TASK_ID, but if main.py's module-level code ever calls
    `register()` twice for the same scheduler, the second call is a no-op
    and the registry stays at 2.
    """
    _fresh_main()

    schedulers = get_schedulers()
    assert len(schedulers) == 2, (
        f"Expected 2 registered schedulers, got {len(schedulers)}: "
        f"{[s.TASK_NAME for s in schedulers]}"
    )

    signal = get_scheduler(1)
    assert signal is not None, "SignalScanScheduler (task_id=1) was not registered"
    assert signal.TASK_NAME == "Signal Scanner"

    poly = get_scheduler(2)
    assert poly is not None, "PolymarketScheduler (task_id=2) was not registered"
    assert poly.TASK_NAME == "Polymarket Poller"


def test_main_module_idempotent_under_reimport():
    """Re-importing main.py must not add a 3rd scheduler to the registry.

    The registry is idempotent by TASK_ID (see `register()`'s docstring),
    so even if the module-level code runs twice (e.g. `python main.py`
    then uvicorn's auto-reload), the second pass is a no-op for already-
    registered task_ids. This is what prevents the double-`start()` bug.
    """
    _fresh_main()
    count_after_first = len(get_schedulers())
    assert count_after_first == 2

    # Force re-execution of the module-level code.
    importlib.reload(sys.modules["main"])
    count_after_reload = len(get_schedulers())

    assert count_after_reload == count_after_first, (
        f"Re-importing main grew the registry: "
        f"{count_after_first} -> {count_after_reload} "
        f"({[s.TASK_NAME for s in get_schedulers()]})"
    )


def test_main_module_constructs_polymarket_scheduler_with_signal_handler():
    """The registered PolymarketScheduler must have its signal handler wired.

    `main.py` constructs the scheduler with `signal_handler=handle_cluster_signal`
    (the function from `api.polymarket` that persists + auto-executes signals).
    If this binding ever breaks, the poller will detect clusters but never
    persist them — the `polymarket_signals` table would stay empty.
    """
    from api.polymarket import handle_cluster_signal

    _fresh_main()

    poly = get_scheduler(2)
    assert poly is not None
    assert poly._signal_handler is handle_cluster_signal, (
        "PolymarketScheduler._signal_handler was not wired to "
        "api.polymarket.handle_cluster_signal"
    )


def test_main_module_signal_scheduler_has_ws_broadcast():
    """The registered SignalScanScheduler must have its ws_broadcast wired.

    This is a regression check for the existing wiring: the scheduler's
    `_ws_broadcast` callable fans scraped posts out over WebSocket so the
    UI can update in real-time. If a future refactor drops the
    `ws_broadcast=_ws_relay` kwarg, scraped posts stop showing up live.
    """
    _fresh_main()

    signal = get_scheduler(1)
    assert signal is not None
    assert callable(signal._ws_broadcast), (
        "SignalScanScheduler._ws_broadcast is not callable — "
        "ws fan-out is broken"
    )
