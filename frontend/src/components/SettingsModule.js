import React, { useState } from 'react';
import './SettingsModule.css';

const CacheManagement = () => {
  const [cacheInfo, setCacheInfo] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleCheckCache = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const response = await fetch('http://localhost:5000/api/cache/info');
      const data = await response.json();
      
      if (data.success) {
        setCacheInfo(data.data);
      } else {
        setError(data.error || 'Failed to fetch cache information');
      }
    } catch (err) {
      setError('Failed to fetch cache information: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleClearCache = async () => {
    if (!window.confirm('Are you sure you want to clear the cache?')) {
      return;
    }

    setLoading(true);
    setError(null);
    
    try {
      const response = await fetch('http://localhost:5000/api/cache/clear', {
        method: 'POST',
      });
      const data = await response.json();
      
      if (data.success) {
        setCacheInfo(null);
        alert('Cache cleared successfully');
      } else {
        setError(data.error || 'Failed to clear cache');
      }
    } catch (err) {
      setError('Failed to clear cache: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const formatDateRange = (range) => {
    if (!range || !range[0] || !range[1]) return 'No data';
    return `${new Date(range[0]).toLocaleString()} to ${new Date(range[1]).toLocaleString()}`;
  };

  return (
    <div className="section">
      <h3>Cache Management</h3>
      {error && <div className="error-message">{error}</div>}
      
      <div className="button-group">
        <button 
          className="action-button" 
          onClick={handleCheckCache}
          disabled={loading}
        >
          {loading ? 'Loading...' : 'Check Cache'}
        </button>
        <button 
          className="action-button remove" 
          onClick={handleClearCache}
          disabled={loading}
        >
          {loading ? 'Clearing...' : 'Clear Cache'}
        </button>
      </div>

      {cacheInfo && (
        <div className="cache-info">
          <h4>Cache Information:</h4>
          {Object.entries(cacheInfo).length === 0 ? (
            <p>Cache is empty</p>
          ) : (
            <div className="cache-entries">
              {Object.entries(cacheInfo).map(([key, info]) => (
                <div key={key} className="cache-entry">
                  <h5>Key: {key}</h5>
                  <p>Shape: {info.shape[0]} rows × {info.shape[1]} columns</p>
                  <p>Date Range: {formatDateRange(info.date_range)}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default CacheManagement;