import React, { useState, useEffect } from 'react';
import { ReferenceLine, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

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
            timestamp: new Date(item.timestamp),
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

  // Filter data based on zoom range
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
      <div className="mb-4 space-x-4">
        <label className="inline-flex items-center">
          <input
            type="checkbox"
            checked={showRSI}
            onChange={() => setShowRSI(!showRSI)}
            className="mr-2"
          />
          Show RSI
        </label>
        <label className="inline-flex items-center">
          <input
            type="checkbox"
            checked={showShortMA}
            onChange={() => setShowShortMA(!showShortMA)}
            className="mr-2"
          />
          Show Short MA
        </label>
        <label className="inline-flex items-center">
          <input
            type="checkbox"
            checked={showLongMA}
            onChange={() => setShowLongMA(!showLongMA)}
            className="mr-2"
          />
          Show Long MA
        </label>
      </div>

      <div className="mb-4 space-x-4">
        <label className="inline-flex items-center">
          Start Date:
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="ml-2"
          />
        </label>
        <label className="inline-flex items-center">
          End Date:
          <input
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="ml-2"
          />
        </label>
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
          
          <ReferenceLine y={30} yAxisId="right" stroke="#ef4444" strokeDasharray="3 3" />
          <ReferenceLine y={70} yAxisId="right" stroke="#22c55e" strokeDasharray="3 3" />

          <Tooltip 
            formatter={(value, name) => [value?.toFixed(2) || value, name]}
          />
          <Legend verticalAlign="top" height={36} />

          <Line 
            yAxisId="left"
            type="monotone"
            dataKey="price"
            stroke="#f97316"
            name="Price"
            dot={false}
          />
          
          {showShortMA && (
            <Line 
              yAxisId="left"
              type="monotone"
              dataKey="ma_short"
              stroke="#22c55e"
              name="Short MA"
              dot={false}
            />
          )}
          
          {showLongMA && (
            <Line 
              yAxisId="left"
              type="monotone"
              dataKey="ma_long"
              stroke="#eab308"
              name="Long MA"
              dot={false}
            />
          )}
          
          {showRSI && (
            <Line 
              yAxisId="right"
              type="monotone"
              dataKey="rsi"
              stroke="#6366f1"
              name="RSI"
              dot={false}
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
};

export default CombinedAnalysisChart;