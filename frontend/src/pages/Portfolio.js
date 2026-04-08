import React, { useState } from 'react';
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { Activity, DollarSign, RefreshCw, Plus } from 'lucide-react';
import { getPortfolioRecommendations, createPortfolio } from '../services/api';

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#84cc16', '#f97316'];

const RISK_PROFILES = [
  { value: 'conservative', label: 'Conservative', description: 'Lower risk, stable returns' },
  { value: 'moderate', label: 'Moderate', description: 'Balanced risk and return' },
  { value: 'aggressive', label: 'Aggressive', description: 'Higher risk, growth focused' },
];

function Portfolio() {
  const [loading, setLoading] = useState(false);
  const [recommendations, setRecommendations] = useState(null);
  const [portfolioMetrics, setPortfolioMetrics] = useState(null);
  const [riskTolerance, setRiskTolerance] = useState('moderate');
  const [investmentAmount, setInvestmentAmount] = useState(10000);
  const [showCreate, setShowCreate] = useState(false);
  const [portfolioName, setPortfolioName] = useState('My Portfolio');
  const [userId, setUserId] = useState(1);
  const [creating, setCreating] = useState(false);

  const getRecommendations = async () => {
    setLoading(true);
    try {
      const res = await getPortfolioRecommendations({
        risk_tolerance: riskTolerance,
        investment_amount: investmentAmount,
        exclude_symbols: [],
      });
      setRecommendations(res.data.recommendations);
      setPortfolioMetrics(res.data.portfolio_metrics);
      setShowCreate(true);
    } catch (error) {
      alert('Failed to generate recommendations. Please ensure stocks are ingested first.');
    } finally {
      setLoading(false);
    }
  };

  const handleCreatePortfolio = async () => {
    setCreating(true);
    try {
      await createPortfolio({
        user_id: userId,
        name: portfolioName,
        risk_tolerance: riskTolerance,
        investment_amount: investmentAmount,
      });
      alert('Portfolio created successfully!');
      setShowCreate(false);
    } catch (error) {
      alert('Failed to create portfolio.');
    } finally {
      setCreating(false);
    }
  };

  const chartData = recommendations?.map((r) => ({
    name: r.symbol,
    value: r.weight * 100,
    amount: r.amount,
  }));

  const returnsData = recommendations?.map((r) => ({
    name: r.symbol,
    return: r.expected_return * 100,
    volatility: r.volatility * 100,
  }));

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Portfolio Generator</h1>

      {/* Configuration */}
      <div className="card">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Investment Profile</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Risk Tolerance</label>
            <div className="space-y-2">
              {RISK_PROFILES.map((profile) => (
                <label key={profile.value} className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="radio"
                    value={profile.value}
                    checked={riskTolerance === profile.value}
                    onChange={(e) => setRiskTolerance(e.target.value)}
                    className="text-blue-600"
                  />
                  <div>
                    <span className="font-medium text-gray-900">{profile.label}</span>
                    <p className="text-xs text-gray-500">{profile.description}</p>
                  </div>
                </label>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Investment Amount</label>
            <div className="relative">
              <DollarSign className="absolute left-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-gray-400" />
              <input
                type="number"
                value={investmentAmount}
                onChange={(e) => setInvestmentAmount(Number(e.target.value))}
                min="1000"
                step="1000"
                className="w-full pl-10 pr-4 py-2 border rounded-lg"
              />
            </div>
          </div>

          <div className="flex items-end">
            <button
              onClick={getRecommendations}
              disabled={loading}
              className="btn-primary w-full flex items-center justify-center"
            >
              {loading ? (
                <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Activity className="h-4 w-4 mr-2" />
              )}
              Generate Recommendations
            </button>
          </div>
        </div>
      </div>

      {/* Results */}
      {recommendations && (
        <>
          {/* Metrics */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            <div className="card">
              <p className="text-sm font-medium text-gray-600">Expected Return</p>
              <p className="text-2xl font-bold text-green-600">
                {portfolioMetrics?.expected_annual_return}%
              </p>
            </div>
            <div className="card">
              <p className="text-sm font-medium text-gray-600">Volatility</p>
              <p className="text-2xl font-bold text-blue-600">
                {portfolioMetrics?.expected_volatility}%
              </p>
            </div>
            <div className="card">
              <p className="text-sm font-medium text-gray-600">Sharpe Ratio</p>
              <p className="text-2xl font-bold text-purple-600">
                {portfolioMetrics?.sharpe_ratio}
              </p>
            </div>
            <div className="card">
              <p className="text-sm font-medium text-gray-600">Risk Level</p>
              <p className="text-2xl font-bold text-gray-900 capitalize">
                {portfolioMetrics?.risk_level}
              </p>
            </div>
          </div>

          {/* Charts */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="card">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Portfolio Allocation</h3>
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={chartData}
                    cx="50%"
                    cy="50%"
                    labelLine={false}
                    label={({ name, value }) => `${name}: ${value.toFixed(1)}%`}
                    outerRadius={100}
                    dataKey="value"
                  >
                    {chartData?.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>

            <div className="card">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Expected Return vs Volatility</h3>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={returnsData}>
                  <XAxis dataKey="name" />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="return" name="Expected Return (%)" fill="#3b82f6" />
                  <Bar dataKey="volatility" name="Volatility (%)" fill="#ef4444" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Recommendations Table */}
          <div className="card">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Recommended Holdings</h3>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Symbol</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Sector</th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Weight</th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Amount</th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Expected Return</th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Sharpe Ratio</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Rationale</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {recommendations.map((rec, index) => (
                    <tr key={index}>
                      <td className="px-6 py-4 font-medium text-gray-900">{rec.symbol}</td>
                      <td className="px-6 py-4 text-gray-600">{rec.sector || 'N/A'}</td>
                      <td className="px-6 py-4 text-right font-medium">
                        {(rec.weight * 100).toFixed(1)}%
                      </td>
                      <td className="px-6 py-4 text-right">
                        ${rec.amount.toLocaleString()}
                      </td>
                      <td className="px-6 py-4 text-right text-green-600">
                        {(rec.expected_return * 100).toFixed(2)}%
                      </td>
                      <td className="px-6 py-4 text-right text-blue-600">
                        {rec.sharpe_ratio.toFixed(2)}
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-600">{rec.rationale}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Create Portfolio */}
          {showCreate && (
            <div className="card bg-blue-50 border-2 border-blue-200">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Save Portfolio</h3>
              <div className="flex items-end space-x-4">
                <div className="flex-1">
                  <label className="block text-sm font-medium text-gray-700 mb-1">Portfolio Name</label>
                  <input
                    type="text"
                    value={portfolioName}
                    onChange={(e) => setPortfolioName(e.target.value)}
                    className="w-full px-3 py-2 border rounded-lg"
                  />
                </div>
                <div className="w-32">
                  <label className="block text-sm font-medium text-gray-700 mb-1">User ID</label>
                  <input
                    type="number"
                    value={userId}
                    onChange={(e) => setUserId(Number(e.target.value))}
                    className="w-full px-3 py-2 border rounded-lg"
                  />
                </div>
                <button
                  onClick={handleCreatePortfolio}
                  disabled={creating}
                  className="btn-primary flex items-center"
                >
                  {creating ? (
                    <RefreshCw className="h-4 w-4 mr-1 animate-spin" />
                  ) : (
                    <Plus className="h-4 w-4 mr-1" />
                  )}
                  Create Portfolio
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default Portfolio;
