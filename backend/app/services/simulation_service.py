import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.stock import Stock, StockPrice
from app.models.portfolio import Portfolio, PortfolioHolding
from app.models.explanation import MarketScenario
from app.services.portfolio_service import PortfolioService

class SimulationService:
    """What-if scenario simulation engine for portfolio stress testing"""
    
    # Historical scenario templates (based on actual historical events)
    SCENARIO_TEMPLATES = {
        "market_crash": {
            "name": "Market Crash (2008-style)",
            "market_drop_pct": -0.40,
            "affected_sectors": ["Technology", "Consumer Cyclical", "Financials"],
            "defensive_sectors": ["Utilities", "Consumer Defensive", "Healthcare"],
            "duration_days": 252,
            "correlation_spike": 0.85,
            "volatility_multiplier": 2.5
        },
        "sector_boom_tech": {
            "name": "Tech Sector Boom (Dot-com 2.0)",
            "market_drop_pct": 0.20,  # Overall market up
            "boom_sectors": ["Technology", "Communication Services"],
            "boom_multiplier": 1.8,
            "lagging_sectors": ["Utilities", "Energy"],
            "lag_multiplier": 0.6,
            "duration_days": 126,
            "correlation_spike": 0.5
        },
        "interest_rate_hike": {
            "name": "Interest Rate Shock (+300bps)",
            "market_drop_pct": -0.15,
            "rate_sensitive_sectors": ["Real Estate", "Utilities", "Financials"],
            "rate_impact": -0.25,
            "benefit_sectors": ["Financials"],  # Banks benefit but REITs hurt
            "duration_days": 180,
            "correlation_spike": 0.65
        },
        "recession": {
            "name": "Economic Recession",
            "market_drop_pct": -0.25,
            "affected_sectors": ["Consumer Cyclical", "Technology", "Materials"],
            "defensive_sectors": ["Healthcare", "Utilities", "Consumer Defensive"],
            "duration_days": 365,
            "correlation_spike": 0.75,
            "volatility_multiplier": 1.8
        },
        "inflation_surge": {
            "name": "Inflation Surge (1970s-style)",
            "market_drop_pct": -0.20,
            "benefit_sectors": ["Energy", "Materials", "Real Estate"],
            "benefit_multiplier": 1.4,
            "hurt_sectors": ["Technology", "Consumer Cyclical"],
            "hurt_multiplier": 0.7,
            "duration_days": 252,
            "correlation_spike": 0.6
        }
    }
    
    def __init__(self, db: Session):
        self.db = db
        self.portfolio_service = PortfolioService(db)
    
    def run_scenario_simulation(
        self,
        portfolio_id: int,
        scenario_type: str,
        custom_parameters: Dict = None
    ) -> Dict:
        """Run a what-if scenario simulation on a portfolio"""
        
        # Get portfolio
        portfolio = self.db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
        if not portfolio:
            return None
        
        # Get current holdings
        holdings = self.db.query(PortfolioHolding).filter(
            PortfolioHolding.portfolio_id == portfolio_id
        ).all()
        
        if not holdings:
            return None
        
        # Get scenario template
        scenario = self.SCENARIO_TEMPLATES.get(scenario_type)
        if not scenario:
            return None
        
        # Override with custom parameters if provided
        if custom_parameters:
            scenario = {**scenario, **custom_parameters}
        
        # Simulate each holding
        stock_impacts = {}
        portfolio_value = portfolio.total_value or sum(
            h.quantity * h.current_price for h in holdings if h.quantity and h.current_price
        ) or 10000  # Default if no positions
        
        total_value_change = 0
        worst_stock = None
        worst_impact = 0
        best_stock = None
        best_impact = 0
        
        for holding in holdings:
            if not holding.stock:
                continue
            
            stock = holding.stock
            symbol = stock.symbol
            sector = stock.sector or "Unknown"
            weight = holding.weight or 0
            
            # Calculate impact based on sector and scenario
            impact = self._calculate_stock_impact(stock, scenario, holdings)
            stock_impacts[symbol] = impact
            
            # Weighted contribution to portfolio
            stock_contribution = weight * impact["price_change_pct"]
            total_value_change += stock_contribution
            
            if impact["price_change_pct"] < worst_impact:
                worst_impact = impact["price_change_pct"]
                worst_stock = symbol
            
            if impact["price_change_pct"] > best_impact:
                best_impact = impact["price_change_pct"]
                best_stock = symbol
        
        # Calculate portfolio-level metrics
        simulated_return = total_value_change
        simulated_value = portfolio_value * (1 + simulated_return)
        
        # Calculate VaR (Value at Risk) - simplified 95%
        impacts = [i["price_change_pct"] for i in stock_impacts.values()]
        if impacts:
            var_95 = np.percentile(impacts, 5)  # 5th percentile
        else:
            var_95 = -0.10
        
        # Max drawdown simulation
        max_drawdown_simulated = min(impacts) if impacts else -0.25
        
        # Worst/best case scenarios
        worst_case = portfolio_value * (1 + worst_impact) if worst_impact < 0 else portfolio_value
        best_case = portfolio_value * (1 + best_impact) if best_impact > 0 else portfolio_value
        
        # Sharpe ratio impact estimation
        # Higher volatility during crisis, similar returns
        current_metrics = self.portfolio_service.calculate_portfolio_metrics(
            [{"weight": h.weight, "expected_return": 0.10, "volatility": 0.20} for h in holdings if h.weight]
        )
        volatility_multiplier = scenario.get("volatility_multiplier", 1.5)
        new_volatility = current_metrics.get("expected_volatility", 15) * volatility_multiplier
        new_sharpe = (current_metrics.get("expected_annual_return", 8) + simulated_return * 100) / new_volatility if new_volatility > 0 else 0
        
        result = {
            "scenario_name": scenario["name"],
            "scenario_type": scenario_type,
            "portfolio_id": portfolio_id,
            "current_value": float(portfolio_value) if portfolio_value else 10000,
            "simulated_value_change": round(simulated_return * 100, 2),
            "simulated_value": round(simulated_value, 2),
            "simulated_sharpe": round(new_sharpe, 3),
            "var_95": round(var_95 * 100, 2),
            "max_drawdown_simulated": round(max_drawdown_simulated * 100, 2),
            "worst_case_value": round(worst_case, 2),
            "best_case_value": round(best_case, 2),
            "worst_performer": {
                "symbol": worst_stock,
                "impact": round(worst_impact * 100, 2)
            } if worst_stock else None,
            "best_performer": {
                "symbol": best_stock,
                "impact": round(best_impact * 100, 2)
            } if best_stock else None,
            "stock_impacts": stock_impacts,
            "rebalancing_suggestions": self._generate_rebalancing_suggestions(stock_impacts, scenario)
        }
        
        return result
    
    def _calculate_stock_impact(self, stock, scenario: Dict, all_holdings: List) -> Dict:
        """Calculate impact on a single stock under scenario"""
        
        sector = stock.sector or "Unknown"
        symbol = stock.symbol
        
        # Base market impact
        base_impact = scenario.get("market_drop_pct", 0)
        
        # Sector-specific adjustments
        sector_adjustment = 0
        reasons = [f"Base market impact: {base_impact*100:.1f}%"]
        
        # Check if stock in affected sectors
        affected_sectors = scenario.get("affected_sectors", [])
        defensive_sectors = scenario.get("defensive_sectors", [])
        boom_sectors = scenario.get("boom_sectors", [])
        lagging_sectors = scenario.get("lagging_sectors", [])
        
        if sector in affected_sectors:
            sector_adjustment = base_impact * 0.3  # Additional 30% impact
            reasons.append(f"{sector} sector is highly affected")
        
        if sector in defensive_sectors:
            sector_adjustment = abs(base_impact) * 0.15  # Smaller decline, or slight gain
            if base_impact < 0:
                sector_adjustment = -sector_adjustment  # Defensive sectors fall less
            reasons.append(f"{sector} is defensive, cushioning impact")
        
        if sector in boom_sectors:
            multiplier = scenario.get("boom_multiplier", 1.5)
            sector_adjustment = base_impact * multiplier
            reasons.append(f"{sector} boom: {multiplier}x sector multiplier")
        
        if sector in lagging_sectors:
            multiplier = scenario.get("lag_multiplier", 0.5)
            sector_adjustment = base_impact * multiplier
            reasons.append(f"{sector} lags in this scenario")
        
        # Rate-sensitive adjustment
        rate_sensitive = scenario.get("rate_sensitive_sectors", [])
        rate_impact = scenario.get("rate_impact", 0)
        if sector in rate_sensitive:
            sector_adjustment += rate_impact
            reasons.append(f"Rate-sensitive sector impact: {rate_impact*100:.1f}%")
        
        # Calculate final impact
        total_impact = base_impact + sector_adjustment
        
        # Add volatility noise (simulate idiosyncratic risk)
        np.random.seed(hash(symbol) % 2**32)
        noise = np.random.normal(0, 0.05)  # 5% standard deviation
        total_impact += noise
        
        return {
            "price_change_pct": round(total_impact, 4),
            "sector": sector,
            "reasons": reasons,
            "base_impact": round(base_impact * 100, 2),
            "sector_adjustment": round(sector_adjustment * 100, 2)
        }
    
    def _generate_rebalancing_suggestions(self, stock_impacts: Dict, scenario: Dict) -> List[Dict]:
        """Generate portfolio rebalancing suggestions based on scenario"""
        
        suggestions = []
        
        # Find stocks to reduce exposure
        for symbol, impact in stock_impacts.items():
            if impact["price_change_pct"] < -0.30:  # Lost 30%+
                suggestions.append({
                    "action": "reduce",
                    "symbol": symbol,
                    "reason": f"{symbol} in {impact['sector']} severely impacted ({impact['price_change_pct']*100:.1f}%). Consider reducing exposure.",
                    "priority": "high"
                })
            elif impact["price_change_pct"] > 0.20:  # Gained 20%+
                suggestions.append({
                    "action": "hold_or_take_profits",
                    "symbol": symbol,
                    "reason": f"{symbol} resilient in {scenario['name']}. Consider taking some profits or holding."
                })
        
        # Sector-level suggestions
        defensive_sectors = scenario.get("defensive_sectors", [])
        if defensive_sectors:
            suggestions.append({
                "action": "increase_sector",
                "sector": defensive_sectors[0],
                "reason": f"Consider increasing {defensive_sectors[0]} exposure as defensive positioning",
                "priority": "medium"
            })
        
        return suggestions
    
    def get_available_scenarios(self) -> List[Dict]:
        """List available scenario templates"""
        return [
            {
                "id": key,
                "name": template["name"],
                "description": self._get_scenario_description(key),
                "severity": "high" if template.get("market_drop_pct", 0) < -0.20 else "medium"
            }
            for key, template in self.SCENARIO_TEMPLATES.items()
        ]
    
    def _get_scenario_description(self, scenario_type: str) -> str:
        """Get human-readable scenario description"""
        descriptions = {
            "market_crash": "Simulates a 2008-style financial crisis with severe market decline and high correlation between assets",
            "sector_boom_tech": "Models a technology sector boom similar to late-1990s, with tech stocks outperforming significantly",
            "interest_rate_hike": "Simulates rapid interest rate increases affecting rate-sensitive sectors",
            "recession": "Models an economic recession with broad market decline and defensive sector outperformance",
            "inflation_surge": "Simulates high inflation environment with commodity and real estate sectors benefiting"
        }
        return descriptions.get(scenario_type, "Custom scenario")
    
    def run_monte_carlo_simulation(
        self,
        portfolio_id: int,
        num_simulations: int = 1000,
        time_horizon_days: int = 252
    ) -> Dict:
        """Run Monte Carlo simulation for probabilistic outcomes"""
        
        portfolio = self.db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
        if not portfolio:
            return None
        
        holdings = self.db.query(PortfolioHolding).filter(
            PortfolioHolding.portfolio_id == portfolio_id
        ).all()
        
        # Get current portfolio value
        portfolio_value = portfolio.total_value or 10000
        
        # Calculate portfolio stats
        weights = np.array([h.weight or 0 for h in holdings])
        
        # Get historical returns for each holding
        returns_data = []
        for holding in holdings:
            stock_returns = self.portfolio_service.get_historical_returns(holding.stock_id, days=252)
            if not stock_returns.empty:
                returns_data.append(stock_returns.values)
            else:
                returns_data.append(np.random.normal(0.0005, 0.02, 252))  # Default
        
        if not returns_data:
            return None
        
        # Run simulations
        simulated_end_values = []
        
        for _ in range(num_simulations):
            daily_returns = []
            for day in range(time_horizon_days):
                # Sample daily returns
                day_returns = []
                for stock_returns in returns_data:
                    if len(stock_returns) > 0:
                        ret = np.random.choice(stock_returns)
                        day_returns.append(ret)
                    else:
                        day_returns.append(np.random.normal(0.0005, 0.02))
                
                portfolio_return = np.dot(weights, day_returns) if len(weights) == len(day_returns) else 0
                daily_returns.append(portfolio_return)
            
            total_return = np.prod([1 + r for r in daily_returns]) - 1
            end_value = portfolio_value * (1 + total_return)
            simulated_end_values.append(end_value)
        
        # Calculate statistics
        simulated_end_values = np.array(simulated_end_values)
        
        return {
            "current_value": float(portfolio_value),
            "median_projected_value": round(np.median(simulated_end_values), 2),
            "mean_projected_value": round(np.mean(simulated_end_values), 2),
            "worst_case_5pct": round(np.percentile(simulated_end_values, 5), 2),
            "best_case_95pct": round(np.percentile(simulated_end_values, 95), 2),
            "probability_of_profit": round(np.mean(simulated_end_values > portfolio_value) * 100, 1),
            "probability_of_10pct_loss": round(np.mean(simulated_end_values < portfolio_value * 0.9) * 100, 1),
            "simulations_run": num_simulations,
            "time_horizon_days": time_horizon_days
        }
    
    def save_scenario(self, user_id: int, scenario_data: Dict) -> MarketScenario:
        """Save a simulation result to database"""
        
        scenario = MarketScenario(
            user_id=user_id,
            scenario_name=scenario_data.get("scenario_name"),
            scenario_type=scenario_data.get("scenario_type"),
            portfolio_id=scenario_data.get("portfolio_id"),
            parameters=scenario_data.get("parameters"),
            simulated_value_change=scenario_data.get("simulated_value_change"),
            simulated_sharpe_change=scenario_data.get("simulated_sharpe_change"),
            worst_case_value=scenario_data.get("worst_case_value"),
            best_case_value=scenario_data.get("best_case_value"),
            var_95=scenario_data.get("var_95"),
            max_drawdown_simulated=scenario_data.get("max_drawdown_simulated"),
            stock_impacts=scenario_data.get("stock_impacts")
        )
        
        self.db.add(scenario)
        self.db.commit()
        self.db.refresh(scenario)
        return scenario
