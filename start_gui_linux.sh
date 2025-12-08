#!/bin/bash

# E-commerce Scraper GUI Startup Script for Linux
# Simple script to start just the GUI tester

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}Starting E-commerce Scraper GUI Tester...${NC}"
echo

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}Virtual environment not found. Creating one...${NC}"
    python3 -m venv .venv
fi

# Activate virtual environment
echo -e "${GREEN}Activating virtual environment...${NC}"
source .venv/bin/activate

# Install dependencies if requirements.txt exists
if [ -f "requirements.txt" ]; then
    echo -e "${GREEN}Installing dependencies...${NC}"
    pip install -r requirements.txt
fi

# Check if tkinter is available
echo -e "${GREEN}Checking for tkinter...${NC}"
if python -c "import tkinter" 2>/dev/null; then
    echo -e "${GREEN}tkinter is available${NC}"
else
    echo -e "${YELLOW}tkinter is not available. Installing system dependencies...${NC}"
    echo -e "${YELLOW}You may need to install tkinter system package.${NC}"
    echo -e "${YELLOW}For Ubuntu/Debian: sudo apt-get install python3-tk${NC}"
    echo -e "${YELLOW}For CentOS/RHEL: sudo yum install tkinter${NC}"
    echo -e "${YELLOW}For Fedora: sudo dnf install python3-tkinter${NC}"
    echo
    read -p "Do you want to try installing python3-tk? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${GREEN}Attempting to install python3-tk...${NC}"
        sudo apt-get update && sudo apt-get install -y python3-tk || {
            echo -e "${RED}Failed to install python3-tk automatically.${NC}"
            echo -e "${YELLOW}Please install it manually and try again.${NC}"
            exit 1
        }
    else
        echo -e "${RED}tkinter is required for the GUI. Please install it manually.${NC}"
        exit 1
    fi
fi

# Check if server is running
echo -e "${GREEN}Checking if API server is running...${NC}"
if curl -s http://localhost:8000/ping >/dev/null 2>&1; then
    echo -e "${GREEN}API server is running at http://localhost:8000${NC}"
else
    echo -e "${YELLOW}API server is not running. Please start the server first with:${NC}"
    echo -e "${YELLOW}  ./start_server_linux.sh${NC}"
    echo
    read -p "Do you want to start the server now? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${GREEN}Starting server...${NC}"
        ./start_server_linux.sh &
        SERVER_PID=$!
        echo -e "${GREEN}Server started with PID: $SERVER_PID${NC}"
        echo -e "${GREEN}Waiting for server to be ready...${NC}"
        sleep 5
    else
        echo -e "${RED}Please start the server first and try again.${NC}"
        exit 1
    fi
fi

# Start the GUI
echo -e "${GREEN}Starting GUI tester...${NC}"
echo -e "${GREEN}Make sure the API server is running at http://localhost:8000${NC}"
echo
python gui_test.py 