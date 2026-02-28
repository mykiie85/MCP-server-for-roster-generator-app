#!/bin/bash
# MCP Roster Server Deployment Helper
# Usage: ./deploy.sh [local|render|test]

set -e

COMMAND=${1:-local}

show_help() {
    echo "MCP Roster Server Deployment Helper"
    echo ""
    echo "Usage: ./deploy.sh [command]"
    echo ""
    echo "Commands:"
    echo "  local     - Run server locally for development"
    echo "  test      - Run test suite"
    echo "  render    - Deploy to Render (requires git push)"
    echo "  validate  - Validate configuration files"
    echo "  help      - Show this help"
    echo ""
}

check_dependencies() {
    echo "🔍 Checking dependencies..."
    
    if ! command -v python3 &> /dev/null; then
        echo "❌ Python 3 not found"
        exit 1
    fi
    
    if ! command -v pip &> /dev/null; then
        echo "❌ pip not found"
        exit 1
    fi
    
    echo "✓ Dependencies OK"
}

run_local() {
    echo "🚀 Starting local server..."
    check_dependencies
    
    if [ ! -d "venv" ]; then
        echo "📦 Creating virtual environment..."
        python3 -m venv venv
    fi
    
    source venv/bin/activate
    
    echo "📦 Installing dependencies..."
    pip install -q -r requirements.txt
    
    echo "🌐 Server starting at http://localhost:10000"
    echo "📊 API docs: http://localhost:10000/docs"
    echo ""
    echo "Press Ctrl+C to stop"
    echo ""
    
    uvicorn main:app --host 0.0.0.0 --port 10000 --reload
}

run_tests() {
    echo "🧪 Running test suite..."
    check_dependencies
    
    source venv/bin/activate 2>/dev/null || true
    pip install -q pytest httpx
    
    python test_client.py
}

validate_config() {
    echo "🔍 Validating configuration..."
    
    # Check Python syntax
    python3 -m py_compile main.py
    echo "✓ main.py syntax OK"
    
    # Check JSON files
    if [ -f "n8n_workflow.json" ]; then
        python3 -c "import json; json.load(open('n8n_workflow.json'))"
        echo "✓ n8n_workflow.json valid"
    fi
    
    # Check YAML
    if command -v python3 -c "import yaml" &> /dev/null; then
        python3 -c "import yaml; yaml.safe_load(open('render.yaml'))"
        echo "✓ render.yaml valid"
    fi
    
    echo ""
    echo "✅ All configuration files valid"
}

deploy_render() {
    echo "🚀 Deploying to Render..."
    
    if [ ! -d ".git" ]; then
        echo "❌ Not a git repository"
        echo "Run: git init && git add . && git commit -m 'Initial commit'"
        exit 1
    fi
    
    echo "📤 Pushing to GitHub..."
    git push origin main
    
    echo ""
    echo "✅ Code pushed to GitHub"
    echo "🌐 Render should auto-deploy"
    echo "📊 Monitor at: https://dashboard.render.com"
}

case $COMMAND in
    local)
        run_local
        ;;
    test)
        run_tests
        ;;
    validate)
        validate_config
        ;;
    render)
        deploy_render
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo "Unknown command: $COMMAND"
        show_help
        exit 1
        ;;
esac