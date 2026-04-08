import React, { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, Minus, RefreshCw, Newspaper, Search } from 'lucide-react';
import { listNews, getSentimentSummary, ingestNews } from '../services/api';

function SentimentBadge({ label, score }) {
  const configs = {
    positive: { color: 'bg-green-100 text-green-800 border-green-200', icon: TrendingUp },
    negative: { color: 'bg-red-100 text-red-800 border-red-200', icon: TrendingDown },
    neutral: { color: 'bg-gray-100 text-gray-800 border-gray-200', icon: Minus },
  };

  const config = configs[label] || configs.neutral;
  const Icon = config.icon;

  return (
    <span className={`inline-flex items-center px-2 py-1 rounded border text-xs font-medium ${config.color}`}>
      <Icon className="h-3 w-3 mr-1" />
      {label} ({score?.toFixed(2)})
    </span>
  );
}

function News() {
  const [articles, setArticles] = useState([]);
  const [sentiment, setSentiment] = useState(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedSymbol, setSelectedSymbol] = useState('');
  const [ingesting, setIngesting] = useState(false);

  useEffect(() => {
    fetchData();
  }, [selectedSymbol]);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [newsRes, sentimentRes] = await Promise.all([
        listNews({ symbol: selectedSymbol || undefined, hours: 48, limit: 50 }),
        getSentimentSummary(selectedSymbol || undefined, 24),
      ]);
      setArticles(newsRes.data || []);
      setSentiment(sentimentRes.data);
    } catch (error) {
      console.error('Error fetching news:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleIngest = async () => {
    setIngesting(true);
    try {
      await ingestNews(searchQuery || undefined);
      await fetchData();
      setSearchQuery('');
    } catch (error) {
      alert('Failed to ingest news.');
    } finally {
      setIngesting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-8 w-8 text-blue-600 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-gray-900">Financial News & Sentiment</h1>
      </div>

      {/* Sentiment Summary */}
      {sentiment && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <div className="card">
            <p className="text-sm font-medium text-gray-600">Articles (24h)</p>
            <p className="text-2xl font-bold text-gray-900">{sentiment.count}</p>
          </div>
          <div className="card">
            <p className="text-sm font-medium text-gray-600">Avg Sentiment</p>
            <p className={`text-2xl font-bold ${
              sentiment.average_sentiment > 0.1 ? 'text-green-600' : 
              sentiment.average_sentiment < -0.1 ? 'text-red-600' : 'text-gray-600'
            }`}>
              {sentiment.average_sentiment.toFixed(2)}
            </p>
          </div>
          <div className="card">
            <p className="text-sm font-medium text-gray-600">Overall Mood</p>
            <p className="text-lg font-bold text-gray-900 capitalize">{sentiment.summary}</p>
          </div>
          <div className="card">
            <p className="text-sm font-medium text-gray-600">Distribution</p>
            <div className="flex items-center space-x-2 mt-2">
              {sentiment.sentiment_distribution && Object.entries(sentiment.sentiment_distribution).map(([label, count]) => (
                <span key={label} className={`text-xs px-2 py-1 rounded ${
                  label === 'positive' ? 'bg-green-100 text-green-800' :
                  label === 'negative' ? 'bg-red-100 text-red-800' :
                  'bg-gray-100 text-gray-800'
                }`}>
                  {label}: {count}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Filters and Ingest */}
      <div className="card">
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex-1 min-w-[200px]">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Filter by Symbol (optional)
            </label>
            <input
              type="text"
              value={selectedSymbol}
              onChange={(e) => setSelectedSymbol(e.target.value.toUpperCase())}
              placeholder="e.g., AAPL"
              className="w-full px-3 py-2 border rounded-lg"
            />
          </div>
          <div className="flex-1 min-w-[200px]">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Ingest New Articles (search query)
            </label>
            <div className="flex space-x-2">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="e.g., finance stock market"
                className="flex-1 px-3 py-2 border rounded-lg"
              />
              <button
                onClick={handleIngest}
                disabled={ingesting}
                className="btn-secondary flex items-center whitespace-nowrap"
              >
                {ingesting ? (
                  <RefreshCw className="h-4 w-4 mr-1 animate-spin" />
                ) : (
                  <Newspaper className="h-4 w-4 mr-1" />
                )}
                Ingest
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Articles List */}
      <div className="space-y-4">
        {articles.length === 0 ? (
          <div className="card text-center py-12">
            <Newspaper className="h-12 w-12 text-gray-400 mx-auto mb-4" />
            <p className="text-gray-500">No news articles found. Try ingesting some news.</p>
          </div>
        ) : (
          articles.map((article) => (
            <div key={article.id} className="card hover:shadow-lg transition-shadow">
              <div className="flex justify-between items-start">
                <div className="flex-1">
                  <h3 className="text-lg font-medium text-gray-900 mb-2">
                    <a
                      href={article.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="hover:text-blue-600 transition"
                    >
                      {article.title}
                    </a>
                  </h3>
                  <p className="text-sm text-gray-600 mb-2 line-clamp-2">
                    {article.content}
                  </p>
                  <div className="flex items-center space-x-4 text-sm text-gray-500">
                    <span>{article.source || 'Unknown'}</span>
                    <span>•</span>
                    <span>
                      {article.published_at
                        ? new Date(article.published_at).toLocaleString()
                        : 'Unknown date'}
                    </span>
                    {article.related_symbols && (
                      <>
                        <span>•</span>
                        <span className="text-blue-600">
                          {article.related_symbols.split(',').join(', ')}
                        </span>
                      </>
                    )}
                  </div>
                </div>
                <div className="ml-4">
                  <SentimentBadge
                    label={article.sentiment_label}
                    score={article.sentiment_score}
                  />
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Load More */}
      {articles.length > 0 && (
        <div className="text-center">
          <p className="text-sm text-gray-500">
            Showing {articles.length} articles
          </p>
        </div>
      )}
    </div>
  );
}

export default News;
