from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from collections import defaultdict
import json

from app.models.user import User
from app.models.portfolio import Portfolio, PortfolioHolding
from app.models.explanation import UserDecisionLog, UserBehaviorProfile
from app.services.portfolio_service import PortfolioService

class BehaviorLearningService:
    """Personal financial behavior learning and adaptive recommendations"""
    
    # Decision type mappings
    DECISION_TYPES = {
        "accepted_full": "Fully accepted AI recommendation",
        "accepted_modified": "Accepted with modifications",
        "rejected": "Rejected recommendation",
        "manual_override": "Manual override - chose different stock",
        "ignored": "No action taken"
    }
    
    # Risk tolerance mapping based on actual behavior
    RISK_PROFILES = {
        "conservative": ["conservative", "defensive", "stable"],
        "moderate": ["moderate", "balanced", "medium"],
        "aggressive": ["aggressive", "growth", "high_risk"]
    }
    
    def __init__(self, db: Session):
        self.db = db
        self.portfolio_service = PortfolioService(db)
    
    def get_or_create_behavior_profile(self, user_id: int) -> UserBehaviorProfile:
        """Get existing profile or create new one"""
        profile = self.db.query(UserBehaviorProfile).filter(
            UserBehaviorProfile.user_id == user_id
        ).first()
        
        if not profile:
            user = self.db.query(User).filter(User.id == user_id).first()
            stated_risk = user.risk_tolerance if user else "moderate"
            
            profile = UserBehaviorProfile(
                user_id=user_id,
                actual_risk_tolerance=stated_risk,
                risk_consistency_score=0.5,
                avg_holding_period_days=365,
                acceptance_rate=0.0,
                learning_data_points=0
            )
            self.db.add(profile)
            self.db.commit()
            self.db.refresh(profile)
        
        return profile
    
    def log_user_decision(
        self,
        user_id: int,
        decision_type: str,
        recommendation_id: Optional[int],
        action_details: Dict
    ) -> UserDecisionLog:
        """Log a user decision for learning"""
        
        # Get current market context
        market_sentiment = 0.5  # Simplified - would fetch from service
        
        # Get portfolio value
        portfolios = self.db.query(Portfolio).filter(Portfolio.user_id == user_id).all()
        total_value = sum(p.total_value for p in portfolios if p.total_value) or 10000
        
        log = UserDecisionLog(
            user_id=user_id,
            decision_type=decision_type,
            recommendation_id=recommendation_id,
            action_taken=action_details.get("action"),
            actual_allocation=action_details.get("actual_allocation"),
            reasoning_provided=action_details.get("reasoning"),
            market_sentiment=market_sentiment,
            portfolio_value=total_value
        )
        
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        
        # Update behavior profile after logging
        self._update_behavior_profile(user_id)
        
        return log
    
    def _update_behavior_profile(self, user_id: int) -> UserBehaviorProfile:
        """Update user's behavior profile based on recent decisions"""
        
        profile = self.get_or_create_behavior_profile(user_id)
        
        # Get recent decisions (last 30 days)
        cutoff = datetime.utcnow() - timedelta(days=30)
        decisions = self.db.query(UserDecisionLog).filter(
            UserDecisionLog.user_id == user_id,
            UserDecisionLog.created_at >= cutoff
        ).all()
        
        if not decisions:
            return profile
        
        # Calculate acceptance rate
        accepted = sum(1 for d in decisions if "accepted" in d.action_taken)
        modified = sum(1 for d in decisions if "modified" in d.action_taken)
        rejected = sum(1 for d in decisions if "rejected" in d.action_taken)
        
        profile.acceptance_rate = accepted / len(decisions) if decisions else 0
        profile.modification_rate = modified / len(decisions) if decisions else 0
        
        # Analyze risk behavior
        risk_score = 0
        for decision in decisions:
            if decision.portfolio_value and decision.actual_allocation:
                # High allocation to volatile assets indicates higher risk tolerance
                if decision.actual_allocation > 0.20:
                    risk_score += 1
        
        # Infer actual risk tolerance from behavior
        if risk_score / len(decisions) > 0.5:
            inferred_risk = "aggressive"
        elif risk_score / len(decisions) > 0.3:
            inferred_risk = "moderate"
        else:
            inferred_risk = "conservative"
        
        # Check consistency
        user = self.db.query(User).filter(User.id == user_id).first()
        stated_risk = user.risk_tolerance if user else "moderate"
        
        if inferred_risk == stated_risk:
            profile.risk_consistency_score = min(1.0, profile.risk_consistency_score + 0.1)
        else:
            profile.risk_consistency_score = max(0.0, profile.risk_consistency_score - 0.1)
            profile.behavior_change_detected = 1
        
        # Update actual risk tolerance if behavior consistently differs
        if profile.risk_consistency_score < 0.5 and profile.learning_data_points > 10:
            profile.actual_risk_tolerance = inferred_risk
        
        # Analyze sector preferences from portfolio
        holdings = self.db.query(PortfolioHolding).join(Portfolio).filter(
            Portfolio.user_id == user_id
        ).all()
        
        sector_weights = defaultdict(float)
        for h in holdings:
            if h.stock and h.stock.sector:
                sector_weights[h.stock.sector] += h.weight or 0
        
        # Update preferred sectors
        top_sectors = sorted(sector_weights.items(), key=lambda x: x[1], reverse=True)[:3]
        profile.preferred_sectors = [s[0] for s in top_sectors]
        
        # Infer dividend preference
        # Simplified - would check if stocks have dividend history
        profile.likes_dividend_stocks = 0  # Default
        
        # Update learning stats
        profile.learning_data_points = len(decisions)
        profile.last_updated = datetime.utcnow()
        
        self.db.commit()
        self.db.refresh(profile)
        return profile
    
    def get_behavior_summary(self, user_id: int) -> Dict:
        """Get summary of user's behavior patterns"""
        
        profile = self.get_or_create_behavior_profile(user_id)
        
        # Get decision history
        cutoff = datetime.utcnow() - timedelta(days=90)
        recent_decisions = self.db.query(UserDecisionLog).filter(
            UserDecisionLog.user_id == user_id,
            UserDecisionLog.created_at >= cutoff
        ).all()
        
        return {
            "user_id": user_id,
            "stated_risk_tolerance": self._get_user_stated_risk(user_id),
            "learned_risk_tolerance": profile.actual_risk_tolerance,
            "risk_consistency": round(profile.risk_consistency_score, 2),
            "ai_acceptance_rate": round(profile.acceptance_rate * 100, 1),
            "modification_rate": round(profile.modification_rate * 100, 1),
            "preferred_sectors": profile.preferred_sectors or [],
            "avoided_sectors": profile.avoided_sectors or [],
            "data_points": profile.learning_data_points,
            "behavior_change_detected": bool(profile.behavior_change_detected),
            "recent_decisions": len(recent_decisions),
            "recommendation_for_ai": self._generate_ai_adjustment(profile)
        }
    
    def _get_user_stated_risk(self, user_id: int) -> str:
        """Get user's stated risk tolerance"""
        user = self.db.query(User).filter(User.id == user_id).first()
        return user.risk_tolerance if user else "moderate"
    
    def _generate_ai_adjustment(self, profile: UserBehaviorProfile) -> Dict:
        """Generate AI recommendation adjustments based on behavior"""
        
        adjustments = {
            "risk_tolerance_override": None,
            "confidence_adjustment": 1.0,
            "sector_weightings": {},
            "explanation_detail_level": "standard"
        }
        
        # Risk tolerance override if inconsistent
        if profile.risk_consistency_score < 0.5 and profile.learning_data_points > 5:
            adjustments["risk_tolerance_override"] = profile.actual_risk_tolerance
            adjustments["explanation_detail_level"] = "detailed"  # More explanation when overriding
        
        # Confidence adjustment based on acceptance rate
        if profile.acceptance_rate < 0.3:
            adjustments["confidence_adjustment"] = 0.7  # Lower confidence, more conservative
            adjustments["explanation_detail_level"] = "very_detailed"
        elif profile.acceptance_rate > 0.8:
            adjustments["confidence_adjustment"] = 1.1  # Higher confidence
        
        # Sector weight adjustments
        if profile.preferred_sectors:
            for sector in profile.preferred_sectors:
                adjustments["sector_weightings"][sector] = 1.2  # 20% boost for preferred
        
        if profile.avoided_sectors:
            for sector in profile.avoided_sectors:
                adjustments["sector_weightings"][sector] = 0.5  # 50% reduction for avoided
        
        return adjustments
    
    def generate_adaptive_recommendations(
        self,
        user_id: int,
        base_recommendations: List[Dict],
        investment_amount: float
    ) -> List[Dict]:
        """Modify recommendations based on user's learned behavior"""
        
        profile = self.get_or_create_behavior_profile(user_id)
        adjustments = self._generate_ai_adjustment(profile)
        
        # Adjust recommendations
        adjusted = []
        
        for rec in base_recommendations:
            adj_rec = rec.copy()
            
            # Apply sector weightings
            sector = rec.get("sector", "Unknown")
            if sector in adjustments["sector_weightings"]:
                factor = adjustments["sector_weightings"][sector]
                adj_rec["weight"] = rec["weight"] * factor
                adj_rec["adjustment_reason"] = f"Sector preference adjusted (factor: {factor})"
            
            # Adjust confidence based on user acceptance rate
            adj_rec["confidence"] = rec.get("confidence", 0.5) * adjustments["confidence_adjustment"]
            
            # Add behavioral insights to explanation
            adj_rec["behavioral_note"] = self._generate_behavioral_note(profile, rec)
            
            adjusted.append(adj_rec)
        
        # Re-normalize weights
        total_weight = sum(r["weight"] for r in adjusted)
        for r in adjusted:
            r["weight"] = round(r["weight"] / total_weight, 3)
            r["amount"] = round(investment_amount * r["weight"], 2)
        
        return adjusted
    
    def _generate_behavioral_note(self, profile: UserBehaviorProfile, rec: Dict) -> str:
        """Generate personalized note based on behavior profile"""
        
        notes = []
        
        # Risk alignment note
        if profile.actual_risk_tolerance == "aggressive" and rec.get("volatility", 0) < 0.20:
            notes.append("You typically prefer higher volatility - this is relatively conservative for you.")
        elif profile.actual_risk_tolerance == "conservative" and rec.get("volatility", 0) > 0.25:
            notes.append("This is more volatile than your typical choices - consider if you're comfortable.")
        
        # Acceptance rate note
        if profile.acceptance_rate < 0.3:
            notes.append("Note: You often modify recommendations. Feel free to adjust this as needed.")
        
        # Sector preference
        sector = rec.get("sector")
        if sector and profile.preferred_sectors and sector in profile.preferred_sectors:
            notes.append(f"Aligned with your preference for {sector} stocks.")
        
        return " ".join(notes) if notes else ""
    
    def detect_behavior_changes(self, user_id: int) -> List[Dict]:
        """Detect significant changes in user behavior"""
        
        # Compare recent vs older behavior
        recent_cutoff = datetime.utcnow() - timedelta(days=30)
        older_cutoff = datetime.utcnow() - timedelta(days=90)
        
        recent_decisions = self.db.query(UserDecisionLog).filter(
            UserDecisionLog.user_id == user_id,
            UserDecisionLog.created_at >= recent_cutoff
        ).all()
        
        older_decisions = self.db.query(UserDecisionLog).filter(
            UserDecisionLog.user_id == user_id,
            UserDecisionLog.created_at >= older_cutoff,
            UserDecisionLog.created_at < recent_cutoff
        ).all()
        
        changes = []
        
        if not recent_decisions or not older_decisions:
            return changes
        
        # Compare acceptance rates
        recent_acceptance = sum(1 for d in recent_decisions if "accepted" in d.action_taken) / len(recent_decisions)
        older_acceptance = sum(1 for d in older_decisions if "accepted" in d.action_taken) / len(older_decisions)
        
        if abs(recent_acceptance - older_acceptance) > 0.2:
            changes.append({
                "type": "acceptance_rate_change",
                "description": f"Your AI acceptance rate changed from {older_acceptance*100:.0f}% to {recent_acceptance*100:.0f}%",
                "significance": "high" if abs(recent_acceptance - older_acceptance) > 0.4 else "medium"
            })
        
        # Compare portfolio values (risk-taking behavior)
        recent_values = [d.portfolio_value for d in recent_decisions if d.portfolio_value]
        older_values = [d.portfolio_value for d in older_decisions if d.portfolio_value]
        
        if recent_values and older_values:
            recent_avg = sum(recent_values) / len(recent_values)
            older_avg = sum(older_values) / len(older_values)
            
            if recent_avg > older_avg * 1.2:
                changes.append({
                    "type": "portfolio_growth",
                    "description": f"Your portfolio value increased {((recent_avg/older_avg)-1)*100:.0f}% recently",
                    "significance": "positive"
                })
        
        return changes
