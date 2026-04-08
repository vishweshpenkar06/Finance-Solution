from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class Portfolio(Base):
    __tablename__ = "portfolios"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    name = Column(String(255), default="My Portfolio")
    total_value = Column(Numeric(15, 2), default=0)
    risk_score = Column(Float)
    strategy = Column(String(50), default="balanced")  # conservative, balanced, growth, aggressive
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    holdings = relationship("PortfolioHolding", back_populates="portfolio", cascade="all, delete-orphan")

class PortfolioHolding(Base):
    __tablename__ = "portfolio_holdings"
    
    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id", ondelete="CASCADE"))
    stock_id = Column(Integer, ForeignKey("stocks.id"))
    quantity = Column(Numeric(15, 4))
    avg_cost = Column(Numeric(12, 4))
    current_price = Column(Numeric(12, 4))
    weight = Column(Float)  # portfolio weight percentage
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    portfolio = relationship("Portfolio", back_populates="holdings")
    stock = relationship("Stock")
