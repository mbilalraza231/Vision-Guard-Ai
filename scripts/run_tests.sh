#!/bin/bash
# VisionGuard AI - Quick Test Runner
# Run this script to execute the test suite with virtual environment

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}VisionGuard AI - Test Suite Runner${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}⚠️  Virtual environment not found!${NC}"
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "Installing dependencies..."
    ./venv/bin/pip install -r requirements.txt
    echo -e "${GREEN}✅ Setup complete!${NC}"
    echo ""
fi

# Activate virtual environment and run test suite
echo -e "${GREEN}Activating virtual environment...${NC}"
source venv/bin/activate

echo -e "${GREEN}Running test suite...${NC}"
echo ""

python tests/run_test_suite.py

echo ""
echo -e "${GREEN}Deactivating virtual environment...${NC}"
deactivate

echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✅ Test runner complete!${NC}"
echo -e "${BLUE}========================================${NC}"
