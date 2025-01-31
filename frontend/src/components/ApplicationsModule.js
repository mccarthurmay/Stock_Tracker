import React, { useState } from 'react';
import './ApplicationsModule.css';

const Scraper = () => {
  const [index, setIndex] = useState('');
  const [fileName, setFileName] = useState('');
  const [fileMode, setFileMode] = useState('add');

  const handleScrape = () => {
    // Implementation here
  };

  return (
    <div className="section">
      <h3>Stock Index Scraper</h3>
      <div className="form-group">
        <label>Index:</label>
        <select 
          value={index}
          onChange={(e) => setIndex(e.target.value)}
          className="select-input"
        >
          <option value="">Select Index</option>
          <option value="dowjones">Dow Jones</option>
          <option value="sp500">S&P 500</option>
          <option value="nasdaq100">NASDAQ 100</option>
        </select>
      </div>
      <div className="form-group">
        <label>Output File Name:</label>
        <input
          type="text"
          value={fileName}
          onChange={(e) => setFileName(e.target.value)}
          className="input-field"
        />
      </div>
      <div className="form-group">
        <label>File Mode:</label>
        <div className="radio-group">
          <label>
            <input
              type="radio"
              value="add"
              checked={fileMode === 'add'}
              onChange={(e) => setFileMode(e.target.value)}
            />
            Add to file
          </label>
          <label>
            <input
              type="radio"
              value="overwrite"
              checked={fileMode === 'overwrite'}
              onChange={(e) => setFileMode(e.target.value)}
            />
            Overwrite file
          </label>
        </div>
      </div>
      <button className="action-button" onClick={handleScrape}>Start Scraping</button>
    </div>
  );
};

const Converter = () => {
  const [file, setFile] = useState(null);
  const [converting, setConverting] = useState(false);

  const handleFileSelect = (event) => {
    setFile(event.target.files[0]);
  };

  const handleConvert = () => {
    setConverting(true);
    // Implementation here
  };

  return (
    <div className="section">
      <h3>Python to EXE Converter</h3>
      <div className="form-group">
        <label>Select Python File:</label>
        <input
          type="file"
          onChange={handleFileSelect}
          accept=".py"
          className="file-input"
        />
      </div>
      <button 
        className="action-button" 
        onClick={handleConvert}
        disabled={!file || converting}
      >
        {converting ? 'Converting...' : 'Convert to EXE'}
      </button>
    </div>
  );
};

const ApplicationsModule = () => {
  const [view, setView] = useState('main');

  const menuItems = [
    {
      title: 'Stock Index Scraper',
      description: 'Scrape stock symbols from major indices',
      action: 'scraper'
    },
    {
      title: 'Python to EXE Converter',
      description: 'Convert Python scripts to executable files',
      action: 'converter'
    }
  ];

  const renderContent = () => {
    switch (view) {
      case 'scraper':
        return <Scraper />;
      case 'converter':
        return <Converter />;
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
      <h2 className="module-title">Applications</h2>
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

export default ApplicationsModule;