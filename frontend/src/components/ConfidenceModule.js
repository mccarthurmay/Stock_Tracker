import './ConfidenceModule.css';
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { DatabaseSelect } from './DatabaseModule';
import CombinedAnalysisChart from './CombinedAnalysisChart';

// 95% Module Components

const UpdateDatabase = () => {
  const [selectedDb, setSelectedDb] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [updateStatus, setUpdateStatus] = useState(null);
  const [timeRemaining, setTimeRemaining] = useState(null);
  const [estimateRequested, setEstimateRequested] = useState(false);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    let timer;
    if (timeRemaining && timeRemaining > 0 && loading) {
      const interval = 1000; // 1 second
      timer = setInterval(() => {
        setTimeRemaining(prev => {
          if (prev <= 0) {
            clearInterval(timer);
            return 0;
          }
          const newTime = prev - 1;
          // Update progress percentage
          setProgress((1 - newTime / timeRemaining) * 100);
          return newTime;
        });
      }, interval);
    }
    return () => {
      if (timer) clearInterval(timer);
    };
  }, [timeRemaining, loading]);

  const formatTime = (seconds) => {
    if (seconds === null) return '--:--';
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
  };

  const getEstimate = async () => {
    try {
      const response = await fetch(`http://localhost:5000/api/database/${selectedDb}/estimate`);
      const data = await response.json();
      
      if (data.success) {
        return data.estimated_time;
      } else {
        throw new Error(data.error || 'Failed to get estimate');
      }
    } catch (err) {
      throw new Error('Failed to get time estimate');
    }
  };

  const handleUpdate = async () => {
    if (!selectedDb) {
      setError('Please select a database');
      return;
    }

    setEstimateRequested(true);
    setError(null);
    setUpdateStatus('Calculating estimated time...');

    try {
      // First get the estimate
      const estimatedTime = await getEstimate();
      setTimeRemaining(estimatedTime);
      setUpdateStatus(`Estimated time: ${formatTime(estimatedTime)}. Proceed with update?`);
      
      // User must confirm before proceeding
      if (!window.confirm(`This update will take approximately ${formatTime(estimatedTime)}. Do you want to continue?`)) {
        setEstimateRequested(false);
        setUpdateStatus(null);
        setTimeRemaining(null);
        setProgress(0);
        return;
      }

      // Start the update
      setLoading(true);
      setProgress(0);
      setUpdateStatus('Updating database...');

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
        throw new Error(data.error || 'Failed to update database');
      }
    } catch (err) {
      setError(err.message || 'Failed to connect to server');
    } finally {
      setLoading(false);
      setEstimateRequested(false);
      setTimeRemaining(null);
      setProgress(0);
    }
  };

  return (
    <div className="section">
      <h3 className="text-xl font-bold mb-4">Update Database</h3>
      <h5>Alpaca API Call Limit: 150/min</h5>
      
      <DatabaseSelect 
        className="select-input w-full p-2 mb-4 border rounded"
        value={selectedDb}
        onChange={(e) => {
          setSelectedDb(e.target.value);
          setEstimateRequested(false);
          setUpdateStatus(null);
          setError(null);
          setTimeRemaining(null);
          setProgress(0);
        }}
      />

      <button 
        className="update-button bg-blue-500 text-white px-4 py-2 rounded w-full disabled:opacity-50"
        onClick={handleUpdate}
        disabled={loading || !selectedDb}
      >
        {loading ? 'Updating...' : estimateRequested ? 'Getting estimate...' : 'Update Database'}
      </button>

      {timeRemaining !== null && loading && (
        <div className="mt-4">
          <div className="bg-blue-100 p-4 rounded">
            <p className="text-blue-800">
              Time remaining: {formatTime(timeRemaining)}
            </p>
            <div className="w-full bg-blue-200 rounded-full h-2.5 mt-2">
              <div 
                className="bg-blue-600 h-2.5 rounded-full transition-all duration-1000"
                style={{ width: `${Math.min(100, progress)}%` }}
              />
            </div>
          </div>
        </div>
      )}

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
    </div>
  );
};

const ShowDatabases = () => {
  const [selectedDb, setSelectedDb] = useState('');
  const [sortChoice, setSortChoice] = useState('normal');
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedTicker, setSelectedTicker] = useState(null);
  const [showChart, setShowChart] = useState(false);
  const [tickerHistory, setTickerHistory] = useState([]);
  
  // Using array for visited tickers instead of Set for better visibility of state changes
  const [visitedTickers, setVisitedTickers] = useState([]);
  
  // Create refs for chart element and clicked row position
  const chartRef = useRef(null);
  const clickedRowRef = useRef(null);

  const sortOptions = [
    { value: 'normal', label: 'Below 95% CI' },
    { value: 'short', label: 'Above 95% CI' },
    { value: 'rsi', label: 'RSI Value' },
    { value: 'turn', label: 'RSI Turnover' }
  ];

  const fetchDatabaseData = useCallback(async () => {
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
  }, [selectedDb, sortChoice]);

  useEffect(() => {
    fetchDatabaseData();
  }, [fetchDatabaseData, selectedDb]);

  const handleTickerClick = (ticker, rowElement) => {
    // Add current ticker to history if different from last viewed
    if (selectedTicker && selectedTicker !== ticker) {
      setTickerHistory(prev => [...prev, selectedTicker]);
    }
    
    // Store reference to the clicked row element
    clickedRowRef.current = rowElement;
    
    // Mark ticker as visited if not already
    if (!visitedTickers.includes(ticker)) {
      setVisitedTickers(prev => [...prev, ticker]);
      console.log("Added to visited:", ticker);
    }
    
    setSelectedTicker(ticker);
    setShowChart(true);
  };

  // Handle returning to table
  const handleReturnToTable = () => {
    setShowChart(false);
    
    // Scroll back to the clicked row
    setTimeout(() => {
      if (clickedRowRef.current) {
        clickedRowRef.current.scrollIntoView({ 
          behavior: 'smooth',
          block: 'center'
        });
      }
    }, 100);
  };

  // Scroll to chart when it becomes visible
  useEffect(() => {
    if (showChart && chartRef.current) {
      // Use setTimeout to ensure the chart is rendered
      setTimeout(() => {
        chartRef.current.scrollIntoView({ 
          behavior: 'smooth',
          block: 'start'
        });
      }, 100);
    }
  }, [showChart, selectedTicker]);

  // Modal component for the chart
  const ChartModal = () => {
    if (!showChart) return null;

    return (
      <div 
        ref={chartRef}
        className="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50"
      >
        {/* Semi-transparent overlay to clearly separate from the table */}
        <div className="absolute inset-0" onClick={() => setShowChart(false)}></div>
        
        {/* Chart container with visual distinction */}
        <div className="bg-white rounded-lg p-6 max-w-4xl w-full max-h-[80vh] overflow-y-auto relative shadow-2xl border-2 border-blue-200">
          {/* Header bar with visual separation */}
          <div className="flex justify-between items-center mb-4 pb-3 border-b border-gray-200">
            <div className="flex items-center gap-3">
              <h3 className="text-xl font-bold text-blue-800">{selectedTicker} Analysis</h3>
              
              {/* Return to table button */}
              <button
                onClick={handleReturnToTable}
                className="flex items-center gap-1 text-blue-600 hover:text-blue-800 bg-blue-50 hover:bg-blue-100 px-2 py-1 rounded transition-colors"
                aria-label="Return to table view"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" 
                  stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M19 12H5M12 19l-7-7 7-7"/>
                </svg>
                Return to table
              </button>
            </div>
            
            <button 
              onClick={() => setShowChart(false)}
              className="text-gray-500 hover:text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-full p-1"
              aria-label="Close chart"
            >
              <span className="text-2xl block w-6 h-6 flex items-center justify-center">&times;</span>
            </button>
          </div>
          
          {/* Visual badge to distinguish this is the chart section */}
          <div className="absolute top-4 right-4 bg-blue-100 text-blue-800 px-2 py-1 rounded-full text-xs font-medium">
            Chart View
          </div>
          
          {/* Chart content */}
          <div className="mt-2">
            <CombinedAnalysisChart ticker={selectedTicker} />
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="section">
      <h3 className="text-xl font-bold mb-4">Show Database</h3>
      
      {/* Info Section */}
      <div className="mb-6 p-4 bg-blue-50 rounded-lg border border-blue-100">
        <h4 className="font-semibold text-blue-800 mb-2">About This Tool</h4>
        <p className="text-blue-900 mb-3">
          This tool allows you to view and analyze stock data with confidence intervals, RSI indicators, and moving averages.
        </p>
        
        <h5 className="font-medium text-blue-800 mb-1">How to use:</h5>
        <ol className="list-decimal list-inside text-blue-900 space-y-1 mb-3">
          <li>Select a database from the dropdown menu</li>
          <li>Choose how to sort the data (by RSI, CI values, etc.)</li>
          <li>Click on any ticker symbol to view its detailed analysis chart</li>
          <li>Use the "Return to table" button to go back to the database view</li>
        </ol>
        
        <h5 className="font-medium text-blue-800 mb-1">Column Explanations:</h5>
        <ul className="list-disc list-inside text-blue-900 text-sm grid grid-cols-2 gap-x-4 gap-y-1">
          <li><span className="font-medium">Below/Above 95% CI</span>: Percentage deviation from confidence interval</li>
          <li><span className="font-medium">RSI</span>: Relative Strength Index value</li>
          <li><span className="font-medium">RSI Turnover</span>: Average days between RSI trend changes</li>
          <li><span className="font-medium">MA Status</span>: Current moving average trend</li>
          <li><span className="font-medium">Buy/Sell Signal</span>: Trading signals based on analysis</li>
        </ul>
      </div>
      
      {/* Chart Modal - positioned outside main content flow */}
      <ChartModal />
      
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

      {/* Show history navigation if available */}
      {tickerHistory.length > 0 && !showChart && (
        <div className="mb-4 p-2 bg-gray-50 rounded">
          <p className="text-sm text-gray-600 mb-1">Recently viewed:</p>
          <div className="flex flex-wrap gap-2">
            {[...tickerHistory].reverse().slice(0, 5).map((ticker, idx) => (
              <button
                key={idx}
                onClick={() => handleTickerClick(ticker)}
                className={`px-2 py-1 text-sm border rounded transition-colors ${
                  visitedTickers.includes(ticker) 
                    ? 'bg-red-50 text-red-700 border-red-200 font-bold'
                    : 'bg-white text-blue-600 border-gray-300 hover:bg-blue-50'
                }`}
              >
                {visitedTickers.includes(ticker) ? '✓ ' : ''}{ticker}
              </button>
            ))}
          </div>
        </div>
      )}

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
                <th className="border p-2 text-left">RSI Turnover</th>
                <th className="border p-2 text-left">MA Status</th>
                <th className="border p-2 text-left">Buy Signal</th>
                <th className="border p-2 text-left">Sell Signal</th>
              </tr>
            </thead>
            <tbody>
              {data.map((item, index) => (
                <tr 
                  key={index} 
                  className={index % 2 === 0 ? 'bg-white' : 'bg-gray-50'} 
                  ref={element => {
                    // Store reference to row element when ticker matches selected ticker
                    if (item.Ticker === selectedTicker) {
                      clickedRowRef.current = element;
                    }
                  }}
                >
                  <td className="border p-2">
                    <button
                      onClick={(e) => handleTickerClick(item.Ticker, e.currentTarget.closest('tr'))}
                      className={`font-medium focus:outline-none ${
                        visitedTickers.includes(item.Ticker) 
                          ? 'text-red-600 font-bold' // Bold red for visited
                          : 'text-blue-600 hover:text-blue-800' // Blue for unvisited
                      }`}
                      aria-label={`View chart analysis for ${item.Ticker}`}
                    >
                      {/* Clear indicator for visited tickers */}
                      {visitedTickers.includes(item.Ticker) ? '✓ ' : ''}
                      {item.Ticker}
                    </button>
                  </td>
                  <td className="border p-2">{item['% Below 95% CI']}%</td>
                  <td className="border p-2">{item['% Above 95% CI']}%</td>
                  <td className="border p-2">{item.RSI}</td>
                  <td className="border p-2">{item['RSI Avg Turnover']}</td>
                  <td className="border p-2">{item.MA?.[0]} ({item.MA?.[1]})</td>
                  <td className="border p-2">
                    {item.Buy === true ? (
                      <span className="px-2 py-1 bg-green-100 text-green-800 rounded">Yes</span>
                    ) : item.Buy === false ? (
                      <span className="px-2 py-1 bg-red-100 text-red-800 rounded">No</span>
                    ) : (
                      '-'
                    )}
                  </td>
                  <td className="border p-2">
                    {item.Sell === true ? (
                      <span className="px-2 py-1 bg-green-100 text-green-800 rounded">Yes</span>
                    ) : item.Sell === false ? (
                      <span className="px-2 py-1 bg-red-100 text-red-800 rounded">No</span>
                    ) : (
                      '-'
                    )}
                  </td>
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

      case 'graph':
        return (
          <>
            <h4>Combined Analysis Chart:</h4>
            <CombinedAnalysisChart ticker={ticker} />
          </>
        );
      
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
        <button className="calc-button" onClick={() => handleCalculation('graph')}>Show Chart</button>

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