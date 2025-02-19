import React, { useState, useEffect } from 'react';
import { ReferenceLine, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Scatter } from 'recharts';

const CombinedAnalysisChart = ({ ticker }) => {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showRSI, setShowRSI] = useState(true);
  const [showShortMA, setShowShortMA] = useState(true);
  const [showLongMA, setShowLongMA] = useState(true);

  // Zoom state for start and end dates
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  // Bull markers for RSI oversold/overbought
  const bullMarkers = data.filter(item => item.bull_run).map(item => ({
    x: item.timestamp, // Use the timestamp for X axis
    y: item.rsi,       // Use RSI for Y axis
  }));

  useEffect(() => {
    const fetchData = async () => {
      if (!ticker) return;

      try {
        const response = await fetch(`http://localhost:5000/api/analysis/${ticker}`);
        const result = await response.json();

        if (result.success) {
          const formattedData = result.data.map(item => ({
            ...item,
            date: new Date(item.timestamp).toLocaleDateString(),
            timestamp: new Date(item.timestamp), // Store the original timestamp for filtering
          }));
          setData(formattedData);
        } else {
          throw new Error(result.error || 'Failed to fetch data');
        }
      } catch (err) {
        console.error("Chart error:", err);
        setError('Failed to load data: ' + err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [ticker]);

  // Filter data based on zoom range (startDate, endDate)
  const filteredData = data.filter(item => {
    if (!startDate && !endDate) return true;
    const itemDate = new Date(item.timestamp);
    if (startDate && itemDate < new Date(startDate)) return false;
    if (endDate && itemDate > new Date(endDate)) return false;
    return true;
  });

  if (loading) return <div className="p-4">Loading...</div>;
  if (error) return <div className="p-4 text-red-600">Error: {error}</div>;
  if (!filteredData.length) return <div className="p-4">No data available for the selected date range</div>;

  return (
    <div className="mt-5 p-5 bg-white rounded-lg shadow-md overflow-hidden">
      <div className="mb-4">
        <label>
          <input
            type="checkbox"
            checked={showRSI}
            onChange={() => setShowRSI(!showRSI)}
          />
          Show RSI
        </label>
        <label className="ml-4">
          <input
            type="checkbox"
            checked={showShortMA}
            onChange={() => setShowShortMA(!showShortMA)}
          />
          Show Short MA
        </label>
        <label className="ml-4">
          <input
            type="checkbox"
            checked={showLongMA}
            onChange={() => setShowLongMA(!showLongMA)}
          />
          Show Long MA
        </label>
      </div>

      <div className="mb-4">
        <label>Start Date: </label>
        <input
          type="date"
          value={startDate}
          onChange={(e) => setStartDate(e.target.value)}
        />
        <label className="ml-4">End Date: </label>
        <input
          type="date"
          value={endDate}
          onChange={(e) => setEndDate(e.target.value)}
        />
      </div>

      <ResponsiveContainer width="100%" height={400}>
        <LineChart
          data={filteredData}
          margin={{ top: 5, right: 30, left: 20, bottom: 25 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
          
          <XAxis 
            dataKey="date"
            angle={-45}
            textAnchor="end"
            height={60}
          />
          
          <YAxis 
            yAxisId="left"
            domain={([dataMin, dataMax]) => [dataMin - 5, dataMax + 5]}
            label={{ value: 'Price', angle: -90, position: 'insideLeft' }}
          />
          
          <YAxis 
            yAxisId="right"
            orientation="right"
            domain={[0, 100]}
            label={{ value: 'RSI', angle: 90, position: 'insideRight' }}
          />
          
          <ReferenceLine 
            y={30} 
            yAxisId="right" 
            stroke="red" 
            strokeDasharray="3 3" 
          />
          <ReferenceLine 
            y={70} 
            yAxisId="right" 
            stroke="green" 
            strokeDasharray="3 3" 
          />

          <Tooltip />
          <Legend verticalAlign="top" height={36} /> 

          {showShortMA && (
            <Line 
                yAxisId="left"
                type="monotone"
                dataKey="ma_short"
                stroke="#82ca9d"
                name="Short MA"
                dot={false}
            />
          )}
          
          {showLongMA && (
            <Line 
                yAxisId="left"
                type="monotone"
                dataKey="ma_long"
                stroke="#ffc658"
                name="Long MA"
                dot={false}
            />
          )}
          
          {showRSI && (
            <Line 
                yAxisId="right"
                type="monotone"
                dataKey="rsi"
                stroke="#8884d8"
                strokeOpacity={0.8}
                name="RSI"
                dot={false}
            />
          )}
          
          <Line 
            yAxisId="left"
            type="monotone"
            dataKey="price"
            stroke="#ff7300"
            name="Price"
            dot={false}
          />

          {/* Bull markers (RSI oversold or overbought) */}
          {bullMarkers.length > 0 && (
            <Scatter 
              yAxisId="right"
              data={bullMarkers}
              line={{ stroke: 'red', strokeWidth: 3 }}
              fill="red"
              name="Bull Markers"
              shape="cross"
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
};

export default CombinedAnalysisChart;
