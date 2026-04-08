import React, { useState, useEffect } from 'react';
import { Search, Plus, RefreshCw, Activity, TrendingUp } from 'lucide-react';
import { listStocks, ingestStock, batchIngestStocks, getAllStockMetrics } from '../services/api';

function Stocks() {
  const [stocks, setStocks] = useState([]);
  const [metrics, setMetrics] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [newSymbol, setNewSymbol] = useState('');
  const [ingesting, setIngesting] = useState(false);
  const [selectedStock, setSelectedStock] = useState(null);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const [stocksRes, metricsRes] = await Promise.all([
        listStocks({ limit: 100 }),
        getAllStockMetrics(),
      ]);
      setStocks(stocksRes.data || []);
      setMetrics(metricsRes.data?.stocks || []);
    } catch (error) {
      console.error('Error fetching stocks:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleIngest = async (e) => {
    e.preventDefault();
    if (!newSymbol.trim()) return;

    setIngesting(true);
    try {
      await ingestStock(newSymbol.trim().toUpperCase());
      setNewSymbol('');
      await fetchData();
    } catch (error) {
      alert('Failed to ingest stock. Please try again.');
    } finally {
      setIngesting(false);
    }
  };

  const handleBatchIngest = async () => {
    const defaultStocks = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'JPM', 'JNJ', 'V'];
    
    setIngesting(true);
    try {
      await batchIngestStocks(defaultStocks);
      await fetchData();
    } catch (error) {
      alert('Batch ingest failed. Please try again.');
    } finally {
      setIngesting(false);
    }
  };

  const getStockMetrics = (symbol) => {
    return metrics.find(m => m.symbol === symbol);
  };

  const filteredStocks = stocks.filter(s =>
    s.symbol.toLowerCase().includes(searchTerm.toLowerCase()) ||
    (s.name && s.name.toLowerCase().includes(searchTerm.toLowerCase()))
  );

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
        <h1 className="text-2xl font-bold text-gray-900">Stocks</h1>
        <button
          onClick={handleBatchIngest}
          disabled={ingesting}
          className="btn-secondary flex items-center"
        >
          <Plus className="h-4 w-4 mr-1" />
          Ingest Popular Stocks
        </button>
      </div>

      {/* Add Stock */}
      <div className="card">
        <form onSubmit={handleIngest} className="flex items-end space-x-4">
          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Add Stock Symbol
            </label>
            <input
              type="text"
              value={newSymbol}
              onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
              placeholder="e.g., AAPL"
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <button
            type="submit"
            disabled={ingesting}
            className="btn-primary flex items-center"
          >
            {ingesting ? (
              <RefreshCw className="h-4 w-4 mr-1 animate-spin" />
            ) : (
              <Plus className="h-4 w-4 mr-1" />
            )}
            Ingest
          </button>
        </form>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-gray-400" />
        <input
          type="text"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          placeholder="Search stocks..."
          className="w-full pl-10 pr-4 py-2 border rounded-lg"
        />
      </div>

      {/* Stock Table */}
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Symbol</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Sector</th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Annual Return</th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Volatility</th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Sharpe</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {filteredStocks.map((stock) => {
                const m = getStockMetrics(stock.symbol);
                return (
                  <tr
                    key={stock.id}
                    className="hover:bg-gray-50 cursor-pointer"
                    onClick={() => setSelectedStock(stock)}
                  >
                    <td className="px-6 py-4 font-medium text-gray-900">{stock.symbol}</td>
                    <td className="px-6 py-4 text-gray-600">{stock.name}</td>
                    <td className="px-6 py-4 text-gray-600">{stock.sector || 'N/A'}</td>
                    <td className="px-6 py-4 text-right">
                      {m ? (
                        <span className={m.annual_return >= 0 ? 'text-green-600' : 'text-red-600'}>
                          {(m.annual_return * 100).toFixed(1)}%
                        </span>
                      ) : (
                        <span className="text-gray-400">-</span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-right text-gray-600">
                      {m ? `${(m.annual_volatility * 100).toFixed(1)}%` : '-'}
                    </td>
                    <td className="px-6 py-4 text-right">
                      {m ? (
                        <span className="font-medium text-blue-600">{m.sharpe_ratio.toFixed(2)}</span>
                      ) : (
                        <span className="text-gray-400">-</span>
                      )}
                    </td>
                  </tr>
                );
              })}
              {filteredStocks.length === 0 && (
                <tr>
                  <td colSpan="6" className="px-6 py-8 text-center text-gray-500">
                    {stocks.length === 0
                      ? 'No stocks in database. Add some stocks to get started.'
                      : 'No stocks match your search.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Stock Count */}
      <div className="text-sm text-gray-500">
        Showing {filteredStocks.length} of {stocks.length} stocks
      </div>
    </div>
  );
}

export default Stocks;
