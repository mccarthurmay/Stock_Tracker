import React, { useState } from 'react';
import './DayTradeModule.css';

const PaperTrading = () => {
  const [isTrading, setIsTrading] = useState(false);
  const [status, setStatus] = useState('');

  const handleStartTrading = () => {
    setIsTrading(true);
    setStatus('Paper trading session started...');
    // Implementation here
  };

  const handleStopTrading = () => {
    setIsTrading(false);
    setStatus('Paper trading session ended.');
    // Implementation here
  };

  return (
    <div className="section">
      <h3>Paper Trading</h3>
      <div className="trading-controls">
        {!isTrading ? (
          <button 
            className="action-button start" 
            onClick={handleStartTrading}
          >
            Start Paper Trading
          </button>
        ) : (
          <button 
            className="action-button stop" 
            onClick={handleStopTrading}
          >
            Stop Trading
          </button>
        )}
      </div>
      {status && (
        <div className="status-message">
          {status}
        </div>
      )}
    </div>
  );
};

const DayTradeModule = () => {
  return (
    <div>
      <h2 className="module-title">Day Trading Module</h2>
      <p>Not in working condition.</p>
      <PaperTrading />
    </div>
  );
};

export default DayTradeModule;