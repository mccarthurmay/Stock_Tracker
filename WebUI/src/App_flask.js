import React, { useState, useEffect } from 'react';

function App() {
  const [result, setResult] = useState('');
  
  // Function to fetch the result from Python script 1
  const fetchScript1Result = async () => {
    const response = await fetch('http://localhost:5000/run-script1');
    const data = await response.json();
    setResult(data.result);  // Update the state with the result from Python
  };


  return (
    <div>
      <h1>Python Output:</h1>
      <div>
        <button onClick={fetchScript1Result}>Run Script 1</button>
      </div>
      <div>
        <h2>Result:</h2>
        <pre>{result}</pre>
      </div>
    </div>
  );
}

export default App;
