# Smart Finance Solutions

AI-powered financial data aggregation, sentiment analysis, and portfolio optimization platform.

## Features

- **Data Aggregation**: Ingest stock data from Yahoo Finance with historical prices
- **Sentiment Analysis**: Analyze financial news sentiment using NLP
- **Portfolio Optimization**: Risk-based portfolio recommendations using Modern Portfolio Theory
- **Dashboard**: Interactive React dashboard with charts and insights

## Tech Stack

- **Backend**: Python, FastAPI, SQLAlchemy, PostgreSQL
- **AI/ML**: Pandas, Scikit-learn, TextBlob (sentiment analysis)
- **Frontend**: React.js, Recharts, Tailwind CSS
- **Data Sources**: Yahoo Finance, News API

## Quick Start

### Prerequisites

- Docker & Docker Compose
- API Keys (optional):
  - [Alpha Vantage](https://www.alphavantage.co/support/#api-key) (for additional data)
  - [News API](https://newsapi.org/) (for sentiment analysis)

### 1. Clone and Setup

```bash
git clone <repository>
cd Finance-Solution

# Copy environment file
cp backend/.env.example backend/.env

# Add your API keys (optional but recommended)
# Edit backend/.env and add:
# ALPHA_VANTAGE_API_KEY=your_key_here
# NEWS_API_KEY=your_key_here
```

### 2. Run with Docker Compose

```bash
docker-compose up --build
```

This will start:
- PostgreSQL database on port 5432
- FastAPI backend on http://localhost:8000
- React frontend on http://localhost:3000

### 3. Access the Application

- **Dashboard**: http://localhost:3000
- **API Docs**: http://localhost:8000/docs (Swagger UI)
- **Health Check**: http://localhost:8000/health

## API Endpoints

### Stocks
- `POST /api/stocks/ingest/{symbol}` - Ingest a stock
- `POST /api/stocks/batch-ingest` - Ingest multiple stocks
- `GET /api/stocks/` - List all stocks
- `GET /api/stocks/{symbol}` - Get stock details
- `GET /api/stocks/{symbol}/prices` - Get historical prices
- `GET /api/stocks/{symbol}/metrics` - Get risk/return metrics

### News
- `POST /api/news/ingest` - Ingest news articles
- `GET /api/news/` - List news articles
- `GET /api/news/sentiment` - Get sentiment summary

### Portfolio
- `POST /api/portfolio/recommendations` - Generate AI recommendations
- `POST /api/portfolio/create` - Create a portfolio
- `GET /api/portfolio/stock-metrics` - Get all stock metrics
- `GET /api/portfolio/user/{user_id}` - Get user portfolios

### Insights
- `GET /api/insights/dashboard` - Get dashboard insights
- `GET /api/insights/market-overview` - Get market overview
- `GET /api/insights/risk-scenarios` - Compare risk profiles

## Usage Guide

### 1. Ingest Stocks

Via API or use the "Ingest Popular Stocks" button in the dashboard to load:
AAPL, MSFT, GOOGL, AMZN, TSLA, META, NVDA, JPM, JNJ, V

Or ingest a specific stock:
```bash
curl -X POST http://localhost:8000/api/stocks/ingest/TSLA
```

### 2. Ingest News

Use the News page to fetch and analyze financial news articles. Sentiment scores range from -1 (negative) to +1 (positive).

### 3. Generate Portfolio

Navigate to the Portfolio page:
1. Select your risk tolerance (Conservative, Moderate, Aggressive)
2. Set your investment amount
3. Click "Generate Recommendations"
4. View AI-suggested allocations with expected returns and Sharpe ratios

## Project Structure

```
.
├── backend/
│   ├── app/
│   │   ├── api/           # FastAPI routes
│   │   ├── core/          # Config, database
│   │   ├── models/        # SQLAlchemy models
│   │   └── services/      # Business logic
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── pages/         # Dashboard, Stocks, Portfolio, News
│   │   ├── services/      # API client
│   │   └── components/    # Reusable UI components
│   ├── Dockerfile
│   └── package.json
└── docker-compose.yml
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| DATABASE_URL | PostgreSQL connection string | Yes |
| ALPHA_VANTAGE_API_KEY | Alpha Vantage API key | No |
| NEWS_API_KEY | News API key | No |
| SECRET_KEY | JWT secret | Yes |
| DEBUG | Debug mode | Yes |

## Development

### Run Backend Only

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m nltk.downloader punkt vader_lexicon
uvicorn app.main:app --reload
```

### Run Frontend Only

```bash
cd frontend
npm install
npm start
```

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Frontend      │────▶│   FastAPI        │────▶│   PostgreSQL    │
│   (React)       │     │   (Python)       │     │   (Database)    │
│                 │◄────│                  │◄────│                 │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                │
                                ▼
                       ┌──────────────────┐
                       │   External APIs  │
                       │   - Yahoo Finance│
                       │   - News API     │
                       └──────────────────┘
```

## License

MIT
