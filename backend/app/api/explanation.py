from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel

from app.core.database import get_db
from app.services.explanation_service import ExplanationService
from app.services.simulation_service import SimulationService
from app.services.trust_score_service import TrustScoreService
from app.services.behavior_service import BehaviorLearningService
from app.services.opportunity_service import OpportunityRadarService

router = APIRouter()

class StockSelectionExplanation(BaseModel):
    stock_id: int
    symbol: str
    stock_name: str
    sector: str
    primary_factors: List[dict]
    risk_factors: List[dict]
    confidence: float
    reasoning_text: str
    feature_importance: dict

class PortfolioAllocationExplanation(BaseModel):
    strategy_overview: str
    sector_allocation_reasoning: str
    risk_balance_reasoning: str
    rebalancing_recommendations: List[dict]

@router.post("/stock-selection/{stock_id}")
def explain_stock_selection(
    stock_id: int,
    risk_tolerance: str = "moderate",
    db: Session = Depends(get_db)
):
    """Get detailed explanation for why a stock was selected"""
    service = ExplanationService(db)
    
    portfolio_context = {"current_sectors": []}  # Simplified for now
    explanation = service.explain_stock_selection(stock_id, portfolio_context, risk_tolerance)
    
    if not explanation:
        raise HTTPException(status_code=404, detail="Stock not found or insufficient data")
    
    return explanation

@router.post("/portfolio/{portfolio_id}")
def explain_portfolio_allocation(
    portfolio_id: int,
    db: Session = Depends(get_db)
):
    """Get explanation for portfolio allocation decisions"""
    from app.models.portfolio import Portfolio, PortfolioHolding
    
    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    holdings = db.query(PortfolioHolding).filter(
        PortfolioHolding.portfolio_id == portfolio_id
    ).all()
    
    service = ExplanationService(db)
    
    # Build recommendations list from holdings
    recommendations = []
    for h in holdings:
        if h.stock:
            recommendations.append({
                "stock_id": h.stock_id,
                "symbol": h.stock.symbol,
                "sector": h.stock.sector,
                "weight": h.weight,
                "amount": 10000 * (h.weight or 0),  # Default amount
                "expected_return": 0.10,
                "volatility": 0.20,
                "sharpe_ratio": 0.5,
                "rationale": "Existing holding"
            })
    
    explanation = service.explain_portfolio_allocation(
        recommendations,
        portfolio.strategy or "moderate"
    )
    
    return explanation

# === What-If Simulation Routes ===

@router.get("/scenarios/available")
def get_available_scenarios(db: Session = Depends(get_db)):
    """List all available simulation scenarios"""
    service = SimulationService(db)
    return service.get_available_scenarios()

@router.post("/simulate/{portfolio_id}/{scenario_type}")
def run_scenario_simulation(
    portfolio_id: int,
    scenario_type: str,
    custom_params: dict = None,
    db: Session = Depends(get_db)
):
    """Run a what-if scenario simulation on a portfolio"""
    service = SimulationService(db)
    
    result = service.run_scenario_simulation(portfolio_id, scenario_type, custom_params)
    
    if not result:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    return result

@router.post("/simulate/compare/{portfolio_id}")
def compare_scenarios(
    portfolio_id: int,
    scenario_types: List[str],
    db: Session = Depends(get_db)
):
    """Compare portfolio performance across multiple scenarios"""
    service = SimulationService(db)
    
    return service.compare_scenarios(portfolio_id, scenario_types)

@router.post("/simulate/monte-carlo/{portfolio_id}")
def run_monte_carlo_simulation(
    portfolio_id: int,
    num_simulations: int = 1000,
    time_horizon_days: int = 252,
    db: Session = Depends(get_db)
):
    """Run Monte Carlo simulation for probabilistic outcomes"""
    service = SimulationService(db)
    
    result = service.run_monte_carlo_simulation(
        portfolio_id,
        num_simulations,
        time_horizon_days
    )
    
    if not result:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    return result

# === Data Trust Score Routes ===

@router.get("/trust/sources")
def get_source_rankings(db: Session = Depends(get_db)):
    """Get ranked list of all data sources by trust score"""
    service = TrustScoreService(db)
    return service.get_all_source_rankings()

@router.get("/trust/article/{article_id}")
def get_article_trust_score(
    article_id: int,
    db: Session = Depends(get_db)
):
    """Get trust score for a specific article"""
    from app.models.news import NewsArticle
    
    article = db.query(NewsArticle).filter(NewsArticle.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    service = TrustScoreService(db)
    return service.get_article_trust_score(article)

@router.get("/trust/report")
def get_data_quality_report(
    days: int = 7,
    db: Session = Depends(get_db)
):
    """Generate overall data quality report"""
    service = TrustScoreService(db)
    return service.get_data_quality_report(days)

# === Behavior Learning Routes ===

@router.get("/behavior/profile/{user_id}")
def get_user_behavior_profile(
    user_id: int,
    db: Session = Depends(get_db)
):
    """Get user's learned behavior profile"""
    service = BehaviorLearningService(db)
    return service.get_behavior_summary(user_id)

@router.post("/behavior/log-decision")
def log_user_decision(
    user_id: int,
    decision_type: str,
    recommendation_id: int = None,
    action_details: dict = None,
    db: Session = Depends(get_db)
):
    """Log a user decision for behavior learning"""
    service = BehaviorLearningService(db)
    
    log = service.log_user_decision(
        user_id,
        decision_type,
        recommendation_id,
        action_details or {}
    )
    
    return {
        "id": log.id,
        "user_id": log.user_id,
        "decision_type": log.decision_type,
        "action_taken": log.action_taken,
        "logged_at": log.created_at.isoformat() if log.created_at else None
    }

@router.get("/behavior/changes/{user_id}")
def detect_behavior_changes(
    user_id: int,
    db: Session = Depends(get_db)
):
    """Detect significant changes in user behavior"""
    service = BehaviorLearningService(db)
    return service.detect_behavior_changes(user_id)

@router.post("/behavior/adaptive-recommendations/{user_id}")
def get_adaptive_recommendations(
    user_id: int,
    base_recommendations: List[dict],
    investment_amount: float = 10000,
    db: Session = Depends(get_db)
):
    """Get recommendations adapted to user's learned behavior"""
    service = BehaviorLearningService(db)
    return service.generate_adaptive_recommendations(
        user_id,
        base_recommendations,
        investment_amount
    )

# === Opportunity Radar Routes ===

@router.get("/opportunities/scan")
def scan_for_opportunities(
    limit: int = 50,
    min_score: float = 0.65,
    db: Session = Depends(get_db)
):
    """Scan all stocks for investment opportunities"""
    service = OpportunityRadarService(db)
    opportunities = service.scan_all_stocks(limit)
    
    # Filter by score
    filtered = [o for o in opportunities if o["detection_score"] >= min_score]
    
    return {
        "opportunities_found": len(filtered),
        "top_opportunities": filtered[:10],
        "scan_time": "completed"
    }

@router.get("/opportunities/analyze/{stock_id}")
def analyze_opportunity(
    stock_id: int,
    db: Session = Depends(get_db)
):
    """Deep analysis of a single stock for opportunity signals"""
    service = OpportunityRadarService(db)
    analysis = service.analyze_opportunity(stock_id)
    
    if not analysis:
        raise HTTPException(status_code=404, detail="Stock not found or insufficient data")
    
    return analysis

@router.get("/opportunities/active")
def get_active_opportunities(
    min_score: float = 0.6,
    db: Session = Depends(get_db)
):
    """Get all active opportunities from database"""
    service = OpportunityRadarService(db)
    return service.get_active_opportunities(min_score)
