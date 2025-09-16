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

  // State for "Why" popup
  const [showWhyPopup, setShowWhyPopup] = useState(false);
  const [whyData, setWhyData] = useState(null);

  const sortOptions = [
    { value: 'normal', label: 'Below 95% CI' },
    { value: 'finalbuy', label: 'Final Buy Signal' },
    { value: 'stage1', label: 'Stage 1 Signal' },
    { value: 'rsi', label: 'RSI Value' },
    { value: 'turn', label: 'RSI Turnover' },
    { value: 'expected_return', label: 'Expected Return' },
    { value: 'profit_prob', label: 'Profit Probability' },
  ];
  
  // Update the handleWhyClick function
  const handleWhyClick = async (tickerData) => {
    setWhyData(tickerData);
    setShowWhyPopup(true);
    
    // Fetch enhanced analysis in background
    const detailedAnalysis = await fetchDetailedAnalysis(tickerData.Ticker);
    if (detailedAnalysis) {
      setWhyData(prev => ({
        ...prev,
        detailedAnalysis: detailedAnalysis
      }));
    }
  };

  // Add this function to the ShowDatabases component
  const fetchDetailedAnalysis = async (ticker) => {
    try {
      const response = await fetch(`http://localhost:5000/api/why-analysis/${ticker}`);
      const result = await response.json();
      
      if (result.success) {
        return result.data;
      } else {
        console.error('Failed to fetch detailed analysis:', result.error);
        return null;
      }
    } catch (err) {
      console.error('Error fetching detailed analysis:', err);
      return null;
    }
  };


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
  // Modal component for "Why" analysis
  const WhyModal = () => {
    if (!showWhyPopup || !whyData) return null;

    // Determine if this is a portfolio database
    const isPortfolio = selectedDb.toLowerCase().includes('portfolio') || selectedDb.toLowerCase().startsWith('p_');
    
    const finalSignal = isPortfolio 
      ? (whyData.Sell === true ? 'SELL' : 'DON\'T SELL')
      : (whyData.FinalBuy === true ? 'BUY' : 'DON\'T BUY');

    // Check if this is new database format with Monte Carlo data
    const hasMonteCarloData = whyData.MC_Data && typeof whyData.MC_Data === 'object';
    const isNewFormat = 'FinalBuy' in whyData;

    return (
      <div className="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50">
        <div className="absolute inset-0" onClick={() => setShowWhyPopup(false)}></div>
        
        <div className="bg-white rounded-lg p-6 max-w-4xl w-full max-h-[90vh] overflow-y-auto relative shadow-2xl border-2 border-green-200">
          <div className="flex justify-between items-center mb-4 pb-3 border-b border-gray-200">
            <h3 className="text-xl font-bold text-green-800">Why {finalSignal}: {whyData.Ticker}</h3>
            
            <button 
              onClick={() => setShowWhyPopup(false)}
              className="text-gray-500 hover:text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-full p-1"
              aria-label="Close analysis"
            >
              <span className="text-2xl block w-6 h-6 flex items-center justify-center">&times;</span>
            </button>
          </div>
          
          <div className="absolute top-4 right-4 bg-green-100 text-green-800 px-2 py-1 rounded-full text-xs font-medium">
            {isNewFormat ? 'Two-Stage Analysis' : 'Traditional Analysis'}
          </div>
          
          <div className="space-y-4">
            {/* Current Statistical Conditions */}
            <div className="bg-blue-50 p-4 rounded-lg">
              <h4 className="font-semibold text-blue-800 mb-3">📊 Current Statistical Conditions</h4>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p><strong>Below 95% CI:</strong> <span className="text-blue-700">{whyData['% Below 95% CI']}%</span></p>
                  <p><strong>RSI Level:</strong> <span className="text-blue-700">{whyData.RSI}</span></p>
                  <p><strong>RSI Turnover:</strong> <span className="text-blue-700">{whyData['RSI Avg Turnover']} days</span></p>
                </div>
                <div>
                  <p><strong>RSI Accuracy (COS):</strong> <span className="text-blue-700">{whyData['RSI COS']}</span></p>
                  <p><strong>RSI Accuracy (MSD):</strong> <span className="text-blue-700">{whyData['RSI MSD']}</span></p>
                  <p><strong>Moving Average:</strong> <span className="text-blue-700">{whyData.MA ? whyData.MA[0] : 'N/A'}</span></p>
                </div>
              </div>
              
              {isNewFormat && (
                <div className="mt-3 pt-3 border-t border-blue-200">
                  <p><strong>Stage 1 Signal:</strong> <span className={whyData.Buy ? 'text-green-600 font-bold' : 'text-gray-600'}>{whyData.Buy ? 'BUY' : 'NO BUY'}</span></p>
                  <p><strong>Final Signal:</strong> <span className={finalSignal.includes('BUY') || finalSignal.includes('SELL') ? 'text-green-600 font-bold' : 'text-gray-600'}>{finalSignal}</span></p>
                  {hasMonteCarloData && (
                    <>
                      <p><strong>Monte Carlo Validation:</strong> <span className={whyData.MC_Validation ? 'text-green-600 font-bold' : 'text-red-600'}>{whyData.MC_Validation ? 'PASSED' : 'FAILED'}</span></p>
                      <p><strong>Expected Return:</strong> <span className="text-blue-700">{whyData.MC_Data.expected_return}%</span></p>
                      <p><strong>Profit Probability:</strong> <span className="text-blue-700">{whyData.MC_Data.prob_profit}%</span></p>
                    </>
                  )}
                </div>
              )}
            </div>

            {/* Algorithm Reasoning */}
            <div className="bg-yellow-50 p-4 rounded-lg">
              <h4 className="font-semibold text-yellow-800 mb-3">🧠 Algorithm Reasoning</h4>
              <div className="text-sm text-gray-700 space-y-3">
                {isNewFormat ? (
                  <>
                    <div className="bg-white p-3 rounded border-l-4 border-yellow-400">
                      <p><strong>Stage 1 (Technical Analysis):</strong> {whyData.Buy ? 'Passed - Technical indicators suggest oversold conditions with potential for reversal.' : 'Failed - Current technical conditions do not meet buy criteria.'}</p>
                    </div>
                    
                    <div className="bg-white p-3 rounded border-l-4 border-yellow-400">
                      {whyData.Buy ? (
                        hasMonteCarloData ? (
                          <p><strong>Stage 2 (Monte Carlo Validation):</strong> {whyData.MC_Validation ? 
                            `Passed - Simulation shows ${whyData.MC_Data.prob_profit}% chance of profit with ${whyData.MC_Data.expected_return}% expected return.` : 
                            `Failed - Monte Carlo simulation indicates insufficient probability of profit (${whyData.MC_Data.prob_profit}%) or unfavorable risk/reward.`}</p>
                        ) : (
                          <p><strong>Stage 2 (Monte Carlo Validation):</strong> Failed to run - Insufficient historical data or technical error prevented Monte Carlo analysis.</p>
                        )
                      ) : (
                        <p><strong>Stage 2 (Monte Carlo Validation):</strong> Skipped - Stage 1 did not pass, so Monte Carlo validation was not needed.</p>
                      )}
                    </div>
                    
                    <div className="bg-white p-3 rounded border-l-4 border-green-400">
                      <p><strong>Final Decision:</strong> {isPortfolio 
                        ? `${finalSignal.includes('SELL') ? 'SELL' : 'HOLD'} based on ${whyData.Sell ? 'profit-taking signals' : 'continued holding potential'}.`
                        : `${finalSignal.includes('BUY') ? 'BUY' : 'DON\'T BUY'} - ${whyData.FinalBuy ? 'Both stages passed' : whyData.Buy ? 'Stage 1 passed but Stage 2 failed or could not run' : 'Stage 1 failed'}.`
                      }</p>
                    </div>
                  </>
                ) : (
                  <div className="bg-white p-3 rounded border-l-4 border-yellow-400">
                    <p><strong>Traditional Analysis:</strong> {isPortfolio 
                      ? `This ${finalSignal.includes('SELL') ? 'sell' : 'hold'} signal is based on ${whyData.Sell ? 'overbought conditions and profit-taking indicators' : 'continued strength and holding potential'}.`
                      : `This ${finalSignal.includes('BUY') ? 'buy' : 'no-buy'} signal is based on ${whyData.Buy ? 'oversold conditions and value opportunity indicators' : 'current market conditions not meeting buy criteria'}.`
                    }</p>
                  </div>
                )}
              </div>
            </div>

            {/* Detailed Analysis Section - NEW */}
            {whyData.detailedAnalysis && (
              <div className="bg-indigo-50 p-4 rounded-lg">
                <h4 className="font-semibold text-indigo-800 mb-3">🔍 Detailed Analysis</h4>
                <div className="text-sm text-gray-700 space-y-3">
                  <div className="bg-white p-3 rounded border-l-4 border-indigo-400">
                    <p><strong>Why This Stock Was Flagged:</strong></p>
                    <p className="mt-1">{whyData.detailedAnalysis.detailed_reasoning.why_flagged}</p>
                  </div>
                  
                  <div className="bg-white p-3 rounded border-l-4 border-indigo-400">
                    <p><strong>Expected Outcome:</strong></p>
                    <p className="mt-1">{whyData.detailedAnalysis.detailed_reasoning.expected_outcome}</p>
                  </div>
                  
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div className="bg-white p-3 rounded border">
                      <p><strong>Key Opportunity Factors:</strong></p>
                      <ul className="mt-1 text-xs space-y-1">
                        {whyData.detailedAnalysis.risk_assessment.opportunity_factors.map((factor, idx) => (
                          <li key={idx} className="text-green-700">• {factor}</li>
                        ))}
                      </ul>
                    </div>
                    
                    <div className="bg-white p-3 rounded border">
                      <p><strong>Risk Factors:</strong></p>
                      <ul className="mt-1 text-xs space-y-1">
                        {whyData.detailedAnalysis.risk_assessment.risk_factors.map((factor, idx) => (
                          <li key={idx} className="text-red-700">• {factor}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                  
                  <div className="bg-white p-3 rounded border-l-4 border-green-400">
                    <p><strong>Overall Confidence:</strong> <span className="font-semibold">{whyData.detailedAnalysis.risk_assessment.overall_confidence}</span></p>
                    <p className="mt-1 text-xs">{whyData.detailedAnalysis.risk_assessment.confidence_explanation}</p>
                  </div>
                </div>
              </div>
            )}

            {/* Risk Assessment */}
            <div className="bg-red-50 p-4 rounded-lg">
              <h4 className="font-semibold text-red-800 mb-3">⚠️ Risk Assessment</h4>
              <div className="text-sm text-gray-700 space-y-2">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <p><strong>Market Risk:</strong> General market volatility could impact this position regardless of individual stock fundamentals.</p>
                    <p><strong>Sector Risk:</strong> Industry-specific events or trends could affect stock performance.</p>
                  </div>
                  <div>
                    <p><strong>Technical Risk:</strong> {whyData.RSI > 70 ? 'RSI indicates overbought conditions' : whyData.RSI < 30 ? 'RSI indicates oversold conditions' : 'RSI in neutral territory'}.</p>
                    <p><strong>Timing Risk:</strong> Entry/exit timing based on technical indicators may not align with market movements.</p>
                  </div>
                </div>
                
                {hasMonteCarloData && (
                  <div className="mt-3 p-3 bg-white rounded border">
                    <p><strong>Quantified Risk:</strong> Monte Carlo simulation suggests {whyData.MC_Data.prob_loss}% probability of loss with average loss of {whyData.MC_Data.avg_loss}%.</p>
                  </div>
                )}
                
                <div className="mt-3 p-2 bg-red-100 rounded text-red-800 text-xs">
                  <strong>Disclaimer:</strong> This is algorithmic analysis for educational purposes only, not financial advice. Past performance does not guarantee future results.
                </div>
              </div>
            </div>

            {/* Time Horizon & Confidence */}
            <div className="bg-gray-50 p-4 rounded-lg">
              <h4 className="font-semibold text-gray-800 mb-3">📅 Time Horizon & Confidence</h4>
              <div className="text-sm text-gray-700 space-y-2">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <p><strong>Expected Timeframe:</strong> {whyData['RSI Avg Turnover']} days average based on historical RSI patterns.</p>
                    <p><strong>Technical Confidence:</strong> {whyData['RSI COS'] > 0.8 ? 'High' : whyData['RSI COS'] > 0.6 ? 'Medium' : 'Low'} correlation between RSI and price movements.</p>
                  </div>
                  <div>
                    {hasMonteCarloData ? (
                      <>
                        <p><strong>Statistical Confidence:</strong> Based on {whyData.MC_Data.simulations_run} Monte Carlo simulations over {whyData.MC_Data.time_horizon_days} days.</p>
                        <p><strong>Volatility:</strong> {whyData.MC_Data.volatility}% daily volatility detected.</p>
                      </>
                    ) : (
                      <>
                        <p><strong>Analysis Type:</strong> Traditional technical analysis without probabilistic validation.</p>
                        <p><strong>Recommendation:</strong> Consider updating database for enhanced Monte Carlo analysis.</p>
                      </>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* Historical Performance Context */}
            <div className="bg-purple-50 p-4 rounded-lg">
              <h4 className="font-semibold text-purple-800 mb-3">📈 Historical Context</h4>
              <div className="text-sm text-gray-700">
                <p><strong>RSI Pattern:</strong> Based on {whyData['RSI Avg Turnover']}-day average turnover cycles, this stock typically moves from oversold to overbought conditions over this timeframe.</p>
                <p><strong>Moving Average Trend:</strong> {whyData.MA && whyData.MA[0] === 'BULL' ? 'Currently in bullish trend' : whyData.MA && whyData.MA[0] === 'BEAR' ? 'Currently in bearish trend' : 'Trend direction unclear'}. {whyData['MA Converging'] ? 'Moving averages are converging, suggesting potential trend change.' : 'Moving averages show stable trend direction.'}</p>
                
                {hasMonteCarloData && (
                  <div className="mt-2 p-3 bg-white rounded border">
                    <p><strong>Simulation Results:</strong> Out of {whyData.MC_Data.simulations_run} scenarios, {whyData.MC_Data.prob_profit}% resulted in profit with average gain of {whyData.MC_Data.avg_profit}%.</p>
                  </div>
                )}
              </div>
            </div>
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
          This advanced stock analysis tool combines traditional technical indicators with cutting-edge anomaly detection to identify unusual market opportunities. It's specifically designed to find stocks experiencing statistically significant deviations from normal trading patterns - perfect for identifying oversold conditions, black swan events, and mean reversion opportunities.
        </p>
        
        <h5 className="font-medium text-blue-800 mb-1">How to use:</h5>
        <ol className="list-decimal list-inside text-blue-900 space-y-1 mb-4">
          <li>Select a database from the dropdown menu</li>
          <li>Choose how to sort the data (by anomaly count, RSI, CI values, etc.)</li>
          <li>Look for stocks with high anomaly counts and favorable Z-scores for best opportunities</li>
          <li>Click on any ticker symbol to view its detailed analysis chart</li>
          <li>Use the "Return to table" button to go back to the database view</li>
        </ol>
        
        <h5 className="font-medium text-blue-800 mb-2">Buy Signal Triggers:</h5>
        <div className="mb-3 p-3 bg-green-50 rounded border border-green-200">
          <p className="text-green-800 text-sm">
            <span className="font-medium">Buy = Yes</span> when any of these conditions are met:
          </p>
          <ul className="list-disc list-inside text-green-800 text-sm mt-1 ml-4">
            <li><span className="font-medium">Strong Signal:</span> 3+ anomalies detected, Z-Score downward, price below trend, RSI &lt; 35</li>
            <li><span className="font-medium">Medium Signal:</span> 2+ anomalies detected, negative volatility breakout, significant trend deviation, RSI &lt; 32</li>
            <li><span className="font-medium">Traditional Signal:</span> Below 95% confidence interval, RSI &lt; 31, Z-Score not upward</li>
          </ul>
        </div>
        
        <h5 className="font-medium text-blue-800 mb-2">Column Explanations:</h5>
        <ul className="list-disc list-inside text-blue-900 text-sm space-y-2">
          <li><span className="font-medium">Below 95% CI</span>: How far the current price is below the statistical "normal" range. Positive values indicate potential buying opportunities (stock is unusually cheap).</li>
          
          <li><span className="font-medium">RSI</span>: Relative Strength Index (0-100). Values below 30 indicate oversold conditions, above 70 indicate overbought. Used to confirm entry/exit timing.</li>
          
          <li><span className="font-medium">RSI Turnover</span>: Average number of days between major RSI trend changes (70→30 cycles). Helps predict how long current conditions might last.</li>
          
          <li><span className="font-medium">Anomaly Count</span>: Number of statistical anomaly detection methods that flagged unusual behavior (0-4). Higher counts indicate stronger confidence in abnormal price movements.</li>
          
          <li><span className="font-medium">Z-Score</span>: Measures how many standard deviations the price is from its recent average. Buy opportunities: &lt; -2.0 (unusually low), Sell signals: &gt; +2.0 (unusually high), Normal range: -1.5 to +1.5.</li>
          
          <li><span className="font-medium">Trend Dev</span>: Shows if current price deviates significantly from the established trend line. BL=Below trend (potential buy), AB=Above trend (potential sell).</li>
          
          <li><span className="font-medium">Vol Break</span>: Indicates when price volatility exceeds normal patterns, suggesting unusual market activity. NEG=Downward volatility spike, POS=Upward volatility spike.</li>
          
          <li><span className="font-medium">Buy/Sell Signal</span>: Final trading recommendation combining all analyses. Enhanced signals use multiple confirmation methods for higher accuracy than traditional single-indicator approaches.</li>
        </ul>
        
        <div className="mt-3 p-3 bg-blue-100 rounded">
          <p className="text-blue-800 text-sm font-medium">💡 Pro Tip: Click "Why?" on any ticker to understand the detailed reasoning behind buy/sell signals.</p>
        </div>
      </div>
      
      {/* Chart Modal - positioned outside main content flow */}
      <ChartModal />

      {/* Why Analysis Modal */}
      <WhyModal />
      
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
                <th className="border p-2 text-left">RSI</th>
                <th className="border p-2 text-left">Final Signal</th>
                <th className="border p-2 text-left">Why</th>
              </tr>
            </thead>
            <tbody>
              {data.map((item, index) => {
                // Determine if this is a portfolio database
                const isPortfolio = selectedDb.toLowerCase().includes('portfolio') || selectedDb.toLowerCase().startsWith('p_');
                const hasMCData = item.MC_Data && typeof item.MC_Data === 'object';
                const mcValidation = item.MC_Validation || false;

                // Determine final signal based on database type
                const finalSignal = isPortfolio 
                  ? (item.Sell === true ? 'SELL' : 'DON\'T SELL')
                  : ((item.FinalBuy === true || (item.FinalBuy === undefined && item.Buy === true)) ? 'BUY' : 'DON\'T BUY');

                
                const signalColor = isPortfolio
                  ? (item.Sell === true ? 'bg-red-100 text-red-800' : 'bg-gray-100 text-gray-800')
                  : item.FinalBuy === true 
                    ? 'bg-green-100 text-green-800'  // Final buy signal
                    : item.Buy === true 
                      ? 'bg-yellow-100 text-yellow-800'  // Stage 1 only
                      : 'bg-gray-100 text-gray-800';     // No signal

                return (
                  <tr 
                    key={index} 
                    className={index % 2 === 0 ? 'bg-white' : 'bg-gray-50'} 
                  >
                    <td className="border p-2">
                      <button
                        onClick={(e) => handleTickerClick(item.Ticker, e.currentTarget.closest('tr'))}
                        className={`font-medium focus:outline-none ${
                          visitedTickers.includes(item.Ticker) 
                            ? 'text-red-600 font-bold' 
                            : 'text-blue-600 hover:text-blue-800'
                        }`}
                      >
                        {visitedTickers.includes(item.Ticker) ? '✓ ' : ''}
                        {item.Ticker}
                      </button>
                    </td>
                    <td className="border p-2">{item['% Below 95% CI']}%</td>
                    <td className="border p-2">{item.RSI}</td>
                    <td className="border p-2">
                      <span className={`px-2 py-1 rounded text-sm font-medium ${signalColor}`}>
                        {finalSignal}
                      </span>
                    </td>
                    <td className="border p-2">
                      <button
                        onClick={() => handleWhyClick(item)}
                        className="px-3 py-1 bg-blue-500 text-white rounded hover:bg-blue-600 text-sm"
                      >
                        Why?
                      </button>
                    </td>
                  </tr>
                );
              })}
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