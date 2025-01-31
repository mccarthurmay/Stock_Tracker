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
  const [file, setFile] = useState(null);
  const [dbName, setDbName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleFileUpload = (event) => {
    setFile(event.target.files[0]);
    setError(null);
  };

  const handleSubmit = async () => {
    if (!file || !dbName) {
      setError('Please provide both a database name and a file');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      // First, read the file content
      const fileContent = await file.text();
      
      // Send the file content and database name to the server
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
        setFile(null);
        // Reset the file input
        const fileInput = document.querySelector('.file-input');
        if (fileInput) fileInput.value = '';
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
        <label>Upload Ticker File:</label>
        <input
          type="file"
          onChange={handleFileUpload}
          accept=".txt"
          className="file-input"
          disabled={loading}
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
      {error && (
        <div className="error-message text-red-500 mt-2">
          {error}
        </div>
      )}
      <button 
        className="action-button"
        onClick={handleSubmit}
        disabled={loading || !file || !dbName}
      >
        {loading ? 'Creating...' : 'Create Database'}
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
export { DatabaseSelect };
export default DatabaseModule; 