# MCP Roster Server

AI-powered Laboratory Duty Roster Generation System for Mwananyamala Regional Referral Hospital with **realistic shift preferences**.

## Features

- ✅ **N→N→SD→DO Night Shift Pattern**: Automatic compliance with hospital policy
- ✅ **Realistic Shift Preferences**: 13 staff strict OH, weekend preferences, PM/night/EMD/BIMA predominant
- ✅ **Annual Leave Integration**: Respects 2026 leave schedule
- ✅ **Multi-Lab Support**: Main Lab, Emergency Lab (EMD), BIMA Lab, TB Lab
- ✅ **Excel Export**: Generates ISO-compliant roster files
- ✅ **MCP Protocol**: Compatible with OpenAI Agents and n8n

## Realistic Shift Preferences

### Categories Implemented:
- **13 staff:** Strict OH only (no PM/EMD/BIMA)
- **2 staff:** OH weekdays + PM weekends (shuffle)
- **1 staff:** OH weekdays + PM Sunday only
- **5 staff:** EMD predominant (Emergency Lab)
- **3 staff:** PM predominant
- **3 staff:** Night predominant
- **2 staff:** BIMA predominant

### Weekend Distribution:
- **Saturday-only:** 9 staff
- **Sunday-only:** 5 staff
- **PM shuffle:** 2 staff

See [SHIFT_PREFERENCES.md](SHIFT_PREFERENCES.md) for complete documentation.

## Deployment to Render

### Option 1: Render Blueprint (Recommended)

1. Fork this repository to GitHub
2. Connect to Render: https://dashboard.render.com/blueprints
3. Select your repository
4. Render auto-detects `render.yaml`
5. Click "Apply"

### Option 2: Manual Web Service

1. Create new Web Service on Render
2. Connect your GitHub repo
3. Settings:
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port 10000`

## API Endpoints

### Generate Roster (MCP Tool)