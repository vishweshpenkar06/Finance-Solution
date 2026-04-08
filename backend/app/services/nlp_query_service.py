from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import re
import json

from app.models.portfolio import Portfolio, PortfolioHolding
from app.models.stock import Stock, StockPrice
from app.models.news import NewsArticle
from app.services.portfolio_service import PortfolioService
from app.services.explanation_service import ExplanationService
from app.services.fusion_service import DataFusionService

class NLPQueryService:
    """Natural Language Query Interface - Chat with Your Portfolio"""
    
    # Query patterns for intent recognition
    QUERY_PATTERNS = {
        "portfolio_summary": [
            r"how is my portfolio",
            r"portfolio summary",
            r"what is my portfolio",
            r"show my portfolio",
            r"portfolio status"
        ],
        "risk_analysis": [
            r"(?:why is|what makes) my portfolio risky",
            r"how risky is my portfolio",
            r"portfolio risk",
            r"risk assessment",
            r"dangerous",
            r"volatility"
        ],
        "performance": [
            r"how (?:is|are) my (?:returns|performance)",
            r"portfolio performance",
            r"my returns",
            r"am i making money",
            r"performance summary",
            r"how much (?:gain|profit|loss)"
        ],
        "comparison": [
            r"compare (?:to|with|against)",
            r"benchmark",
            r"vs\.",
            r"versus",
            r"outperform"
        ],
        "recommendations": [
            r"what (?:should|to) (?:buy|invest)",
            r"best stock",
            r"recommendation",
            r"suggest investment",
            r"where (?:should|to) invest"
        ],
        "rebalancing": [
            r"rebalance",
            r"should i (?:sell|buy)",
            r"allocation",
            r"drift"
        ],
        "opportunities": [
            r"opportunit",
            r"undervalued",
            r"good (?:buy|investment)",
            r"hidden gem",
            r"buy now"
        ],
        "sentiment": [
            r"sentiment",
            r"news about",
            r"what (?:is|are) (?:the|people) saying",
            r"market mood",
            r"bullish|bearish"
        ],
        "explain_stock": [
            r"why (?:was|is) .* selected",
            r"explain.* in my portfolio",
            r"tell me about",
            r"what about.* stock"
        ],
        "help": [
            r"help",
            r"what can you do",
            r"commands",
            r"available",
            r"features"
        ]
    }
    
    def __init__(self, db: Session):
        self.db = db
        self.portfolio_service = PortfolioService(db)
        self.explanation_service = ExplanationService(db)
        self.fusion_service = DataFusionService(db)
    
    def process_query(self, query: str, user_id: int, portfolio_id: int = None) -> Dict:
        """Process a natural language query and return a response"""
        
        query_lower = query.lower().strip()
        
        # Detect intent
        intent = self._detect_intent(query_lower)
        
        # Extract entities (stock symbols, time periods, etc.)
        entities = self._extract_entities(query_lower)
        
        # Generate response based on intent
        response = self._generate_response(intent, entities, user_id, portfolio_id)
        
        return {
            "original_query": query,
            "detected_intent": intent,
            "entities": entities,
            "response": response,
            "processed_at": datetime.utcnow().isoformat()
        }
    
    def _detect_intent(self, query: str) -> str:
        """Detect user intent from query patterns"""
        
        scores = {}
        
        for intent, patterns in self.QUERY_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, query, re.IGNORECASE):
                    scores[intent] = scores.get(intent, 0) + 1
        
        if not scores:
            return "general"
        
        # Return highest scoring intent
        return max(scores.items(), key=lambda x: x[1])[0]
    
    def _extract_entities(self, query: str) -> Dict:
        """Extract relevant entities from query"""
        
        entities = {
            "symbols": [],
            "time_period": None,
            "metrics": [],
            "actions": []
        }
        
        # Extract stock symbols (1-5 uppercase letters)
        symbol_pattern = r'\b([A-Z]{1,5})\b'
        symbols = re.findall(symbol_pattern, query.upper())
        
        # Filter out common words
        common_words = {'A', 'I', 'CEO', 'CFO', 'IPO', 'GDP', 'USA', 'ETF', 'NYSE', 'NASDAQ', 'WHY', 'WHAT', 'HOW'}
        entities["symbols"] = [s for s in symbols if s not in common_words]
        
        # Extract time periods
        time_patterns = {
            "1d": r'(?:today|1 day|daily)',
            "1w": r'(?:1 week|weekly|this week)',
            "1m": r'(?:1 month|monthly|this month)',
            "3m": r'(?:3 month|quarter)',
            "6m": r'(?:6 month|half year)',
            "1y": r'(?:1 year|yearly|annual|this year)',
            "ytd": r'(?:ytd|year to date)',
            "all": r'(?:all time|since inception)'
        }
        
        for period, pattern in time_patterns.items():
            if re.search(pattern, query, re.IGNORECASE):
                entities["time_period"] = period
                break
        
        # Extract metrics
        metric_patterns = {
            "risk": r'(?:risk|volatility|dangerous)',
            "return": r'(?:return|gain|profit|performance)',
            "sharpe": r'(?:sharpe|risk.?adjusted)',
            "drawdown": r'(?:drawdown|decline|drop)',
            "sentiment": r'(?:sentiment|mood|feeling)',
            "valuation": r'(?:valuation|pe ratio|price)'
        }
        
        for metric, pattern in metric_patterns.items():
            if re.search(pattern, query, re.IGNORECASE):
                entities["metrics"].append(metric)
        
        # Extract action intents
        action_patterns = {
            "buy": r'(?:buy|purchase|add)',
            "sell": r'(?:sell|exit|remove)',
            "hold": r'(?:hold|keep|maintain)',
            "rebalance": r'(?:rebalance|reallocate)'
        }
        
        for action, pattern in action_patterns.items():
            if re.search(pattern, query, re.IGNORECASE):
                entities["actions"].append(action)
        
        return entities
    
    def _generate_response(
        self,
        intent: str,
        entities: Dict,
        user_id: int,
        portfolio_id: int = None
    ) -> Dict:
        """Generate appropriate response based on intent"""
        
        response_generators = {
            "portfolio_summary": self._generate_portfolio_summary,
            "risk_analysis": self._generate_risk_response,
            "performance": self._generate_performance_response,
            "comparison": self._generate_comparison_response,
            "recommendations": self._generate_recommendations_response,
            "rebalancing": self._generate_rebalancing_response,
            "opportunities": self._generate_opportunities_response,
            "sentiment": self._generate_sentiment_response,
            "explain_stock": self._generate_explain_stock_response,
            "help": self._generate_help_response,
            "general": self._generate_general_response
        }
        
        generator = response_generators.get(intent, self._generate_general_response)
        return generator(entities, user_id, portfolio_id)
    
    def _generate_portfolio_summary(self, entities: Dict, user_id: int, portfolio_id: int = None) -> Dict:
        """Generate portfolio summary response"""
        
        # Get user's portfolio
        portfolio = self._get_user_portfolio(user_id, portfolio_id)
        if not portfolio:
            return {
                "text": "I don't see any portfolio for you yet. Would you like me to help you create one?",
                "type": "empty_portfolio",
                "data": None
            }
        
        # Get holdings
        holdings = self.db.query(PortfolioHolding).filter(
            PortfolioHolding.portfolio_id == portfolio.id
        ).all()
        
        total_value = 0
        holdings_summary = []
        
        for h in holdings:
            if h.stock and h.quantity and h.current_price:
                value = float(h.quantity) * float(h.current_price)
                total_value += value
                holdings_summary.append({
                    "symbol": h.stock.symbol,
                    "name": h.stock.name,
                    "value": value,
                    "weight": h.weight
                })
        
        # Get metrics
        metrics = self._get_portfolio_metrics(portfolio.id, holdings)
        
        return {
            "text": self._format_portfolio_summary(portfolio, total_value, len(holdings_summary), metrics),
            "type": "portfolio_summary",
            "data": {
                "portfolio_name": portfolio.name,
                "total_value": total_value,
                "holdings_count": len(holdings_summary),
                "metrics": metrics,
                "top_holdings": sorted(holdings_summary, key=lambda x: x["value"], reverse=True)[:5]
            }
        }
    
    def _generate_risk_response(self, entities: Dict, user_id: int, portfolio_id: int = None) -> Dict:
        """Generate risk analysis response"""
        
        portfolio = self._get_user_portfolio(user_id, portfolio_id)
        if not portfolio:
            return {"text": "Please create a portfolio first to analyze its risk.", "type": "no_portfolio"}
        
        holdings = self.db.query(PortfolioHolding).filter(
            PortfolioHolding.portfolio_id == portfolio.id
        ).all()
        
        # Calculate risk breakdown
        risk_breakdown = self._calculate_portfolio_risk_breakdown(holdings)
        
        return {
            "text": self._format_risk_explanation(risk_breakdown),
            "type": "risk_analysis",
            "data": risk_breakdown,
            "visualization": {
                "type": "risk_heatmap",
                "data": risk_breakdown["sector_risks"]
            }
        }
    
    def _generate_performance_response(self, entities: Dict, user_id: int, portfolio_id: int = None) -> Dict:
        """Generate performance summary response"""
        
        portfolio = self._get_user_portfolio(user_id, portfolio_id)
        if not portfolio:
            return {"text": "Please create a portfolio first to see performance.", "type": "no_portfolio"}
        
        # Get performance data
        holdings = self.db.query(PortfolioHolding).filter(
            PortfolioHolding.portfolio_id == portfolio.id
        ).all()
        
        total_value = 0
        cost_basis = 0
        
        for h in holdings:
            if h.quantity and h.current_price and h.avg_cost:
                total_value += float(h.quantity) * float(h.current_price)
                cost_basis += float(h.quantity) * float(h.avg_cost)
        
        pnl = total_value - cost_basis
        pnl_pct = (pnl / cost_basis * 100) if cost_basis > 0 else 0
        
        return {
            "text": self._format_performance_summary(total_value, cost_basis, pnl, pnl_pct),
            "type": "performance_summary",
            "data": {
                "total_value": total_value,
                "cost_basis": cost_basis,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "is_profitable": pnl > 0
            }
        }
    
    def _generate_recommendations_response(self, entities: Dict, user_id: int, portfolio_id: int = None) -> Dict:
        """Generate recommendations response"""
        
        user = self.db.query(User).filter(User.id == user_id).first()
        risk_tolerance = user.risk_tolerance if user else "moderate"
        
        recommendations = self.portfolio_service.generate_portfolio_recommendations(
            risk_tolerance=risk_tolerance,
            investment_amount=10000
        )
        
        return {
            "text": f"Based on your {risk_tolerance} risk profile, here are my top recommendations:\n\n" +
                    self._format_recommendations(recommendations[:5]),
            "type": "recommendations",
            "data": {
                "risk_profile": risk_tolerance,
                "recommendations": recommendations[:5]
            }
        }
    
    def _generate_opportunities_response(self, entities: Dict, user_id: int, portfolio_id: int = None) -> Dict:
        """Generate opportunities response"""
        
        opportunities = self.fusion_service.scan_for_fusion_opportunities(limit=5)
        
        return {
            "text": f"I found {len(opportunities)} interesting opportunities using data fusion:\n\n" +
                    self._format_opportunities(opportunities),
            "type": "opportunities",
            "data": opportunities
        }
    
    def _generate_sentiment_response(self, entities: Dict, user_id: int, portfolio_id: int = None) -> Dict:
        """Generate sentiment analysis response"""
        
        symbols = entities.get("symbols", [])
        
        if symbols:
            # Specific stock sentiment
            results = []
            for symbol in symbols[:3]:
                sentiment = self.news_service.get_sentiment_summary(symbol, hours=72)
                results.append({
                    "symbol": symbol,
                    "sentiment": sentiment
                })
            
            return {
                "text": self._format_sentiment_summary(results),
                "type": "sentiment_specific",
                "data": results
            }
        else:
            # Market-wide sentiment
            sentiment = self.news_service.get_sentiment_summary(hours=24)
            
            return {
                "text": f"Market sentiment in the last 24 hours:\n" +
                        f"Overall: {sentiment.get('summary', 'neutral')}\n" +
                        f"Score: {sentiment.get('average_sentiment', 0):.2f}\n" +
                        f"Articles analyzed: {sentiment.get('count', 0)}",
                "type": "sentiment_market",
                "data": sentiment
            }
    
    def _generate_explain_stock_response(self, entities: Dict, user_id: int, portfolio_id: int = None) -> Dict:
        """Generate stock explanation response"""
        
        symbols = entities.get("symbols", [])
        if not symbols:
            # Try to extract from query differently
            return {
                "text": "Which stock would you like me to explain? Please mention a ticker symbol like AAPL or MSFT.",
                "type": "clarification"
            }
        
        symbol = symbols[0]
        stock = self.db.query(Stock).filter(Stock.symbol == symbol).first()
        
        if not stock:
            return {
                "text": f"I don't have data for {symbol} yet. Would you like me to add it to our database?",
                "type": "stock_not_found"
            }
        
        # Get explanation
        explanation = self.explanation_service.explain_stock_selection(
            stock.id,
            {"current_sectors": []},
            "moderate"
        )
        
        return {
            "text": f"Here's why {symbol} {explanation.get('reasoning_text', 'was selected')}:",
            "type": "stock_explanation",
            "data": explanation
        }
    
    def _generate_help_response(self, entities: Dict, user_id: int, portfolio_id: int = None) -> Dict:
        """Generate help response"""
        
        return {
            "text": """🤖 **Smart Finance Assistant**

Here's what I can help you with:

**Portfolio Questions:**
- "How is my portfolio doing?"
- "Why is my portfolio risky?"
- "Show my performance"

**Investment Decisions:**
- "What should I invest in?"
- "Any good opportunities?"
- "Should I rebalance?"

**Stock Analysis:**
- "Tell me about AAPL"
- "News sentiment on TSLA?"
- "Explain why NVDA is in my portfolio"

**Comparisons:**
- "Compare my portfolio to S&P 500"
- "How am I doing vs NIFTY 50?"

Just ask naturally - I understand what you mean! 🚀""",
            "type": "help",
            "data": {
                "categories": list(self.QUERY_PATTERNS.keys())
            }
        }
    
    def _generate_general_response(self, entities: Dict, user_id: int, portfolio_id: int = None) -> Dict:
        """Generate general/unclear response"""
        
        return {
            "text": "I'm not sure I understand. You can ask me about:\n" +
                    "• Your portfolio performance\n" +
                    "• Risk analysis\n" +
                    "• Investment recommendations\n" +
                    "• Stock explanations\n" +
                    "• Market sentiment\n\n" +
                    "Try 'help' for more options!",
            "type": "clarification"
        }
    
    # Helper methods for response generation
    def _get_user_portfolio(self, user_id: int, portfolio_id: int = None):
        """Get user's portfolio"""
        query = self.db.query(Portfolio).filter(Portfolio.user_id == user_id)
        if portfolio_id:
            query = query.filter(Portfolio.id == portfolio_id)
        return query.first()
    
    def _get_portfolio_metrics(self, portfolio_id: int, holdings) -> Dict:
        """Calculate portfolio metrics"""
        weights = [h.weight for h in holdings if h.weight]
        return {
            "risk_score": 0.15,  # Simplified
            "diversification_score": len(set(h.stock.sector for h in holdings if h.stock)) if holdings else 0
        }
    
    def _calculate_portfolio_risk_breakdown(self, holdings) -> Dict:
        """Calculate detailed risk breakdown"""
        sector_risks = {}
        total_value = 0
        
        for h in holdings:
            if h.stock and h.weight:
                metrics = self.portfolio_service.calculate_stock_metrics(h.stock_id)
                if metrics:
                    sector = h.stock.sector or "Unknown"
                    if sector not in sector_risks:
                        sector_risks[sector] = []
                    sector_risks[sector].append({
                        "symbol": h.stock.symbol,
                        "volatility": metrics.get("annual_volatility", 0),
                        "weight": h.weight
                    })
                    total_value += float(h.quantity or 0) * float(h.current_price or 0)
        
        return {
            "total_value": total_value,
            "sector_risks": sector_risks,
            "concentration_risk": "high" if any(len(s) > 3 for s in sector_risks.values()) else "medium"
        }
    
    # Formatting methods
    def _format_portfolio_summary(self, portfolio, total_value, holdings_count, metrics) -> str:
        return f"📊 **{portfolio.name} Summary**\n\n" \
               f"💰 Total Value: ${total_value:,.2f}\n" \
               f"📈 Holdings: {holdings_count} positions\n" \
               f"⚖️ Diversification: {metrics.get('diversification_score', 0)} sectors\n" \
               f"🎯 Strategy: {portfolio.strategy or 'balanced'}\n" \
               f"📉 Risk Level: {portfolio.risk_score or 'moderate'}"
    
    def _format_risk_explanation(self, risk_breakdown) -> str:
        text = "⚠️ **Risk Analysis**\n\n"
        text += f"Total Portfolio Value: ${risk_breakdown['total_value']:,.2f}\n\n"
        text += "Sector Risk Breakdown:\n"
        
        for sector, stocks in risk_breakdown["sector_risks"].items():
            avg_vol = sum(s["volatility"] for s in stocks) / len(stocks) if stocks else 0
            text += f"  • {sector}: {len(stocks)} stocks, avg volatility {avg_vol*100:.1f}%\n"
        
        text += f"\n⚠️ Concentration Risk: {risk_breakdown['concentration_risk']}"
        
        return text
    
    def _format_performance_summary(self, total_value, cost_basis, pnl, pnl_pct) -> str:
        emoji = "🟢" if pnl > 0 else "🔴"
        return f"{emoji} **Performance Summary**\n\n" \
               f"💰 Current Value: ${total_value:,.2f}\n" \
               f"💵 Cost Basis: ${cost_basis:,.2f}\n" \
               f"{'📈' if pnl > 0 else '📉'} P&L: ${pnl:,.2f} ({pnl_pct:+.2f}%)"
    
    def _format_recommendations(self, recommendations) -> str:
        text = ""
        for i, rec in enumerate(recommendations, 1):
            text += f"{i}. **{rec['symbol']}** ({rec.get('sector', 'N/A')})\n" \
                   f"   Weight: {rec['weight']*100:.1f}% | Expected Return: {rec['expected_return']*100:.1f}% | Sharpe: {rec['sharpe_ratio']}\n" \
                   f"   {rec.get('rationale', '')}\n\n"
        return text
    
    def _format_opportunities(self, opportunities) -> str:
        text = ""
        for opp in opportunities[:5]:
            text += f"• **{opp['symbol']}** - Score: {opp['detection_score']:.2f}\n" \
                   f"  Type: {opp['opportunity_type']} | Confidence: {opp['confidence']}\n" \
                   f"  {opp['fusion_insight'][:100]}...\n\n"
        return text
    
    def _format_sentiment_summary(self, results) -> str:
        text = "📰 **Sentiment Analysis**\n\n"
        for r in results:
            s = r["sentiment"]
            emoji = "🟢" if s.get("summary") == "positive" else "🔴" if s.get("summary") == "negative" else "⚪"
            text += f"{emoji} {r['symbol']}: {s.get('summary', 'neutral')} " \
                   f"(score: {s.get('average_sentiment', 0):.2f})\n"
        return text
