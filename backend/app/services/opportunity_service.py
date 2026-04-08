from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import numpy as np
from sqlalchemy import func

from app.models.stock import Stock, StockPrice
from app.models.news import NewsArticle
from app.models.explanation import OpportunityAlert
from app.services.portfolio_service import PortfolioService
from app.services.news_service import NewsService

class OpportunityRadarService:
    """Detect undervalued stocks and early investment opportunities"""
    
    # Detection thresholds
    THRESHOLDS = {
        "undervalued_pe": 15.0,  # P/E ratio below this
        "undervalued_pb": 1.5,  # P/B ratio below this
        "price_vs_ma_discount": -0.10,  # 10% below moving average
        "volume_spike_min": 2.0,  # 2x average volume
        "sentiment_shift_threshold": 0.3,  # 30% sentiment change
        "rsi_oversold": 30.0,
        "rsi_overbought": 70.0,
        "score_threshold": 0.65  # Minimum score to trigger alert
    }
    
    # Opportunity type weights for final score
    SCORE_WEIGHTS = {
        "value_score": 0.25,
        "sentiment_score": 0.20,
        "momentum_score": 0.20,
        "technical_score": 0.20,
        "volume_score": 0.15
    }
    
    def __init__(self, db: Session):
        self.db = db
        self.portfolio_service = PortfolioService(db)
        self.news_service = NewsService(db)
    
    def scan_all_stocks(self, limit: int = 50) -> List[Dict]:
        """Scan all available stocks for opportunities"""
        
        stocks = self.db.query(Stock).limit(limit).all()
        opportunities = []
        
        for stock in stocks:
            opp = self.analyze_opportunity(stock.id)
            if opp and opp["detection_score"] >= self.THRESHOLDS["score_threshold"]:
                opportunities.append(opp)
        
        # Sort by detection score
        opportunities.sort(key=lambda x: x["detection_score"], reverse=True)
        return opportunities[:20]  # Top 20
    
    def analyze_opportunity(self, stock_id: int) -> Optional[Dict]:
        """Deep analysis of a single stock for opportunity signals"""
        
        stock = self.db.query(Stock).filter(Stock.id == stock_id).first()
        if not stock:
            return None
        
        # Get metrics
        metrics = self.portfolio_service.calculate_stock_metrics(stock_id)
        if not metrics:
            return None
        
        # Calculate various opportunity scores
        value_score = self._calculate_value_score(stock, metrics)
        sentiment_score = self._calculate_sentiment_score(stock.symbol)
        momentum_score = self._calculate_momentum_score(stock_id, metrics)
        technical_score = self._calculate_technical_score(stock_id)
        volume_score = self._calculate_volume_score(stock_id)
        
        # Weighted final score
        final_score = (
            value_score * self.SCORE_WEIGHTS["value_score"] +
            sentiment_score * self.SCORE_WEIGHTS["sentiment_score"] +
            momentum_score * self.SCORE_WEIGHTS["momentum_score"] +
            technical_score * self.SCORE_WEIGHTS["technical_score"] +
            volume_score * self.SCORE_WEIGHTS["volume_score"]
        )
        
        # Generate detection reasons
        reasons = []
        if value_score > 0.7:
            reasons.append({
                "factor": "value",
                "description": f"Potential undervaluation detected (score: {value_score:.2f})",
                "strength": "strong" if value_score > 0.85 else "moderate"
            })
        
        if sentiment_score > 0.7:
            reasons.append({
                "factor": "sentiment",
                "description": f"Positive sentiment shift detected (score: {sentiment_score:.2f})",
                "strength": "strong" if sentiment_score > 0.85 else "moderate"
            })
        
        if momentum_score > 0.7:
            reasons.append({
                "factor": "momentum",
                "description": f"Positive momentum building (score: {momentum_score:.2f})",
                "strength": "strong" if momentum_score > 0.85 else "moderate"
            })
        
        if technical_score > 0.7:
            reasons.append({
                "factor": "technical",
                "description": f"Technical indicators suggest opportunity (score: {technical_score:.2f})",
                "strength": "strong" if technical_score > 0.85 else "moderate"
            })
        
        if volume_score > 0.7:
            reasons.append({
                "factor": "volume",
                "description": f"Unusual volume activity detected (score: {volume_score:.2f})",
                "strength": "strong" if volume_score > 0.85 else "moderate"
            })
        
        # Determine opportunity type
        opportunity_type = self._classify_opportunity_type(reasons, final_score)
        
        # Get price data for additional context
        latest_price = self._get_latest_price(stock_id)
        
        return {
            "stock_id": stock_id,
            "symbol": stock.symbol,
            "name": stock.name,
            "sector": stock.sector,
            "detection_score": round(final_score, 3),
            "confidence": self._calculate_confidence(reasons, final_score),
            "opportunity_type": opportunity_type,
            "detection_reasons": reasons,
            "current_price": latest_price,
            "component_scores": {
                "value": round(value_score, 3),
                "sentiment": round(sentiment_score, 3),
                "momentum": round(momentum_score, 3),
                "technical": round(technical_score, 3),
                "volume": round(volume_score, 3)
            },
            "key_metrics": {
                "annual_return": round(metrics.get("annual_return", 0) * 100, 2),
                "volatility": round(metrics.get("annual_volatility", 0) * 100, 2),
                "sharpe_ratio": round(metrics.get("sharpe_ratio", 0), 2),
                "max_drawdown": round(metrics.get("max_drawdown", 0) * 100, 2)
            },
            "detected_at": datetime.utcnow().isoformat()
        }
    
    def _calculate_value_score(self, stock: Stock, metrics: Dict) -> float:
        """Calculate value/undervaluation score"""
        
        score = 0.0
        factors = []
        
        # P/E analysis (simplified - using market cap as proxy)
        if stock.market_cap:
            market_cap_billions = float(stock.market_cap) / 1e9
            # Lower market cap relative to sector could indicate value
            if stock.sector == "Financial" and market_cap_billions < 50:
                score += 0.3
                factors.append("Small-cap financial potential value")
        
        # Sharpe ratio indicates value
        sharpe = metrics.get("sharpe_ratio", 0)
        if sharpe > 1.0:
            score += 0.35
            factors.append("High risk-adjusted returns (Sharpe > 1.0)")
        elif sharpe > 0.5:
            score += 0.20
            factors.append("Good risk-adjusted returns")
        
        # Return vs volatility ratio
        returns = metrics.get("annual_return", 0)
        volatility = metrics.get("annual_volatility", 0)
        if volatility > 0 and returns / volatility > 0.5:
            score += 0.25
            factors.append("Good return per unit of risk")
        
        # Recovery from drawdown
        max_dd = metrics.get("max_drawdown", -1)
        if max_dd > -0.20:  # Small drawdown suggests stability
            score += 0.10
        elif max_dd < -0.40:  # Large drawdown - potential recovery play
            score += 0.15  # Contrarian value opportunity
            factors.append("Potential recovery play after large drawdown")
        
        return min(1.0, score)
    
    def _calculate_sentiment_score(self, symbol: str) -> float:
        """Calculate sentiment-based opportunity score"""
        
        # Get current sentiment
        current = self.news_service.get_sentiment_summary(symbol, hours=24)
        # Get recent historical sentiment
        recent = self.news_service.get_sentiment_summary(symbol, hours=168)
        
        score = 0.0
        
        if not current or current.get("summary") == "no_data":
            return 0.5  # Neutral if no data
        
        current_avg = current.get("average_sentiment", 0)
        recent_avg = recent.get("average_sentiment", 0) if recent else 0
        
        # Positive current sentiment
        if current_avg > 0.3:
            score += 0.3
        elif current_avg > 0.1:
            score += 0.2
        
        # Sentiment improvement (momentum)
        if current_avg > recent_avg + 0.1:
            score += 0.35  # Sentiment improving
        
        # High volume of positive news
        pos_count = current.get("sentiment_distribution", {}).get("positive", 0)
        total = current.get("count", 1)
        if total > 0 and pos_count / total > 0.6:
            score += 0.25
        
        return min(1.0, score)
    
    def _calculate_momentum_score(self, stock_id: int, metrics: Dict) -> float:
        """Calculate momentum score based on recent performance"""
        
        score = 0.0
        returns = metrics.get("annual_return", 0)
        
        # Positive return momentum
        if returns > 0.20:  # 20% annual return
            score += 0.4
        elif returns > 0.10:
            score += 0.25
        elif returns > 0:
            score += 0.10
        
        # Sharpe momentum
        sharpe = metrics.get("sharpe_ratio", 0)
        if sharpe > 1.0:
            score += 0.35
        elif sharpe > 0.5:
            score += 0.20
        
        # Consistency check - low volatility with positive returns
        volatility = metrics.get("annual_volatility", 1)
        if returns > 0 and volatility < 0.20:
            score += 0.25  # Steady performer
        
        return min(1.0, score)
    
    def _calculate_technical_score(self, stock_id: int) -> float:
        """Calculate technical indicator score"""
        
        # Get price history
        cutoff = datetime.utcnow() - timedelta(days=100)
        prices = self.db.query(StockPrice).filter(
            StockPrice.stock_id == stock_id,
            StockPrice.timestamp >= cutoff
        ).order_by(StockPrice.timestamp).all()
        
        if len(prices) < 50:
            return 0.5  # Insufficient data
        
        closes = [float(p.close_price) for p in prices if p.close_price]
        
        if len(closes) < 50:
            return 0.5
        
        score = 0.0
        
        # Calculate RSI
        deltas = np.diff(closes)
        gains = [d if d > 0 else 0 for d in deltas[-14:]]
        losses = [abs(d) if d < 0 else 0 for d in deltas[-14:]]
        
        avg_gain = sum(gains) / len(gains) if gains else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        
        if avg_loss > 0:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            
            # Oversold bounce opportunity
            if rsi < self.THRESHOLDS["rsi_oversold"]:
                score += 0.4
            # Strong momentum
            elif rsi > 50 and rsi < 70:
                score += 0.25
        
        # Price vs Moving Averages
        ma_50 = np.mean(closes[-50:]) if len(closes) >= 50 else closes[0]
        ma_20 = np.mean(closes[-20:]) if len(closes) >= 20 else closes[0]
        current = closes[-1]
        
        # Golden cross potential (short MA crossing above long MA)
        if ma_20 > ma_50:
            score += 0.3
        
        # Price discount to MA
        discount = (current - ma_50) / ma_50 if ma_50 > 0 else 0
        if discount < self.THRESHOLDS["price_vs_ma_discount"]:
            score += 0.3  # Discount to moving average
        
        return min(1.0, score)
    
    def _calculate_volume_score(self, stock_id: int) -> float:
        """Calculate volume anomaly score"""
        
        cutoff = datetime.utcnow() - timedelta(days=30)
        recent_prices = self.db.query(StockPrice).filter(
            StockPrice.stock_id == stock_id,
            StockPrice.timestamp >= cutoff
        ).order_by(StockPrice.timestamp).all()
        
        if len(recent_prices) < 10:
            return 0.5
        
        volumes = [p.volume for p in recent_prices if p.volume]
        
        if len(volumes) < 10:
            return 0.5
        
        avg_volume = np.mean(volumes[:-5])  # Average excluding last 5 days
        recent_volume = np.mean(volumes[-5:])
        
        if avg_volume > 0:
            volume_ratio = recent_volume / avg_volume
            
            if volume_ratio >= self.THRESHOLDS["volume_spike_min"]:
                return min(1.0, 0.5 + (volume_ratio - 1) * 0.2)
        
        return 0.5  # Normal volume
    
    def _classify_opportunity_type(self, reasons: List[Dict], final_score: float) -> str:
        """Classify the type of opportunity"""
        
        factor_types = [r["factor"] for r in reasons]
        
        if "value" in factor_types and final_score > 0.75:
            return "undervalued"
        elif "sentiment" in factor_types and "momentum" in factor_types:
            return "sentiment_momentum"
        elif "technical" in factor_types and final_score > 0.7:
            return "technical_breakout"
        elif "volume" in factor_types:
            return "volume_anomaly"
        elif final_score > 0.65:
            return "multi_factor"
        else:
            return "watch_list"
    
    def _calculate_confidence(self, reasons: List[Dict], score: float) -> float:
        """Calculate confidence level based on factor diversity and strength"""
        
        # More factors = higher confidence
        factor_count = len(reasons)
        diversity_factor = min(1.0, factor_count / 3)  # Max at 3+ factors
        
        # Score strength
        strength_factor = score
        
        # Strong reason bonus
        strong_reasons = sum(1 for r in reasons if r.get("strength") == "strong")
        strong_factor = min(1.0, 0.7 + strong_reasons * 0.1)
        
        confidence = (diversity_factor * 0.3 + strength_factor * 0.4 + strong_factor * 0.3)
        return round(min(1.0, confidence), 3)
    
    def _get_latest_price(self, stock_id: int) -> Optional[float]:
        """Get latest price for a stock"""
        latest = self.db.query(StockPrice).filter(
            StockPrice.stock_id == stock_id
        ).order_by(StockPrice.timestamp.desc()).first()
        
        return float(latest.close_price) if latest and latest.close_price else None
    
    def save_opportunity(self, opp_data: Dict) -> OpportunityAlert:
        """Save detected opportunity to database"""
        
        alert = OpportunityAlert(
            stock_id=opp_data["stock_id"],
            opportunity_type=opp_data["opportunity_type"],
            detection_score=opp_data["detection_score"],
            confidence=opp_data["confidence"],
            detection_reasons=opp_data["detection_reasons"],
            supporting_data=opp_data["component_scores"],
            expires_at=datetime.utcnow() + timedelta(days=7)
        )
        
        self.db.add(alert)
        self.db.commit()
        self.db.refresh(alert)
        return alert
    
    def get_active_opportunities(self, min_score: float = 0.6) -> List[Dict]:
        """Get all active opportunities from database"""
        
        alerts = self.db.query(OpportunityAlert).filter(
            OpportunityAlert.is_active == 1,
            OpportunityAlert.detection_score >= min_score,
            OpportunityAlert.expires_at > datetime.utcnow()
        ).order_by(OpportunityAlert.detection_score.desc()).all()
        
        return [{
            "id": a.id,
            "symbol": a.stock.symbol if a.stock else "Unknown",
            "type": a.opportunity_type,
            "score": a.detection_score,
            "confidence": a.confidence,
            "detected_at": a.created_at.isoformat() if a.created_at else None,
            "expires_at": a.expires_at.isoformat() if a.expires_at else None,
            "reasons": a.detection_reasons
        } for a in alerts]
