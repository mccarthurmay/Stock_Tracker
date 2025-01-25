import React, { useState } from 'react';
import './SettingsModule.css';

const StartupSettings = () => {
  const [databases, setDatabases] = useState([]);
  const [selectedDb, setSelectedDb] = useState('');
  const [updateOnStartup, setUpdateOnStartup] = useState(false);

  const handleSave = () => {
    // Implementation here
  };

  return (
    <div className="section">
      <h3>Startup Settings</h3>
      <div className="form-group">
        <label>Select Database:</label>
        <select 
          value={selectedDb}
          onChange={(e) => setSelectedDb(e.target.value)}
          className="select-input"
        >
          <option value="">Select Database</option>
          {databases.map(db => (
            <option key={db} value={db}>{db}</option>
          ))}
        </select>
      </div>
      <div className="form-group">
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={updateOnStartup}
            onChange={(e) => setUpdateOnStartup(e.target.checked)}
          />
          Update on Startup
        </label>
      </div>
      <button className="action-button" onClick={handleSave}>Save Settings</button>
    </div>
  );
};

const CacheManagement = () => {
  const [cacheInfo, setCacheInfo] = useState(null);

  const handleCheckCache = () => {
    // Implementation here
  };

  const handleClearCache = () => {
    // Implementation here
  };

  return (
    <div className="section">
      <h3>Cache Management</h3>
      <div className="button-group">
        <button className="action-button" onClick={handleCheckCache}>
          Check Cache
        </button>
        <button className="action-button remove" onClick={handleClearCache}>
          Clear Cache
        </button>
      </div>
      {cacheInfo && (
        <div className="cache-info">
          <h4>Cache Information:</h4>
          <pre>{JSON.stringify(cacheInfo, null, 2)}</pre>
        </div>
      )}
    </div>
  );
};

const SettingsModule = () => {
  const [view, setView] = useState('main');

  const menuItems = [
    {
      title: 'Startup Settings',
      description: 'Configure database update behavior on startup',
      action: 'startup'
    },
    {
      title: 'Cache Management',
      description: 'View and clear application cache',
      action: 'cache'
    }
  ];

  const renderContent = () => {
    switch (view) {
      case 'startup':
        return <StartupSettings />;
      case 'cache':
        return <CacheManagement />;
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
      <h2 className="module-title">Settings</h2>
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

export default SettingsModule;