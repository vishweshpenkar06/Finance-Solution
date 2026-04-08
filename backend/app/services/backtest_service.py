from typing import Dict, List, Optional, Tuple, Callable
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict
import numpy as np
import pandas as pd

from app.models.stock import Stock, StockPrice
from app.models.portfolio import Portfolio, PortfolioHolding
from app.models.snapshot import Benchmark, BenchmarkPrice
from app.services.portfolio_service import PortfolioService
from app.services.benchmark_service import BenchmarkService
from app.services.fusion_service import DataFusionService

@dataclass
class BacktestConfig:
    """Configuration for backtesting a strategy"""
    start_date: datetime
    end_date: datetime
    initial_capital: float
    rebalance_frequency: str  # daily, weekly, monthly, quarterly
    transaction_cost_pct: float = 0.001  # 0.1%
    tax_rate: float = 0.15  # 15% for short-term
    risk_free_rate: float = 0.02  # 2% annual
    benchmark_symbol: str = "^GSPC"
    max_positions: int = 20
    position_sizing: str = "equal"  # equal, risk_parity, momentum_weighted

@dataclass
class BacktestTrade:
    """Record of a trade executed during backtest"""
    date: datetime
    symbol: str
    action: str  # BUY, SELL, REBALANCE
    quantity: float
    price: float
    value: float
    transaction_cost: float
    reason: str

@dataclass
class BacktestResult:
    """Results from a backtest run"""
    config: BacktestConfig
    
    # Portfolio evolution
    portfolio_values: List[Tuple[datetime, float]] = field(default_factory=list)
    cash_values: List[Tuple[datetime, float]] = field(default_factory=list)
    trades: List[BacktestTrade] = field(default_factory=list)
    positions_history: List[Dict] = field(default_factory=list)
    
    # Performance metrics
    total_return_pct: float = 0.0
    annualized_return_pct: float = 0.0
    volatility_pct: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    calmar_ratio: float = 0.0
    
    # Benchmark comparison
    benchmark_return_pct: float = 0.0
    alpha: float = 0.0
    beta: float = 1.0
    information_ratio: float = 0.0
    tracking_error: float = 0.0
    
    # Risk metrics
    var_95: float = 0.0
    var_99: float = 0.0
    sortino_ratio: float = 0.0
    treynor_ratio: float = 0.0
    
    # Trade statistics
    total_trades: int = 0
    profitable_trades: int = 0
    loss_trades: int = 0
    win_rate: float = 0.0
    avg_profit_pct: float = 0.0
    avg_loss_pct: float = 0.0
    profit_factor: float = 0.0
    
    # Strategy-specific insights
    strategy_signals: Dict = field(default_factory=dict)
    sector_rotation_analysis: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Convert result to dictionary for JSON serialization"""
        return {
            "config": {
                "start_date": self.config.start_date.isoformat() if self.config.start_date else None,
                "end_date": self.config.end_date.isoformat() if self.config.end_date else None,
                "initial_capital": self.config.initial_capital,
                "rebalance_frequency": self.config.rebalance_frequency,
                "transaction_cost_pct": self.config.transaction_cost_pct,
                "benchmark_symbol": self.config.benchmark_symbol
            },
            "performance": {
                "total_return_pct": round(self.total_return_pct, 2),
                "annualized_return_pct": round(self.annualized_return_pct, 2),
                "volatility_pct": round(self.volatility_pct, 2),
                "sharpe_ratio": round(self.sharpe_ratio, 3),
                "max_drawdown_pct": round(self.max_drawdown_pct, 2),
                "calmar_ratio": round(self.calmar_ratio, 3)
            },
            "benchmark_comparison": {
                "benchmark_return_pct": round(self.benchmark_return_pct, 2),
                "outperformance_pct": round(self.total_return_pct - self.benchmark_return_pct, 2),
                "alpha": round(self.alpha, 3),
                "beta": round(self.beta, 3),
                "information_ratio": round(self.information_ratio, 3),
                "tracking_error": round(self.tracking_error, 3)
            },
            "risk_metrics": {
                "var_95": round(self.var_95, 2),
                "var_99": round(self.var_99, 2),
                "sortino_ratio": round(self.sortino_ratio, 3),
                "treynor_ratio": round(self.treynor_ratio, 3)
            },
            "trades_summary": {
                "total_trades": self.total_trades,
                "profitable_trades": self.profitable_trades,
                "loss_trades": self.loss_trades,
                "win_rate": round(self.win_rate, 1),
                "avg_profit_pct": round(self.avg_profit_pct, 2),
                "avg_loss_pct": round(self.avg_loss_pct, 2),
                "profit_factor": round(self.profit_factor, 2)
            },
            "portfolio_evolution": {
                "start_value": self.portfolio_values[0][1] if self.portfolio_values else self.config.initial_capital,
                "end_value": self.portfolio_values[-1][1] if self.portfolio_values else 0,
                "value_path": [(d.isoformat() if isinstance(d, datetime) else d, round(v, 2)) 
                                for d, v in self.portfolio_values[-30:]]  # Last 30 points
            }
        }

class BacktestService:
    """Professional backtesting engine for strategy validation"""
    
    def __init__(self, db: Session):
        self.db = db
        self.portfolio_service = PortfolioService(db)
        self.benchmark_service = BenchmarkService(db)
        self.fusion_service = DataFusionService(db)
    
    def run_strategy_backtest(
        self,
        strategy_config: Dict,
        backtest_config: BacktestConfig,
        available_symbols: List[str] = None
    ) -> BacktestResult:
        """
        Run a complete strategy backtest
        
        Strategy config can include:
        - selection_criteria: momentum, value, sentiment, fusion_score
        - weighting_method: equal, risk_parity, inverse_volatility
        - filters: min_market_cap, max_volatility, sector_constraints
        """
        
        result = BacktestResult(config=backtest_config)
        
        # Get available stocks for the period
        if available_symbols:
            available_stocks = self._get_stocks_by_symbols(available_symbols, backtest_config)
        else:
            available_stocks = self._get_available_stocks_for_period(
                backtest_config.start_date,
                backtest_config.end_date
            )
        
        # Initialize portfolio
        cash = backtest_config.initial_capital
        positions: Dict[str, Dict] = {}  # symbol -> {quantity, avg_price, current_price}
        
        # Generate rebalancing dates
        rebalance_dates = self._generate_rebalance_dates(
            backtest_config.start_date,
            backtest_config.end_date,
            backtest_config.rebalance_frequency
        )
        
        # Run simulation day by day
        current_date = backtest_config.start_date
        
        while current_date <= backtest_config.end_date:
            # Update prices for all holdings
            self._update_position_prices(positions, current_date)
            
            # Calculate current portfolio value
            portfolio_value = self._calculate_portfolio_value(positions, cash)
            
            # Record daily portfolio value
            result.portfolio_values.append((current_date, portfolio_value))
            result.cash_values.append((current_date, cash))
            
            # Check for rebalance
            if current_date in rebalance_dates or self._is_last_day(current_date, backtest_config.end_date):
                # Select new portfolio based on strategy
                new_positions = self._select_positions_for_date(
                    current_date,
                    strategy_config,
                    available_stocks,
                    portfolio_value,
                    backtest_config
                )
                
                # Execute rebalancing trades
                trades = self._execute_rebalance(
                    positions,
                    new_positions,
                    current_date,
                    backtest_config
                )
                
                result.trades.extend(trades)
                
                # Update cash after rebalancing
                for trade in trades:
                    if trade.action == "SELL":
                        cash += trade.value - trade.transaction_cost
                    else:
                        cash -= trade.value - trade.transaction_cost
                
                # Record positions
                result.positions_history.append({
                    "date": current_date,
                    "positions": {k: v.copy() for k, v in positions.items()}
                })
            
            current_date += timedelta(days=1)
        
        # Calculate all metrics
        self._calculate_performance_metrics(result, backtest_config)
        self._calculate_benchmark_comparison(result, backtest_config)
        self._calculate_trade_statistics(result)
        
        return result
    
    def _get_stocks_by_symbols(self, symbols: List[str], config: BacktestConfig) -> List[Dict]:
        """Get stock data for specified symbols"""
        stocks = []
        
        for symbol in symbols:
            stock = self.db.query(Stock).filter(Stock.symbol == symbol.upper()).first()
            if stock:
                # Get price history for the period
                prices = self.db.query(StockPrice).filter(
                    StockPrice.stock_id == stock.id,
                    StockPrice.timestamp >= config.start_date,
                    StockPrice.timestamp <= config.end_date
                ).order_by(StockPrice.timestamp).all()
                
                if len(prices) > 20:  # Need sufficient data
                    stocks.append({
                        "stock": stock,
                        "prices": {p.timestamp: p for p in prices}
                    })
        
        return stocks
    
    def _get_available_stocks_for_period(self, start: datetime, end: datetime) -> List[Dict]:
        """Get all stocks with sufficient data for the period"""
        stocks = self.db.query(Stock).limit(50).all()  # Limit to avoid overload
        
        result = []
        for stock in stocks:
            # Count available price days
            count = self.db.query(StockPrice).filter(
                StockPrice.stock_id == stock.id,
                StockPrice.timestamp >= start,
                StockPrice.timestamp <= end
            ).count()
            
            if count > 50:  # Need at least 50 data points
                prices = self.db.query(StockPrice).filter(
                    StockPrice.stock_id == stock.id,
                    StockPrice.timestamp >= start,
                    StockPrice.timestamp <= end
                ).all()
                
                result.append({
                    "stock": stock,
                    "prices": {p.timestamp: p for p in prices}
                })
        
        return result
    
    def _generate_rebalance_dates(
        self,
        start: datetime,
        end: datetime,
        frequency: str
    ) -> List[datetime]:
        """Generate rebalancing schedule"""
        dates = []
        current = start
        
        # First rebalance at start
        dates.append(start)
        
        while current < end:
            if frequency == "daily":
                current += timedelta(days=1)
            elif frequency == "weekly":
                current += timedelta(weeks=1)
            elif frequency == "monthly":
                # Simple month addition
                if current.month == 12:
                    current = current.replace(year=current.year + 1, month=1)
                else:
                    current = current.replace(month=current.month + 1)
            elif frequency == "quarterly":
                month = current.month
                if month <= 3:
                    current = current.replace(month=4)
                elif month <= 6:
                    current = current.replace(month=7)
                elif month <= 9:
                    current = current.replace(month=10)
                else:
                    current = current.replace(year=current.year + 1, month=1)
            else:
                current += timedelta(weeks=2)  # Bi-weekly default
            
            dates.append(current)
        
        return dates
    
    def _update_position_prices(self, positions: Dict[str, Dict], date: datetime):
        """Update all position prices to date"""
        for symbol, pos in positions.items():
            stock = self.db.query(Stock).filter(Stock.symbol == symbol).first()
            if stock:
                price = self.db.query(StockPrice).filter(
                    StockPrice.stock_id == stock.id,
                    StockPrice.timestamp <= date
                ).order_by(StockPrice.timestamp.desc()).first()
                
                if price and price.close_price:
                    pos["current_price"] = float(price.close_price)
    
    def _calculate_portfolio_value(self, positions: Dict[str, Dict], cash: float) -> float:
        """Calculate total portfolio value"""
        total = cash
        for pos in positions.values():
            if "current_price" in pos and "quantity" in pos:
                total += pos["quantity"] * pos["current_price"]
        return total
    
    def _is_last_day(self, current: datetime, end: datetime) -> bool:
        """Check if this is the last day of backtest"""
        return (end - current).days <= 1
    
    def _select_positions_for_date(
        self,
        date: datetime,
        strategy_config: Dict,
        available_stocks: List[Dict],
        portfolio_value: float,
        config: BacktestConfig
    ) -> List[Dict]:
        """Select positions based on strategy criteria"""
        
        # Score all available stocks
        scored_stocks = []
        
        for stock_data in available_stocks:
            stock = stock_data["stock"]
            prices = stock_data["prices"]
            
            # Get price on this date
            if date in prices:
                price_data = prices[date]
                
                # Calculate score based on strategy
                score = self._calculate_strategy_score(
                    stock,
                    prices,
                    date,
                    strategy_config
                )
                
                scored_stocks.append({
                    "symbol": stock.symbol,
                    "score": score,
                    "price": float(price_data.close_price) if price_data.close_price else 0,
                    "stock_id": stock.id
                })
        
        # Sort by score
        scored_stocks.sort(key=lambda x: x["score"], reverse=True)
        
        # Select top positions
        top_n = min(config.max_positions, len(scored_stocks))
        selected = scored_stocks[:top_n]
        
        # Calculate position sizes
        position_size = portfolio_value / len(selected) if selected else 0
        
        for pos in selected:
            pos["target_value"] = position_size
            pos["target_quantity"] = position_size / pos["price"] if pos["price"] > 0 else 0
        
        return selected
    
    def _calculate_strategy_score(
        self,
        stock,
        prices: Dict,
        date: datetime,
        strategy_config: Dict
    ) -> float:
        """Calculate a score for a stock based on strategy criteria"""
        
        criteria = strategy_config.get("selection_criteria", "momentum")
        score = 0.5  # Default neutral
        
        # Get historical prices for scoring
        historical = []
        for i in range(30):
            check_date = date - timedelta(days=i)
            if check_date in prices:
                historical.append(float(prices[check_date].close_price))
        
        if len(historical) < 10:
            return 0.3  # Insufficient data
        
        if criteria == "momentum":
            # Simple momentum: recent price vs 20-day average
            current = historical[0]
            avg_20 = np.mean(historical[:20])
            if avg_20 > 0:
                momentum = (current - avg_20) / avg_20
                score = 0.5 + momentum * 5  # Scale
        
        elif criteria == "value":
            # Value: Lower price vs recent range
            recent_high = max(historical[:20])
            recent_low = min(historical[:20])
            if recent_high > recent_low:
                position = (historical[0] - recent_low) / (recent_high - recent_low)
                score = 1.0 - position  # Lower position = better value
        
        elif criteria == "fusion":
            # Use data fusion service if available
            # Simplified: combine momentum and volatility
            volatility = np.std(historical[:20]) / np.mean(historical[:20]) if np.mean(historical[:20]) > 0 else 1
            momentum = (historical[0] - historical[-1]) / historical[-1] if historical[-1] > 0 else 0
            score = 0.5 + momentum * 3 - volatility * 0.5
        
        # Apply filters
        min_score = strategy_config.get("min_score", 0.3)
        if score < min_score:
            return 0
        
        return max(0, min(1, score))
    
    def _execute_rebalance(
        self,
        current_positions: Dict[str, Dict],
        target_positions: List[Dict],
        date: datetime,
        config: BacktestConfig
    ) -> List[BacktestTrade]:
        """Execute rebalancing trades to match target positions"""
        
        trades = []
        target_symbols = {p["symbol"] for p in target_positions}
        
        # Sell positions not in target
        for symbol, pos in list(current_positions.items()):
            if symbol not in target_symbols:
                # Sell entire position
                trade = BacktestTrade(
                    date=date,
                    symbol=symbol,
                    action="SELL",
                    quantity=pos["quantity"],
                    price=pos.get("current_price", 0),
                    value=pos["quantity"] * pos.get("current_price", 0),
                    transaction_cost=pos["quantity"] * pos.get("current_price", 0) * config.transaction_cost_pct,
                    reason="No longer in target portfolio"
                )
                trades.append(trade)
                del current_positions[symbol]
        
        # Buy/adjust target positions
        for target in target_positions:
            symbol = target["symbol"]
            target_qty = target["target_quantity"]
            
            if symbol in current_positions:
                # Adjust existing position
                current = current_positions[symbol]
                diff = target_qty - current["quantity"]
                
                if abs(diff) > 0.01:  # Minimum trade size
                    action = "BUY" if diff > 0 else "SELL"
                    qty = abs(diff)
                    price = target["price"]
                    value = qty * price
                    
                    trade = BacktestTrade(
                        date=date,
                        symbol=symbol,
                        action=action,
                        quantity=qty,
                        price=price,
                        value=value,
                        transaction_cost=value * config.transaction_cost_pct,
                        reason="Rebalance to target weight"
                    )
                    trades.append(trade)
                    
                    current["quantity"] = target_qty
                    current["current_price"] = price
            else:
                # New position
                trade = BacktestTrade(
                    date=date,
                    symbol=symbol,
                    action="BUY",
                    quantity=target_qty,
                    price=target["price"],
                    value=target_qty * target["price"],
                    transaction_cost=target_qty * target["price"] * config.transaction_cost_pct,
                    reason="New target position"
                )
                trades.append(trade)
                
                current_positions[symbol] = {
                    "quantity": target_qty,
                    "avg_price": target["price"],
                    "current_price": target["price"]
                }
        
        return trades
    
    def _calculate_performance_metrics(self, result: BacktestResult, config: BacktestConfig):
        """Calculate comprehensive performance metrics"""
        
        if not result.portfolio_values:
            return
        
        # Total return
        start_value = result.portfolio_values[0][1]
        end_value = result.portfolio_values[-1][1]
        result.total_return_pct = (end_value - start_value) / start_value * 100
        
        # Annualized return
        years = (config.end_date - config.start_date).days / 365.25
        if years > 0:
            result.annualized_return_pct = ((end_value / start_value) ** (1/years) - 1) * 100
        
        # Daily returns and volatility
        values = [v for _, v in result.portfolio_values]
        if len(values) > 1:
            daily_returns = [(values[i] - values[i-1]) / values[i-1] for i in range(1, len(values))]
            
            result.volatility_pct = np.std(daily_returns) * np.sqrt(252) * 100
            
            # Sharpe ratio
            excess_return = result.annualized_return_pct / 100 - config.risk_free_rate
            if result.volatility_pct > 0:
                result.sharpe_ratio = excess_return / (result.volatility_pct / 100)
            
            # Max drawdown
            cum_returns = np.cumprod([1 + r for r in daily_returns])
            running_max = np.maximum.accumulate(cum_returns)
            drawdowns = (cum_returns - running_max) / running_max
            result.max_drawdown_pct = np.min(drawdowns) * 100
            
            # Calmar ratio
            if abs(result.max_drawdown_pct) > 0:
                result.calmar_ratio = result.annualized_return_pct / abs(result.max_drawdown_pct)
            
            # VaR
            result.var_95 = np.percentile(daily_returns, 5) * 100
            result.var_99 = np.percentile(daily_returns, 1) * 100
            
            # Sortino ratio (downside deviation)
            downside_returns = [r for r in daily_returns if r < 0]
            if downside_returns:
                downside_std = np.std(downside_returns) * np.sqrt(252)
                if downside_std > 0:
                    result.sortino_ratio = (result.annualized_return_pct / 100 - config.risk_free_rate) / downside_std
    
    def _calculate_benchmark_comparison(self, result: BacktestResult, config: BacktestConfig):
        """Calculate benchmark comparison metrics"""
        
        # Get benchmark prices for the period
        benchmark = self.db.query(Benchmark).filter(
            Benchmark.symbol == config.benchmark_symbol
        ).first()
        
        if not benchmark:
            # Ingest if needed
            benchmark = self.benchmark_service.ingest_benchmark(
                config.benchmark_symbol,
                config.benchmark_symbol,
                "index"
            )
        
        if benchmark:
            prices = self.db.query(BenchmarkPrice).filter(
                BenchmarkPrice.benchmark_id == benchmark.id,
                BenchmarkPrice.timestamp >= config.start_date,
                BenchmarkPrice.timestamp <= config.end_date
            ).order_by(BenchmarkPrice.timestamp).all()
            
            if len(prices) > 1:
                start_price = float(prices[0].value)
                end_price = float(prices[-1].value)
                result.benchmark_return_pct = (end_price - start_price) / start_price * 100
                
                # Alpha and beta (simplified)
                result.alpha = result.total_return_pct - result.benchmark_return_pct
                result.beta = 1.0  # Would need covariance calculation
                result.tracking_error = abs(result.total_return_pct - result.benchmark_return_pct)
    
    def _calculate_trade_statistics(self, result: BacktestResult):
        """Calculate trade-level statistics"""
        
        result.total_trades = len(result.trades)
        
        if result.total_trades == 0:
            return
        
        # Track P&L per trade
        trade_pnl = []
        
        for i, trade in enumerate(result.trades):
            if trade.action == "SELL":
                # Find corresponding buy
                for j in range(i-1, -1, -1):
                    if result.trades[j].symbol == trade.symbol and result.trades[j].action == "BUY":
                        buy = result.trades[j]
                        pnl_pct = (trade.price - buy.price) / buy.price * 100
                        trade_pnl.append(pnl_pct)
                        break
        
        if trade_pnl:
            result.profitable_trades = sum(1 for p in trade_pnl if p > 0)
            result.loss_trades = sum(1 for p in trade_pnl if p <= 0)
            result.win_rate = result.profitable_trades / len(trade_pnl) * 100
            
            profits = [p for p in trade_pnl if p > 0]
            losses = [p for p in trade_pnl if p <= 0]
            
            if profits:
                result.avg_profit_pct = np.mean(profits)
            if losses:
                result.avg_loss_pct = np.mean(losses)
            
            if sum(losses) != 0:
                result.profit_factor = abs(sum(profits) / sum(losses))
    
    def compare_strategies(
        self,
        strategies: List[Dict],
        config: BacktestConfig,
        available_symbols: List[str] = None
    ) -> Dict:
        """Compare multiple strategies over the same period"""
        
        results = {}
        
        for strategy in strategies:
            name = strategy.get("name", f"Strategy_{len(results)+1}")
            result = self.run_strategy_backtest(
                strategy,
                config,
                available_symbols
            )
            results[name] = result
        
        # Rank strategies
        ranking = sorted(
            results.items(),
            key=lambda x: x[1].sharpe_ratio,
            reverse=True
        )
        
        return {
            "config": config,
            "strategy_results": {k: v.to_dict() for k, v in results.items()},
            "ranking": [(name, {
                "sharpe": r.sharpe_ratio,
                "return": r.total_return_pct,
                "drawdown": r.max_drawdown_pct
            }) for name, r in ranking],
            "best_strategy": ranking[0][0] if ranking else None,
            "comparison_period_days": (config.end_date - config.start_date).days
        }
