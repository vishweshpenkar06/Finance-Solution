from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from app.core.database import get_db
from app.services.stock_data_service import StockDataService

router = APIRouter()

class StockInfo(BaseModel):
    symbol: str
    name: Optional[str]
    sector: Optional[str]
    industry: Optional[str]
    market_cap: Optional[float]

class StockPriceData(BaseModel):
    timestamp: str
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: Optional[float]
    volume: Optional[int]

class StockResponse(StockInfo):
    id: int
    
    class Config:
        from_attributes = True

@router.post("/ingest/{symbol}")
async def ingest_stock(symbol: str, db: Session = Depends(get_db)):
    """Ingest stock data from external sources"""
    service = StockDataService(db)
    stock = await service.ingest_stock(symbol)
    
    if not stock:
        raise HTTPException(status_code=400, detail=f"Failed to ingest stock: {symbol}")
    
    return {
        "success": True,
        "stock": {
            "id": stock.id,
            "symbol": stock.symbol,
            "name": stock.name
        }
    }

@router.post("/batch-ingest")
async def batch_ingest_stocks(symbols: List[str], db: Session = Depends(get_db)):
    """Ingest multiple stocks at once"""
    service = StockDataService(db)
    results = await service.batch_ingest(symbols)
    
    return {
        "success": results["success"],
        "failed": results["failed"],
        "total": len(symbols)
    }

@router.get("/", response_model=List[StockResponse])
def list_stocks(
    sector: Optional[str] = None,
    skip: int = 0, 
    limit: int = 100, 
    db: Session = Depends(get_db)
):
    """List all stocks in database"""
    from app.models.stock import Stock
    
    query = db.query(Stock)
    if sector:
        query = query.filter(Stock.sector == sector)
    
    stocks = query.offset(skip).limit(limit).all()
    return stocks

@router.get("/{symbol}", response_model=StockResponse)
def get_stock(symbol: str, db: Session = Depends(get_db)):
    """Get stock by symbol"""
    from app.models.stock import Stock
    
    stock = db.query(Stock).filter(Stock.symbol == symbol.upper()).first()
    if not stock:
        raise HTTPException(status_code=404, detail="Stock not found")
    
    return stock

@router.get("/{symbol}/prices")
def get_stock_prices(
    symbol: str, 
    days: int = Query(default=30, le=365),
    db: Session = Depends(get_db)
):
    """Get historical prices for a stock"""
    from app.models.stock import Stock, StockPrice
    from datetime import datetime, timedelta
    
    stock = db.query(Stock).filter(Stock.symbol == symbol.upper()).first()
    if not stock:
        raise HTTPException(status_code=404, detail="Stock not found")
    
    cutoff = datetime.utcnow() - timedelta(days=days)
    prices = db.query(StockPrice).filter(
        StockPrice.stock_id == stock.id,
        StockPrice.timestamp >= cutoff
    ).order_by(StockPrice.timestamp.desc()).all()
    
    return [{
        "timestamp": p.timestamp.isoformat(),
        "open": float(p.open_price) if p.open_price else None,
        "high": float(p.high_price) if p.high_price else None,
        "low": float(p.low_price) if p.low_price else None,
        "close": float(p.close_price) if p.close_price else None,
        "volume": p.volume,
    } for p in prices]

@router.get("/{symbol}/metrics")
def get_stock_metrics(symbol: str, db: Session = Depends(get_db)):
    """Get calculated risk/return metrics for a stock"""
    from app.models.stock import Stock
    from app.services.portfolio_service import PortfolioService
    
    stock = db.query(Stock).filter(Stock.symbol == symbol.upper()).first()
    if not stock:
        raise HTTPException(status_code=404, detail="Stock not found")
    
    service = PortfolioService(db)
    metrics = service.calculate_stock_metrics(stock.id)
    
    if not metrics:
        raise HTTPException(status_code=400, detail="Insufficient data to calculate metrics")
    
    return {
        "symbol": stock.symbol,
        "name": stock.name,
        "sector": stock.sector,
        **metrics
    }
