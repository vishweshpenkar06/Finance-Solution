import asyncio
import json
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
import yfinance as yf

from app.core.websocket import manager
from app.models.stock import Stock, StockPrice
from app.models.portfolio import Portfolio, PortfolioHolding
from app.models.alert import Alert, AlertHistory
from app.models.news import NewsArticle
from app.services.portfolio_service import PortfolioService
from app.services.news_service import NewsService

class StreamingService:
    """Real-time streaming service for prices and alerts"""
    
    def __init__(self, db: Session):
        self.db = db
        self.portfolio_service = PortfolioService(db)
        self.news_service = NewsService(db)
    
    async def stream_price_updates(self, symbols: List[str]):
        """Stream real-time price updates via WebSocket"""
        for symbol in symbols:
            try:
                ticker = yf.Ticker(symbol)
                data = ticker.info
                
                if data:
                    price_update = {
                        "type": "price_update",
                        "symbol": symbol,
                        "price": data.get("currentPrice") or data.get("regularMarketPrice"),
                        "change": data.get("regularMarketChange"),
                        "change_percent": data.get("regularMarketChangePercent"),
                        "volume": data.get("regularMarketVolume"),
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    
                    await manager.send_to_symbol_subscribers(symbol, price_update)
            except Exception as e:
                print(f"Error streaming price for {symbol}: {e}")
    
    async def check_and_send_alerts(self):
        """Check alert conditions and send notifications"""
        # Get all active alerts
        alerts = self.db.query(Alert).filter(
            Alert.is_active == True
        ).all()
        
        for alert in alerts:
            triggered = await self._evaluate_alert(alert)
            
            if triggered and not alert.is_triggered:
                # Mark as triggered
                alert.is_triggered = True
                alert.triggered_at = datetime.utcnow()
                alert.trigger_context = triggered["context"]
                
                # Create history record
                history = AlertHistory(
                    alert_id=alert.id,
                    user_id=alert.user_id,
                    triggered_value=triggered["value"],
                    threshold_value=triggered["threshold"],
                    context_data=triggered["context"]
                )
                self.db.add(history)
                
                # Send WebSocket notification
                await manager.broadcast_alert({
                    "id": alert.id,
                    "user_id": alert.user_id,
                    "type": alert.alert_type,
                    "name": alert.alert_name,
                    "message": triggered["message"],
                    "severity": triggered["severity"],
                    "context": triggered["context"],
                    "timestamp": datetime.utcnow().isoformat()
                })
        
        self.db.commit()
    
    async def _evaluate_alert(self, alert: Alert) -> Optional[Dict]:
        """Evaluate if an alert should be triggered"""
        conditions = alert.trigger_conditions or {}
        metric = conditions.get("metric")
        operator = conditions.get("operator")
        threshold = conditions.get("threshold")
        
        if not all([metric, operator, threshold]):
            return None
        
        # Get current value based on metric type
        current_value = None
        context = {}
        
        if metric == "portfolio_risk":
            if alert.portfolio_id:
                portfolio = self.db.query(Portfolio).filter(
                    Portfolio.id == alert.portfolio_id
                ).first()
                if portfolio:
                    holdings = self.db.query(PortfolioHolding).filter(
                        PortfolioHolding.portfolio_id == alert.portfolio_id
                    ).all()
                    
                    # Calculate portfolio volatility
                    weights = [h.weight for h in holdings if h.weight]
                    volatilities = []
                    for h in holdings:
                        metrics = self.portfolio_service.calculate_stock_metrics(h.stock_id)
                        if metrics:
                            volatilities.append(metrics.get("annual_volatility", 0.2))
                    
                    if weights and volatilities:
                        current_value = sum(w * v for w, v in zip(weights, volatilities))
                        context["portfolio_name"] = portfolio.name
                        context["holding_count"] = len(holdings)
        
        elif metric == "sentiment_drop":
            if alert.portfolio_id:
                # Get sentiment for portfolio holdings
                holdings = self.db.query(PortfolioHolding).filter(
                    PortfolioHolding.portfolio_id == alert.portfolio_id
                ).all()
                
                sentiments = []
                for h in holdings:
                    if h.stock:
                        summary = self.news_service.get_sentiment_summary(h.stock.symbol, hours=24)
                        if summary.get("average_sentiment"):
                            sentiments.append(summary["average_sentiment"])
                
                if sentiments:
                    current_value = sum(sentiments) / len(sentiments)
                    context["avg_sentiment"] = current_value
                    context["affected_stocks"] = [h.stock.symbol for h in holdings if h.stock]
        
        elif metric == "price_target":
            symbol = conditions.get("symbol")
            if symbol:
                stock = self.db.query(Stock).filter(Stock.symbol == symbol).first()
                if stock:
                    latest = self.db.query(StockPrice).filter(
                        StockPrice.stock_id == stock.id
                    ).order_by(StockPrice.timestamp.desc()).first()
                    
                    if latest and latest.close_price:
                        current_value = float(latest.close_price)
                        context["symbol"] = symbol
        
        if current_value is None:
            return None
        
        # Evaluate condition
        triggered = False
        if operator == ">" and current_value > threshold:
            triggered = True
        elif operator == "<" and current_value < threshold:
            triggered = True
        elif operator == ">=" and current_value >= threshold:
            triggered = True
        elif operator == "<=" and current_value <= threshold:
            triggered = True
        elif operator == "==" and abs(current_value - threshold) < 0.001:
            triggered = True
        
        if triggered:
            severity = "high" if abs(current_value - threshold) / threshold > 0.2 else "medium"
            
            message = self._generate_alert_message(alert, current_value, threshold, context)
            
            return {
                "value": current_value,
                "threshold": threshold,
                "context": context,
                "message": message,
                "severity": severity
            }
        
        return None
    
    def _generate_alert_message(self, alert: Alert, current_value: float, 
                                threshold: float, context: Dict) -> str:
        """Generate human-readable alert message"""
        
        alert_type = alert.alert_type
        
        if alert_type == "risk_spike":
            change_pct = abs((current_value - threshold) / threshold * 100)
            return f"⚠️ Your portfolio risk increased by {change_pct:.1f}% due to market volatility. Current risk: {current_value*100:.1f}%"
        
        elif alert_type == "sentiment_drop":
            return f"📉 Sentiment alert: Market sentiment dropped to {current_value:.2f} for your holdings. Review positions in {', '.join(context.get('affected_stocks', [])[:3])}"
        
        elif alert_type == "opportunity":
            return f"🎯 Opportunity detected: {context.get('opportunity_name', 'New investment opportunity')} matches your criteria"
        
        elif alert_type == "rebalance_needed":
            return f"🔄 Portfolio drift detected: Allocation differs from target by {(current_value * 100):.1f}%. Rebalancing recommended."
        
        elif alert_type == "price_target":
            direction = "above" if current_value > threshold else "below"
            return f"📊 {context.get('symbol', 'Stock')} price reached {direction} target of ${threshold:.2f}. Current: ${current_value:.2f}"
        
        return f"Alert triggered: {alert.alert_name} - Value: {current_value}, Threshold: {threshold}"
    
    async def send_portfolio_update(self, portfolio_id: int):
        """Send real-time portfolio update to subscribers"""
        portfolio = self.db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
        if not portfolio:
            return
        
        holdings = self.db.query(PortfolioHolding).filter(
            PortfolioHolding.portfolio_id == portfolio_id
        ).all()
        
        # Calculate current metrics
        total_value = 0
        holdings_data = []
        
        for h in holdings:
            if h.stock and h.quantity and h.current_price:
                value = float(h.quantity) * float(h.current_price)
                total_value += value
                holdings_data.append({
                    "symbol": h.stock.symbol,
                    "quantity": float(h.quantity),
                    "price": float(h.current_price),
                    "value": value,
                    "weight": h.weight
                })
        
        # Calculate portfolio-level metrics
        portfolio_metrics = {
            "total_value": total_value,
            "holdings": holdings_data,
            "updated_at": datetime.utcnow().isoformat()
        }
        
        await manager.send_to_portfolio_subscribers(portfolio_id, {
            "type": "portfolio_update",
            "portfolio_id": portfolio_id,
            "data": portfolio_metrics
        })

class AlertService:
    """Service for managing alerts"""
    
    ALERT_TEMPLATES = {
        "risk_spike": {
            "name": "Portfolio Risk Alert",
            "description": "Alert when portfolio volatility exceeds threshold",
            "default_conditions": {"metric": "portfolio_risk", "operator": ">", "threshold": 0.25}
        },
        "sentiment_drop": {
            "name": "Sentiment Alert",
            "description": "Alert when market sentiment drops significantly",
            "default_conditions": {"metric": "sentiment_drop", "operator": "<", "threshold": -0.2}
        },
        "opportunity": {
            "name": "Opportunity Detection",
            "description": "Alert when new investment opportunities match criteria",
            "default_conditions": {"metric": "opportunity_score", "operator": ">", "threshold": 0.7}
        },
        "rebalance_needed": {
            "name": "Rebalance Alert",
            "description": "Alert when portfolio allocation drifts from target",
            "default_conditions": {"metric": "drift_pct", "operator": ">", "threshold": 0.05}
        }
    }
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_alert(self, user_id: int, alert_type: str, custom_conditions: Dict = None,
                    portfolio_id: int = None, name: str = None) -> Alert:
        """Create a new alert"""
        
        template = self.ALERT_TEMPLATES.get(alert_type, {})
        conditions = custom_conditions or template.get("default_conditions", {})
        
        alert = Alert(
            user_id=user_id,
            portfolio_id=portfolio_id,
            alert_type=alert_type,
            alert_name=name or template.get("name", f"Alert {alert_type}"),
            trigger_conditions=conditions,
            is_active=True,
            notification_channels=["websocket"]
        )
        
        self.db.add(alert)
        self.db.commit()
        self.db.refresh(alert)
        return alert
    
    def get_user_alerts(self, user_id: int, include_inactive: bool = False) -> List[Alert]:
        """Get all alerts for a user"""
        query = self.db.query(Alert).filter(Alert.user_id == user_id)
        
        if not include_inactive:
            query = query.filter(Alert.is_active == True)
        
        return query.order_by(Alert.created_at.desc()).all()
    
    def acknowledge_alert(self, alert_id: int, action: str = "acknowledged") -> Alert:
        """Mark alert as acknowledged by user"""
        alert = self.db.query(Alert).filter(Alert.id == alert_id).first()
        if alert:
            alert.is_acknowledged = True
            alert.acknowledged_at = datetime.utcnow()
            alert.user_action = action
            
            # Reset triggered state for future triggers
            alert.is_triggered = False
            
            self.db.commit()
            self.db.refresh(alert)
        
        return alert
