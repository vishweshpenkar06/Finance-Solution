from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from app.core.database import get_db
from app.services.portfolio_service import PortfolioService

router = APIRouter()

class PortfolioRecommendation(BaseModel):
    stock_id: int
    symbol: str
    sector: Optional[str]
    weight: float
    amount: float
    expected_return: float
    volatility: float
    sharpe_ratio: float
    rationale: str

class PortfolioMetrics(BaseModel):
    expected_annual_return: float
    expected_volatility: float
    sharpe_ratio: float
    risk_level: str

class CreatePortfolioRequest(BaseModel):
    user_id: int
    name: str = "My Portfolio"
    risk_tolerance: str = "moderate"
    investment_amount: float = 10000

class RecommendationRequest(BaseModel):
    risk_tolerance: str = "moderate"
    investment_amount: float = 10000
    exclude_symbols: Optional[List[str]] = []

@router.post("/recommendations")
def get_recommendations(
    request: RecommendationRequest,
    db: Session = Depends(get_db)
):
    """Generate portfolio recommendations based on risk profile"""
    service = PortfolioService(db)
    
    recommendations = service.generate_portfolio_recommendations(
        risk_tolerance=request.risk_tolerance,
        investment_amount=request.investment_amount,
        exclude_symbols=request.exclude_symbols or []
    )
    
    metrics = service.calculate_portfolio_metrics(recommendations)
    
    return {
        "recommendations": recommendations,
        "portfolio_metrics": metrics
    }

@router.post("/create")
def create_portfolio(
    request: CreatePortfolioRequest,
    db: Session = Depends(get_db)
):
    """Create a new portfolio with AI recommendations"""
    service = PortfolioService(db)
    
    # Generate recommendations
    recommendations = service.generate_portfolio_recommendations(
        risk_tolerance=request.risk_tolerance,
        investment_amount=request.investment_amount
    )
    
    if not recommendations:
        raise HTTPException(status_code=400, detail="Unable to generate recommendations - insufficient stock data")
    
    # Create portfolio
    portfolio = service.create_portfolio(
        user_id=request.user_id,
        name=request.name,
        recommendations=recommendations
    )
    
    metrics = service.calculate_portfolio_metrics(recommendations)
    
    return {
        "portfolio_id": portfolio.id,
        "name": portfolio.name,
        "recommendations": recommendations,
        "metrics": metrics
    }

@router.get("/user/{user_id}")
def get_user_portfolios(user_id: int, db: Session = Depends(get_db)):
    """Get all portfolios for a user"""
    from app.models.portfolio import Portfolio, PortfolioHolding
    from app.models.stock import Stock
    
    portfolios = db.query(Portfolio).filter(Portfolio.user_id == user_id).all()
    
    result = []
    for p in portfolios:
        holdings = []
        for h in p.holdings:
            holdings.append({
                "symbol": h.stock.symbol if h.stock else None,
                "name": h.stock.name if h.stock else None,
                "weight": h.weight,
                "quantity": float(h.quantity) if h.quantity else 0,
                "current_price": float(h.current_price) if h.current_price else None
            })
        
        result.append({
            "id": p.id,
            "name": p.name,
            "strategy": p.strategy,
            "risk_score": p.risk_score,
            "holdings": holdings,
            "created_at": p.created_at.isoformat() if p.created_at else None
        })
    
    return result

@router.get("/{portfolio_id}/rebalance")
def get_rebalance_suggestions(portfolio_id: int, db: Session = Depends(get_db)):
    """Get rebalancing suggestions for an existing portfolio"""
    service = PortfolioService(db)
    suggestions = service.rebalance_portfolio(portfolio_id)
    
    return {
        "portfolio_id": portfolio_id,
        "suggestions": suggestions
    }

@router.get("/stock-metrics")
def get_all_stock_metrics(db: Session = Depends(get_db)):
    """Get risk/return metrics for all available stocks"""
    service = PortfolioService(db)
    metrics_df = service.get_all_stock_metrics()
    
    if metrics_df.empty:
        return {"stocks": [], "count": 0}
    
    stocks_list = metrics_df.to_dict('records')
    
    return {
        "stocks": stocks_list,
        "count": len(stocks_list)
    }
