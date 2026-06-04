from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from services.short_selling_engine import ShortSellingEngine
from services.event_pipeline import EventPipeline

router = APIRouter(prefix="/api/analyze", tags=["analysis"])
engine = ShortSellingEngine()

class AnalyzeShortRequest(BaseModel):
    symbol: str
    dimensions: Optional[List[str]] = None
    timeframe: Optional[str] = "24h"
    include_recommendation: Optional[bool] = True

class CompareRequest(BaseModel):
    symbols: List[str]
    dimensions: Optional[List[str]] = None
    sort_by: Optional[str] = None

class AnalyzeEventsRequest(BaseModel):
    symbol: str
    time_range: Optional[str] = "24h"

@router.post("/short")
async def analyze_short(req: AnalyzeShortRequest):
    try:
        report = await engine.analyze(req.symbol, dimensions=req.dimensions, timeframe=req.timeframe)
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/compare")
async def analyze_compare(req: CompareRequest):
    try:
        result = await engine.compare(req.symbols, dimensions=req.dimensions)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/report/{symbol}")
async def get_cached_report(symbol: str):
    from services.database import get_db
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM analysis_reports WHERE symbol = ? ORDER BY created_at DESC LIMIT 1",
            (symbol.upper(),),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="No report found for token")
        return dict(row)
    finally:
        conn.close()

@router.post("/events")
async def analyze_events(req: AnalyzeEventsRequest):
    """Run the event-causality pipeline for a single symbol.

    Returns a structured event timeline + LLM-written causal narrative
    with a confidence score. Combines news (CoinDesk + The Block via
    Playwright), social (Binance Square top-N hottest), on-chain
    (whale transfers), and derivatives (liquidations + funding rate
    shifts) into one response.
    """
    valid_ranges = {"1h", "4h", "24h", "7d"}
    if req.time_range not in valid_ranges:
        raise HTTPException(
            status_code=400,
            detail=f"time_range must be one of {sorted(valid_ranges)}",
        )
    if not req.symbol or not req.symbol.strip():
        raise HTTPException(status_code=400, detail="symbol is required")

    pipeline = EventPipeline()
    return await pipeline.run(req.symbol.upper(), req.time_range)
