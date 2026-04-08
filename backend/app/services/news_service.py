import httpx
import re
from datetime import datetime
from typing import List, Dict
from textblob import TextBlob
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.models.news import NewsArticle

settings = get_settings()

class NewsService:
    
    def __init__(self, db: Session):
        self.db = db
        self.news_api_key = settings.NEWS_API_KEY
    
    async def fetch_financial_news(self, query: str = "finance OR stock OR market", 
                                   page_size: int = 50) -> List[Dict]:
        """Fetch news from News API"""
        if not self.news_api_key:
            return []
        
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": query,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": page_size,
            "apiKey": self.news_api_key
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            data = response.json()
            
            if data.get("status") == "ok":
                return data.get("articles", [])
            return []
    
    async def fetch_stock_specific_news(self, symbol: str, page_size: int = 20) -> List[Dict]:
        """Fetch news for specific stock symbol"""
        query = f"{symbol} stock OR {symbol} shares OR {symbol} earnings"
        return await self.fetch_financial_news(query, page_size)
    
    def analyze_sentiment(self, text: str) -> Dict:
        """Analyze sentiment using TextBlob"""
        if not text:
            return {"score": 0, "label": "neutral"}
        
        blob = TextBlob(text)
        polarity = blob.sentiment.polarity  # -1 to 1
        
        if polarity > 0.1:
            label = "positive"
        elif polarity < -0.1:
            label = "negative"
        else:
            label = "neutral"
        
        return {
            "score": polarity,
            "label": label
        }
    
    def extract_stock_symbols(self, text: str) -> List[str]:
        """Extract potential stock symbols from text (uppercase 1-5 letter words)"""
        if not text:
            return []
        
        # Pattern: 1-5 uppercase letters (common stock symbol format)
        pattern = r'\b[A-Z]{1,5}\b'
        matches = re.findall(pattern, text or "")
        
        # Filter out common words
        common_words = {'A', 'I', 'CEO', 'CFO', 'IPO', 'GDP', 'USA', 'ETF', 'NYSE', 'NASDAQ'}
        return list(set([m for m in matches if m not in common_words]))
    
    def save_article(self, article_data: Dict, symbols: List[str] = None) -> NewsArticle:
        """Save news article to database"""
        title = article_data.get("title", "")
        content = article_data.get("content") or article_data.get("description", "")
        
        # Check for duplicate
        existing = self.db.query(NewsArticle).filter(
            NewsArticle.url == article_data.get("url")
        ).first()
        
        if existing:
            return existing
        
        # Analyze sentiment
        sentiment = self.analyze_sentiment(title + " " + (content or ""))
        
        # Extract symbols if not provided
        if symbols is None:
            symbols = self.extract_stock_symbols(title + " " + (content or ""))
        
        published_at = None
        if article_data.get("publishedAt"):
            try:
                published_at = datetime.fromisoformat(
                    article_data["publishedAt"].replace("Z", "+00:00")
                )
            except:
                pass
        
        article = NewsArticle(
            title=title,
            content=content,
            source=article_data.get("source", {}).get("name"),
            url=article_data.get("url"),
            published_at=published_at,
            sentiment_score=sentiment["score"],
            sentiment_label=sentiment["label"],
            related_symbols=",".join(symbols) if symbols else None
        )
        
        self.db.add(article)
        self.db.commit()
        self.db.refresh(article)
        return article
    
    async def ingest_news(self, query: str = None, page_size: int = 50) -> Dict:
        """Complete news ingestion pipeline"""
        if query:
            articles = await self.fetch_financial_news(query, page_size)
        else:
            articles = await self.fetch_financial_news(page_size=page_size)
        
        saved_count = 0
        for article_data in articles:
            try:
                self.save_article(article_data)
                saved_count += 1
            except Exception as e:
                print(f"Error saving article: {e}")
        
        return {
            "fetched": len(articles),
            "saved": saved_count
        }
    
    def get_sentiment_summary(self, symbol: str = None, 
                             hours: int = 24) -> Dict:
        """Get sentiment summary for recent news"""
        from datetime import timedelta
        
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        query = self.db.query(NewsArticle).filter(NewsArticle.created_at >= cutoff)
        
        if symbol:
            query = query.filter(NewsArticle.related_symbols.contains(symbol))
        
        articles = query.all()
        
        if not articles:
            return {"count": 0, "average_sentiment": 0, "summary": "no_data"}
        
        scores = [a.sentiment_score for a in articles if a.sentiment_score is not None]
        avg_score = sum(scores) / len(scores) if scores else 0
        
        sentiment_counts = {"positive": 0, "negative": 0, "neutral": 0}
        for a in articles:
            if a.sentiment_label:
                sentiment_counts[a.sentiment_label] = sentiment_counts.get(a.sentiment_label, 0) + 1
        
        return {
            "count": len(articles),
            "average_sentiment": round(avg_score, 3),
            "sentiment_distribution": sentiment_counts,
            "summary": "positive" if avg_score > 0.1 else "negative" if avg_score < -0.1 else "neutral"
        }
