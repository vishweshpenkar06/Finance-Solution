import numpy as np
import pandas as pd
from typing import List, Dict, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.stock import Stock, StockPrice
from app.models.portfolio import Portfolio, PortfolioHolding
from app.models.user import User

class PortfolioService:
    
    RISK_PROFILES = {
        "conservative": {"max_volatility": 0.15, "target_return": 0.06, "stock_allocation": 0.40},
        "moderate": {"max_volatility": 0.25, "target_return": 0.10, "stock_allocation": 0.60},
        "aggressive": {"max_volatility": 0.40, "target_return": 0.15, "stock_allocation": 0.80},
    }
    
    SECTOR_ALLOCATION = {
        "conservative": {"Technology": 0.15, "Healthcare": 0.25, "Finance": 0.25, "Consumer": 0.20, "Utilities": 0.15},
        "moderate": {"Technology": 0.25, "Healthcare": 0.20, "Finance": 0.20, "Consumer": 0.20, "Utilities": 0.15},
        "aggressive": {"Technology": 0.35, "Healthcare": 0.15, "Finance": 0.20, "Consumer": 0.20, "Utilities": 0.10},
    }
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_historical_returns(self, stock_id: int, days: int = 252) -> pd.Series:
        """Calculate daily returns for a stock"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        prices = self.db.query(StockPrice).filter(
            StockPrice.stock_id == stock_id,
            StockPrice.timestamp >= cutoff
        ).order_by(StockPrice.timestamp).all()
        
        if len(prices) < 30:
            return pd.Series()
        
        df = pd.DataFrame([{
            "timestamp": p.timestamp,
            "close": float(p.close_price)
        } for p in prices])
        
        df.set_index("timestamp", inplace=True)
        df["return"] = df["close"].pct_change()
        return df["return"].dropna()
    
    def calculate_stock_metrics(self, stock_id: int) -> Dict:
        """Calculate key metrics for a stock"""
        returns = self.get_historical_returns(stock_id)
        
        if returns.empty or len(returns) < 30:
            return None
        
        # Annualized metrics (252 trading days)
        annual_return = returns.mean() * 252
        annual_volatility = returns.std() * np.sqrt(252)
        
        # Sharpe ratio (assuming 2% risk-free rate)
        risk_free_rate = 0.02
        sharpe_ratio = (annual_return - risk_free_rate) / annual_volatility if annual_volatility > 0 else 0
        
        # Calculate max drawdown
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = drawdown.min()
        
        return {
            "annual_return": annual_return,
            "annual_volatility": annual_volatility,
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown": max_drawdown,
            "return_risk_ratio": annual_return / annual_volatility if annual_volatility > 0 else 0
        }
    
    def get_all_stock_metrics(self) -> pd.DataFrame:
        """Get metrics for all stocks with sufficient data"""
        stocks = self.db.query(Stock).all()
        
        metrics_list = []
        for stock in stocks:
            metrics = self.calculate_stock_metrics(stock.id)
            if metrics:
                metrics["stock_id"] = stock.id
                metrics["symbol"] = stock.symbol
                metrics["sector"] = stock.sector
                metrics_list.append(metrics)
        
        return pd.DataFrame(metrics_list)
    
    def calculate_correlation_matrix(self, stock_ids: List[int]) -> pd.DataFrame:
        """Calculate correlation matrix for stocks"""
        returns_dict = {}
        
        for stock_id in stock_ids:
            stock = self.db.query(Stock).filter(Stock.id == stock_id).first()
            if stock:
                returns = self.get_historical_returns(stock_id)
                if not returns.empty and len(returns) >= 60:
                    returns_dict[stock.symbol] = returns
        
        if len(returns_dict) < 2:
            return pd.DataFrame()
        
        # Align dates and calculate correlation
        returns_df = pd.DataFrame(returns_dict)
        returns_df = returns_df.dropna()
        
        return returns_df.corr()
    
    def generate_portfolio_recommendations(
        self, 
        risk_tolerance: str = "moderate",
        investment_amount: float = 10000,
        exclude_symbols: List[str] = None
    ) -> List[Dict]:
        """Generate portfolio recommendations based on risk profile"""
        
        risk_profile = self.RISK_PROFILES.get(risk_tolerance, self.RISK_PROFILES["moderate"])
        sector_allocation = self.SECTOR_ALLOCATION.get(risk_tolerance, self.SECTOR_ALLOCATION["moderate"])
        
        # Get stock metrics
        metrics_df = self.get_all_stock_metrics()
        if metrics_df.empty:
            return []
        
        # Filter by volatility constraint
        max_vol = risk_profile["max_volatility"]
        eligible = metrics_df[metrics_df["annual_volatility"] <= max_vol].copy()
        
        if exclude_symbols:
            eligible = eligible[~eligible["symbol"].isin(exclude_symbols)]
        
        if eligible.empty:
            # Relax constraint if no stocks meet criteria
            eligible = metrics_df.copy()
        
        # Score stocks based on risk-adjusted returns
        eligible["score"] = (
            eligible["sharpe_ratio"] * 0.4 +
            eligible["return_risk_ratio"] * 0.3 -
            eligible["max_drawdown"].abs() * 0.3
        )
        
        # Select top stocks by sector
        recommendations = []
        used_stocks = set()
        
        for sector, target_weight in sector_allocation.items():
            sector_stocks = eligible[eligible["sector"] == sector].sort_values("score", ascending=False)
            
            if not sector_stocks.empty:
                # Pick top 1-2 stocks per sector
                picks = sector_stocks.head(2)
                
                for _, stock in picks.iterrows():
                    if stock["symbol"] not in used_stocks:
                        weight = target_weight / len(picks)
                        amount = investment_amount * weight
                        
                        recommendations.append({
                            "stock_id": int(stock["stock_id"]),
                            "symbol": stock["symbol"],
                            "sector": stock["sector"],
                            "weight": round(weight, 3),
                            "amount": round(amount, 2),
                            "expected_return": round(stock["annual_return"], 4),
                            "volatility": round(stock["annual_volatility"], 4),
                            "sharpe_ratio": round(stock["sharpe_ratio"], 3),
                            "rationale": f"Top {sector} pick with strong risk-adjusted returns"
                        })
                        used_stocks.add(stock["symbol"])
        
        # If we don't have enough sector-specific picks, fill with best overall
        if len(recommendations) < 5:
            remaining = eligible[~eligible["symbol"].isin(used_stocks)].sort_values("score", ascending=False).head(5 - len(recommendations))
            
            for _, stock in remaining.iterrows():
                weight = (1 - sum(r["weight"] for r in recommendations)) / len(remaining)
                amount = investment_amount * weight
                
                recommendations.append({
                    "stock_id": int(stock["stock_id"]),
                    "symbol": stock["symbol"],
                    "sector": stock["sector"],
                    "weight": round(weight, 3),
                    "amount": round(amount, 2),
                    "expected_return": round(stock["annual_return"], 4),
                    "volatility": round(stock["annual_volatility"], 4),
                    "sharpe_ratio": round(stock["sharpe_ratio"], 3),
                    "rationale": "Diversification pick with strong fundamentals"
                })
        
        # Normalize weights to sum to 1
        total_weight = sum(r["weight"] for r in recommendations)
        for r in recommendations:
            r["weight"] = round(r["weight"] / total_weight, 3)
            r["amount"] = round(investment_amount * r["weight"], 2)
        
        return recommendations
    
    def calculate_portfolio_metrics(self, recommendations: List[Dict]) -> Dict:
        """Calculate expected portfolio-level metrics"""
        if not recommendations:
            return {}
        
        weights = np.array([r["weight"] for r in recommendations])
        returns = np.array([r["expected_return"] for r in recommendations])
        volatilities = np.array([r["volatility"] for r in recommendations])
        
        portfolio_return = np.sum(weights * returns)
        
        # Simplified portfolio volatility (ignoring correlations for now)
        portfolio_volatility = np.sqrt(np.sum(weights**2 * volatilities**2))
        
        # Sharpe ratio
        risk_free_rate = 0.02
        sharpe = (portfolio_return - risk_free_rate) / portfolio_volatility if portfolio_volatility > 0 else 0
        
        return {
            "expected_annual_return": round(portfolio_return * 100, 2),
            "expected_volatility": round(portfolio_volatility * 100, 2),
            "sharpe_ratio": round(sharpe, 3),
            "risk_level": "low" if portfolio_volatility < 0.15 else "medium" if portfolio_volatility < 0.25 else "high"
        }
    
    def create_portfolio(self, user_id: int, name: str, 
                        recommendations: List[Dict]) -> Portfolio:
        """Save portfolio to database"""
        
        # Calculate metrics
        metrics = self.calculate_portfolio_metrics(recommendations)
        
        portfolio = Portfolio(
            user_id=user_id,
            name=name,
            risk_score=metrics.get("expected_volatility", 0),
            strategy="balanced"
        )
        
        self.db.add(portfolio)
        self.db.commit()
        self.db.refresh(portfolio)
        
        # Add holdings
        for rec in recommendations:
            holding = PortfolioHolding(
                portfolio_id=portfolio.id,
                stock_id=rec["stock_id"],
                quantity=0,  # User needs to buy
                avg_cost=0,
                weight=rec["weight"]
            )
            self.db.add(holding)
        
        self.db.commit()
        return portfolio
    
    def rebalance_portfolio(self, portfolio_id: int) -> List[Dict]:
        """Suggest rebalancing for existing portfolio"""
        portfolio = self.db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
        if not portfolio:
            return []
        
        # Get current holdings
        holdings = self.db.query(PortfolioHolding).filter(
            PortfolioHolding.portfolio_id == portfolio_id
        ).all()
        
        # Get user risk tolerance
        user = self.db.query(User).filter(User.id == portfolio.user_id).first()
        risk_tolerance = user.risk_tolerance if user else "moderate"
        
        # Generate new recommendations
        held_symbols = [h.stock.symbol for h in holdings]
        current_value = sum(h.quantity * h.current_price for h in holdings if h.quantity > 0)
        
        new_recs = self.generate_portfolio_recommendations(
            risk_tolerance=risk_tolerance,
            investment_amount=max(current_value, 10000),
            exclude_symbols=[]
        )
        
        # Compare with current and suggest changes
        suggestions = []
        current_weights = {h.stock.symbol: h.weight for h in holdings}
        
        for rec in new_recs:
            symbol = rec["symbol"]
            current_weight = current_weights.get(symbol, 0)
            diff = rec["weight"] - current_weight
            
            action = "hold"
            if diff > 0.05:
                action = "buy"
            elif diff < -0.05:
                action = "sell"
            
            suggestions.append({
                "symbol": symbol,
                "current_weight": round(current_weight, 3),
                "target_weight": rec["weight"],
                "action": action,
                "expected_return": rec["expected_return"],
                "rationale": rec["rationale"]
            })
        
        return suggestions
