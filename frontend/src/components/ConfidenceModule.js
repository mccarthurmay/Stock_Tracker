import './ConfidenceModule.css';
import React, { useState, useEffect } from 'react';
import { DatabaseSelect } from './DatabaseModule';

// 95% Module Components

const UpdateDatabase = () => {
  const [selectedDb, setSelectedDb] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [updateStatus, setUpdateStatus] = useState(null);

  const handleUpdate = async () => {
    if (!selectedDb) {
      setError('Please select a database');
      return;
    }

    setLoading(true);
    setError(null);
    setUpdateStatus('Updating database...');

    try {
      const response = await fetch(`http://localhost:5000/api/database/${selectedDb}/update`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      });

      const data = await response.json();
      
      if (data.success) {
        setUpdateStatus('Database updated successfully');
      } else {
        setError(data.error || 'Failed to update database');
      }
    } catch (err) {
      setError('Failed to connect to server');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="section">
      <h3 className="text-xl font-bold mb-4">Update Database</h3>
      <h5>Alpaca API Call Limit: 200/min</h5>
      <h5>SMP500 would take 3+ minutes to scan through</h5>
      <DatabaseSelect 
        className="select-input w-full p-2 mb-4 border rounded"
        value={selectedDb}
        onChange={(e) => setSelectedDb(e.target.value)}
      />

      <button 
        className="update-button bg-blue-500 text-white px-4 py-2 rounded w-full disabled:opacity-50"
        onClick={handleUpdate}
        disabled={loading || !selectedDb}
      >
        {loading ? 'Updating...' : 'Update Database'}
      </button>

      {error && (
        <div className="error-message text-red-500 mt-2">
          {error}
        </div>
      )}

      {updateStatus && !error && (
        <div className="success-message text-green-500 mt-2">
          {updateStatus}
        </div>
      )}

      {loading && (
        <div className="loading-indicator text-gray-500 mt-2">
          Please wait while the database is being updated...
        </div>
      )}
    </div>
  );
};
const ShowDatabases = () => {
  const [selectedDb, setSelectedDb] = useState('');
  const [sortChoice, setSortChoice] = useState('normal');
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const sortOptions = [
    { value: 'normal', label: 'Below 95% CI' },
    { value: 'short', label: 'Above 95% CI' },
    { value: 'msd', label: 'RSI MSD' },
    { value: 'rsi', label: 'RSI Value' },
    { value: 'turn', label: 'RSI Turnover' }
  ];

  const fetchDatabaseData = async () => {
    if (!selectedDb) return;
    
    setLoading(true);
    setError(null);
    
    try {
      const response = await fetch(`http://localhost:5000/api/database/${selectedDb}/load?sort=${sortChoice}`);
      const result = await response.json();
      
      if (result.success) {
        setData(result.data);
      } else {
        setError(result.error || 'Failed to load database');
      }
    } catch (err) {
      setError('Failed to connect to server');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (selectedDb) {
      fetchDatabaseData();
    }
  }, [selectedDb, sortChoice]);

  return (
    <div className="section">
      <h3 className="text-xl font-bold mb-4">Show Database</h3>
      
      <div className="mb-4 flex gap-4">
        <DatabaseSelect 
          className="select-input w-1/2 p-2 border rounded"
          value={selectedDb}
          onChange={(e) => setSelectedDb(e.target.value)}
        />
        
        <select
          className="select-input w-1/2 p-2 border rounded"
          value={sortChoice}
          onChange={(e) => setSortChoice(e.target.value)}
        >
          {sortOptions.map(option => (
            <option key={option.value} value={option.value}>
              Sort by {option.label}
            </option>
          ))}
        </select>
      </div>

      {loading && (
        <div className="text-gray-500">Loading database...</div>
      )}

      {error && (
        <div className="text-red-500">Error: {error}</div>
      )}

      {data.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse table-auto">
            <thead>
              <tr className="bg-gray-100">
                <th className="border p-2 text-left">Ticker</th>
                <th className="border p-2 text-left">Below 95% CI</th>
                <th className="border p-2 text-left">Above 95% CI</th>
                <th className="border p-2 text-left">RSI</th>
                <th className="border p-2 text-left">RSI MSD</th>
                <th className="border p-2 text-left">RSI Turnover</th>
                <th className="border p-2 text-left">MA Status</th>
              </tr>
            </thead>
            <tbody>
              {data.map((item, index) => (
                <tr key={index} className={index % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                  <td className="border p-2">{item.Ticker}</td>
                  <td className="border p-2">{item['% Below 95% CI']?.toFixed(2)}%</td>
                  <td className="border p-2">{item['% Above 95% CI']?.toFixed(2)}%</td>
                  <td className="border p-2">{item.RSI?.toFixed(2)}</td>
                  <td className="border p-2">{item['RSI MSD']?.toFixed(2)}</td>
                  <td className="border p-2">{item['RSI Avg Turnover']}</td>
                  <td className="border p-2">{item.MA?.[0]} ({item.MA?.[1]})</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

const UpdateExperiments = () => {
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);
  const [status, setStatus] = useState('');

  const runExperiments = async () => {
    setLoading(true);
    setError(null);
    setStatus('Starting experiments...');

    try {
      // Run experiments endpoint
      const response = await fetch('http://localhost:5000/api/experiments/run', {
        method: 'POST',
      });

      const data = await response.json();
      
      if (data.success) {
        setResults(data.results);
        setStatus('Experiments completed successfully');
      } else {
        setError(data.error || 'Failed to run experiments');
      }
    } catch (err) {
      setError('Failed to connect to server');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="section">
      <h3 className="text-xl font-bold mb-4">Run Experiments</h3>
      
      <div className="space-y-4">
        <div className="bg-gray-50 p-4 rounded">
          <p className="text-gray-700">This will run the following experiments:</p>
          <ul className="list-disc ml-6 mt-2 space-y-2">
            <li>Check and verify settings</li>
            <li>Run winrate analysis</li>
            <li>Scan winrate data</li>
            <li>Calculate winrate potential</li>
          </ul>
        </div>

        <button 
          className="w-full bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600 disabled:opacity-50"
          onClick={runExperiments}
          disabled={loading}
        >
          {loading ? 'Running Experiments...' : 'Run All Experiments'}
        </button>

        {status && (
          <div className="text-gray-600 italic">
            {status}
          </div>
        )}

        {error && (
          <div className="text-red-500">
            Error: {error}
          </div>
        )}

        {results && (
          <div className="mt-4 bg-white p-4 rounded border">
            <h4 className="font-bold mb-2">Results:</h4>
            <pre className="whitespace-pre-wrap">
              {JSON.stringify(results, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
};

const Calculations = () => {
  const [ticker, setTicker] = useState('');
  const [calculationData, setCalculationData] = useState(null);
  const [calculationType, setCalculationType] = useState(''); // Add this line
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchRSI = async (calculationType) => {
    if (!ticker) {
      setError("Please enter a ticker symbol");
      return;
    }

    setLoading(true);
    setError(null);
    setCalculationType(calculationType);

    try {
      let endpoint = `http://localhost:5000/api/rsi/${ticker}`;

      if (calculationType === 'accuracy') {
        endpoint = `http://localhost:5000/api/rsi/accuracy/${ticker}`;
      }

      if (calculationType === 'turnover') {
        endpoint = `http://localhost:5000/api/rsi/turnover/${ticker}`;
      }

      if (calculationType === 'ma') {
        endpoint = `http://localhost:5000/api/rsi/ma/${ticker}`;
      }


      const response = await fetch(endpoint);
      const data = await response.json();

      if (data.success) {
        setCalculationData(data.data);
      } else {
        setError(data.error || 'Failed to fetch RSI data');
      }
    } catch (err) {
      setError('Failed to connect to server');
    } finally {
      setLoading(false);
    }
  };

  const handleCalculation = (calculationType) => {
    fetchRSI(calculationType)
  }
  const renderResult = () => {
    if (!calculationData) return null;

    switch (calculationType) {
      case 'accuracy':
        return (
          <>
            <h4>RSI Accuracy Results:</h4>
            <p className="result-value">
              Cosine Similarity: {calculationData.cos?.toFixed(4) || 'N/A'}
            </p>
            <p className="result-value">
              MSD Accuracy: {calculationData.msd?.toFixed(4) || 'N/A'}
            </p>
          </>
        );
      case 'turnover':
        return (
          <>
            <h4>RSI Turnover Results:</h4>
            <p className="result-value">
              {calculationData.turnover? calculationData.turnover : 'N/A' } days
            </p>
          </>
        );
      
      case 'ma':
        return(
          <>
            <h4>Moving Average Results:</h4>
            <p className="result-value">
              Market: {calculationData.latest_market? calculationData.latest_market : 'N/A'} 
            </p>
            <p className="result-value">
              Date Market Changed: {calculationData.latest_date? calculationData.latest_date : 'N/A'}
            </p>
            <p className="result-value">
              Approaching Change? {calculationData.converging? calculationData.converging: 'N/A'}
            </p>
          </>
        )
      
      default:
        return (
          <>
            <h4>RSI Results:</h4>
            <p className="result-value">
              Current RSI: {calculationData.rsi?.toFixed(2) || 'N/A'}
            </p>
          </>
        );
    }
  };

  return (
    <div className="section">
      <h3>Calculations</h3>
      <input
        type="text"
        placeholder="Enter ticker symbol"
        value={ticker}
        onChange={(e) => setTicker(e.target.value.toUpperCase())}
        className="input-field"
      />
      <div className="calc-options">
        <button className="calc-button" onClick={() => handleCalculation('basic')}>RSI</button>
        <button className="calc-button" onClick={() => handleCalculation('accuracy')}>RSI Accuracy (Trend)</button>
        <button className="calc-button" onClick={() => handleCalculation('turnover')}>RSI Turnover</button>
        <button className="calc-button" onClick={() => handleCalculation('ma')}>Moving Average</button>
      </div>

      {loading && <div>Loading...</div>}
      {error && <div className="error">{error}</div>}
      
      {calculationData && !loading && (
        <div className="calculation-result">
          <div className="result-card">
            {renderResult()}
          </div>
        </div>
      )}
    </div>
  );
};
// Main 95% Module Component
const ConfidenceModule = () => {
  const [view, setView] = useState('main');

  const menuItems = [
    {
      title: 'Update Database',
      description: 'Update specific database',
      action: 'update-db'
    },
    {
      title: 'Show Databases',
      description: 'View database information',
      action: 'show-db'
    },
    {
      title: 'Calculations',
      description: 'RSI, accuracy, turnover, moving average',
      action: 'calculations'
    },
    {
      title: 'Run Experiments',
      description: 'Update "winrate" experiment',
      action: 'update-experiments' 
    }
  ];

  const renderContent = () => {
    switch (view) {
      case 'update-db':
        return <UpdateDatabase />;
      case 'show-db':
        return <ShowDatabases />;
      case 'calculations':
        return <Calculations />;
      case 'update-experiments':  // Added this case
        return <UpdateExperiments />;
      default:
        return (
          <div className="menu-grid">
            {menuItems.map((item) => (
              <button
                key={item.action}
                onClick={() => setView(item.action)}
                className="menu-button"
              >
                <div className="menu-item">
                  <h3>{item.title}</h3>
                  <p>{item.description}</p>
                </div>
              </button>
            ))}
          </div>
        );
    }
  };

  return (
    <div>
      <h2 className="module-title">95% Confidence Module</h2>
      {view !== 'main' && (
        <button 
          onClick={() => setView('main')}
          className="back-button"
        >
          Back
        </button>
      )}
      {renderContent()}
    </div>
  );
};

export default ConfidenceModule;