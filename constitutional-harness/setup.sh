#!/bin/bash

# Constitutional Alignment Harness - Setup Script

echo "Setting up Constitutional Alignment Harness..."

# Check for Node.js
if ! command -v node &> /dev/null; then
    echo "Error: Node.js is not installed"
    echo "Please install Node.js 18+ from https://nodejs.org/"
    exit 1
fi

# Check Node version
NODE_VERSION=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_VERSION" -lt 18 ]; then
    echo "Error: Node.js version must be 18 or higher"
    echo "Current version: $(node -v)"
    exit 1
fi

echo "✓ Node.js $(node -v) found"

# Install dependencies
echo "Installing dependencies..."
npm install

# Create logs directory
mkdir -p logs

echo "✓ Dependencies installed"
echo "✓ Logs directory created"

# Check for API keys
if [ -z "$ANTHROPIC_API_KEY" ] && [ -z "$OPENAI_API_KEY" ]; then
    echo ""
    echo "⚠️  Warning: No API keys found in environment"
    echo ""
    echo "Please set one of the following:"
    echo "  export ANTHROPIC_API_KEY='your-key-here'"
    echo "  export OPENAI_API_KEY='your-key-here'"
    echo ""
fi

echo ""
echo "Setup complete! 🎉"
echo ""
echo "Quick Start:"
echo "  1. Set your API key (if not already set):"
echo "     export ANTHROPIC_API_KEY='your-key-here'"
echo ""
echo "  2. Run the example:"
echo "     npm run example"
echo ""
echo "  3. Or build and use in your own project:"
echo "     npm run build"
echo ""
echo "See README.md for full documentation."
