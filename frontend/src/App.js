import React, { useState } from 'react';
import './App.css';
import ConfidenceModule from './components/ConfidenceModule';
import DatabaseModule from './components/DatabaseModule';
import ApplicationsModule from './components/ApplicationsModule';
import SettingsModule from './components/SettingsModule';
import DayTradeModule from './components/DayTradeModule';

const Layout = ({ children }) => (
  <div className="app">
    <nav className="navbar">
      <h1>Stock Tracker</h1>
    </nav>
    <main className="main-content">{children}</main>
  </div>
);

const MainMenu = ({ onNavigate }) => {
  const menuItems = [
    {
      title: 'Day Trading',
      description: 'Run paper trading simulation',
      path: 'daytrading'
    },
    {
      title: '95% Module',
      description: 'Manage 95% confidence interval analysis',
      path: 'confidence'
    },
    {
      title: 'Manage Databases',
      description: 'Database operations and management',
      path: 'databases'
    },
    {
      title: 'Applications',
      description: 'External tools and utilities',
      path: 'applications'
    },
    {
      title: 'Settings',
      description: 'Configure application settings',
      path: 'settings'
    }
  ];

  return (
    <div className="menu-grid">
      {menuItems.map((item) => (
        <button
          key={item.path}
          onClick={() => onNavigate(item.path)}
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
};

const App = () => {
  const [currentView, setCurrentView] = useState('main');

  const handleNavigate = (path) => {
    setCurrentView(path);
  };

  const renderContent = () => {
    switch (currentView) {
      case 'main':
        return <MainMenu onNavigate={handleNavigate} />;
      case 'daytrading':
        return <DayTradeModule />;
      case 'confidence':
        return <ConfidenceModule />;
      case 'databases':
        return <DatabaseModule />;
      case 'applications':
        return <ApplicationsModule />;
      case 'settings':
        return <SettingsModule />;
      default:
        return <MainMenu onNavigate={handleNavigate} />;
    }
  };

  return (
    <Layout>
      {currentView !== 'main' && (
        <button
          onClick={() => setCurrentView('main')}
          className="back-button"
        >
          Back to Main Menu
        </button>
      )}
      {renderContent()}
    </Layout>
  );
};

export default App;