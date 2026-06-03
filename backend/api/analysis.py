from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from services.short_selling_engine import ShortSellingEngine

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
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM analysis_reports WHERE symbol = ? ORDER BY created_at DESC LIMIT 1",
        (symbol.upper(),),
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No report found for token")
    return dict(row)
