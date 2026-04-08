from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from collections import defaultdict

from app.models.explanation import DataTrustScore
from app.models.news import NewsArticle

class TrustScoreService:
    """Data trust and credibility scoring system"""
    
    # Source credibility baselines
    SOURCE_BASELINES = {
        "Bloomberg": 0.90,
        "Reuters": 0.88,
        "Financial Times": 0.87,
        "CNBC": 0.82,
        "MarketWatch": 0.78,
        "Yahoo Finance": 0.75,
        "Seeking Alpha": 0.70,
        "Alpha Vantage": 0.82,
    }
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_or_create_trust_score(self, source_name: str) -> DataTrustScore:
        """Get existing trust score or create new one"""
        trust = self.db.query(DataTrustScore).filter(
            DataTrustScore.source_name == source_name
        ).first()
        
        if not trust:
            baseline = self.SOURCE_BASELINES.get(source_name, 0.70)
            trust = DataTrustScore(
                source_name=source_name,
                source_type="news_api" if "api" in source_name.lower() else "market_data",
                overall_score=baseline,
                accuracy_score=baseline,
                timeliness_score=0.80,
                consistency_score=0.75
            )
            self.db.add(trust)
            self.db.commit()
            self.db.refresh(trust)
        return trust
    
    def calculate_cross_verification(self, article: NewsArticle) -> float:
        """Check how many sources corroborate the same information"""
        if not article.related_symbols:
            return 0.5
        
        symbols = article.related_symbols.split(",")[:5]
        cutoff = datetime.utcnow() - timedelta(days=3)
        
        similar = self.db.query(NewsArticle).filter(
            NewsArticle.related_symbols.contains(symbols[0]),
            NewsArticle.id != article.id,
            NewsArticle.created_at >= cutoff
        ).limit(20).all()
        
        unique_sources = set(a.source for a in similar if a.source)
        return min(1.0, 0.5 + len(unique_sources) * 0.1)
    
    def check_timeliness(self, article: NewsArticle) -> float:
        """Score how timely/recent the data is"""
        if not article.published_at:
            return 0.5
        
        age_hours = (datetime.utcnow() - article.published_at.replace(tzinfo=None)).total_seconds() / 3600
        
        if age_hours < 1: return 1.0
        elif age_hours < 6: return 0.95
        elif age_hours < 24: return 0.85
        elif age_hours < 72: return 0.70
        else: return 0.40
    
    def get_article_trust_score(self, article: NewsArticle) -> Dict:
        """Get trust score for a specific article"""
        source_trust = self.get_or_create_trust_score(article.source or "Unknown")
        timeliness = self.check_timeliness(article)
        verification = self.calculate_cross_verification(article)
        
        overall = (
            source_trust.overall_score * 0.5 +
            timeliness * 0.25 +
            verification * 0.25
        )
        
        return {
            "article_id": article.id,
            "title": article.title,
            "source": article.source,
            "source_trust": round(source_trust.overall_score, 2),
            "timeliness": round(timeliness, 2),
            "cross_verified": verification > 0.7,
            "overall_score": round(overall, 3),
            "reliability": "High" if overall >= 0.80 else "Medium" if overall >= 0.60 else "Low"
        }
    
    def get_all_source_rankings(self) -> List[Dict]:
        """Get ranked list of all data sources"""
        for source in self.SOURCE_BASELINES.keys():
            self.get_or_create_trust_score(source)
        
        scores = self.db.query(DataTrustScore).order_by(
            DataTrustScore.overall_score.desc()
        ).all()
        
        return [{
            "source": s.source_name,
            "score": round(s.overall_score, 3),
            "accuracy": round(s.accuracy_score, 3),
            "tier": "Tier 1" if s.overall_score >= 0.85 else 
                    "Tier 2" if s.overall_score >= 0.70 else "Tier 3"
        } for s in scores]
    
    def get_data_quality_report(self, days: int = 7) -> Dict:
        """Generate overall data quality report"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        total = self.db.query(NewsArticle).filter(
            NewsArticle.created_at >= cutoff
        ).count()
        
        sources = self.db.query(NewsArticle.source).filter(
            NewsArticle.created_at >= cutoff
        ).distinct().count()
        
        scores = self.db.query(DataTrustScore).all()
        avg = sum(s.overall_score for s in scores) / len(scores) if scores else 0
        
        return {
            "articles_ingested": total,
            "unique_sources": sources,
            "average_trust_score": round(avg, 3),
            "quality_rating": "Excellent" if avg >= 0.80 else "Good" if avg >= 0.65 else "Fair"
        }
