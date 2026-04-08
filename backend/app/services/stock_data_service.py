import httpx
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.models.stock import Stock, StockPrice

settings = get_settings()

class StockDataService:
    
    def __init__(self, db: Session):
        self.db = db
        self.alpha_vantage_key = settings.ALPHA_VANTAGE_API_KEY
    
    async def fetch_stock_info(self, symbol: str) -> Dict:
        """Fetch basic stock info from Yahoo Finance"""
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            return {
                "symbol": symbol.upper(),
                "name": info.get("longName", info.get("shortName", symbol)),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "market_cap": info.get("marketCap"),
            }
        except Exception as e:
            print(f"Error fetching stock info for {symbol}: {e}")
            return None
    
    async def fetch_historical_prices(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        """Fetch historical prices from Yahoo Finance"""
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=period)
            hist.reset_index(inplace=True)
            hist['symbol'] = symbol.upper()
            return hist
        except Exception as e:
            print(f"Error fetching historical prices for {symbol}: {e}")
            return pd.DataFrame()
    
    async def fetch_alpha_vantage_daily(self, symbol: str) -> List[Dict]:
        """Fetch daily prices from Alpha Vantage"""
        if not self.alpha_vantage_key:
            return []
        
        url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={symbol}&apikey={self.alpha_vantage_key}"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            data = response.json()
            
            if "Time Series (Daily)" in data:
                time_series = data["Time Series (Daily)"]
                prices = []
                for date_str, values in time_series.items():
                    prices.append({
                        "timestamp": datetime.strptime(date_str, "%Y-%m-%d"),
                        "open": float(values["1. open"]),
                        "high": float(values["2. high"]),
                        "low": float(values["3. low"]),
                        "close": float(values["4. close"]),
                        "volume": int(values["5. volume"]),
                    })
                return prices
            return []
    
    def save_stock(self, symbol: str, info: Dict) -> Stock:
        """Save or update stock in database"""
        stock = self.db.query(Stock).filter(Stock.symbol == symbol.upper()).first()
        
        if not stock:
            stock = Stock(
                symbol=symbol.upper(),
                name=info.get("name"),
                sector=info.get("sector"),
                industry=info.get("industry"),
                market_cap=info.get("market_cap")
            )
            self.db.add(stock)
        else:
            stock.name = info.get("name", stock.name)
            stock.sector = info.get("sector", stock.sector)
            stock.market_cap = info.get("market_cap", stock.market_cap)
        
        self.db.commit()
        self.db.refresh(stock)
        return stock
    
    def save_prices(self, stock_id: int, prices_data: List[Dict]):
        """Save price data to database"""
        for price_data in prices_data:
            existing = self.db.query(StockPrice).filter(
                StockPrice.stock_id == stock_id,
                StockPrice.timestamp == price_data["timestamp"]
            ).first()
            
            if not existing:
                price = StockPrice(
                    stock_id=stock_id,
                    timestamp=price_data["timestamp"],
                    open_price=price_data.get("open"),
                    high_price=price_data.get("high"),
                    low_price=price_data.get("low"),
                    close_price=price_data.get("close"),
                    volume=price_data.get("volume"),
                    adj_close=price_data.get("close")
                )
                self.db.add(price)
        
        self.db.commit()
    
    async def ingest_stock(self, symbol: str) -> Optional[Stock]:
        """Complete ingestion pipeline for a stock"""
        # Fetch and save stock info
        info = await self.fetch_stock_info(symbol)
        if not info:
            return None
        
        stock = self.save_stock(symbol, info)
        
        # Fetch and save historical prices
        prices_df = await self.fetch_historical_prices(symbol)
        if not prices_df.empty:
            prices_data = []
            for _, row in prices_df.iterrows():
                prices_data.append({
                    "timestamp": row["Date"].to_pydatetime() if hasattr(row["Date"], 'to_pydatetime') else row["Date"],
                    "open": row["Open"],
                    "high": row["High"],
                    "low": row["Low"],
                    "close": row["Close"],
                    "volume": int(row["Volume"]),
                })
            self.save_prices(stock.id, prices_data)
        
        return stock
    
    async def batch_ingest(self, symbols: List[str]) -> Dict[str, any]:
        """Ingest multiple stocks"""
        results = {"success": [], "failed": []}
        
        for symbol in symbols:
            try:
                stock = await self.ingest_stock(symbol)
                if stock:
                    results["success"].append(symbol)
                else:
                    results["failed"].append(symbol)
            except Exception as e:
                print(f"Failed to ingest {symbol}: {e}")
                results["failed"].append(symbol)
        
        return results
