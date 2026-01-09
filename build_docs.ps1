# Documentation build and serve script for Jubilee Automation (PowerShell)

$ErrorActionPreference = "Stop"

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "Jubilee Powder - Documentation Builder" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

# Check if mkdocs is installed
try {
    $mkdocsVersion = mkdocs --version 2>&1
    Write-Host "✅ MkDocs found: $mkdocsVersion" -ForegroundColor Green
    Write-Host ""
} catch {
    Write-Host "❌ MkDocs is not installed." -ForegroundColor Red
    Write-Host ""
    Write-Host "To install, run:" -ForegroundColor Yellow
    Write-Host "  pip install mkdocs mkdocs-material mkdocstrings[python]"
    Write-Host ""
    Write-Host "Or install from requirements.txt:" -ForegroundColor Yellow
    Write-Host "  pip install -r requirements.txt"
    exit 1
}

# Function to display menu
function Show-Menu {
    Write-Host "What would you like to do?" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  1) Build documentation (creates site/ directory)"
    Write-Host "  2) Serve documentation locally (with live reload)"
    Write-Host "  3) Build with strict mode (catch all warnings)"
    Write-Host "  4) Deploy to GitHub Pages"
    Write-Host "  5) Clean build artifacts"
    Write-Host "  6) Exit"
    Write-Host ""
}

# Function to build docs
function Build-Docs {
    Write-Host "📦 Building documentation..." -ForegroundColor Yellow
    mkdocs build
    Write-Host ""
    Write-Host "✅ Documentation built successfully!" -ForegroundColor Green
    Write-Host "   Output directory: site/"
    Write-Host ""
}

# Function to serve docs
function Serve-Docs {
    Write-Host "🚀 Starting local documentation server..." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "   Open your browser to: http://127.0.0.1:8000" -ForegroundColor Green
    Write-Host ""
    Write-Host "   Press Ctrl+C to stop the server" -ForegroundColor Yellow
    Write-Host ""
    mkdocs serve
}

# Function to build strict
function Build-Strict {
    Write-Host "📦 Building documentation in strict mode..." -ForegroundColor Yellow
    mkdocs build --strict
    Write-Host ""
    Write-Host "✅ Documentation built successfully with no warnings!" -ForegroundColor Green
    Write-Host "   Output directory: site/"
    Write-Host ""
}

# Function to deploy
function Deploy-Docs {
    Write-Host "🚀 Deploying to GitHub Pages..." -ForegroundColor Yellow
    Write-Host ""
    $confirmation = Read-Host "Are you sure you want to deploy? (y/N)"
    if ($confirmation -eq 'y' -or $confirmation -eq 'Y') {
        mkdocs gh-deploy
        Write-Host ""
        Write-Host "✅ Documentation deployed to GitHub Pages!" -ForegroundColor Green
    } else {
        Write-Host "❌ Deployment cancelled" -ForegroundColor Red
    }
    Write-Host ""
}

# Function to clean
function Clean-Docs {
    Write-Host "🧹 Cleaning build artifacts..." -ForegroundColor Yellow
    if (Test-Path "site") {
        Remove-Item -Recurse -Force site
    }
    Write-Host "✅ Clean complete!" -ForegroundColor Green
    Write-Host ""
}

# Main loop
while ($true) {
    Show-Menu
    $choice = Read-Host "Enter your choice [1-6]"
    Write-Host ""
    
    switch ($choice) {
        "1" {
            Build-Docs
        }
        "2" {
            Serve-Docs
        }
        "3" {
            Build-Strict
        }
        "4" {
            Deploy-Docs
        }
        "5" {
            Clean-Docs
        }
        "6" {
            Write-Host "👋 Goodbye!" -ForegroundColor Cyan
            exit 0
        }
        default {
            Write-Host "❌ Invalid option. Please choose 1-6." -ForegroundColor Red
            Write-Host ""
        }
    }
    
    Read-Host "Press Enter to continue..."
    Write-Host ""
    Write-Host ""
}

