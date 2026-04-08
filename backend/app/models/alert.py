from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON, Boolean, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class Alert(Base):
    """Smart alerts for portfolio monitoring"""
    __tablename__ = "alerts"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    portfolio_id = Column(Integer, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=True)
    
    # Alert configuration
    alert_type = Column(String(50))  # risk_spike, sentiment_drop, opportunity, rebalance_needed, price_target
    alert_name = Column(String(255))
    
    # Trigger conditions
    trigger_conditions = Column(JSON)  # {"metric": "portfolio_risk", "operator": ">", "threshold": 0.25}
    
    # Alert status
    is_active = Column(Boolean, default=True)
    is_triggered = Column(Boolean, default=False)
    triggered_at = Column(DateTime(timezone=True))
    
    # Trigger context (data at time of trigger)
    trigger_context = Column(JSON)  # Portfolio/sentiment state when triggered
    
    # Alert delivery
    notification_channels = Column(JSON, default=list)  # ["websocket", "email", "push"]
    delivery_status = Column(JSON, default=dict)  # {"websocket": "delivered", ...}
    
    # User interaction
    is_acknowledged = Column(Boolean, default=False)
    acknowledged_at = Column(DateTime(timezone=True))
    user_action = Column(String(50))  # ignored, acted, dismissed
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    user = relationship("User")
    portfolio = relationship("Portfolio")

class AlertHistory(Base):
    """History of triggered alerts"""
    __tablename__ = "alert_history"
    
    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id", ondelete="CASCADE"))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    
    # Trigger details
    triggered_value = Column(Float)  # The value that triggered it
    threshold_value = Column(Float)   # The threshold it crossed
    
    # Context snapshot
    context_data = Column(JSON)
    
    # Delivery tracking
    channels_delivered = Column(JSON)
    read_at = Column(DateTime(timezone=True))
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    alert = relationship("Alert")

class StreamingPrice(Base):
    """Cache for real-time streaming prices"""
    __tablename__ = "streaming_prices"
    
    id = Column(Integer, primary_key=True, index=True)
    stock_id = Column(Integer, ForeignKey("stocks.id", ondelete="CASCADE"))
    symbol = Column(String(20), index=True)
    
    # Latest data
    last_price = Column(Numeric(12, 4))
    change = Column(Numeric(12, 4))
    change_percent = Column(Float)
    volume = Column(Integer)
    
    # Streaming metadata
    last_updated = Column(DateTime(timezone=True))
    data_source = Column(String(50))
    
    # Cache control
    ttl_seconds = Column(Integer, default=60)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    stock = relationship("Stock")
