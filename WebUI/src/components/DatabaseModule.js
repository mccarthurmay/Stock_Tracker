import React, { useState } from 'react';
import './DatabaseModule.css';

const CreateDatabase = () => {
    // eslint-disable-next-line
  const [file, setFile] = useState(null);
  const [dbName, setDbName] = useState('');

  const handleFileUpload = (event) => {
    setFile(event.target.files[0]);
  };

  const handleSubmit = () => {
    // Implementation here
  };

  return (
    <div className="section">
      <h3>Create Database</h3>
      <div className="form-group">
        <label>Database Name:</label>
        <input
          type="text"
          value={dbName}
          onChange={(e) => setDbName(e.target.value)}
          className="input-field"
        />
      </div>
      <div className="form-group">
        <label>Upload Ticker File:</label>
        <input
          type="file"
          onChange={handleFileUpload}
          accept=".txt"
          className="file-input"
        />
      </div>
      <div className="file-format">
        <h4>File Format Guide:</h4>
        <pre>
            {`AAPL
        MSFT
        GOOGL
        ...`}
        </pre>
        <p>One ticker symbol per line</p>
      </div>
      <button className="action-button" onClick={handleSubmit}>Create Database</button>
    </div>
  );
};

const ModifyDatabase = () => {
  const [selectedDb, setSelectedDb] = useState('');
  const [ticker, setTicker] = useState('');

  const handleAddTicker = () => {
    // Implementation here
  };

  const handleRemoveTicker = () => {
    // Implementation here
  };

  return (
    <div className="section">
      <h3>Modify Database</h3>
      <select 
        className="select-input"
        value={selectedDb}
        onChange={(e) => setSelectedDb(e.target.value)}
      >
        <option value="">Select Database</option>
      </select>
      <div className="form-group">
        <input
          type="text"
          placeholder="Enter ticker symbol"
          value={ticker}
          onChange={(e) => setTicker(e.target.value)}
          className="input-field"
        />
        <div className="button-group">
          <button className="action-button" onClick={handleAddTicker}>Add Ticker</button>
          <button className="action-button remove" onClick={handleRemoveTicker}>Remove Ticker</button>
        </div>
      </div>
    </div>
  );
};

const ResetDatabase = () => {
  const [selectedDb, setSelectedDb] = useState('');

  const handleReset = () => {
    // Implementation here
  };

  return (
    <div className="section">
      <h3>Reset Database</h3>
      <select 
        className="select-input"
        value={selectedDb}
        onChange={(e) => setSelectedDb(e.target.value)}
      >
        <option value="">Select Database</option>
      </select>
      <button className="action-button remove" onClick={handleReset}>Reset Database</button>
    </div>
  );
};

const DatabaseModule = () => {
  const [view, setView] = useState('main');

  const menuItems = [
    {
      title: 'Create Database',
      description: 'Create new database from file',
      action: 'create'
    },
    {
      title: 'Add/Remove Ticker',
      description: 'Modify database contents',
      action: 'modify'
    },
    {
      title: 'Reset Database',
      description: 'Clear database contents',
      action: 'reset'
    }
  ];

  const renderContent = () => {
    switch (view) {
      case 'create':
        return <CreateDatabase />;
      case 'modify':
        return <ModifyDatabase />;
      case 'reset':
        return <ResetDatabase />;
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
      <h2 className="module-title">Database Management</h2>
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

export default DatabaseModule;