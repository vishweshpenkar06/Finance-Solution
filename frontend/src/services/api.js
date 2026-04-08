import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Dashboard APIs
export const getDashboardInsights = () => api.get('/insights/dashboard');
export const getMarketOverview = () => api.get('/insights/market-overview');
export const getRiskScenarios = (amount) => api.get(`/insights/risk-scenarios?investment_amount=${amount}`);

// Stock APIs
export const listStocks = (params) => api.get('/stocks/', { params });
export const getStock = (symbol) => api.get(`/stocks/${symbol}`);
export const getStockPrices = (symbol, days = 30) => api.get(`/stocks/${symbol}/prices?days=${days}`);
export const getStockMetrics = (symbol) => api.get(`/stocks/${symbol}/metrics`);
export const ingestStock = (symbol) => api.post(`/stocks/ingest/${symbol}`);
export const batchIngestStocks = (symbols) => api.post('/stocks/batch-ingest', symbols);

// Portfolio APIs
export const getPortfolioRecommendations = (data) => api.post('/portfolio/recommendations', data);
export const createPortfolio = (data) => api.post('/portfolio/create', data);
export const getUserPortfolios = (userId) => api.get(`/portfolio/user/${userId}`);
export const getRebalanceSuggestions = (portfolioId) => api.get(`/portfolio/${portfolioId}/rebalance`);
export const getAllStockMetrics = () => api.get('/portfolio/stock-metrics');

// News APIs
export const listNews = (params) => api.get('/news/', { params });
export const getSentimentSummary = (symbol, hours = 24) => {
  const params = { hours };
  if (symbol) params.symbol = symbol;
  return api.get('/news/sentiment', { params });
};
export const ingestNews = (query) => api.post('/news/ingest', null, { params: { query } });
