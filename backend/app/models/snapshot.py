from sqlalchemy import Column, Integer, Float, DateTime, ForeignKey, JSON, String, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class PortfolioSnapshot(Base):
    """Store portfolio history snapshots for tracking over time"""
    __tablename__ = "portfolio_snapshots"
    
    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id", ondelete="CASCADE"))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    
    # Portfolio metrics at snapshot time
    total_value = Column(Numeric(15, 2))
    cost_basis = Column(Numeric(15, 2))
    realized_pnl = Column(Numeric(15, 2))
    unrealized_pnl = Column(Numeric(15, 2))
    
    # Risk metrics
    portfolio_volatility = Column(Float)
    portfolio_sharpe = Column(Float)
    portfolio_beta = Column(Float)
    max_drawdown_pct = Column(Float)
    
    # Allocation breakdown
    sector_allocation = Column(JSON)  # {"Technology": 0.35, ...}
    asset_allocation = Column(JSON)   # {"stocks": 0.80, "cash": 0.20}
    
    # Performance vs benchmark
    benchmark_symbol = Column(String(20))
    benchmark_return = Column(Float)  # Period return
    portfolio_return = Column(Float)  # Same period
    alpha = Column(Float)
    tracking_error = Column(Float)
    
    # Holdings snapshot
    holdings_snapshot = Column(JSON)  # [{symbol, quantity, value, weight}, ...]
    
    # Period for this snapshot
    period_start = Column(DateTime(timezone=True))
    period_end = Column(DateTime(timezone=True))
    
    # Metadata
    snapshot_type = Column(String(20), default="daily")  # daily, weekly, monthly, event
    triggered_by = Column(String(50))  # scheduled, rebalance, user_action
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    portfolio = relationship("Portfolio")
    user = relationship("User")

class PortfolioEvent(Base):
    """Track significant portfolio events"""
    __tablename__ = "portfolio_events"
    
    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id", ondelete="CASCADE"))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    
    event_type = Column(String(50))  # rebalance, alert_triggered, user_action, milestone
    event_data = Column(JSON)  # Event-specific details
    
    # Impact tracking
    value_before = Column(Numeric(15, 2))
    value_after = Column(Numeric(15, 2))
    change_pct = Column(Float)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    portfolio = relationship("Portfolio")
    user = relationship("User")

class Benchmark(Base):
    """Store benchmark data for comparison"""
    __tablename__ = "benchmarks"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), unique=True, index=True)
    name = Column(String(255))
    benchmark_type = Column(String(50))  # index, sector, custom
    
    # Price data reference
    last_updated = Column(DateTime(timezone=True))
    
    # Metadata
    description = Column(String(500))
    constituents = Column(JSON)  # For custom benchmarks
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class BenchmarkPrice(Base):
    """Historical benchmark prices"""
    __tablename__ = "benchmark_prices"
    
    id = Column(Integer, primary_key=True, index=True)
    benchmark_id = Column(Integer, ForeignKey("benchmarks.id", ondelete="CASCADE"))
    timestamp = Column(DateTime(timezone=True), nullable=False)
    value = Column(Numeric(12, 4))  # Index value
    change_pct = Column(Float)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    benchmark = relationship("Benchmark")
