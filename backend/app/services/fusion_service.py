from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from collections import defaultdict
import numpy as np

from app.models.stock import Stock, StockPrice
from app.models.news import NewsArticle
from app.models.portfolio import Portfolio, PortfolioHolding
from app.services.portfolio_service import PortfolioService
from app.services.news_service import NewsService

class DataFusionService:
    """Smart Data Fusion Layer - Combine price, sentiment, volume into composite signals"""
    
    # Signal weights for composite scoring
    SIGNAL_WEIGHTS = {
        "price_momentum": 0.25,
        "sentiment_momentum": 0.25,
        "volume_anomaly": 0.20,
        "technical_confluence": 0.20,
        "risk_adjusted_momentum": 0.10
    }
    
    # Signal classification thresholds
    SIGNAL_THRESHOLDS = {
        "strong_buy": 0.75,
        "buy": 0.60,
        "neutral_high": 0.45,
        "neutral": 0.35,
        "neutral_low": 0.25,
        "sell": 0.15,
        "strong_sell": 0.0
    }
    
    def __init__(self, db: Session):
        self.db = db
        self.portfolio_service = PortfolioService(db)
        self.news_service = NewsService(db)
    
    def generate_composite_signal(self, stock_id: int) -> Dict:
        """Generate composite investment signal by fusing multiple data sources"""
        
        stock = self.db.query(Stock).filter(Stock.id == stock_id).first()
        if not stock:
            return None
        
        # Gather individual signals
        price_signal = self._analyze_price_momentum(stock_id)
        sentiment_signal = self._analyze_sentiment_momentum(stock.symbol)
        volume_signal = self._analyze_volume_anomaly(stock_id)
        technical_signal = self._analyze_technical_confluence(stock_id)
        risk_signal = self._analyze_risk_adjusted_momentum(stock_id)
        
        # Calculate weighted composite score
        composite_score = (
            price_signal["score"] * self.SIGNAL_WEIGHTS["price_momentum"] +
            sentiment_signal["score"] * self.SIGNAL_WEIGHTS["sentiment_momentum"] +
            volume_signal["score"] * self.SIGNAL_WEIGHTS["volume_anomaly"] +
            technical_signal["score"] * self.SIGNAL_WEIGHTS["technical_confluence"] +
            risk_signal["score"] * self.SIGNAL_WEIGHTS["risk_adjusted_momentum"]
        )
        
        # Determine signal classification
        classification = self._classify_signal(composite_score)
        
        # Generate fusion insight
        insight = self._generate_fusion_insight(
            stock.symbol,
            price_signal,
            sentiment_signal,
            volume_signal,
            technical_signal,
            composite_score,
            classification
        )
        
        return {
            "stock_id": stock_id,
            "symbol": stock.symbol,
            "name": stock.name,
            "composite_score": round(composite_score, 3),
            "signal_classification": classification,
            "confidence": self._calculate_fusion_confidence(
                [price_signal, sentiment_signal, volume_signal, technical_signal, risk_signal]
            ),
            "component_signals": {
                "price_momentum": price_signal,
                "sentiment_momentum": sentiment_signal,
                "volume_anomaly": volume_signal,
                "technical_confluence": technical_signal,
                "risk_adjusted_momentum": risk_signal
            },
            "fusion_insight": insight,
            "contradiction_analysis": self._detect_contradictions(
                price_signal, sentiment_signal, volume_signal
            ),
            "trading_recommendation": self._generate_trading_recommendation(
                classification, composite_score, stock
            ),
            "generated_at": datetime.utcnow().isoformat()
        }
    
    def _analyze_price_momentum(self, stock_id: int) -> Dict:
        """Analyze price momentum patterns"""
        
        metrics = self.portfolio_service.calculate_stock_metrics(stock_id)
        if not metrics:
            return {"score": 0.5, "strength": "neutral", "factors": []}
        
        score = 0.5  # Neutral baseline
        factors = []
        
        # Return momentum
        annual_return = metrics.get("annual_return", 0)
        if annual_return > 0.20:
            score += 0.20
            factors.append({"type": "strong_positive_return", "impact": "high", "value": annual_return})
        elif annual_return > 0.10:
            score += 0.10
            factors.append({"type": "positive_return", "impact": "medium", "value": annual_return})
        elif annual_return < -0.10:
            score -= 0.15
            factors.append({"type": "negative_return", "impact": "high", "value": annual_return})
        
        # Sharpe ratio quality
        sharpe = metrics.get("sharpe_ratio", 0)
        if sharpe > 1.0:
            score += 0.10
            factors.append({"type": "high_quality_returns", "impact": "medium", "sharpe": sharpe})
        elif sharpe < 0:
            score -= 0.10
            factors.append({"type": "poor_risk_adjusted_returns", "impact": "medium", "sharpe": sharpe})
        
        # Max drawdown recovery
        max_dd = metrics.get("max_drawdown", -1)
        if max_dd > -0.15:  # Small drawdown
            score += 0.05
            factors.append({"type": "low_drawdown", "impact": "low", "max_dd": max_dd})
        elif max_dd < -0.40:  # Large drawdown
            score -= 0.10
            factors.append({"type": "high_drawdown_risk", "impact": "medium", "max_dd": max_dd})
        
        # Normalize score
        score = max(0, min(1, score))
        
        strength = "strong" if score > 0.75 else "moderate" if score > 0.55 else "weak" if score > 0.35 else "negative"
        
        return {
            "score": round(score, 3),
            "strength": strength,
            "factors": factors,
            "raw_metrics": {
                "annual_return": round(annual_return * 100, 2),
                "sharpe_ratio": round(sharpe, 2),
                "max_drawdown": round(max_dd * 100, 2)
            }
        }
    
    def _analyze_sentiment_momentum(self, symbol: str) -> Dict:
        """Analyze sentiment momentum and news flow"""
        
        # Get recent vs historical sentiment
        recent = self.news_service.get_sentiment_summary(symbol, hours=24)
        older = self.news_service.get_sentiment_summary(symbol, hours=168)
        
        score = 0.5
        factors = []
        
        current_sentiment = recent.get("average_sentiment", 0)
        older_sentiment = older.get("average_sentiment", 0)
        
        # Sentiment level
        if current_sentiment > 0.3:
            score += 0.20
            factors.append({"type": "positive_sentiment", "impact": "high", "score": current_sentiment})
        elif current_sentiment > 0.1:
            score += 0.10
            factors.append({"type": "mildly_positive_sentiment", "impact": "medium", "score": current_sentiment})
        elif current_sentiment < -0.2:
            score -= 0.20
            factors.append({"type": "negative_sentiment", "impact": "high", "score": current_sentiment})
        elif current_sentiment < -0.1:
            score -= 0.10
            factors.append({"type": "mildly_negative_sentiment", "impact": "medium", "score": current_sentiment})
        
        # Sentiment momentum (improvement)
        sentiment_change = current_sentiment - older_sentiment
        if sentiment_change > 0.15:
            score += 0.15
            factors.append({"type": "improving_sentiment", "impact": "high", "change": sentiment_change})
        elif sentiment_change > 0.05:
            score += 0.08
            factors.append({"type": "slightly_improving_sentiment", "impact": "low", "change": sentiment_change})
        elif sentiment_change < -0.15:
            score -= 0.15
            factors.append({"type": "deteriorating_sentiment", "impact": "high", "change": sentiment_change})
        
        # News volume spike (early indicator)
        recent_count = recent.get("count", 0)
        older_avg = older.get("count", 1) / 7  # Daily average
        
        if older_avg > 0 and recent_count > older_avg * 2:
            # High volume - check if positive or negative
            pos_ratio = recent.get("sentiment_distribution", {}).get("positive", 0) / recent_count if recent_count else 0
            if pos_ratio > 0.6:
                score += 0.10
                factors.append({"type": "positive_news_spike", "impact": "medium", "volume_ratio": recent_count / older_avg})
            elif pos_ratio < 0.3:
                score -= 0.10
                factors.append({"type": "negative_news_spike", "impact": "medium", "volume_ratio": recent_count / older_avg})
        
        score = max(0, min(1, score))
        
        strength = "strong" if score > 0.75 else "moderate" if score > 0.55 else "weak" if score > 0.35 else "negative"
        
        return {
            "score": round(score, 3),
            "strength": strength,
            "factors": factors,
            "sentiment_data": {
                "current": round(current_sentiment, 3),
                "change": round(sentiment_change, 3),
                "articles_24h": recent_count
            }
        }
    
    def _analyze_volume_anomaly(self, stock_id: int) -> Dict:
        """Analyze volume patterns for accumulation/distribution"""
        
        cutoff = datetime.utcnow() - timedelta(days=30)
        
        prices = self.db.query(StockPrice).filter(
            StockPrice.stock_id == stock_id,
            StockPrice.timestamp >= cutoff
        ).order_by(StockPrice.timestamp).all()
        
        if len(prices) < 20:
            return {"score": 0.5, "strength": "neutral", "factors": []}
        
        # Calculate average volume
        volumes = [p.volume for p in prices if p.volume]
        if not volumes:
            return {"score": 0.5, "strength": "neutral", "factors": []}
        
        avg_volume = np.mean(volumes[:-5])  # Exclude recent
        recent_volume = np.mean(volumes[-5:])
        
        # Calculate price trend
        recent_prices = [float(p.close_price) for p in prices[-10:] if p.close_price]
        price_trend = (recent_prices[-1] - recent_prices[0]) / recent_prices[0] if recent_prices and len(recent_prices) >= 2 and recent_prices[0] > 0 else 0
        
        score = 0.5
        factors = []
        
        # Volume spike analysis
        if avg_volume > 0:
            volume_ratio = recent_volume / avg_volume
            
            if volume_ratio > 2.0 and price_trend > 0.02:
                # High volume + rising price = accumulation
                score += 0.25
                factors.append({
                    "type": "accumulation_detected",
                    "impact": "high",
                    "volume_spike": round(volume_ratio, 2),
                    "price_trend": round(price_trend * 100, 2)
                })
            elif volume_ratio > 2.0 and price_trend < -0.02:
                # High volume + falling price = distribution
                score -= 0.25
                factors.append({
                    "type": "distribution_detected",
                    "impact": "high",
                    "volume_spike": round(volume_ratio, 2),
                    "price_trend": round(price_trend * 100, 2)
                })
            elif volume_ratio > 1.5:
                # Elevated volume, neutral price
                score += 0.10
                factors.append({
                    "type": "elevated_volume",
                    "impact": "medium",
                    "volume_ratio": round(volume_ratio, 2)
                })
            elif volume_ratio < 0.5:
                # Very low volume - watch for breakout
                score += 0.05
                factors.append({
                    "type": "low_volume_consolidation",
                    "impact": "low",
                    "volume_ratio": round(volume_ratio, 2)
                })
        
        score = max(0, min(1, score))
        
        strength = "strong" if score > 0.75 else "moderate" if score > 0.55 else "weak" if score > 0.35 else "negative"
        
        return {
            "score": round(score, 3),
            "strength": strength,
            "factors": factors,
            "volume_data": {
                "average_30d": int(avg_volume),
                "recent_5d": int(recent_volume),
                "ratio": round(volume_ratio, 2) if avg_volume > 0 else 1.0,
                "price_trend_10d": round(price_trend * 100, 2)
            }
        }
    
    def _analyze_technical_confluence(self, stock_id: int) -> Dict:
        """Analyze technical indicator confluence"""
        
        cutoff = datetime.utcnow() - timedelta(days=100)
        
        prices = self.db.query(StockPrice).filter(
            StockPrice.stock_id == stock_id,
            StockPrice.timestamp >= cutoff
        ).order_by(StockPrice.timestamp).all()
        
        if len(prices) < 50:
            return {"score": 0.5, "strength": "neutral", "factors": []}
        
        closes = [float(p.close_price) for p in prices if p.close_price]
        
        score = 0.5
        factors = []
        
        # Moving average alignment
        ma_20 = np.mean(closes[-20:])
        ma_50 = np.mean(closes[-50:])
        current = closes[-1]
        
        # Golden cross / Death cross
        if ma_20 > ma_50 * 1.02:  # Golden cross area
            score += 0.15
            factors.append({"type": "ma_golden_zone", "impact": "high", "ma20": ma_20, "ma50": ma_50})
        elif ma_20 < ma_50 * 0.98:  # Death cross area
            score -= 0.15
            factors.append({"type": "ma_death_zone", "impact": "high", "ma20": ma_20, "ma50": ma_50})
        
        # Price vs moving averages
        if current > ma_20 * 1.02:  # Above 20 MA
            score += 0.10
            factors.append({"type": "above_short_ma", "impact": "medium"})
        elif current < ma_20 * 0.98:
            score -= 0.10
            factors.append({"type": "below_short_ma", "impact": "medium"})
        
        if current > ma_50 * 1.05:  # Above 50 MA with margin
            score += 0.10
            factors.append({"type": "above_long_ma", "impact": "medium"})
        elif current < ma_50 * 0.95:
            score -= 0.10
            factors.append({"type": "below_long_ma", "impact": "medium"})
        
        # Trend consistency
        price_20_days_ago = closes[-21] if len(closes) > 20 else closes[0]
        price_50_days_ago = closes[-51] if len(closes) > 50 else closes[0]
        
        trend_20 = (current - price_20_days_ago) / price_20_days_ago if price_20_days_ago > 0 else 0
        trend_50 = (current - price_50_days_ago) / price_50_days_ago if price_50_days_ago > 0 else 0
        
        if trend_20 > 0 and trend_50 > 0:
            score += 0.10
            factors.append({"type": "consistent_uptrend", "impact": "medium", "trend_20": trend_20, "trend_50": trend_50})
        elif trend_20 < 0 and trend_50 < 0:
            score -= 0.10
            factors.append({"type": "consistent_downtrend", "impact": "medium", "trend_20": trend_20, "trend_50": trend_50})
        
        score = max(0, min(1, score))
        
        strength = "strong" if score > 0.75 else "moderate" if score > 0.55 else "weak" if score > 0.35 else "negative"
        
        return {
            "score": round(score, 3),
            "strength": strength,
            "factors": factors,
            "technical_data": {
                "current_price": current,
                "ma_20": round(ma_20, 2),
                "ma_50": round(ma_50, 2),
                "price_vs_ma20_pct": round((current / ma_20 - 1) * 100, 2),
                "price_vs_ma50_pct": round((current / ma_50 - 1) * 100, 2)
            }
        }
    
    def _analyze_risk_adjusted_momentum(self, stock_id: int) -> Dict:
        """Analyze momentum relative to risk/volatility"""
        
        metrics = self.portfolio_service.calculate_stock_metrics(stock_id)
        if not metrics:
            return {"score": 0.5, "strength": "neutral", "factors": []}
        
        score = 0.5
        factors = []
        
        returns = metrics.get("annual_return", 0)
        volatility = metrics.get("annual_volatility", 1)
        sharpe = metrics.get("sharpe_ratio", 0)
        
        # Return per unit of risk
        if volatility > 0:
            return_per_risk = returns / volatility
            if return_per_risk > 0.8:
                score += 0.20
                factors.append({"type": "excellent_risk_efficiency", "impact": "high", "ratio": return_per_risk})
            elif return_per_risk > 0.5:
                score += 0.10
                factors.append({"type": "good_risk_efficiency", "impact": "medium", "ratio": return_per_risk})
            elif return_per_risk < 0:
                score -= 0.15
                factors.append({"type": "poor_risk_efficiency", "impact": "high", "ratio": return_per_risk})
        
        # Sharpe quality
        if sharpe > 1.5:
            score += 0.15
            factors.append({"type": "excellent_sharpe", "impact": "high", "sharpe": sharpe})
        elif sharpe > 1.0:
            score += 0.10
            factors.append({"type": "good_sharpe", "impact": "medium", "sharpe": sharpe})
        elif sharpe < 0:
            score -= 0.10
            factors.append({"type": "negative_sharpe", "impact": "medium", "sharpe": sharpe})
        
        score = max(0, min(1, score))
        
        strength = "strong" if score > 0.75 else "moderate" if score > 0.55 else "weak" if score > 0.35 else "negative"
        
        return {
            "score": round(score, 3),
            "strength": strength,
            "factors": factors,
            "risk_metrics": {
                "annual_return": round(returns * 100, 2),
                "volatility": round(volatility * 100, 2),
                "sharpe": round(sharpe, 2),
                "return_per_risk": round(returns / volatility, 3) if volatility > 0 else 0
            }
        }
    
    def _classify_signal(self, score: float) -> str:
        """Classify composite score into signal category"""
        if score >= self.SIGNAL_THRESHOLDS["strong_buy"]:
            return "STRONG_BUY"
        elif score >= self.SIGNAL_THRESHOLDS["buy"]:
            return "BUY"
        elif score >= self.SIGNAL_THRESHOLDS["neutral_high"]:
            return "CAUTIOUS_BUY"
        elif score >= self.SIGNAL_THRESHOLDS["neutral"]:
            return "NEUTRAL"
        elif score >= self.SIGNAL_THRESHOLDS["neutral_low"]:
            return "CAUTIOUS_SELL"
        elif score >= self.SIGNAL_THRESHOLDS["sell"]:
            return "SELL"
        else:
            return "STRONG_SELL"
    
    def _calculate_fusion_confidence(self, components: List[Dict]) -> float:
        """Calculate confidence based on component agreement"""
        scores = [c["score"] for c in components]
        
        # Agreement is when scores align in same direction
        avg_score = np.mean(scores)
        variance = np.var(scores)
        
        # High variance reduces confidence
        base_confidence = 0.8
        confidence = base_confidence - (variance * 0.5)
        
        return round(max(0.3, min(0.95, confidence)), 3)
    
    def _generate_fusion_insight(
        self,
        symbol: str,
        price_signal: Dict,
        sentiment_signal: Dict,
        volume_signal: Dict,
        technical_signal: Dict,
        composite_score: float,
        classification: str
    ) -> str:
        """Generate human-readable fusion insight"""
        
        insights = []
        
        # Identify strongest signal
        signals = [
            ("price", price_signal["score"]),
            ("sentiment", sentiment_signal["score"]),
            ("volume", volume_signal["score"]),
            ("technical", technical_signal["score"])
        ]
        strongest = max(signals, key=lambda x: x[1])
        
        # Build narrative
        if classification in ["STRONG_BUY", "BUY"]:
            insights.append(f"{symbol} shows strong buying opportunity.")
            
            if strongest[0] == "sentiment" and sentiment_signal["strength"] in ["strong", "moderate"]:
                insights.append("Positive sentiment momentum is a key driver.")
            
            if volume_signal["score"] > 0.6:
                insights.append("Volume patterns suggest institutional accumulation.")
            
            if technical_signal["score"] > 0.6:
                insights.append("Technical indicators align bullishly.")
                
        elif classification == "NEUTRAL":
            insights.append(f"{symbol} shows mixed signals - neutral positioning recommended.")
            
            # Note any contradictions
            if price_signal["score"] > 0.6 and sentiment_signal["score"] < 0.4:
                insights.append("Price strength contradicts weak sentiment - watch for reversal.")
            elif price_signal["score"] < 0.4 and sentiment_signal["score"] > 0.6:
                insights.append("Positive sentiment may drive price recovery.")
                
        elif classification in ["STRONG_SELL", "SELL"]:
            insights.append(f"{symbol} shows caution signals - consider reducing exposure.")
            
            if sentiment_signal["score"] < 0.3:
                insights.append("Negative sentiment trend supports defensive action.")
        
        return " ".join(insights)
    
    def _detect_contradictions(self, *signals: Dict) -> List[Dict]:
        """Detect contradictory signals between components"""
        
        contradictions = []
        signal_names = ["price", "sentiment", "volume", "technical"]
        
        # Check for strong divergences
        for i, (name, signal) in enumerate(zip(signal_names, signals)):
            for j, (other_name, other_signal) in enumerate(zip(signal_names, signals)):
                if i < j:  # Avoid duplicates
                    score_diff = abs(signal["score"] - other_signal["score"])
                    
                    if score_diff > 0.4:  # Significant divergence
                        contradictions.append({
                            "type": "significant_divergence",
                            "components": [name, other_name],
                            "divergence_score": round(score_diff, 3),
                            "interpretation": f"{name} and {other_name} show conflicting signals - exercise caution"
                        })
        
        return contradictions
    
    def _generate_trading_recommendation(
        self,
        classification: str,
        composite_score: float,
        stock: Stock
    ) -> Dict:
        """Generate actionable trading recommendation"""
        
        recommendations = {
            "STRONG_BUY": {
                "action": "Accumulate",
                "position_size": "Full target allocation",
                "timing": "Immediate",
                "stop_loss": "Use 10% trailing stop",
                "note": "Strong confluence of signals supports conviction"
            },
            "BUY": {
                "action": "Initiate position",
                "position_size": "Standard allocation",
                "timing": "Within 1-2 days",
                "stop_loss": "Use 8% stop loss",
                "note": "Favorable setup with manageable risk"
            },
            "CAUTIOUS_BUY": {
                "action": "Small initial position",
                "position_size": "Half standard allocation",
                "timing": "Watch for confirmation",
                "stop_loss": "Tight 5% stop",
                "note": "Wait for additional confirmation"
            },
            "NEUTRAL": {
                "action": "Hold/Watch",
                "position_size": "Current allocation",
                "timing": "Monitor for clearer signals",
                "stop_loss": "Maintain current stops",
                "note": "No strong directional edge"
            },
            "CAUTIOUS_SELL": {
                "action": "Reduce position",
                "position_size": "Trim 25-50%",
                "timing": "Over next few sessions",
                "stop_loss": "Raise stop to protect gains",
                "note": "Signs of weakening - preserve capital"
            },
            "SELL": {
                "action": "Exit position",
                "position_size": "Close position",
                "timing": "Within 1-2 days",
                "stop_loss": "Use current price as stop",
                "note": "Risk/reward no longer favorable"
            },
            "STRONG_SELL": {
                "action": "Urgent exit",
                "position_size": "Close immediately",
                "timing": "As soon as possible",
                "stop_loss": "Market order if needed",
                "note": "Multiple bearish signals align"
            }
        }
        
        return recommendations.get(classification, recommendations["NEUTRAL"])
    
    def scan_for_fusion_opportunities(self, limit: int = 20) -> List[Dict]:
        """Scan all stocks for high-conviction fusion signals"""
        
        stocks = self.db.query(Stock).limit(200).all()
        
        opportunities = []
        for stock in stocks:
            signal = self.generate_composite_signal(stock.id)
            if signal and signal["composite_score"] >= 0.65:
                opportunities.append(signal)
        
        # Sort by score
        opportunities.sort(key=lambda x: x["composite_score"], reverse=True)
        return opportunities[:limit]
    
    def get_portfolio_fusion_analysis(self, portfolio_id: int) -> Dict:
        """Analyze all holdings in a portfolio with fusion signals"""
        
        holdings = self.db.query(PortfolioHolding).filter(
            PortfolioHolding.portfolio_id == portfolio_id
        ).all()
        
        stock_signals = []
        for h in holdings:
            if h.stock:
                signal = self.generate_composite_signal(h.stock_id)
                if signal:
                    signal["current_weight"] = h.weight
                    signal["current_value"] = float(h.quantity or 0) * float(h.current_price or 0)
                    stock_signals.append(signal)
        
        # Portfolio-level fusion metrics
        avg_score = np.mean([s["composite_score"] for s in stock_signals]) if stock_signals else 0.5
        
        buy_signals = sum(1 for s in stock_signals if s["signal_classification"] in ["BUY", "STRONG_BUY"])
        sell_signals = sum(1 for s in stock_signals if s["signal_classification"] in ["SELL", "STRONG_SELL"])
        
        # Top opportunities within portfolio
        top_opportunities = sorted(
            [s for s in stock_signals if s["composite_score"] > 0.7],
            key=lambda x: x["composite_score"],
            reverse=True
        )[:5]
        
        return {
            "portfolio_id": portfolio_id,
            "holdings_analyzed": len(stock_signals),
            "average_composite_score": round(avg_score, 3),
            "portfolio_health": "strong" if avg_score > 0.6 else "moderate" if avg_score > 0.4 else "weak",
            "buy_signals_count": buy_signals,
            "sell_signals_count": sell_signals,
            "top_opportunities": top_opportunities,
            "all_signals": stock_signals,
            "recommendation": self._generate_portfolio_fusion_recommendation(
                avg_score, buy_signals, sell_signals, len(stock_signals)
            )
        }
    
    def _generate_portfolio_fusion_recommendation(
        self,
        avg_score: float,
        buy_signals: int,
        sell_signals: int,
        total_holdings: int
    ) -> str:
        """Generate portfolio-level fusion recommendation"""
        
        if avg_score > 0.6 and buy_signals > sell_signals * 2:
            return "Portfolio shows strong positive fusion signals. Consider adding to winning positions."
        elif sell_signals > buy_signals and avg_score < 0.4:
            return "Portfolio fusion signals are concerning. Review defensive positioning."
        elif buy_signals > 0 and sell_signals > 0:
            return "Mixed signals in portfolio. Rebalancing towards higher-scoring names recommended."
        else:
            return "Portfolio fusion signals are neutral. Monitor for clearer directional moves."
