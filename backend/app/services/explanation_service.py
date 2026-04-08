from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta

from app.models.stock import Stock, StockPrice
from app.models.news import NewsArticle
from app.models.explanation import RecommendationExplanation, DataTrustScore
from app.services.portfolio_service import PortfolioService
from app.services.news_service import NewsService

class ExplanationService:
    """Generate explainable AI insights for recommendations"""
    
    def __init__(self, db: Session):
        self.db = db
        self.portfolio_service = PortfolioService(db)
        self.news_service = NewsService(db)
    
    def explain_stock_selection(
        self,
        stock_id: int,
        portfolio_context: Dict,
        risk_tolerance: str = "moderate"
    ) -> Dict:
        """Generate detailed explanation for why a stock was selected"""
        
        stock = self.db.query(Stock).filter(Stock.id == stock_id).first()
        if not stock:
            return None
        
        # Get metrics
        metrics = self.portfolio_service.calculate_stock_metrics(stock_id)
        if not metrics:
            return None
        
        explanations = {
            "stock_symbol": stock.symbol,
            "stock_name": stock.name,
            "sector": stock.sector,
            "primary_factors": [],
            "risk_factors": [],
            "confidence": 0.0,
            "feature_importance": {},
            "reasoning_text": ""
        }
        
        # Analyze sentiment contribution
        sentiment_summary = self.news_service.get_sentiment_summary(stock.symbol, hours=168)
        sentiment_score = 50 + (sentiment_summary.get("average_sentiment", 0) * 50)
        explanations["feature_importance"]["sentiment"] = round(abs(sentiment_summary.get("average_sentiment", 0)), 3)
        
        # Analyze metrics
        sharpe = metrics.get("sharpe_ratio", 0)
        volatility = metrics.get("annual_volatility", 0)
        max_dd = metrics.get("max_drawdown", 0)
        annual_return = metrics.get("annual_return", 0)
        
        # Build reasoning
        factors = []
        
        # Sharpe ratio factor
        if sharpe > 1.0:
            factors.append({
                "factor": "risk_adjusted_returns",
                "description": f"Strong Sharpe ratio of {sharpe:.2f} indicates excellent risk-adjusted returns",
                "impact": "high",
                "score": min(100, sharpe * 33)
            })
        elif sharpe > 0.5:
            factors.append({
                "factor": "risk_adjusted_returns",
                "description": f"Good Sharpe ratio of {sharpe:.2f} shows solid risk-adjusted performance",
                "impact": "medium",
                "score": sharpe * 50
            })
        
        # Volatility assessment
        risk_profile = self.portfolio_service.RISK_PROFILES.get(risk_tolerance, {})
        max_vol = risk_profile.get("max_volatility", 0.25)
        
        if volatility <= max_vol * 0.8:
            factors.append({
                "factor": "volatility",
                "description": f"Low volatility ({volatility*100:.1f}%) aligns with your {risk_tolerance} risk profile",
                "impact": "high",
                "score": 85
            })
        elif volatility <= max_vol:
            factors.append({
                "factor": "volatility",
                "description": f"Volatility ({volatility*100:.1f}%) within acceptable range for your profile",
                "impact": "medium",
                "score": 70
            })
        else:
            factors.append({
                "factor": "volatility",
                "description": f"Higher volatility ({volatility*100:.1f}%) but offset by strong returns",
                "impact": "low",
                "score": 50
            })
        
        # Return factor
        if annual_return > 0.15:
            factors.append({
                "factor": "expected_returns",
                "description": f"High expected annual return of {annual_return*100:.1f}%",
                "impact": "high",
                "score": min(100, annual_return * 200)
            })
        elif annual_return > 0.08:
            factors.append({
                "factor": "expected_returns",
                "description": f"Solid expected annual return of {annual_return*100:.1f}%",
                "impact": "medium",
                "score": annual_return * 400
            })
        
        # Sector diversification
        current_sectors = portfolio_context.get("current_sectors", [])
        if stock.sector and stock.sector not in current_sectors:
            factors.append({
                "factor": "diversification",
                "description": f"Adds {stock.sector} exposure, improving portfolio diversification",
                "impact": "medium",
                "score": 80
            })
        
        # Sentiment factor
        if sentiment_summary.get("summary") == "positive":
            factors.append({
                "factor": "market_sentiment",
                "description": f"Positive news sentiment ({sentiment_summary.get('count', 0)} articles analyzed)",
                "impact": "medium",
                "score": sentiment_score
            })
        
        # Calculate overall confidence
        if factors:
            avg_score = sum(f["score"] for f in factors) / len(factors)
            explanations["confidence"] = round(avg_score / 100, 2)
        
        explanations["primary_factors"] = factors
        
        # Risk factors
        risks = []
        if max_dd < -0.25:
            risks.append({
                "risk": "high_drawdown",
                "description": f"Historical max drawdown of {max_dd*100:.1f}% indicates significant downside risk",
                "severity": "high"
            })
        
        if volatility > max_vol:
            risks.append({
                "risk": "volatility_mismatch",
                "description": f"Volatility exceeds your risk tolerance threshold",
                "severity": "medium"
            })
        
        if sentiment_summary.get("summary") == "negative":
            risks.append({
                "risk": "negative_sentiment",
                "description": f"Recent negative news sentiment may impact short-term performance",
                "severity": "medium"
            })
        
        if not stock.market_cap or stock.market_cap < 1_000_000_000:
            risks.append({
                "risk": "small_cap",
                "description": "Smaller market cap stock may have lower liquidity",
                "severity": "low"
            })
        
        explanations["risk_factors"] = risks
        
        # Generate human-readable reasoning text
        reasoning_parts = []
        
        # Top factor explanation
        if factors:
            top_factor = max(factors, key=lambda x: x["score"])
            reasoning_parts.append(f"{stock.symbol} was selected primarily due to its {top_factor['factor'].replace('_', ' ')}. {top_factor['description']}.")
        
        # Risk assessment
        if not risks:
            reasoning_parts.append("Risk analysis shows no major concerns for your risk profile.")
        else:
            risk_text = f"However, {len(risks)} risk factor(s) identified: " + ", ".join([r["risk"].replace("_", " ") for r in risks[:2]])
            reasoning_parts.append(risk_text)
        
        # Portfolio fit
        if stock.sector:
            reasoning_parts.append(f"The {stock.sector} sector {'adds new diversification' if stock.sector not in current_sectors else 'aligns with your current allocation'} to your portfolio.")
        
        explanations["reasoning_text"] = " ".join(reasoning_parts)
        
        return explanations
    
    def explain_portfolio_allocation(
        self,
        recommendations: List[Dict],
        risk_tolerance: str
    ) -> Dict:
        """Explain overall portfolio allocation decisions"""
        
        explanation = {
            "strategy_overview": "",
            "sector_allocation_reasoning": "",
            "risk_balance_reasoning": "",
            "rebalancing_recommendations": []
        }
        
        # Strategy based on risk tolerance
        strategies = {
            "conservative": "Capital preservation with steady income and low volatility",
            "moderate": "Balanced growth with managed risk through diversification",
            "aggressive": "Growth maximization accepting higher volatility for higher returns"
        }
        
        explanation["strategy_overview"] = strategies.get(
            risk_tolerance, 
            "Balanced risk-adjusted return strategy"
        )
        
        # Analyze sector distribution
        sectors = {}
        for rec in recommendations:
            sector = rec.get("sector", "Unknown")
            sectors[sector] = sectors.get(sector, 0) + rec.get("weight", 0)
        
        sector_text = "Portfolio allocated across sectors: " + ", ".join(
            [f"{s} ({w*100:.0f}%)" for s, w in sectors.items()]
        )
        explanation["sector_allocation_reasoning"] = sector_text
        
        # Risk balance explanation
        avg_volatility = sum(r.get("volatility", 0) * r.get("weight", 0) for r in recommendations)
        explanation["risk_balance_reasoning"] = (
            f"Weighted average portfolio volatility of {avg_volatility*100:.1f}% "
            f"aligns with {risk_tolerance} risk profile"
        )
        
        return explanation
    
    def save_explanation(
        self,
        portfolio_id: int,
        stock_id: int,
        explanation_data: Dict
    ) -> RecommendationExplanation:
        """Save explanation to database for future reference"""
        
        factors = explanation_data.get("primary_factors", [])
        feature_imp = {}
        for f in factors:
            feature_imp[f["factor"]] = f.get("score", 0) / 100
        
        explanation = RecommendationExplanation(
            portfolio_id=portfolio_id,
            stock_id=stock_id,
            primary_factors=[f["factor"] for f in factors],
            reasoning_text=explanation_data.get("reasoning_text"),
            risk_factors=explanation_data.get("risk_factors"),
            confidence_level=explanation_data.get("confidence"),
            feature_importance=feature_imp,
            sentiment_score=explanation_data.get("feature_importance", {}).get("sentiment", 0) * 100
        )
        
        self.db.add(explanation)
        self.db.commit()
        self.db.refresh(explanation)
        return explanation
