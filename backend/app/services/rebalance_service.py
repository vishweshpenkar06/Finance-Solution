from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import numpy as np
from collections import defaultdict

from app.models.portfolio import Portfolio, PortfolioHolding
from app.models.stock import Stock, StockPrice
from app.models.explanation import RecommendationExplanation
from app.services.portfolio_service import PortfolioService
from app.core.websocket import manager

class RebalanceService:
    """Auto-rebalancing engine with action triggers"""
    
    # Rebalancing thresholds
    DRIFT_THRESHOLD = 0.05  # 5% drift triggers rebalancing recommendation
    REBALANCE_TOLERANCE = 0.02  # Allow 2% variance from target
    
    # Tax/transaction cost assumptions (simplified)
    TRANSACTION_COST_PCT = 0.001  # 0.1% per trade
    TAX_COST_PCT = 0.15  # 15% short-term capital gains
    
    def __init__(self, db: Session):
        self.db = db
        self.portfolio_service = PortfolioService(db)
    
    def analyze_drift(self, portfolio_id: int) -> Dict:
        """Analyze current portfolio drift from target allocations"""
        
        portfolio = self.db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
        if not portfolio:
            return None
        
        holdings = self.db.query(PortfolioHolding).filter(
            PortfolioHolding.portfolio_id == portfolio_id
        ).all()
        
        # Calculate current weights based on market values
        total_value = 0
        current_weights = {}
        
        for h in holdings:
            if h.stock and h.quantity and h.current_price:
                value = float(h.quantity) * float(h.current_price)
                total_value += value
                current_weights[h.stock.symbol] = {
                    "stock_id": h.stock_id,
                    "current_weight": 0,
                    "target_weight": h.weight or 0,
                    "current_value": value,
                    "current_price": float(h.current_price),
                    "quantity": float(h.quantity),
                    "avg_cost": float(h.avg_cost) if h.avg_cost else float(h.current_price)
                }
        
        # Calculate actual weights
        for symbol, data in current_weights.items():
            if total_value > 0:
                data["current_weight"] = data["current_value"] / total_value
            data["drift"] = data["current_weight"] - data["target_weight"]
        
        # Identify significant drifts
        drifts = []
        for symbol, data in current_weights.items():
            drift_pct = abs(data["drift"]) * 100
            if drift_pct > self.DRIFT_THRESHOLD * 100:
                drifts.append({
                    "symbol": symbol,
                    "drift_pct": round(drift_pct, 2),
                    "direction": "overweight" if data["drift"] > 0 else "underweight",
                    "current_weight": round(data["current_weight"] * 100, 2),
                    "target_weight": round(data["target_weight"] * 100, 2),
                    "requires_action": drift_pct > self.REBALANCE_TOLERANCE * 100 * 2
                })
        
        # Sort by drift magnitude
        drifts.sort(key=lambda x: x["drift_pct"], reverse=True)
        
        return {
            "portfolio_id": portfolio_id,
            "portfolio_name": portfolio.name,
            "total_value": round(total_value, 2),
            "drift_analysis": drifts,
            "max_drift": drifts[0]["drift_pct"] if drifts else 0,
            "rebalance_needed": len(drifts) > 0 and any(d["requires_action"] for d in drifts),
            "analyzed_at": datetime.utcnow().isoformat()
        }
    
    def generate_rebalance_actions(
        self, 
        portfolio_id: int,
        constraints: Dict = None
    ) -> List[Dict]:
        """Generate specific rebalancing actions"""
        
        drift_analysis = self.analyze_drift(portfolio_id)
        if not drift_analysis or not drift_analysis["rebalance_needed"]:
            return []
        
        portfolio = self.db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
        holdings = self.db.query(PortfolioHolding).filter(
            PortfolioHolding.portfolio_id == portfolio_id
        ).all()
        
        actions = []
        total_value = drift_analysis["total_value"]
        
        for drift in drift_analysis["drift_analysis"]:
            if not drift["requires_action"]:
                continue
            
            symbol = drift["symbol"]
            holding = next((h for h in holdings if h.stock and h.stock.symbol == symbol), None)
            
            if not holding or not holding.current_price:
                continue
            
            current_price = float(holding.current_price)
            current_qty = float(holding.quantity or 0)
            target_weight = drift["target_weight"] / 100
            
            # Calculate target value and quantity
            target_value = total_value * target_weight
            current_value = current_qty * current_price
            value_difference = target_value - current_value
            
            if drift["direction"] == "overweight":
                # Need to sell
                sell_value = current_value - target_value
                sell_qty = sell_value / current_price if current_price > 0 else 0
                
                # Calculate tax implication
                unrealized_pnl = (current_price - float(holding.avg_cost or current_price)) * current_qty
                if unrealized_pnl > 0:
                    tax_cost = unrealized_pnl * self.TAX_COST_PCT * (sell_qty / current_qty)
                else:
                    tax_cost = 0
                
                actions.append({
                    "action": "SELL",
                    "symbol": symbol,
                    "current_qty": round(current_qty, 4),
                    "target_qty": round(target_value / current_price, 4),
                    "sell_qty": round(sell_qty, 4),
                    "sell_value": round(sell_value, 2),
                    "estimated_tax_cost": round(tax_cost, 2),
                    "transaction_cost": round(sell_value * self.TRANSACTION_COST_PCT, 2),
                    "rationale": f"{symbol} is overweight by {drift['drift_pct']:.1f}%. Selling {sell_qty:.2f} shares to align with target.",
                    "priority": "high" if drift["drift_pct"] > 10 else "medium"
                })
            
            else:
                # Need to buy
                buy_value = target_value - current_value
                buy_qty = buy_value / current_price if current_price > 0 else 0
                
                actions.append({
                    "action": "BUY",
                    "symbol": symbol,
                    "current_qty": round(current_qty, 4),
                    "target_qty": round(target_value / current_price, 4),
                    "buy_qty": round(buy_qty, 4),
                    "buy_value": round(buy_value, 2),
                    "transaction_cost": round(buy_value * self.TRANSACTION_COST_PCT, 2),
                    "rationale": f"{symbol} is underweight by {drift['drift_pct']:.1f}%. Buying {buy_qty:.2f} shares to align with target.",
                    "priority": "high" if drift["drift_pct"] > 10 else "medium"
                })
        
        # Calculate total impact
        total_buy_value = sum(a["buy_value"] for a in actions if a["action"] == "BUY")
        total_sell_value = sum(a["sell_value"] for a in actions if a["action"] == "SELL")
        total_transaction_cost = sum(a.get("transaction_cost", 0) for a in actions)
        total_tax_cost = sum(a.get("estimated_tax_cost", 0) for a in actions)
        
        return {
            "actions": actions,
            "summary": {
                "total_actions": len(actions),
                "total_buy_value": round(total_buy_value, 2),
                "total_sell_value": round(total_sell_value, 2),
                "net_cash_required": round(total_buy_value - total_sell_value, 2),
                "estimated_transaction_costs": round(total_transaction_cost, 2),
                "estimated_tax_costs": round(total_tax_cost, 2),
                "total_implementation_cost": round(total_transaction_cost + total_tax_cost, 2)
            },
            "portfolio_impact": {
                "risk_reduction_estimate": "Medium - Restores target diversification",
                "tax_efficiency": "Tax-optimized sequencing recommended" if total_tax_cost > 0 else "No tax impact",
                "implementation_timeline": "Immediate" if len(actions) <= 3 else "Staged over 2-3 days"
            }
        }
    
    def optimize_rebalance_timing(
        self,
        portfolio_id: int,
        days_ahead: int = 7
    ) -> Dict:
        """Suggest optimal timing for rebalancing based on market conditions"""
        
        drift_analysis = self.analyze_drift(portfolio_id)
        if not drift_analysis:
            return None
        
        # Get sentiment for next days
        sentiment = self.db.query(Stock).join(PortfolioHolding).filter(
            PortfolioHolding.portfolio_id == portfolio_id
        ).limit(5).all()
        
        market_sentiment_score = 0.5  # Neutral default
        
        # Simple timing logic
        if market_sentiment_score > 0.3:
            recommendation = "Favorable - Market sentiment is positive for rebalancing"
            urgency = "medium"
        elif market_sentiment_score < -0.2:
            recommendation = "Consider delaying - Negative sentiment may present better entry points"
            urgency = "low"
        else:
            recommendation = "Neutral timing - Proceed based on drift magnitude alone"
            urgency = "medium"
        
        return {
            "current_drift": drift_analysis["max_drift"],
            "market_sentiment": market_sentiment_score,
            "recommendation": recommendation,
            "urgency": urgency,
            "suggested_date": (datetime.utcnow() + timedelta(days=1 if urgency == "high" else 3)).isoformat(),
            "factors": {
                "drift_magnitude": "High" if drift_analysis["max_drift"] > 10 else "Medium",
                "market_conditions": "Favorable" if market_sentiment_score > 0.2 else "Mixed",
                "tax_considerations": "Consider tax-loss harvesting opportunities"
            }
        }
    
    def apply_rebalance_simulation(
        self,
        portfolio_id: int,
        actions: List[Dict],
        dry_run: bool = True
    ) -> Dict:
        """Simulate or apply rebalancing actions"""
        
        portfolio = self.db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
        if not portfolio:
            return None
        
        results = {
            "portfolio_id": portfolio_id,
            "dry_run": dry_run,
            "actions_applied": [],
            "actions_failed": [],
            "new_portfolio_state": None
        }
        
        for action in actions:
            try:
                symbol = action["symbol"]
                holding = self.db.query(PortfolioHolding).join(Stock).filter(
                    PortfolioHolding.portfolio_id == portfolio_id,
                    Stock.symbol == symbol
                ).first()
                
                if not holding:
                    results["actions_failed"].append({
                        "action": action,
                        "reason": "Holding not found"
                    })
                    continue
                
                if not dry_run:
                    # Actually update quantities
                    if action["action"] == "SELL":
                        sell_qty = action["sell_qty"]
                        new_qty = float(holding.quantity) - sell_qty
                        holding.quantity = max(0, new_qty)
                    elif action["action"] == "BUY":
                        buy_qty = action["buy_qty"]
                        # Update average cost basis
                        old_qty = float(holding.quantity or 0)
                        old_cost = float(holding.avg_cost or 0) * old_qty
                        new_cost = action["buy_value"]
                        new_total_qty = old_qty + buy_qty
                        
                        if new_total_qty > 0:
                            holding.avg_cost = (old_cost + new_cost) / new_total_qty
                        holding.quantity = new_total_qty
                
                results["actions_applied"].append(action)
                
            except Exception as e:
                results["actions_failed"].append({
                    "action": action,
                    "reason": str(e)
                })
        
        if not dry_run:
            self.db.commit()
            # Recalculate weights
            self.recalculate_portfolio_weights(portfolio_id)
            
            # Send real-time update
            from app.services.streaming_service import StreamingService
            streaming = StreamingService(self.db)
            asyncio.create_task(streaming.send_portfolio_update(portfolio_id))
        
        # Calculate new state
        new_state = self.analyze_drift(portfolio_id)
        results["new_portfolio_state"] = new_state
        
        return results
    
    def recalculate_portfolio_weights(self, portfolio_id: int):
        """Recalculate portfolio weights after rebalancing"""
        
        holdings = self.db.query(PortfolioHolding).filter(
            PortfolioHolding.portfolio_id == portfolio_id
        ).all()
        
        total_value = 0
        for h in holdings:
            if h.quantity and h.current_price:
                total_value += float(h.quantity) * float(h.current_price)
        
        # Update weights
        for h in holdings:
            if h.quantity and h.current_price and total_value > 0:
                value = float(h.quantity) * float(h.current_price)
                h.weight = value / total_value
            else:
                h.weight = 0
        
        self.db.commit()
    
    def generate_rebalance_report(self, portfolio_id: int) -> Dict:
        """Generate comprehensive rebalancing report"""
        
        drift = self.analyze_drift(portfolio_id)
        actions = self.generate_rebalance_actions(portfolio_id)
        timing = self.optimize_rebalance_timing(portfolio_id)
        
        return {
            "report_type": "Rebalancing Analysis",
            "generated_at": datetime.utcnow().isoformat(),
            "portfolio_id": portfolio_id,
            "drift_analysis": drift,
            "recommended_actions": actions,
            "timing_analysis": timing,
            "executive_summary": self._generate_executive_summary(drift, actions, timing)
        }
    
    def _generate_executive_summary(self, drift: Dict, actions: Dict, timing: Dict) -> str:
        """Generate executive summary of rebalancing needs"""
        
        if not drift["rebalance_needed"]:
            return f"✅ {drift['portfolio_name']} is well-balanced. Maximum drift is only {drift['max_drift']:.1f}%, within tolerance. No action required."
        
        action_count = len(actions.get("actions", []))
        summary = f"⚠️ {drift['portfolio_name']} requires rebalancing. "
        summary += f"Maximum drift of {drift['max_drift']:.1f}% detected. "
        summary += f"{action_count} trades recommended with estimated cost of ${actions.get('summary', {}).get('total_implementation_cost', 0):.2f}. "
        summary += f"Market timing: {timing.get('recommendation', 'Proceed with caution')}."
        
        return summary

import asyncio
