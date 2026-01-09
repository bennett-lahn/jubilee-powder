#!/bin/bash
# Documentation build and serve script for Jubilee Automation

set -e  # Exit on error

echo "=================================================="
echo "Jubilee Powder - Documentation Builder"
echo "=================================================="
echo ""

# Check if mkdocs is installed
if ! command -v mkdocs &> /dev/null; then
    echo "❌ MkDocs is not installed."
    echo ""
    echo "To install, run:"
    echo "  pip install mkdocs mkdocs-material mkdocstrings[python]"
    echo ""
    echo "Or install from requirements.txt:"
    echo "  pip install -r requirements.txt"
    exit 1
fi

echo "✅ MkDocs found: $(mkdocs --version)"
echo ""

# Function to display menu
show_menu() {
    echo "What would you like to do?"
    echo ""
    echo "  1) Build documentation (creates site/ directory)"
    echo "  2) Serve documentation locally (with live reload)"
    echo "  3) Build with strict mode (catch all warnings)"
    echo "  4) Deploy to GitHub Pages"
    echo "  5) Clean build artifacts"
    echo "  6) Exit"
    echo ""
}

# Function to build docs
build_docs() {
    echo "📦 Building documentation..."
    mkdocs build
    echo ""
    echo "✅ Documentation built successfully!"
    echo "   Output directory: site/"
    echo ""
}

# Function to serve docs
serve_docs() {
    echo "🚀 Starting local documentation server..."
    echo ""
    echo "   Open your browser to: http://127.0.0.1:8000"
    echo ""
    echo "   Press Ctrl+C to stop the server"
    echo ""
    mkdocs serve
}

# Function to build strict
build_strict() {
    echo "📦 Building documentation in strict mode..."
    mkdocs build --strict
    echo ""
    echo "✅ Documentation built successfully with no warnings!"
    echo "   Output directory: site/"
    echo ""
}

# Function to deploy
deploy_docs() {
    echo "🚀 Deploying to GitHub Pages..."
    echo ""
    read -p "Are you sure you want to deploy? (y/N) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        mkdocs gh-deploy
        echo ""
        echo "✅ Documentation deployed to GitHub Pages!"
    else
        echo "❌ Deployment cancelled"
    fi
    echo ""
}

# Function to clean
clean_docs() {
    echo "🧹 Cleaning build artifacts..."
    rm -rf site/
    echo "✅ Clean complete!"
    echo ""
}

# Main loop
while true; do
    show_menu
    read -p "Enter your choice [1-6]: " choice
    echo ""
    
    case $choice in
        1)
            build_docs
            ;;
        2)
            serve_docs
            ;;
        3)
            build_strict
            ;;
        4)
            deploy_docs
            ;;
        5)
            clean_docs
            ;;
        6)
            echo "👋 Goodbye!"
            exit 0
            ;;
        *)
            echo "❌ Invalid option. Please choose 1-6."
            echo ""
            ;;
    esac
    
    read -p "Press Enter to continue..."
    echo ""
    echo ""
done

