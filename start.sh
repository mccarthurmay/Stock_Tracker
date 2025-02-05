#!/bin/bash

echo "Starting Market Analysis Tool..."

# Check for Python installation
if ! command -v python3 &> /dev/null; then
    echo "Python is not installed! Please install Python 3.8 or higher."
    exit 1
fi

# Check for Node.js installation
if ! command -v node &> /dev/null; then
    echo "Node.js is not installed! Please install Node.js 14 or higher."
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Check and install Python requirements
echo "Checking Python requirements..."
pip freeze > installed_requirements.txt
if ! cmp -s requirements.txt installed_requirements.txt; then
    echo "Installing Python requirements..."
    pip install -r requirements.txt
fi
rm installed_requirements.txt

# Install frontend dependencies if needed
cd frontend || exit
if [ ! -d "node_modules" ]; then
    echo "Installing frontend dependencies..."
    npm install
fi

# Start both servers
echo "Starting servers..."
cd ..
(source venv/bin/activate && python app.py) &
(cd frontend && npm start) &

# Store process IDs
echo $! > .server_pid
echo $! > .frontend_pid

echo "Application started! Please wait for the browser to open..."

# Trap Ctrl+C to clean up processes
cleanup() {
    echo "Stopping servers..."
    if [ -f .server_pid ]; then
        kill $(cat .server_pid) 2>/dev/null
        rm .server_pid
    fi
    if [ -f .frontend_pid ]; then
        kill $(cat .frontend_pid) 2>/dev/null
        rm .frontend_pid
    fi
    deactivate
    exit 0
}

trap cleanup INT

# Wait for user input
echo "Press Ctrl+C to stop the application"
wait