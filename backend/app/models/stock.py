from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Numeric, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class Stock(Base):
    __tablename__ = "stocks"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), unique=True, index=True, nullable=False)
    name = Column(String(255))
    sector = Column(String(100))
    industry = Column(String(100))
    market_cap = Column(Numeric(20, 2))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    prices = relationship("StockPrice", back_populates="stock", cascade="all, delete-orphan")

class StockPrice(Base):
    __tablename__ = "stock_prices"
    
    id = Column(Integer, primary_key=True, index=True)
    stock_id = Column(Integer, ForeignKey("stocks.id", ondelete="CASCADE"))
    timestamp = Column(DateTime(timezone=True), nullable=False)
    open_price = Column(Numeric(12, 4))
    high_price = Column(Numeric(12, 4))
    low_price = Column(Numeric(12, 4))
    close_price = Column(Numeric(12, 4))
    volume = Column(Integer)
    adj_close = Column(Numeric(12, 4))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    stock = relationship("Stock", back_populates="prices")
    
    __table_args__ = (
        Index('idx_stock_timestamp', 'stock_id', 'timestamp'),
    )
