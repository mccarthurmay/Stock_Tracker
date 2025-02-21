import React from 'react';
import CombinedAnalysisChart from './CombinedAnalysisChart';

const ChartPopup = ({ ticker }) => {
  return (
    <div className="p-4 min-h-screen bg-white">
      <h2 className="text-2xl font-bold mb-4">{ticker} Analysis</h2>
      <CombinedAnalysisChart ticker={ticker} />
    </div>
  );
};

export default ChartPopup;