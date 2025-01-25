import React, { useState } from 'react';
import './ConfidenceModule.css';

// 95% Module Components
const UpdateAll = () => {
  const [selectedOptions, setSelectedOptions] = useState({
    settings: false,
    databases: false,
    portfolios: false,
    experiments: false
  });

  const handleUpdate = () => {
    // Implementation here
  };

  return (
    <div className="section">
      <h3>Update All</h3>
      <div className="update-options">
        <label>
          <input 
            type="checkbox" 
            checked={selectedOptions.databases}
            onChange={e => setSelectedOptions({...selectedOptions, databases: e.target.checked})}
          /> 
          Update databases
        </label>
        <label>
          <input 
            type="checkbox" 
            checked={selectedOptions.portfolios}
            onChange={e => setSelectedOptions({...selectedOptions, portfolios: e.target.checked})}
          /> 
          Update portfolios
        </label>
        <label>
          <input 
            type="checkbox" 
            checked={selectedOptions.experiments}
            onChange={e => setSelectedOptions({...selectedOptions, experiments: e.target.checked})}
          /> 
          Run shortrate/Winrate experiments
        </label>
        <button className="update-button" onClick={handleUpdate}>Update Selected</button>
      </div>
    </div>
  );
};

const UpdateDatabase = () => (
  <div className="section">
    <h3>Update Database</h3>
    <select className="select-input">
      <option value="">Select Database</option>
    </select>
    <button className="update-button">Update</button>
  </div>
);

const UpdatePortfolio = () => (
  <div className="section">
    <h3>Update Portfolio</h3>
    <select className="select-input">
      <option value="">Select Portfolio</option>
    </select>
    <button className="update-button">Update</button>
  </div>
);

const UpdateExperiments = () => (
  <div className="section">
    <h3>Update Shortrate/Winrate</h3>
    <select className="select-input">
      <option value="shortrate">Shortrate</option>
      <option value="winrate">Winrate</option>
    </select>
    <button className="update-button">Update</button>
  </div>
);

const ShowDatabases = () => {
  const [databaseType, setDatabaseType] = useState('databases');
  const [selectedDatabase, setSelectedDatabase] = useState('');

  return (
    <div className="section">
      <h3>Show Databases</h3>
      <select 
        className="select-input"
        value={databaseType}
        onChange={(e) => setDatabaseType(e.target.value)}
      >
        <option value="databases">Databases</option>
        <option value="portfolio">Portfolio</option>
        <option value="experiments">Shortrate/Winrate</option>
      </select>
      <select 
        className="select-input"
        value={selectedDatabase}
        onChange={(e) => setSelectedDatabase(e.target.value)}
      >
        <option value="">Select Specific Database</option>
      </select>
      <div className="database-list">
        {/* Database content will be displayed here */}
      </div>
    </div>
  );
};

const Calculations = () => {
  const [calculation, setCalculation] = useState(null);
  const [ticker, setTicker] = useState('');

  const handleCalculation = (type) => {
    setCalculation(type);
  };

  return (
    <div className="section">
      <h3>Calculations</h3>
      <input
        type="text"
        placeholder="Enter ticker symbol"
        value={ticker}
        onChange={(e) => setTicker(e.target.value)}
        className="input-field"
      />
      <div className="calc-options">
        <button className="calc-button" onClick={() => handleCalculation('rsi')}>RSI</button>
        <button className="calc-button" onClick={() => handleCalculation('rsi-accuracy')}>RSI Accuracy (Trend)</button>
        <button className="calc-button" onClick={() => handleCalculation('rsi-turnover')}>RSI Turnover</button>
        <button className="calc-button" onClick={() => handleCalculation('moving-average')}>Moving Average</button>
      </div>
      {calculation && (
        <div className="calculation-result">
          {/* Results will be displayed here */}
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
      title: 'Update All',
      description: 'Update settings, databases, portfolios, and experiments',
      action: 'update-all'
    },
    {
      title: 'Update Database',
      description: 'Update specific database',
      action: 'update-db'
    },
    {
      title: 'Update Portfolio',
      description: 'Update portfolio data',
      action: 'update-portfolio'
    },
    {
      title: 'Update Experiments',
      description: 'Update shortrate/winrate experiments',
      action: 'update-experiments'
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
    }
  ];

  const renderContent = () => {
    switch (view) {
      case 'update-all':
        return <UpdateAll />;
      case 'update-db':
        return <UpdateDatabase />;
      case 'update-portfolio':
        return <UpdatePortfolio />;
      case 'update-experiments':
        return <UpdateExperiments />;
      case 'show-db':
        return <ShowDatabases />;
      case 'calculations':
        return <Calculations />;
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