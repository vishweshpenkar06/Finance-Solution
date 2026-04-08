from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import json
import numpy as np

from app.models.snapshot import PortfolioSnapshot, PortfolioEvent
from app.models.portfolio import Portfolio, PortfolioHolding
from app.models.stock import Stock
from app.services.portfolio_service import PortfolioService
from app.services.benchmark_service import BenchmarkService
from app.services.cache import cached

class SnapshotService:
    """Portfolio history tracking and snapshot management"""
    
    def __init__(self, db: Session):
        self.db = db
        self.portfolio_service = PortfolioService(db)
        self.benchmark_service = BenchmarkService(db)
    
    def create_snapshot(
        self,
        portfolio_id: int,
        snapshot_type: str = "daily",
        triggered_by: str = "scheduled"
    ) -> PortfolioSnapshot:
        """Create a portfolio snapshot at current state"""
        
        portfolio = self.db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
        if not portfolio:
            return None
        
        holdings = self.db.query(PortfolioHolding).filter(
            PortfolioHolding.portfolio_id == portfolio_id
        ).all()
        
        # Calculate current metrics
        total_value = 0
        cost_basis = 0
        unrealized_pnl = 0
        holdings_snapshot = []
        sector_allocation = {}
        
        for h in holdings:
            if h.stock and h.quantity and h.current_price:
                value = float(h.quantity) * float(h.current_price)
                cost = float(h.quantity) * float(h.avg_cost or h.current_price)
                
                total_value += value
                cost_basis += cost
                unrealized_pnl += (value - cost)
                
                weight = h.weight or 0
                
                # Sector allocation
                sector = h.stock.sector or "Unknown"
                sector_allocation[sector] = sector_allocation.get(sector, 0) + weight
                
                holdings_snapshot.append({
                    "stock_id": h.stock_id,
                    "symbol": h.stock.symbol,
                    "name": h.stock.name,
                    "sector": sector,
                    "quantity": float(h.quantity),
                    "avg_cost": float(h.avg_cost or 0),
                    "current_price": float(h.current_price),
                    "current_value": value,
                    "weight": weight,
                    "unrealized_pnl": value - cost,
                    "unrealized_pnl_pct": (value - cost) / cost if cost > 0 else 0
                })
        
        # Calculate risk metrics
        portfolio_metrics = self._calculate_portfolio_risk_metrics(portfolio_id, holdings)
        
        # Compare to benchmark
        benchmark_comparison = None
        benchmark_symbol = "^GSPC"  # Default to S&P 500
        
        if portfolio_metrics.get("returns_available"):
            benchmark_comp = self.benchmark_service.compare_portfolio_vs_benchmark(
                portfolio_id,
                benchmark_symbol,
                period_days=30
            )
            if benchmark_comp:
                benchmark_comparison = {
                    "symbol": benchmark_symbol,
                    "outperformance_pct": benchmark_comp["comparison"]["outperformance_pct"],
                    "alpha": benchmark_comp["comparison"]["alpha"],
                    "beta": benchmark_comp["comparison"]["beta"]
                }
        
        snapshot = PortfolioSnapshot(
            portfolio_id=portfolio_id,
            user_id=portfolio.user_id,
            total_value=total_value,
            cost_basis=cost_basis,
            realized_pnl=0,  # Would require trade history
            unrealized_pnl=unrealized_pnl,
            portfolio_volatility=portfolio_metrics.get("volatility"),
            portfolio_sharpe=portfolio_metrics.get("sharpe"),
            portfolio_beta=benchmark_comparison.get("beta") if benchmark_comparison else None,
            max_drawdown_pct=portfolio_metrics.get("max_drawdown"),
            sector_allocation=sector_allocation,
            asset_allocation={"stocks": 1.0, "cash": 0.0},  # Simplified
            benchmark_symbol=benchmark_symbol,
            benchmark_return=benchmark_comparison.get("outperformance_pct") if benchmark_comparison else None,
            portfolio_return=portfolio_metrics.get("return_1m"),
            alpha=benchmark_comparison.get("alpha") if benchmark_comparison else None,
            holdings_snapshot=holdings_snapshot,
            period_start=datetime.utcnow() - timedelta(days=30),
            period_end=datetime.utcnow(),
            snapshot_type=snapshot_type,
            triggered_by=triggered_by
        )
        
        self.db.add(snapshot)
        self.db.commit()
        self.db.refresh(snapshot)
        
        return snapshot
    
    def _calculate_portfolio_risk_metrics(
        self,
        portfolio_id: int,
        holdings: List[PortfolioHolding]
    ) -> Dict:
        """Calculate risk metrics for snapshot"""
        
        returns = []
        weights = []
        
        for h in holdings:
            if h.weight and h.stock:
                stock_returns = self.portfolio_service.get_historical_returns(
                    h.stock_id, days=252
                )
                if not stock_returns.empty:
                    returns.append(stock_returns.values)
                    weights.append(h.weight)
        
        if not returns or not weights:
            return {
                "volatility": None,
                "sharpe": None,
                "max_drawdown": None,
                "returns_available": False
            }
        
        # Calculate portfolio returns (weighted average)
        # Simplified - assumes independent returns
        portfolio_returns = np.average(returns, axis=0, weights=weights)
        
        volatility = np.std(portfolio_returns) * np.sqrt(252)
        annual_return = np.mean(portfolio_returns) * 252
        
        # Sharpe
        risk_free = 0.02
        sharpe = (annual_return - risk_free) / volatility if volatility > 0 else 0
        
        # Max drawdown
        cum_returns = np.cumprod(1 + portfolio_returns)
        running_max = np.maximum.accumulate(cum_returns)
        drawdown = (cum_returns - running_max) / running_max
        max_dd = np.min(drawdown)
        
        return {
            "volatility": round(volatility, 4),
            "sharpe": round(sharpe, 3),
            "max_drawdown": round(max_dd, 4),
            "return_1m": round(annual_return / 12, 4),
            "returns_available": True
        }
    
    def get_portfolio_history(
        self,
        portfolio_id: int,
        days: int = 90,
        snapshot_type: str = None
    ) -> List[Dict]:
        """Get portfolio historical snapshots"""
        
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        query = self.db.query(PortfolioSnapshot).filter(
            PortfolioSnapshot.portfolio_id == portfolio_id,
            PortfolioSnapshot.created_at >= cutoff
        )
        
        if snapshot_type:
            query = query.filter(PortfolioSnapshot.snapshot_type == snapshot_type)
        
        snapshots = query.order_by(PortfolioSnapshot.created_at.desc()).all()
        
        return [{
            "id": s.id,
            "date": s.created_at.isoformat() if s.created_at else None,
            "total_value": float(s.total_value) if s.total_value else 0,
            "unrealized_pnl": float(s.unrealized_pnl) if s.unrealized_pnl else 0,
            "volatility": s.portfolio_volatility,
            "sharpe": s.portfolio_sharpe,
            "alpha": s.alpha,
            "vs_benchmark": s.benchmark_return,
            "snapshot_type": s.snapshot_type,
            "sector_allocation": s.sector_allocation,
            "holdings_count": len(s.holdings_snapshot) if s.holdings_snapshot else 0
        } for s in snapshots]
    
    def get_performance_report(
        self,
        portfolio_id: int,
        period_days: int = 90
    ) -> Dict:
        """Generate comprehensive performance report"""
        
        # Get start and end snapshots
        history = self.get_portfolio_history(portfolio_id, period_days)
        
        if len(history) < 2:
            return {
                "error": "Insufficient history for performance report",
                "recommendation": "Wait for more data or create snapshots"
            }
        
        start_value = history[-1]["total_value"]
        end_value = history[0]["total_value"]
        
        total_return = (end_value - start_value) / start_value if start_value > 0 else 0
        
        # Calculate rolling returns
        daily_returns = []
        for i in range(len(history) - 1):
            if history[i]["total_value"] > 0 and history[i + 1]["total_value"] > 0:
                daily_return = (history[i]["total_value"] - history[i + 1]["total_value"]) / history[i + 1]["total_value"]
                daily_returns.append(daily_return)
        
        volatility = np.std(daily_returns) * np.sqrt(252) if daily_returns else 0
        
        # Best/worst periods
        values = [h["total_value"] for h in history]
        peak = max(values)
        trough = min(values)
        
        return {
            "portfolio_id": portfolio_id,
            "period_days": period_days,
            "period_return": round(total_return * 100, 2),
            "annualized_return": round(((1 + total_return) ** (365 / period_days) - 1) * 100, 2),
            "volatility": round(volatility * 100, 2),
            "start_value": round(start_value, 2),
            "end_value": round(end_value, 2),
            "peak_value": round(peak, 2),
            "trough_value": round(trough, 2),
            "max_gain_from_start": round((peak - start_value) / start_value * 100, 2),
            "max_drawdown": round((trough - peak) / peak * 100, 2),
            "vs_benchmark": history[0].get("vs_benchmark", 0),
            "snapshot_count": len(history),
            "assessment": self._generate_performance_assessment(total_return, volatility)
        }
    
    def _generate_performance_assessment(self, total_return: float, volatility: float) -> str:
        """Generate performance assessment text"""
        
        if total_return > 0.15 and volatility < 0.20:
            return "🌟 Excellent: Strong returns with manageable risk"
        elif total_return > 0.05 and volatility < 0.25:
            return "✅ Solid: Good risk-adjusted performance"
        elif total_return > 0:
            return "📊 Positive: Gaining but watch volatility"
        elif total_return > -0.10:
            return "⚠️ Caution: Slight underperformance, review strategy"
        else:
            return "🔴 Review Needed: Significant underperformance"
    
    def track_portfolio_event(
        self,
        portfolio_id: int,
        user_id: int,
        event_type: str,
        event_data: Dict,
        value_before: float = None,
        value_after: float = None
    ) -> PortfolioEvent:
        """Track a significant portfolio event"""
        
        change_pct = ((value_after - value_before) / value_before * 100) if value_before and value_before > 0 else 0
        
        event = PortfolioEvent(
            portfolio_id=portfolio_id,
            user_id=user_id,
            event_type=event_type,
            event_data=event_data,
            value_before=value_before,
            value_after=value_after,
            change_pct=change_pct
        )
        
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        
        return event
    
    def get_portfolio_events(
        self,
        portfolio_id: int,
        event_type: str = None,
        days: int = 90
    ) -> List[Dict]:
        """Get portfolio event history"""
        
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        query = self.db.query(PortfolioEvent).filter(
            PortfolioEvent.portfolio_id == portfolio_id,
            PortfolioEvent.created_at >= cutoff
        )
        
        if event_type:
            query = query.filter(PortfolioEvent.event_type == event_type)
        
        events = query.order_by(PortfolioEvent.created_at.desc()).all()
        
        return [{
            "id": e.id,
            "type": e.event_type,
            "data": e.event_data,
            "value_before": float(e.value_before) if e.value_before else None,
            "value_after": float(e.value_after) if e.value_after else None,
            "change_pct": e.change_pct,
            "timestamp": e.created_at.isoformat() if e.created_at else None
        } for e in events]
    
    def schedule_daily_snapshot(self, portfolio_id: int) -> bool:
        """Schedule a daily snapshot (called by background job)"""
        self.create_snapshot(portfolio_id, "daily", "scheduled")
        return True
    
    @cached(ttl=60, key_prefix="portfolio_history")
    def get_cached_history(self, portfolio_id: int, days: int = 90) -> List[Dict]:
        """Cached version of history retrieval"""
        return self.get_portfolio_history(portfolio_id, days)
