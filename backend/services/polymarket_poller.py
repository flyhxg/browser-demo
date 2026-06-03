"""Polymarket Top Users Poller.

Polls top 200 traders and aggregates their trades into cluster signals.
"""
import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from services.polymarket_data_api import PolymarketDataApiClient

logger = logging.getLogger(__name__)


@dataclass
class AggregatedPosition:
    """Aggregated trades for a market/outcome/side."""

    market_slug: str
    question: str
    side: str
    outcome: str
    token_id: str
    condition_id: str
    total_amount: float
    total_value: float
    unique_users: int
    avg_price: float
    contributors: list[dict[str, Any]]


@dataclass
class ClusterSignal:
    """Detected cluster signal from top traders."""

    market_slug: str
    question: str
    side: str
    outcome: str
    token_id: str
    condition_id: str
    total_amount: float
    total_value: float
    unique_users: int
    avg_price: float
    confidence: float
    net_inflow: float
    direction: str
    detected_at: float = field(default_factory=time.time)


class TopUsersPoller:
    """Poll top traders and emit cluster signals."""

    def __init__(
        self,
        poll_interval: int = 60,
        leaderboard_limit: int = 200,
        positions_limit: int = 20,
        cluster_min_users: int = 3,
        cluster_min_value: float = 1000.0,
        market_expiry_hours: int = 6,
        min_price: float = 0.01,
        max_price: float = 0.99,
    ) -> None:
        self.data_api = PolymarketDataApiClient()
        self.poll_interval = poll_interval
        self.leaderboard_limit = leaderboard_limit
        self.positions_limit = positions_limit
        self.cluster_min_users = cluster_min_users
        self.cluster_min_value = cluster_min_value
        self.market_expiry_hours = market_expiry_hours
        self.min_price = min_price
        self.max_price = max_price

        self._running = False
        self._poll_task: Optional[asyncio.Task] = None
        self._top_users: list[dict[str, Any]] = []
        self._signal_cache: dict[str, float] = {}
        self._signal_cache_ttl = 300  # 5 minutes
        self._handlers: list = []

    def on_signal(self, handler: callable) -> None:
        """Register a signal handler."""
        self._handlers.append(handler)

    async def start(self) -> None:
        """Start the poller."""
        if self._running:
            return
        self._running = True
        await self._refresh_leaderboard()
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("TopUsersPoller started | interval=%ds | leaderboard_limit=%d", self.poll_interval, self.leaderboard_limit)

    async def stop(self) -> None:
        """Stop the poller."""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        await self.data_api.close()
        logger.info("TopUsersPoller stopped")

    async def _poll_loop(self) -> None:
        """Main polling loop."""
        while self._running:
            try:
                await asyncio.sleep(self.poll_interval)
                await self._poll_all_trades()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Poll loop error: %s", e)

    async def _refresh_leaderboard(self) -> None:
        """Refresh top traders list."""
        logger.info("Refreshing leaderboard...")
        all_traders: list[dict[str, Any]] = []
        limit = 50
        pages = self.leaderboard_limit // limit

        for page in range(pages):
            offset = page * limit
            traders = await self.data_api.get_leaderboard(
                limit=limit,
                offset=offset,
                order_by="PNL",
            )
            if not traders:
                break
            all_traders.extend(traders)
            if len(traders) < limit:
                break

        self._top_users = [
            {"address": t.get("proxyWallet", ""), "username": t.get("userName", "")}
            for t in all_traders
            if t.get("proxyWallet")
        ]
        logger.info("Leaderboard refreshed: %d users", len(self._top_users))

    async def _poll_all_trades(self) -> None:
        """Poll trades for all top users."""
        if not self._top_users:
            return

        now = datetime.now(timezone.utc)
        start_ts = int((now - datetime.timedelta(seconds=self.poll_interval + 10)).timestamp())

        semaphore = asyncio.Semaphore(20)
        all_trades: list[dict[str, Any]] = []

        async def _poll_user(user: dict[str, Any]) -> list[dict[str, Any]]:
            async with semaphore:
                try:
                    trades = await asyncio.wait_for(
                        self.data_api.get_user_activity(
                            user=user["address"],
                            limit=self.positions_limit,
                            start=start_ts,
                            sort_by="TIMESTAMP",
                            sort_direction="DESC",
                        ),
                        timeout=30.0,
                    )
                    return trades if trades else []
                except asyncio.TimeoutError:
                    return []
                except Exception as e:
                    logger.debug("Poll user %s error: %s", user["address"][:10], e)
                    return []

        results = await asyncio.gather(*[_poll_user(u) for u in self._top_users])
        for trades in results:
            if trades:
                all_trades.extend(trades)

        if all_trades:
            await self._process_trades(all_trades)

    async def _process_trades(self, trades: list[dict[str, Any]]) -> None:
        """Process trades and emit signals."""
        # Step 1: Aggregate by (market_slug, side, outcome)
        aggregated = self._aggregate_trades(trades)

        # Step 2: Calculate net inflow per market/outcome
        market_data: dict[str, dict[str, Any]] = {}
        for agg in aggregated:
            key = f"{agg.market_slug}:{agg.outcome}"
            if key not in market_data:
                market_data[key] = {
                    "buy_value": 0.0,
                    "sell_value": 0.0,
                    "buy_agg": None,
                    "sell_agg": None,
                    "market_slug": agg.market_slug,
                    "outcome": agg.outcome,
                    "condition_id": agg.condition_id,
                    "token_id": agg.token_id,
                }

            data = market_data[key]
            if agg.side == "BUY":
                data["buy_value"] += agg.total_value
                if data["buy_agg"] is None or agg.total_value > data["buy_agg"].total_value:
                    data["buy_agg"] = agg
            else:
                data["sell_value"] += agg.total_value
                if data["sell_agg"] is None or agg.total_value > data["sell_agg"].total_value:
                    data["sell_agg"] = agg

        # Step 3: Check thresholds and emit signals
        for key, data in market_data.items():
            net_inflow = data["buy_value"] - data["sell_value"]
            buy_users = data["buy_agg"].unique_users if data["buy_agg"] else 0
            sell_users = data["sell_agg"].unique_users if data["sell_agg"] else 0
            total_users = buy_users + sell_users

            if abs(net_inflow) < self.cluster_min_value:
                continue
            if total_users < self.cluster_min_users:
                continue

            # Price check on the dominant side
            price_check_agg = data["buy_agg"] if net_inflow > 0 else data["sell_agg"]
            if price_check_agg and not (self.min_price <= price_check_agg.avg_price <= self.max_price):
                continue

            direction = "BUY" if net_inflow > 0 else "SELL"
            signal_agg = data["buy_agg"] if net_inflow > 0 else data["sell_agg"]
            if signal_agg is None:
                continue

            # Deduplicate
            cache_key = f"{data['market_slug']}:{direction}"
            if self._is_duplicate(cache_key):
                continue
            self._mark_sent(cache_key)

            signal = ClusterSignal(
                market_slug=data["market_slug"],
                question=signal_agg.question,
                side=direction,
                outcome=data["outcome"],
                token_id=data["token_id"],
                condition_id=data["condition_id"],
                total_amount=signal_agg.total_amount,
                total_value=abs(net_inflow),
                unique_users=total_users,
                avg_price=signal_agg.avg_price,
                confidence=min(total_users / 10, 1.0),
                net_inflow=net_inflow,
                direction=direction,
            )

            await self._emit_signal(signal)

    def _aggregate_trades(self, trades: list[dict[str, Any]]) -> list[AggregatedPosition]:
        """Aggregate raw trades by (market_slug, side, outcome)."""
        groups: dict[tuple, dict[str, Any]] = defaultdict(lambda: {
            "market_slug": "", "side": "", "outcome": "", "token_id": "", "condition_id": "",
            "amounts": [], "values": [], "contributors": [], "prices_sum": 0.0,
        })

        for trade in trades:
            slug = trade.get("slug", trade.get("marketSlug", "unknown"))
            side = trade.get("side", "BUY")
            outcome = trade.get("outcome", "YES")
            token_id = trade.get("assetId", trade.get("tokenId", ""))
            condition_id = trade.get("conditionId", "")
            size = float(trade.get("size", 0))
            price = float(trade.get("price", 0))
            value = size * price
            user = trade.get("proxyWallet", trade.get("user", ""))

            key = (slug, side, outcome)
            g = groups[key]
            g["market_slug"] = slug
            g["side"] = side
            g["outcome"] = outcome
            g["token_id"] = token_id
            g["condition_id"] = condition_id
            g["question"] = trade.get("question", trade.get("marketQuestion", slug))
            g["amounts"].append(size)
            g["values"].append(value)
            g["prices_sum"] += price
            g["contributors"].append({"user": user, "amount": size, "value": value})

        result = []
        for key, g in groups.items():
            total_amount = sum(g["amounts"])
            total_value = sum(g["values"])
            unique_users = len(set(c["user"] for c in g["contributors"]))
            avg_price = g["prices_sum"] / len(g["amounts"]) if g["amounts"] else 0
            result.append(AggregatedPosition(
                market_slug=g["market_slug"],
                question=g["question"],
                side=g["side"],
                outcome=g["outcome"],
                token_id=g["token_id"],
                condition_id=g["condition_id"],
                total_amount=total_amount,
                total_value=total_value,
                unique_users=unique_users,
                avg_price=avg_price,
                contributors=g["contributors"],
            ))
        return result

    def _is_duplicate(self, key: str) -> bool:
        last = self._signal_cache.get(key, 0)
        if time.time() - last < self._signal_cache_ttl:
            return True
        return False

    def _mark_sent(self, key: str) -> None:
        self._signal_cache[key] = time.time()

    async def _emit_signal(self, signal: ClusterSignal) -> None:
        """Emit signal to all handlers."""
        logger.info(
            "ClusterSignal | %s | %s | net=$%.2f | users=%d | price=%.3f | conf=%.1f%%",
            signal.market_slug, signal.direction, signal.net_inflow,
            signal.unique_users, signal.avg_price, signal.confidence * 100,
        )
        for handler in self._handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    asyncio.create_task(handler(signal))
                else:
                    handler(signal)
            except Exception as e:
                logger.error("Signal handler error: %s", e)
