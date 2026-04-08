from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class RecommendationExplanation(Base):
    """Store detailed explanations for AI recommendations"""
    __tablename__ = "recommendation_explanations"
    
    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id", ondelete="CASCADE"))
    stock_id = Column(Integer, ForeignKey("stocks.id"))
    explanation_type = Column(String(50), default="selection")  # selection, weight, risk, timing
    
    # Factor scores (0-100)
    sentiment_score = Column(Float)
    volatility_score = Column(Float)
    return_score = Column(Float)
    diversification_score = Column(Float)
    sector_score = Column(Float)
    momentum_score = Column(Float)
    
    # Explanation details
    primary_factors = Column(JSON)  # List of main factors influencing decision
    reasoning_text = Column(Text)  # Human-readable explanation
    risk_factors = Column(JSON)  # List of identified risks
    confidence_level = Column(Float)  # 0-1 confidence in this recommendation
    
    # Feature importance for explainability
    feature_importance = Column(JSON)  # {factor: importance_weight}
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    portfolio = relationship("Portfolio")
    stock = relationship("Stock")

class UserDecisionLog(Base):
    """Track user decisions for behavior learning"""
    __tablename__ = "user_decision_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    decision_type = Column(String(50))  # accepted_recommendation, rejected, modified, manual_trade
    recommendation_id = Column(Integer, ForeignKey("recommendation_explanations.id"))
    
    # Decision details
    action_taken = Column(String(50))  # accepted, rejected, modified_held, modified_weight
    actual_allocation = Column(Float)  # User's actual allocation vs recommended
    reasoning_provided = Column(Text)  # Optional user feedback
    
    # Market context at time of decision
    market_sentiment = Column(Float)
    portfolio_value = Column(Float)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User")

class DataTrustScore(Base):
    """Track trust scores for data sources"""
    __tablename__ = "data_trust_scores"
    
    id = Column(Integer, primary_key=True, index=True)
    source_name = Column(String(255), unique=True, index=True)
    source_type = Column(String(50))  # news_api, yahoo_finance, alpha_vantage, sec_filing
    
    # Credibility metrics
    overall_score = Column(Float, default=0.5)  # 0-1
    accuracy_score = Column(Float, default=0.5)  # Based on prediction accuracy
    timeliness_score = Column(Float, default=0.5)  # Data freshness
    consistency_score = Column(Float, default=0.5)  # Cross-verification with other sources
    
    # Historical tracking
    total_predictions = Column(Integer, default=0)
    correct_predictions = Column(Integer, default=0)
    last_verified_at = Column(DateTime(timezone=True))
    
    # Source metadata
    verification_history = Column(JSON, default=list)  # [{date, score, reason}]
    cross_references = Column(JSON, default=list)  # Other sources that corroborate
    
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class MarketScenario(Base):
    """Store what-if simulation scenarios"""
    __tablename__ = "market_scenarios"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    scenario_name = Column(String(255))
    scenario_type = Column(String(50))  # crash, boom, rate_change, sector_rotation, recession
    
    # Scenario parameters
    parameters = Column(JSON)  # {market_drop_pct, affected_sectors, duration_days, etc}
    
    # Portfolio impact simulation results
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"))
    simulated_value_change = Column(Float)  # Percentage change
    simulated_sharpe_change = Column(Float)
    worst_case_value = Column(Float)
    best_case_value = Column(Float)
    
    # Risk analysis
    var_95 = Column(Float)  # Value at Risk 95%
    max_drawdown_simulated = Column(Float)
    
    # Individual stock impacts
    stock_impacts = Column(JSON)  # {symbol: {price_change, reason}}
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User")
    portfolio = relationship("Portfolio")

class OpportunityAlert(Base):
    """Store detected investment opportunities"""
    __tablename__ = "opportunity_alerts"
    
    id = Column(Integer, primary_key=True, index=True)
    stock_id = Column(Integer, ForeignKey("stocks.id", ondelete="CASCADE"))
    opportunity_type = Column(String(50))  # undervalued, sentiment_shift, momentum, breakout
    
    # Detection metrics
    detection_score = Column(Float)  # Overall opportunity score 0-1
    confidence = Column(Float)  # 0-1 confidence level
    
    # Value indicators
    pe_ratio = Column(Float)
    price_to_book = Column(Float)
    price_vs_fair_value = Column(Float)  # Percentage undervalued
    
    # Sentiment indicators
    sentiment_change_24h = Column(Float)
    sentiment_change_7d = Column(Float)
    news_volume_spike = Column(Float)  # Increase in news coverage
    
    # Technical indicators
    rsi = Column(Float)
    price_vs_50d_ma = Column(Float)  # Percentage from 50-day MA
    price_vs_200d_ma = Column(Float)
    volume_spike = Column(Float)  # Unusual volume
    
    # Explanation
    detection_reasons = Column(JSON)  # List of factors that triggered detection
    supporting_data = Column(JSON)  # Additional supporting metrics
    
    # Status
    is_active = Column(Integer, default=1)
    expires_at = Column(DateTime(timezone=True))
    user_acknowledged = Column(Integer, default=0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    stock = relationship("Stock")

class UserBehaviorProfile(Base):
    """Store learned user behavior patterns"""
    __tablename__ = "user_behavior_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    
    # Learned preferences
    preferred_sectors = Column(JSON, default=list)  # ["Technology", "Healthcare"]
    avoided_sectors = Column(JSON, default=list)
    
    # Risk behavior (learned from actual actions)
    actual_risk_tolerance = Column(String(20))  # may differ from stated preference
    risk_consistency_score = Column(Float)  # How consistent is user's risk behavior
    
    # Trading patterns
    avg_holding_period_days = Column(Float)
    rebalancing_frequency = Column(String(20))  # monthly, quarterly, yearly
    likes_dividend_stocks = Column(Integer, default=0)
    prefers_growth_over_value = Column(Integer, default=0)
    
    # Decision patterns
    acceptance_rate = Column(Float)  # % of AI recommendations accepted
    modification_rate = Column(Float)  # % of recommendations modified
    manual_override_frequency = Column(Float)
    
    # Adaptation data
    last_updated = Column(DateTime(timezone=True), onupdate=func.now())
    learning_data_points = Column(Integer, default=0)
    behavior_change_detected = Column(Integer, default=0)
    
    user = relationship("User")
