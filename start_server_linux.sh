#!/bin/bash

# E-commerce Scraper Server Startup Script for Linux
# Simple script to start just the API server

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}Starting E-commerce Scraper API...${NC}"
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

# Install Playwright browsers
echo -e "${GREEN}Installing Playwright browsers...${NC}"
playwright install

# Start the server
echo -e "${GREEN}Starting API server...${NC}"
echo -e "${GREEN}API will be available at: http://localhost:8000${NC}"
echo
python -m app.main 