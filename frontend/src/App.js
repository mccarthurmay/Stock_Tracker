import React from 'react';
import './App.css';
import ConfidenceModule from './components/ConfidenceModule';

const App = () => (
  <div className="app">
    <nav className="navbar">
      <h1>Stock Tracker</h1>
    </nav>
    <main className="main-content">
      <ConfidenceModule />
    </main>
  </div>
);

export default App;
