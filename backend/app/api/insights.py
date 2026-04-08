from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timedelta

from app.core.database import get_db
from app.services.portfolio_service import PortfolioService
from app.services.news_service import NewsService

router = APIRouter()

@router.get("/dashboard")
def get_dashboard_insights(db: Session = Depends(get_db)):
    """Get comprehensive insights for dashboard"""
    
    news_service = NewsService(db)
    portfolio_service = PortfolioService(db)
    
    # Market sentiment
    sentiment = news_service.get_sentiment_summary(hours=24)
    
    # Top performing stocks
    all_metrics = portfolio_service.get_all_stock_metrics()
    
    top_performers = []
    if not all_metrics.empty:
        top = all_metrics.nlargest(5, 'sharpe_ratio')
        for _, row in top.iterrows():
            top_performers.append({
                "symbol": row['symbol'],
                "sector": row['sector'],
                "annual_return": round(row['annual_return'] * 100, 2),
                "volatility": round(row['annual_volatility'] * 100, 2),
                "sharpe_ratio": round(row['sharpe_ratio'], 3)
            })
    
    # Count data
    from app.models.stock import Stock
    from app.models.news import NewsArticle
    
    stock_count = db.query(Stock).count()
    
    cutoff = datetime.utcnow() - timedelta(hours=24)
    news_count = db.query(NewsArticle).filter(NewsArticle.created_at >= cutoff).count()
    
    return {
        "market_sentiment": sentiment,
        "top_performers": top_performers,
        "data_summary": {
            "total_stocks": stock_count,
            "news_articles_24h": news_count,
            "last_updated": datetime.utcnow().isoformat()
        }
    }

@router.get("/market-overview")
def get_market_overview(db: Session = Depends(get_db)):
    """Get market-wide insights"""
    news_service = NewsService(db)
    portfolio_service = PortfolioService(db)
    
    # Recent sentiment trends
    sentiment_24h = news_service.get_sentiment_summary(hours=24)
    sentiment_7d = news_service.get_sentiment_summary(hours=168)
    
    # Sector performance
    all_metrics = portfolio_service.get_all_stock_metrics()
    
    sector_performance = {}
    if not all_metrics.empty:
        for sector in all_metrics['sector'].unique():
            if sector:
                sector_data = all_metrics[all_metrics['sector'] == sector]
                sector_performance[sector] = {
                    "avg_return": round(sector_data['annual_return'].mean() * 100, 2),
                    "avg_volatility": round(sector_data['annual_volatility'].mean() * 100, 2),
                    "avg_sharpe": round(sector_data['sharpe_ratio'].mean(), 3),
                    "stock_count": len(sector_data)
                }
    
    return {
        "sentiment": {
            "24h": sentiment_24h,
            "7d": sentiment_7d
        },
        "sector_performance": sector_performance
    }

@router.get("/risk-scenarios")
def get_risk_scenarios(
    investment_amount: float = Query(default=10000),
    db: Session = Depends(get_db)
):
    """Generate portfolio scenarios for different risk profiles"""
    
    portfolio_service = PortfolioService(db)
    
    scenarios = {}
    for risk in ["conservative", "moderate", "aggressive"]:
        recommendations = portfolio_service.generate_portfolio_recommendations(
            risk_tolerance=risk,
            investment_amount=investment_amount
        )
        metrics = portfolio_service.calculate_portfolio_metrics(recommendations)
        
        scenarios[risk] = {
            "recommendations_count": len(recommendations),
            "expected_return": metrics.get("expected_annual_return"),
            "expected_volatility": metrics.get("expected_volatility"),
            "sharpe_ratio": metrics.get("sharpe_ratio"),
            "risk_level": metrics.get("risk_level")
        }
    
    return {
        "investment_amount": investment_amount,
        "scenarios": scenarios
    }
