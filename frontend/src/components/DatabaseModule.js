import React, { useState, useEffect } from 'react';
import './DatabaseModule.css';


const DatabaseSelect = ({ value, onChange, className }) => {
  const [databases, setDatabases] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchDatabases = async () => {
      try {
        const response = await fetch('http://localhost:5000/api/databases');
        const data = await response.json();
        if (data.success) {
          setDatabases(data.data);
        } else {
          setError(data.error);
        }
      } catch (err) {
        setError('Failed to fetch databases');
      }
    };

    fetchDatabases();
  }, []);

  if (error) {
    return <div className="text-red-500">Error loading databases: {error}</div>;
  }

  return (
    <select 
      className={className}
      value={value}
      onChange={onChange}
    >
      <option value="">Select Database</option>
      {databases.map(db => (
        <option key={db} value={db}>{db}</option>
      ))}
    </select>
  );
};


const CreateDatabase = () => {
  const [selectedFile, setSelectedFile] = useState('');
  const [dbName, setDbName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [availableFiles, setAvailableFiles] = useState([]);
  const [fileContent, setFileContent] = useState(null);

  // Fetch available files when component mounts
  useEffect(() => {
    fetchAvailableFiles();
  }, []);

  const fetchAvailableFiles = async () => {
    try {
      const response = await fetch('http://localhost:5000/api/ticker-lists');
      const data = await response.json();
      
      if (data.success) {
        setAvailableFiles(data.files);
      } else {
        setError('Failed to fetch available files');
      }
    } catch (err) {
      setError('Failed to fetch available files: ' + err.message);
    }
  };

  const handleFileSelect = async (event) => {
    const filename = event.target.value;
    setSelectedFile(filename);
    setError(null);

    if (filename) {
      try {
        const response = await fetch(`http://localhost:5000/api/ticker-lists/${filename}`);
        const data = await response.json();
        
        if (data.success) {
          setFileContent(data.content);
        } else {
          setError('Failed to load file content');
          setFileContent(null);
        }
      } catch (err) {
        setError('Failed to load file content: ' + err.message);
        setFileContent(null);
      }
    } else {
      setFileContent(null);
    }
  };

  const handleSubmit = async () => {
    if (!fileContent || !dbName) {
      setError('Please provide both a database name and select a file');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`http://localhost:5000/api/database/${dbName}/create`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          tickers: fileContent.split('\n').map(line => line.trim()).filter(line => line),
        }),
      });

      const data = await response.json();
      
      if (data.success) {
        alert('Database created successfully');
        setDbName('');
        setSelectedFile('');
        setFileContent(null);
      } else {
        setError(data.error || 'Failed to create database');
      }
    } catch (err) {
      setError('Failed to create database: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="section">
      <h3>Create Database</h3>
      {error && <div className="error-message">{error}</div>}
      
      <div className="form-group">
        <label>Database Name:</label>
        <input
          type="text"
          value={dbName}
          onChange={(e) => setDbName(e.target.value)}
          className="input-field"
          disabled={loading}
        />
      </div>
      
      <div className="form-group">
        <label>Select Ticker List:</label>
        <select
          value={selectedFile}
          onChange={handleFileSelect}
          className="select-input"
          disabled={loading}
        >
          <option value="">Select a file</option>
          {availableFiles.map(file => (
            <option key={file} value={file}>
              {file}
            </option>
          ))}
        </select>
      </div>
      
      {fileContent && (
        <div className="form-group">
          <label>File Preview:</label>
          <div className="file-preview">
            {fileContent.split('\n').slice(0, 5).map((line, index) => (
              <div key={index}>{line}</div>
            ))}
            {fileContent.split('\n').length > 5 && (
              <div>... and {fileContent.split('\n').length - 5} more lines</div>
            )}
          </div>
        </div>
      )}
      
      <button
        className="action-button"
        onClick={handleSubmit}
        disabled={loading || !fileContent || !dbName}
      >
        {loading ? 'Creating Database...' : 'Create Database'}
      </button>
    </div>
  );
};

const API_BASE_URL = 'http://localhost:5000/api';

const Scraper = () => {
  const [index, setIndex] = useState('');
  const [fileName, setFileName] = useState('');
  const [fileMode, setFileMode] = useState('add');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleScrape = async () => {
    if (!index || !fileName) {
      setError('Please fill in all fields');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/scrape`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          index,
          fileName,
          fileMode
        }),
      });

      const data = await response.json();
      if (!data.success) {
        throw new Error(data.error || 'Failed to scrape index');
      }

      alert('Scraping completed successfully!');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="section">
      <h3>Stock Index Scraper</h3>
      {error && <div className="error-message">{error}</div>}
      <div className="form-group">
        <label>Index:</label>
        <select 
          value={index}
          onChange={(e) => setIndex(e.target.value)}
          className="select-input"
          disabled={loading}
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
          disabled={loading}
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
              disabled={loading}
            />
            Add to file
          </label>
          <label>
            <input
              type="radio"
              value="overwrite"
              checked={fileMode === 'overwrite'}
              onChange={(e) => setFileMode(e.target.value)}
              disabled={loading}
            />
            Overwrite file
          </label>
        </div>
      </div>
      <button 
        className="action-button" 
        onClick={handleScrape}
        disabled={loading}
      >
        {loading ? 'Scraping...' : 'Start Scraping'}
      </button>
    </div>
  );
};

const ModifyDatabase = () => {
  const [selectedDb, setSelectedDb] = useState('');
  const [ticker, setTicker] = useState('');

  const handleAddTicker = async () => {
    if (!selectedDb || !ticker) return;

    try {
      const response = await fetch(`http://localhost:5000/api/database/${selectedDb}/add`, {
        method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ ticker }),
    });
    const data = await response.json();
    if (data.success) {
      setTicker('');
      alert('Ticker added successfully');
    } else {
      alert(data.error)
    }
    



  } catch (err) {
    alert('Failed to add ticker');
  }
};


  const handleRemoveTicker = () => {
    if (!selectedDb || !ticker) return;

    try {
      const response = fetch(`http://localhost:5000/api/database/${selectedDb}/remove`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ ticker }),
      });
      const data = response.json();
      if (data.success) {
        setTicker('');
        alert('Ticker removed successfully');
      } else {
        alert(data.error);
      }
    } catch (err) {
      alert('Failed to remove ticker');
    }
  };

  return (
    <div className="section">
      <h3 className="text-xl font-bold mb-4">Modify Database</h3>
      <DatabaseSelect 
        className="select-input w-full p-2 mb-4 border rounded"
        value={selectedDb}
        onChange={(e) => setSelectedDb(e.target.value)}
      />
      <div className="form-group">
        <input
          type="text"
          placeholder="Enter ticker symbol"
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          className="input-field w-full p-2 mb-4 border rounded"
        />
        <div className="button-group flex gap-2">
          <button 
            className="action-button bg-blue-500 text-white px-4 py-2 rounded"
            onClick={handleAddTicker}
          >
            Add Ticker
          </button>
          <button 
            className="action-button remove bg-red-500 text-white px-4 py-2 rounded"
            onClick={handleRemoveTicker}
          >
            Remove Ticker
          </button>
        </div>
      </div>
    </div>
  );
};


const ResetDatabase = () => {
  const [selectedDb, setSelectedDb] = useState('');

  const handleReset = async () => {
    if (!selectedDb) return;
    
    if (window.confirm(`Are you sure you want to reset database "${selectedDb}"?`)) {
      try {
        const response = await fetch(`http://localhost:5000/api/database/${selectedDb}/reset`, {
          method: 'POST',
        });
        const data = await response.json();
        if (data.success) {
          setSelectedDb('');
          alert('Database reset successfully');
        } else {
          alert(data.error);
        }
      } catch (err) {
        alert('Failed to reset database');
      }
    }
  };

  return (
    <div className="section">
      <h3 className="text-xl font-bold mb-4">Reset Database</h3>
      <DatabaseSelect 
        className="select-input w-full p-2 mb-4 border rounded"
        value={selectedDb}
        onChange={(e) => setSelectedDb(e.target.value)}
      />
      <button 
        className="action-button remove bg-red-500 text-white px-4 py-2 rounded"
        onClick={handleReset}
      >
        Reset Database
      </button>
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
    },
    {
      title: 'Stock Index Scraper',
      description: 'Scrape stock symbols from major indices into txt',
      action: 'scraper'
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
      case 'scraper':
        return <Scraper />;
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
export { DatabaseSelect };
export default DatabaseModule; 