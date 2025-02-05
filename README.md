# Stock Market Analysis Tool

A comprehensive tool for analyzing stock market data using various technical indicators, including RSI analysis, confidence intervals, and day trading capabilities.

## Features

- **95% Confidence Interval Analysis**: Track and analyze stock performance using statistical confidence intervals
- **RSI Analysis**: Calculate and monitor Relative Strength Index with accuracy metrics
- **Database Management**: Create and maintain stock databases with flexible ticker management
- **Day Trading Module**: Paper trading simulation capabilities
- **Stock Index Scraper**: Automated scraping of major market indices (Dow Jones, S&P 500, NASDAQ 100)
- **Moving Average Analysis**: Track market trends using various moving average calculations
- **Smart Caching**: Efficient data management with automatic cache optimization

## Prerequisites

- Python 3.8 or higher
- Node.js 14 or higher
- Chrome/Chromium browser (for web scraping functionality)

## Dependencies

### Python Packages
All Python dependencies are specified in `requirements.txt` and include:
- alpaca-trade-api (for market data)
- Flask & Flask-CORS (backend server)
- pandas, numpy, scipy (data analysis)
- matplotlib (visualization)
- selenium (web scraping)
- scikit-learn (machine learning components)
- Additional supporting packages

### Node.js Packages
Frontend dependencies are managed through `package.json` and include:
- React (UI framework)
- Tailwind CSS (styling)
- Additional development dependencies

## Installation

1. Clone the repository:
```bash
git clone [repository-url]
cd Stock_Analysis
```

2. Configure Alpaca API credentials:
Create or modify `config.py`:
```python
import os
os.environ['ALPACA_KEY'] = "your_api_key"
os.environ['ALPACA_SECRET'] = "your_api_secret"
```

## Starting the Application

### Windows Users (start.bat)
Simply run `start.bat` in the root directory. The script will:
1. Check for Python and Node.js installations
2. Create a Python virtual environment if it doesn't exist
3. Activate the virtual environment
4. Install/update Python requirements automatically
5. Install frontend dependencies if needed
6. Start both backend and frontend servers
7. Open the application in your default browser

To stop the application:
- Press 'Q' in the command window
- All processes will be automatically cleaned up
- Virtual environment will be deactivated

### Unix/Linux/Mac Users (start.sh)
Run `start.sh` in the root directory. The script will:
1. Verify Python and Node.js installations
2. Create a Python virtual environment if it doesn't exist
3. Activate the virtual environment
4. Install/update Python requirements automatically
5. Install frontend dependencies if needed
6. Start both backend and frontend servers
7. Open the application in your default browser

To stop the application:
- Press Ctrl+C in the terminal
- All processes will be automatically cleaned up
- Virtual environment will be deactivated

## Project Structure

### Backend Components
- `app.py`: Flask server implementation with API endpoints
- `analysis.py`: Core analysis functions including RSI and confidence intervals
- `database.py`: Database management and operations
- `day_trade.py`: Day trading simulation logic
- `scraper.py`: Web scraping functionality for stock indices
- `requirements.txt`: Python dependency specifications

### Frontend Components
- `App.js`: Main React application component
- `ConfidenceModule.js`: 95% confidence interval analysis interface
- `DatabaseModule.js`: Database management interface
- `DayTradeModule.js`: Day trading interface
- `SettingsModule.js`: Application settings and cache management
- `package.json`: Node.js dependency specifications

## API Endpoints

### Database Operations
- `GET /api/databases`: List all available databases
- `POST /api/database/<dbname>/create`: Create a new database
- `POST /api/database/<dbname>/update`: Update existing database
- `POST /api/database/<dbname>/add`: Add ticker to database
- `POST /api/database/<dbname>/remove`: Remove ticker from database
- `POST /api/database/<dbname>/reset`: Reset database
- `GET /api/database/<dbname>/estimate`: Get update time estimate

### Analysis Operations
- `GET /api/rsi/<ticker>`: Get RSI calculations
- `GET /api/rsi/accuracy/<ticker>`: Get RSI accuracy metrics
- `GET /api/rsi/turnover/<ticker>`: Get RSI turnover analysis
- `GET /api/rsi/ma/<ticker>`: Get moving average analysis

### Scraping Operations
- `POST /api/scrape`: Scrape stock symbols from major indices

### Cache Management
- `GET /api/cache/info`: Get cache status
- `POST /api/cache/clear`: Clear cache

## Performance Considerations

### Rate Limits
- Alpaca API calls are limited to 150 requests per minute
- The application implements smart throttling to prevent rate limit issues

### Caching
- Automatic caching of frequently accessed data
- Cache management through Settings module
- Configurable cache duration and size limits

### Virtual Environment
- Isolated Python environment for consistent dependencies
- Automatic creation and management through startup scripts
- Prevents conflicts with system Python packages

## Security Notes

- API keys should be stored securely and never committed to version control
- The application runs in paper trading mode by default for safety
- Virtual environment ensures dependency security
- Always verify API endpoint access and permissions

## Error Handling

The application implements comprehensive error handling for:
- API rate limiting
- Network connectivity issues
- Invalid ticker symbols
- Database operations
- File I/O operations
- Dependency management
- Virtual environment issues

## Troubleshooting

### Common Issues
1. Virtual Environment Problems
   - Delete the `venv` directory and let the startup script recreate it
   - Ensure Python version compatibility

2. Node.js Dependencies
   - Clear `node_modules` and let the startup script reinstall
   - Check for Node.js version compatibility

3. API Rate Limits
   - Monitor the Settings module for cache status
   - Adjust batch operations timing

### Logs
- Backend logs are available in the Flask server output
- Frontend development server provides React-related logs
- Check startup script output for dependency issues

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

Please ensure:
- Virtual environment is not committed
- Dependencies are properly documented
- API keys and secrets are not included

## License

This project is licensed under the MIT License - see the LICENSE file for details.