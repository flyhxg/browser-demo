# 0001: Split `signals` into `posts` + `opportunities`

**Status:** Accepted (with the 2026-06-05 auto-LLM signal pipeline spec)

The `signals` table conflated two distinct concepts: the raw social-media Post (text + author + engagement) and the derived trade Opportunity (LLM-extracted token + action + confidence). The LLM auto-pipeline makes the distinction load-bearing — every Post may yield zero or more Opportunities, and many other parts of the system care about one or the other but not both. We rename `signals` → `posts`, introduce an `opportunities` table (1:N from posts, one row per (post, token) pair), and add `token_metric_snapshots` to persist the technical/fundamental context fed to the LLM at decision time.

## Considered Options

- **Keep `signals` as-is, add `is_trade_signal` columns in place.** Rejected: the dual meaning of `signal` is a glossary conflict (CONTEXT.md defines it as a trade opportunity; the table stores posts). Continuing to overload the term makes future queries and UI work ambiguous.
- **Rename `signals` → `posts`, add `opportunities` as a 1:1 child.** Rejected: a single Post mentioning both $SOL and $ETH should be able to produce two Opportunities. The relationship is 1:N, not 1:1.
- **No rename; new `opportunities` table only, with `source_signal_id` FK.** Rejected: leaves the glossary/table mismatch in place; future readers will keep asking "what is a signal?".

## Consequences

- Backwards compatibility: a SQL view `signals AS SELECT * FROM posts` keeps `api/trading.py` and the scheduler reading from `signals` for one migration window, then is dropped once all call sites are updated.
- FKs from `trades.signal_id`, `signal_validation` etc. are not auto-updated by SQLite on rename. They become soft references (column name only, no FK enforcement at insert time — which matches the existing code's read patterns).
- The 113 existing mock/historical rows carry over to `posts` unchanged. They are not LLM-analyzed (only new posts are); backfill is in "Out of scope / Future".
- Every consumer of `signals` must be updated to either `posts` (semantically correct) or `signals` (view, transitional). A grep at migration time ensures no stragglers before the view is dropped.
