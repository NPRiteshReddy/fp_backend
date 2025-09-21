#!/usr/bin/env python3
"""
Investment Portfolio Tracker - Backend API
Hugging Face Deployment Entry Point
"""

import uvicorn
from backend_production_ready import app

if __name__ == "__main__":
    # Run FastAPI on Hugging Face Spaces default port
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=7860,  # Hugging Face Spaces default port
        log_level="info"
    )