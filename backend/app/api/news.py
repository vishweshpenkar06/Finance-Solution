from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from app.core.database import get_db
from app.services.news_service import NewsService

router = APIRouter()

class SentimentSummary(BaseModel):
    count: int
    average_sentiment: float
    sentiment_distribution: dict
    summary: str

class ArticleResponse(BaseModel):
    id: int
    title: str
    content: Optional[str]
    source: Optional[str]
    url: Optional[str]
    published_at: Optional[str]
    sentiment_score: Optional[float]
    sentiment_label: Optional[str]
    related_symbols: Optional[str]
    
    class Config:
        from_attributes = True

@router.post("/ingest")
async def ingest_news(
    query: Optional[str] = None,
    page_size: int = Query(default=50, le=100),
    db: Session = Depends(get_db)
):
    """Ingest news articles from external sources"""
    service = NewsService(db)
    result = await service.ingest_news(query, page_size)
    
    return result

@router.get("/sentiment")
def get_sentiment_summary(
    symbol: Optional[str] = None,
    hours: int = Query(default=24, ge=1, le=168),
    db: Session = Depends(get_db)
):
    """Get sentiment summary for recent news"""
    service = NewsService(db)
    summary = service.get_sentiment_summary(symbol, hours)
    
    return summary

@router.get("/")
def list_news(
    symbol: Optional[str] = None,
    sentiment: Optional[str] = None,
    hours: int = Query(default=48, ge=1, le=168),
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """List news articles with optional filters"""
    from app.models.news import NewsArticle
    from datetime import datetime, timedelta
    
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    
    query = db.query(NewsArticle).filter(NewsArticle.created_at >= cutoff)
    
    if symbol:
        query = query.filter(NewsArticle.related_symbols.contains(symbol))
    
    if sentiment:
        query = query.filter(NewsArticle.sentiment_label == sentiment)
    
    articles = query.order_by(NewsArticle.published_at.desc()).offset(skip).limit(limit).all()
    
    return [{
        "id": a.id,
        "title": a.title,
        "source": a.source,
        "published_at": a.published_at.isoformat() if a.published_at else None,
        "sentiment_score": a.sentiment_score,
        "sentiment_label": a.sentiment_label,
        "related_symbols": a.related_symbols,
        "url": a.url
    } for a in articles]

@router.get("/by-symbol/{symbol}")
def get_news_by_symbol(
    symbol: str,
    hours: int = Query(default=48, ge=1, le=168),
    db: Session = Depends(get_db)
):
    """Get news specific to a stock symbol"""
    service = NewsService(db)
    articles = service.fetch_stock_specific_news(symbol)
    
    return {"symbol": symbol.upper(), "articles_found": len(articles)}
