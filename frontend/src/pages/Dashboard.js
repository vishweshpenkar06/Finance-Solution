import React, { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, Minus, Activity, DollarSign, BarChart3 } from 'lucide-react';
import { getDashboardInsights, getRiskScenarios } from '../services/api';

function SentimentBadge({ sentiment }) {
  const configs = {
    positive: { icon: TrendingUp, color: 'bg-green-100 text-green-800', label: 'Bullish' },
    negative: { icon: TrendingDown, color: 'bg-red-100 text-red-800', label: 'Bearish' },
    neutral: { icon: Minus, color: 'bg-gray-100 text-gray-800', label: 'Neutral' },
  };

  const config = configs[sentiment] || configs.neutral;
  const Icon = config.icon;

  return (
    <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${config.color}`}>
      <Icon className="h-4 w-4 mr-1" />
      {config.label}
    </span>
  );
}

function StatCard({ title, value, subtitle, icon: Icon, trend }) {
  return (
    <div className="card">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-gray-600">{title}</p>
          <p className="text-2xl font-bold text-gray-900 mt-1">{value}</p>
          {subtitle && <p className="text-sm text-gray-500 mt-1">{subtitle}</p>}
        </div>
        <div className="p-3 bg-blue-50 rounded-lg">
          <Icon className="h-6 w-6 text-blue-600" />
        </div>
      </div>
      {trend && (
        <div className="mt-4 flex items-center text-sm">
          <span className={trend >= 0 ? 'text-green-600' : 'text-red-600'}>
            {trend >= 0 ? '+' : ''}{trend}%
          </span>
          <span className="text-gray-500 ml-2">vs last period</span>
        </div>
      )}
    </div>
  );
}

function Dashboard() {
  const [insights, setInsights] = useState(null);
  const [scenarios, setScenarios] = useState(null);
  const [loading, setLoading] = useState(true);
  const [investmentAmount, setInvestmentAmount] = useState(10000);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const [insightsRes, scenariosRes] = await Promise.all([
        getDashboardInsights(),
        getRiskScenarios(investmentAmount),
      ]);
      setInsights(insightsRes.data);
      setScenarios(scenariosRes.data);
    } catch (error) {
      console.error('Error fetching data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleAmountChange = (e) => {
    setInvestmentAmount(Number(e.target.value));
  };

  const refreshScenarios = () => {
    setLoading(true);
    getRiskScenarios(investmentAmount)
      .then((res) => setScenarios(res.data))
      .finally(() => setLoading(false));
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Activity className="h-8 w-8 text-blue-600 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <div className="text-sm text-gray-500">
          Last updated: {insights?.data_summary?.last_updated ? new Date(insights.data_summary.last_updated).toLocaleString() : 'N/A'}
        </div>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <StatCard
          title="Market Sentiment"
          value={<SentimentBadge sentiment={insights?.market_sentiment?.summary} />}
          subtitle={`${insights?.market_sentiment?.count || 0} articles analyzed`}
          icon={BarChart3}
        />
        <StatCard
          title="Avg Sentiment Score"
          value={insights?.market_sentiment?.average_sentiment?.toFixed(2) || '0.00'}
          subtitle="Range: -1 to +1"
          icon={Activity}
        />
        <StatCard
          title="Stocks Tracked"
          value={insights?.data_summary?.total_stocks || 0}
          subtitle="With historical data"
          icon={TrendingUp}
        />
        <StatCard
          title="News (24h)"
          value={insights?.data_summary?.news_articles_24h || 0}
          subtitle="Articles ingested"
          icon={TrendingUp}
        />
      </div>

      {/* Top Performers */}
      <div className="card">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Top Performing Stocks (by Sharpe Ratio)</h2>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead>
              <tr>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Symbol</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Sector</th>
                <th className="px-4 py-2 text-right text-xs font-medium text-gray-500 uppercase">Annual Return</th>
                <th className="px-4 py-2 text-right text-xs font-medium text-gray-500 uppercase">Volatility</th>
                <th className="px-4 py-2 text-right text-xs font-medium text-gray-500 uppercase">Sharpe Ratio</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {insights?.top_performers?.map((stock) => (
                <tr key={stock.symbol} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-900">{stock.symbol}</td>
                  <td className="px-4 py-3 text-gray-600">{stock.sector || 'N/A'}</td>
                  <td className="px-4 py-3 text-right text-green-600">{stock.annual_return}%</td>
                  <td className="px-4 py-3 text-right text-gray-600">{stock.volatility}%</td>
                  <td className="px-4 py-3 text-right font-medium text-blue-600">{stock.sharpe_ratio}</td>
                </tr>
              ))}
              {(!insights?.top_performers || insights.top_performers.length === 0) && (
                <tr>
                  <td colSpan="5" className="px-4 py-8 text-center text-gray-500">
                    No data available. Ingest some stocks first.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Portfolio Scenarios */}
      <div className="card">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold text-gray-900">Portfolio Scenarios</h2>
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2">
              <DollarSign className="h-4 w-4 text-gray-500" />
              <input
                type="number"
                value={investmentAmount}
                onChange={handleAmountChange}
                className="w-32 px-3 py-1 border rounded text-sm"
                min="1000"
                step="1000"
              />
            </div>
            <button onClick={refreshScenarios} className="btn-primary text-sm">
              Update
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {scenarios?.scenarios && Object.entries(scenarios.scenarios).map(([risk, data]) => (
            <div key={risk} className="border rounded-lg p-4">
              <h3 className="text-lg font-medium text-gray-900 capitalize mb-2">{risk}</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-600">Expected Return:</span>
                  <span className="font-medium text-green-600">{data.expected_return}%</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Volatility:</span>
                  <span className="font-medium">{data.expected_volatility}%</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Sharpe Ratio:</span>
                  <span className="font-medium text-blue-600">{data.sharpe_ratio}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Recommendations:</span>
                  <span className="font-medium">{data.recommendations_count}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Sentiment Distribution */}
      {insights?.market_sentiment?.sentiment_distribution && (
        <div className="card">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">News Sentiment Distribution (24h)</h2>
          <div className="grid grid-cols-3 gap-4">
            {Object.entries(insights.market_sentiment.sentiment_distribution).map(([label, count]) => (
              <div key={label} className="text-center p-4 bg-gray-50 rounded-lg">
                <div className="text-2xl font-bold text-gray-900">{count}</div>
                <div className="text-sm text-gray-600 capitalize">{label}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default Dashboard;
