from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
import numpy as np
from collections import defaultdict

from app.models.snapshot import Benchmark, BenchmarkPrice
from app.models.portfolio import Portfolio, PortfolioHolding
from app.models.stock import Stock, StockPrice

class BenchmarkService:
    """Benchmark comparison engine for portfolio performance analysis"""
    
    # Predefined benchmarks
    BENCHMARK_TEMPLATES = {
        "NIFTY_50": {"symbol": "^NSEI", "name": "NIFTY 50", "type": "index"},
        "SENSEX": {"symbol": "^BSESN", "name": "BSE SENSEX", "type": "index"},
        "SP500": {"symbol": "^GSPC", "name": "S&P 500", "type": "index"},
        "NASDAQ": {"symbol": "^IXIC", "name": "NASDAQ Composite", "type": "index"},
        "DOW_JONES": {"symbol": "^DJI", "name": "Dow Jones Industrial", "type": "index"},
        "RUSSELL_2000": {"symbol": "^RUT", "name": "Russell 2000", "type": "index"},
        "GOLD": {"symbol": "GC=F", "name": "Gold Futures", "type": "commodity"},
        "US_TREASURY_10Y": {"symbol": "^TNX", "name": "10-Year Treasury Yield", "type": "bond"},
        "RISK_FREE_RATE": {"symbol": "^IRX", "name": "13-Week Treasury", "type": "risk_free"}
    }
    
    def __init__(self, db: Session):
        self.db = db
    
    def ingest_benchmark(self, symbol: str, name: str = None, benchmark_type: str = "index") -> Benchmark:
        """Ingest a benchmark index"""
        
        existing = self.db.query(Benchmark).filter(Benchmark.symbol == symbol).first()
        if existing:
            return existing
        
        try:
            # Fetch from Yahoo Finance
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            benchmark = Benchmark(
                symbol=symbol,
                name=name or info.get("shortName", info.get("longName", symbol)),
                benchmark_type=benchmark_type,
                description=info.get("description", "")
            )
            
            self.db.add(benchmark)
            self.db.commit()
            self.db.refresh(benchmark)
            
            # Fetch historical prices
            self.fetch_benchmark_prices(benchmark.id, symbol)
            
            return benchmark
            
        except Exception as e:
            print(f"Error ingesting benchmark {symbol}: {e}")
            return None
    
    def fetch_benchmark_prices(self, benchmark_id: int, symbol: str, period: str = "5y") -> bool:
        """Fetch historical prices for a benchmark"""
        
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=period)
            
            for index, row in hist.iterrows():
                # Check for existing
                existing = self.db.query(BenchmarkPrice).filter(
                    BenchmarkPrice.benchmark_id == benchmark_id,
                    BenchmarkPrice.timestamp == index.to_pydatetime()
                ).first()
                
                if not existing:
                    price = BenchmarkPrice(
                        benchmark_id=benchmark_id,
                        timestamp=index.to_pydatetime(),
                        value=row["Close"],
                        change_pct=row["Close"] / row["Open"] - 1 if row["Open"] else 0
                    )
                    self.db.add(price)
            
            self.db.commit()
            return True
            
        except Exception as e:
            print(f"Error fetching benchmark prices: {e}")
            return False
    
    def compare_portfolio_vs_benchmark(
        self,
        portfolio_id: int,
        benchmark_symbol: str,
        period_days: int = 252
    ) -> Dict:
        """Compare portfolio performance against a benchmark"""
        
        # Get portfolio
        portfolio = self.db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
        if not portfolio:
            return None
        
        # Get benchmark
        benchmark = self.db.query(Benchmark).filter(Benchmark.symbol == benchmark_symbol).first()
        if not benchmark:
            # Auto-ingest known benchmarks
            if benchmark_symbol in [b["symbol"] for b in self.BENCHMARK_TEMPLATES.values()]:
                template = next((v for v in self.BENCHMARK_TEMPLATES.values() if v["symbol"] == benchmark_symbol), None)
                if template:
                    benchmark = self.ingest_benchmark(benchmark_symbol, template["name"], template["type"])
            
            if not benchmark:
                return None
        
        # Calculate portfolio returns
        portfolio_returns = self._calculate_portfolio_returns(portfolio_id, period_days)
        
        # Get benchmark returns
        benchmark_returns = self._get_benchmark_returns(benchmark.id, period_days)
        
        if not portfolio_returns or not benchmark_returns:
            return None
        
        # Calculate comparison metrics
        comparison = self._calculate_comparison_metrics(
            portfolio_returns,
            benchmark_returns,
            benchmark_symbol
        )
        
        return {
            "portfolio_id": portfolio_id,
            "portfolio_name": portfolio.name,
            "benchmark_symbol": benchmark_symbol,
            "benchmark_name": benchmark.name,
            "period_days": period_days,
            "portfolio_metrics": {
                "total_return": round(comparison["portfolio_total_return"] * 100, 2),
                "annualized_return": round(comparison["portfolio_annual_return"] * 100, 2),
                "volatility": round(comparison["portfolio_volatility"] * 100, 2),
                "sharpe_ratio": round(comparison["portfolio_sharpe"], 3),
                "max_drawdown": round(comparison["portfolio_max_drawdown"] * 100, 2)
            },
            "benchmark_metrics": {
                "total_return": round(comparison["benchmark_total_return"] * 100, 2),
                "annualized_return": round(comparison["benchmark_annual_return"] * 100, 2),
                "volatility": round(comparison["benchmark_volatility"] * 100, 2),
                "sharpe_ratio": round(comparison["benchmark_sharpe"], 3),
                "max_drawdown": round(comparison["benchmark_max_drawdown"] * 100, 2)
            },
            "comparison": {
                "outperformance_pct": round((comparison["portfolio_total_return"] - comparison["benchmark_total_return"]) * 100, 2),
                "alpha": round(comparison["alpha"] * 100, 2),
                "beta": round(comparison["beta"], 3),
                "tracking_error": round(comparison["tracking_error"] * 100, 2),
                "information_ratio": round(comparison["information_ratio"], 3),
                "treynor_ratio": round(comparison["treynor_ratio"], 3),
                "outperformed": comparison["portfolio_total_return"] > comparison["benchmark_total_return"],
                "volatility_comparison": "higher" if comparison["portfolio_volatility"] > comparison["benchmark_volatility"] else "lower",
                "volatility_difference": round((comparison["portfolio_volatility"] - comparison["benchmark_volatility"]) * 100, 2)
            },
            "rolling_performance": comparison.get("rolling_performance", []),
            "conclusion": self._generate_comparison_summary(comparison)
        }
    
    def _calculate_portfolio_returns(self, portfolio_id: int, period_days: int) -> pd.DataFrame:
        """Calculate daily portfolio returns"""
        
        holdings = self.db.query(PortfolioHolding).filter(
            PortfolioHolding.portfolio_id == portfolio_id
        ).all()
        
        if not holdings:
            return None
        
        cutoff = datetime.utcnow() - timedelta(days=period_days)
        
        # Get prices for all holdings
        portfolio_values = defaultdict(float)
        
        for h in holdings:
            if not h.stock:
                continue
            
            prices = self.db.query(StockPrice).filter(
                StockPrice.stock_id == h.stock_id,
                StockPrice.timestamp >= cutoff
            ).order_by(StockPrice.timestamp).all()
            
            for p in prices:
                if p.timestamp and p.close_price:
                    value = float(h.quantity or 0) * float(p.close_price) * (h.weight or 1)
                    portfolio_values[p.timestamp] += value
        
        if not portfolio_values:
            return None
        
        df = pd.DataFrame([
            {"date": k, "value": v} for k, v in sorted(portfolio_values.items())
        ])
        
        if len(df) < 30:
            return None
        
        df.set_index("date", inplace=True)
        df["returns"] = df["value"].pct_change()
        return df.dropna()
    
    def _get_benchmark_returns(self, benchmark_id: int, period_days: int) -> pd.DataFrame:
        """Get benchmark returns"""
        
        cutoff = datetime.utcnow() - timedelta(days=period_days)
        
        prices = self.db.query(BenchmarkPrice).filter(
            BenchmarkPrice.benchmark_id == benchmark_id,
            BenchmarkPrice.timestamp >= cutoff
        ).order_by(BenchmarkPrice.timestamp).all()
        
        if not prices:
            # Fetch fresh data
            benchmark = self.db.query(Benchmark).filter(Benchmark.id == benchmark_id).first()
            if benchmark:
                self.fetch_benchmark_prices(benchmark_id, benchmark.symbol, "1y")
                prices = self.db.query(BenchmarkPrice).filter(
                    BenchmarkPrice.benchmark_id == benchmark_id,
                    BenchmarkPrice.timestamp >= cutoff
                ).order_by(BenchmarkPrice.timestamp).all()
        
        if not prices or len(prices) < 30:
            return None
        
        df = pd.DataFrame([
            {"date": p.timestamp, "value": float(p.value)} for p in prices
        ])
        
        df.set_index("date", inplace=True)
        df["returns"] = df["value"].pct_change()
        return df.dropna()
    
    def _calculate_comparison_metrics(
        self,
        portfolio_df: pd.DataFrame,
        benchmark_df: pd.DataFrame,
        benchmark_symbol: str
    ) -> Dict:
        """Calculate comparison metrics between portfolio and benchmark"""
        
        # Align dates
        merged = pd.merge(
            portfolio_df[["returns"]],
            benchmark_df[["returns"]],
            left_index=True,
            right_index=True,
            suffixes=("_portfolio", "_benchmark")
        )
        
        if len(merged) < 30:
            return {}
        
        # Calculate total returns
        portfolio_total_return = (portfolio_df["value"].iloc[-1] / portfolio_df["value"].iloc[0]) - 1
        benchmark_total_return = (benchmark_df["value"].iloc[-1] / benchmark_df["value"].iloc[0]) - 1
        
        # Annualized returns
        years = len(merged) / 252
        portfolio_annual = (1 + portfolio_total_return) ** (1/years) - 1 if years > 0 else 0
        benchmark_annual = (1 + benchmark_total_return) ** (1/years) - 1 if years > 0 else 0
        
        # Volatility
        portfolio_vol = merged["returns_portfolio"].std() * np.sqrt(252)
        benchmark_vol = merged["returns_benchmark"].std() * np.sqrt(252)
        
        # Sharpe ratios (assuming 2% risk-free rate)
        risk_free = 0.02
        portfolio_sharpe = (portfolio_annual - risk_free) / portfolio_vol if portfolio_vol > 0 else 0
        benchmark_sharpe = (benchmark_annual - risk_free) / benchmark_vol if benchmark_vol > 0 else 0
        
        # Max drawdown
        portfolio_cum = (1 + merged["returns_portfolio"]).cumprod()
        benchmark_cum = (1 + merged["returns_benchmark"]).cumprod()
        
        portfolio_dd = (portfolio_cum / portfolio_cum.expanding().max() - 1).min()
        benchmark_dd = (benchmark_cum / benchmark_cum.expanding().max() - 1).min()
        
        # Beta and Alpha (CAPM)
        covariance = merged["returns_portfolio"].cov(merged["returns_benchmark"])
        benchmark_var = merged["returns_benchmark"].var()
        beta = covariance / benchmark_var if benchmark_var > 0 else 1.0
        
        alpha = portfolio_annual - (risk_free + beta * (benchmark_annual - risk_free))
        
        # Tracking error
        tracking_diff = merged["returns_portfolio"] - merged["returns_benchmark"]
        tracking_error = tracking_diff.std() * np.sqrt(252)
        
        # Information ratio
        information_ratio = (portfolio_annual - benchmark_annual) / tracking_error if tracking_error > 0 else 0
        
        # Treynor ratio
        treynor = (portfolio_annual - risk_free) / beta if beta > 0 else 0
        
        # Rolling performance (quarterly)
        rolling = []
        for i in range(0, len(merged), 63):  # Approx quarterly
            if i + 63 < len(merged):
                p_ret = (1 + merged["returns_portfolio"].iloc[i:i+63]).prod() - 1
                b_ret = (1 + merged["returns_benchmark"].iloc[i:i+63]).prod() - 1
                rolling.append({
                    "period": f"Q{int(i/63)+1}",
                    "portfolio": round(p_ret * 100, 2),
                    "benchmark": round(b_ret * 100, 2),
                    "difference": round((p_ret - b_ret) * 100, 2),
                    "outperformed": p_ret > b_ret
                })
        
        return {
            "portfolio_total_return": portfolio_total_return,
            "portfolio_annual_return": portfolio_annual,
            "portfolio_volatility": portfolio_vol,
            "portfolio_sharpe": portfolio_sharpe,
            "portfolio_max_drawdown": portfolio_dd,
            "benchmark_total_return": benchmark_total_return,
            "benchmark_annual_return": benchmark_annual,
            "benchmark_volatility": benchmark_vol,
            "benchmark_sharpe": benchmark_sharpe,
            "benchmark_max_drawdown": benchmark_dd,
            "alpha": alpha,
            "beta": beta,
            "tracking_error": tracking_error,
            "information_ratio": information_ratio,
            "treynor_ratio": treynor,
            "rolling_performance": rolling
        }
    
    def _generate_comparison_summary(self, metrics: Dict) -> str:
        """Generate human-readable comparison summary"""
        
        outperf = metrics.get("portfolio_total_return", 0) - metrics.get("benchmark_total_return", 0)
        alpha = metrics.get("alpha", 0)
        
        if outperf > 0.05 and alpha > 0.02:
            return f"🏆 Portfolio significantly outperformed benchmark by {outperf*100:.1f}% with positive alpha of {alpha*100:.2f}%. Strategy is adding value."
        elif outperf > 0:
            return f"✅ Portfolio outperformed benchmark by {outperf*100:.1f}% but alpha of {alpha*100:.2f}% indicates some of this may be from market exposure."
        elif outperf > -0.05:
            return f"⚠️ Portfolio slightly underperformed by {abs(outperf)*100:.1f}%. Review strategy but no immediate action needed."
        else:
            return f"🔴 Portfolio significantly underperformed by {abs(outperf)*100:.1f}%. Strategy review recommended."
    
    def multi_benchmark_comparison(self, portfolio_id: int, period_days: int = 252) -> Dict:
        """Compare portfolio against multiple benchmarks"""
        
        results = {}
        for key, template in self.BENCHMARK_TEMPLATES.items():
            if template["type"] in ["index", "commodity"]:
                result = self.compare_portfolio_vs_benchmark(
                    portfolio_id,
                    template["symbol"],
                    period_days
                )
                if result:
                    results[key] = {
                        "name": result["benchmark_name"],
                        "outperformance": result["comparison"]["outperformance_pct"],
                        "outperformed": result["comparison"]["outperformed"]
                    }
        
        # Rank by outperformance
        ranked = sorted(results.items(), key=lambda x: x[1]["outperformance"], reverse=True)
        
        return {
            "portfolio_id": portfolio_id,
            "period_days": period_days,
            "rankings": [
                {
                    "benchmark": key,
                    "name": data["name"],
                    "outperformance_pct": data["outperformance"],
                    "result": "outperformed" if data["outperformed"] else "underperformed"
                }
                for key, data in ranked
            ],
            "best_comparison": ranked[0] if ranked else None,
            "worst_comparison": ranked[-1] if ranked else None
        }
