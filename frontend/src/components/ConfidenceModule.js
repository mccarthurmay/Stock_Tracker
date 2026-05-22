import './ConfidenceModule.css';
import React, { useState, useEffect, useCallback, useRef } from 'react';

const DatabaseSelect = ({ value, onChange, className }) => {
  const [databases, setDatabases] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch('http://localhost:5000/api/databases')
      .then(r => r.json())
      .then(data => {
        if (data.success) setDatabases(data.data);
        else setError(data.error);
      })
      .catch(() => setError('Failed to fetch databases'));
  }, []);

  if (error) return <div style={{ color: '#f87171' }}>Error loading databases: {error}</div>;

  return (
    <select className={className} value={value} onChange={onChange}>
      <option value="">Select Database</option>
      {databases.map(db => <option key={db} value={db}>{db}</option>)}
    </select>
  );
};

const UpdateDatabase = () => {
  const [selectedDb, setSelectedDb] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [status, setStatus] = useState(null);
  const [timeRemaining, setTimeRemaining] = useState(null);
  const [progress, setProgress] = useState(0);
  const totalTimeRef = useRef(null);

  useEffect(() => {
    if (!loading || !timeRemaining) return;
    const timer = setInterval(() => {
      setTimeRemaining(prev => {
        if (prev <= 0) { clearInterval(timer); return 0; }
        const next = prev - 1;
        setProgress(totalTimeRef.current ? (1 - next / totalTimeRef.current) * 100 : 0);
        return next;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [loading, timeRemaining]);

  const formatTime = (s) => {
    if (s === null) return '--:--';
    return `${Math.floor(s / 60)}:${Math.floor(s % 60).toString().padStart(2, '0')}`;
  };

  const handleUpdate = async () => {
    if (!selectedDb) { setError('Please select a database'); return; }
    setError(null);
    setStatus('Getting estimate...');

    try {
      const res = await fetch(`http://localhost:5000/api/database/${selectedDb}/estimate`);
      const data = await res.json();
      if (!data.success) throw new Error(data.error || 'Failed to get estimate');

      const estimated = data.estimated_time;
      if (!window.confirm(`Estimated time: ${formatTime(estimated)}. Continue?`)) {
        setStatus(null);
        return;
      }

      totalTimeRef.current = estimated;
      setLoading(true);
      setTimeRemaining(estimated);
      setProgress(0);
      setStatus('Updating...');

      const updateRes = await fetch(`http://localhost:5000/api/database/${selectedDb}/update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const updateData = await updateRes.json();
      if (!updateData.success) throw new Error(updateData.error || 'Update failed');
      setStatus('Updated successfully');
    } catch (err) {
      setError(err.message || 'Failed to connect to server');
    } finally {
      setLoading(false);
      setTimeRemaining(null);
      setProgress(0);
    }
  };

  return (
    <div className="section">
      <h3 className="section-title">Update Database</h3>
      <p style={{ color: '#a0aec0', marginBottom: '1rem', fontSize: '0.875rem' }}>API limit: 150 calls/min</p>
      <DatabaseSelect
        className="select-input"
        value={selectedDb}
        onChange={(e) => { setSelectedDb(e.target.value); setError(null); setStatus(null); }}
      />
      <button
        className="action-button"
        style={{ marginTop: '1rem', display: 'block' }}
        onClick={handleUpdate}
        disabled={loading || !selectedDb}
      >
        {loading ? 'Updating...' : 'Update Database'}
      </button>

      {loading && timeRemaining !== null && (
        <div style={{ marginTop: '1rem' }}>
          <p style={{ color: '#a0aec0' }}>Time remaining: {formatTime(timeRemaining)}</p>
          <div style={{ background: '#1a1d23', borderRadius: '4px', height: '8px', marginTop: '6px' }}>
            <div style={{
              background: '#4CAF50', height: '8px', borderRadius: '4px',
              width: `${Math.min(100, progress)}%`, transition: 'width 1s linear'
            }} />
          </div>
        </div>
      )}

      {error && <p style={{ color: '#f87171', marginTop: '0.5rem' }}>{error}</p>}
      {status && !error && <p style={{ color: '#4CAF50', marginTop: '0.5rem' }}>{status}</p>}
    </div>
  );
};

const SORT_OPTIONS = [
  { value: 'normal', label: 'Below 95% CI' },
  { value: 'rsi',    label: 'RSI Value' },
  { value: 'bm',     label: 'Book-to-Market' },
  { value: 'op',     label: 'Profitability' },
  { value: 'inv',    label: 'Investment (low→high)' },
];

const thStyle = {
  padding: '0.6rem 1rem', textAlign: 'left',
  color: '#a0aec0', fontWeight: 600, borderBottom: '1px solid #2e3443',
};
const thTip = { cursor: 'help' };
const tdStyle = { padding: '0.6rem 1rem', borderBottom: '1px solid #2e3443' };

const pct = (v) => `${(v * 100).toFixed(1)}%`;
const Null = () => <span style={{ color: '#4a5568' }}>—</span>;

const ShowDatabases = () => {
  const [selectedDb, setSelectedDb] = useState('');
  const [sortChoice, setSortChoice] = useState('normal');
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    if (!selectedDb) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`http://localhost:5000/api/database/${selectedDb}/load?sort=${sortChoice}`);
      const result = await res.json();
      if (result.success) setData(result.data);
      else setError(result.error || 'Failed to load database');
    } catch {
      setError('Failed to connect to server');
    } finally {
      setLoading(false);
    }
  }, [selectedDb, sortChoice]);

  useEffect(() => { fetchData(); }, [fetchData]);

  return (
    <div className="section">
      <h3 className="section-title">Show Database</h3>
      <div style={{ display: 'flex', gap: '1rem', marginBottom: '1rem' }}>
        <DatabaseSelect
          className="select-input"
          value={selectedDb}
          onChange={(e) => setSelectedDb(e.target.value)}
        />
        <select
          className="select-input"
          value={sortChoice}
          onChange={(e) => setSortChoice(e.target.value)}
        >
          {SORT_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>Sort by {opt.label}</option>
          ))}
        </select>
      </div>

      {loading && <p style={{ color: '#a0aec0' }}>Loading...</p>}
      {error && <p style={{ color: '#f87171' }}>Error: {error}</p>}

      {data.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: '#1a1d23' }}>
                <th style={thStyle}>Ticker</th>
                <th style={thStyle}>% Below 95% CI</th>
                <th style={thStyle}>RSI</th>
                <th style={{...thStyle, ...thTip}} title="Book-to-Market (1/P/B) — higher means cheaper relative to book value">B/M ↑</th>
                <th style={{...thStyle, ...thTip}} title="Operating Profitability (Op. Income / Book Equity) — higher is better">Profitability ↑</th>
                <th style={{...thStyle, ...thTip}} title="Investment / Asset Growth YoY — lower means more conservative (Fama-French CMA)">Investment ↓</th>
              </tr>
            </thead>
            <tbody>
              {data.map((item, i) => (
                <tr key={i} style={{ background: i % 2 === 0 ? '#232730' : '#1e222a' }}>
                  <td style={tdStyle}>{item.Ticker}</td>
                  <td style={tdStyle}>{item['% Below 95% CI']}%</td>
                  <td style={tdStyle}>{item.RSI}</td>
                  <td style={tdStyle}>{item.BM != null ? item.BM.toFixed(3) : <Null />}</td>
                  <td style={tdStyle}>{item.OP != null ? pct(item.OP) : <Null />}</td>
                  <td style={tdStyle}>{item.INV != null ? pct(item.INV) : <Null />}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

const parseTickers = (content) =>
  content
    .split(/[\n,;\t]+/)
    .map(t => t.trim().toUpperCase().replace(/[^A-Z.]/g, ''))
    .filter(t => t.length > 0);

const CreateDatabase = () => {
  const [files, setFiles] = useState([]);
  const [selectedFile, setSelectedFile] = useState('');
  const [tickers, setTickers] = useState([]);
  const [dbName, setDbName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [status, setStatus] = useState(null);

  useEffect(() => {
    fetch('http://localhost:5000/api/ticker-lists')
      .then(r => r.json())
      .then(data => { if (data.success) setFiles(data.files); })
      .catch(() => setError('Failed to fetch ticker lists'));
  }, []);

  const handleFileSelect = async (filename) => {
    setSelectedFile(filename);
    setTickers([]);
    setError(null);
    if (!filename) return;
    try {
      const res = await fetch(`http://localhost:5000/api/ticker-lists/${filename}`);
      const data = await res.json();
      if (data.success) setTickers(parseTickers(data.content));
      else setError(data.error || 'Failed to read file');
    } catch {
      setError('Failed to load ticker list');
    }
  };

  const handleCreate = async () => {
    const name = dbName.trim();
    if (!name || tickers.length === 0) return;
    setLoading(true);
    setError(null);
    setStatus(`Creating "${name}" with ${tickers.length} tickers…`);
    try {
      const res = await fetch(`http://localhost:5000/api/database/${name}/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tickers }),
      });
      const data = await res.json();
      if (data.success) {
        setStatus(`"${name}" created with ${tickers.length} tickers.`);
        setDbName('');
        setSelectedFile('');
        setTickers([]);
      } else {
        setError(data.error || 'Failed to create database');
        setStatus(null);
      }
    } catch {
      setError('Failed to connect to server');
      setStatus(null);
    } finally {
      setLoading(false);
    }
  };

  const estMinutes = Math.ceil(tickers.length * 4 / 150);

  return (
    <div className="section">
      <h3 className="section-title">Create Database</h3>

      <div style={{ marginBottom: '1rem' }}>
        <label style={labelStyle}>Ticker List File</label>
        <select
          className="select-input"
          value={selectedFile}
          onChange={e => handleFileSelect(e.target.value)}
        >
          <option value="">Select a file…</option>
          {files.map(f => <option key={f} value={f}>{f}</option>)}
        </select>
      </div>

      {tickers.length > 0 && (
        <div style={previewBox}>
          <p style={{ color: '#a0aec0', fontSize: '0.875rem', marginBottom: '0.25rem' }}>
            <strong style={{ color: 'white' }}>{tickers.length}</strong> tickers — {tickers.slice(0, 12).join(', ')}{tickers.length > 12 ? ` … +${tickers.length - 12} more` : ''}
          </p>
          <p style={{ color: '#718096', fontSize: '0.8rem' }}>
            Estimated time: ~{estMinutes} min
          </p>
        </div>
      )}

      <div style={{ marginBottom: '1rem' }}>
        <label style={labelStyle}>Database Name</label>
        <input
          type="text"
          placeholder="e.g. sp500"
          value={dbName}
          onChange={e => setDbName(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_'))}
          style={inputStyle}
        />
      </div>

      <button
        className="action-button"
        onClick={handleCreate}
        disabled={loading || !selectedFile || !dbName.trim() || tickers.length === 0}
      >
        {loading ? 'Creating…' : 'Create Database'}
      </button>

      {loading && (
        <p style={{ color: '#a0aec0', marginTop: '0.75rem', fontSize: '0.875rem' }}>
          Processing {tickers.length} tickers — this may take ~{estMinutes} min. Don't close the tab.
        </p>
      )}
      {error  && <p style={{ color: '#f87171', marginTop: '0.5rem' }}>{error}</p>}
      {status && !error && <p style={{ color: '#4CAF50', marginTop: '0.5rem' }}>{status}</p>}
    </div>
  );
};

const labelStyle = { display: 'block', color: '#a0aec0', marginBottom: '0.4rem', fontSize: '0.875rem' };
const inputStyle = {
  background: '#1a1d23', border: '1px solid #2e3443', color: 'white',
  padding: '0.6rem 0.9rem', borderRadius: '0.5rem', maxWidth: '300px', width: '100%',
};
const previewBox = {
  marginBottom: '1rem', padding: '0.75rem',
  background: '#1a1d23', borderRadius: '0.5rem', border: '1px solid #2e3443',
};

const SearchTicker = () => {
  const [input, setInput] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const search = async (ticker) => {
    if (!ticker) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`http://localhost:5000/api/ticker/${ticker}`);
      const data = await res.json();
      if (data.success) {
        setResults(prev => {
          const without = prev.filter(r => r.Ticker !== data.data.Ticker);
          return [data.data, ...without];
        });
      } else {
        setError(data.error || 'Not found');
      }
    } catch {
      setError('Failed to connect to server');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    const ticker = input.trim().toUpperCase();
    if (ticker) { search(ticker); setInput(''); }
  };

  const removeResult = (ticker) =>
    setResults(prev => prev.filter(r => r.Ticker !== ticker));

  return (
    <div className="section">
      <h3 className="section-title">Search Ticker</h3>

      <form onSubmit={handleSubmit} style={{ display: 'flex', gap: '0.75rem', marginBottom: '1rem' }}>
        <input
          type="text"
          placeholder="e.g. AAPL"
          value={input}
          onChange={e => setInput(e.target.value.toUpperCase())}
          style={{
            background: '#1a1d23', border: '1px solid #2e3443', color: 'white',
            padding: '0.6rem 0.9rem', borderRadius: '0.5rem', fontSize: '0.95rem',
            flex: '0 0 160px',
          }}
        />
        <button type="submit" className="action-button" disabled={loading || !input.trim()}>
          {loading ? 'Loading…' : 'Search'}
        </button>
      </form>

      {error && <p style={{ color: '#f87171', marginBottom: '0.5rem' }}>{error}</p>}

      {results.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: '#1a1d23' }}>
                <th style={thStyle}>Ticker</th>
                <th style={thStyle}>% Below 95% CI</th>
                <th style={thStyle}>RSI</th>
                <th style={{...thStyle, ...thTip}} title="Book-to-Market (1/P/B) — higher means cheaper relative to book value">B/M ↑</th>
                <th style={{...thStyle, ...thTip}} title="Operating Profitability (Op. Income / Book Equity) — higher is better">Profitability ↑</th>
                <th style={{...thStyle, ...thTip}} title="Investment / Asset Growth YoY — lower means more conservative (Fama-French CMA)">Investment ↓</th>
                <th style={thStyle}></th>
              </tr>
            </thead>
            <tbody>
              {results.map((item, i) => (
                <tr key={item.Ticker} style={{ background: i % 2 === 0 ? '#232730' : '#1e222a' }}>
                  <td style={{...tdStyle, fontWeight: 600}}>{item.Ticker}</td>
                  <td style={tdStyle}>{item['% Below 95% CI'] != null ? `${item['% Below 95% CI']}%` : <Null />}</td>
                  <td style={tdStyle}>{item.RSI ?? <Null />}</td>
                  <td style={tdStyle}>{item.BM  != null ? item.BM.toFixed(3)  : <Null />}</td>
                  <td style={tdStyle}>{item.OP  != null ? pct(item.OP)        : <Null />}</td>
                  <td style={tdStyle}>{item.INV != null ? pct(item.INV)       : <Null />}</td>
                  <td style={tdStyle}>
                    <button
                      onClick={() => removeResult(item.Ticker)}
                      style={{ background: 'none', border: 'none', color: '#718096', cursor: 'pointer', fontSize: '1rem' }}
                      title="Remove"
                    >✕</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

const MENU_ITEMS = [
  { title: 'Search Ticker',   description: 'Look up RSI, CI, and fundamentals for any ticker', action: 'search' },
  { title: 'Create Database', description: 'Build a new database from a ticker list file',     action: 'create-db' },
  { title: 'Update Database', description: 'Fetch latest data for a database',                 action: 'update-db' },
  { title: 'Show Database',   description: 'View RSI and confidence interval data',             action: 'show-db' },
];

const ConfidenceModule = () => {
  const [view, setView] = useState('main');

  const renderContent = () => {
    switch (view) {
      case 'search':    return <SearchTicker />;
      case 'create-db': return <CreateDatabase />;
      case 'update-db': return <UpdateDatabase />;
      case 'show-db':   return <ShowDatabases />;
      default:
        return (
          <div className="menu-grid">
            {MENU_ITEMS.map(item => (
              <button key={item.action} onClick={() => setView(item.action)} className="menu-button">
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
      {view !== 'main' && (
        <button onClick={() => setView('main')} className="back-button">Back</button>
      )}
      {renderContent()}
    </div>
  );
};

export default ConfidenceModule;
