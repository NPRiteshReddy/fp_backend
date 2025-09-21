#!/usr/bin/env python3
"""
Investment Portfolio Tracker - Backend API
Vercel Deployment Entry Point
"""

import sys
import os

# Add the parent directory to the Python path so we can import our backend
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend_production_ready import app

# Export the FastAPI app for Vercel
# Vercel expects the ASGI app to be available as 'app'
handler = app