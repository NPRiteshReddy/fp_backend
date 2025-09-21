#!/usr/bin/env python3
"""
Investment Portfolio Tracker - Production Ready Backend
Complete FastAPI backend with RLS security and error handling
"""

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, field_validator
from typing import List, Optional
from datetime import date, datetime
import yfinance as yf
import requests
import uvicorn
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Create FastAPI app
app = FastAPI(
    title="Investment Portfolio Tracker API",
    description="Secure backend API with Row Level Security for investment portfolio management",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Supabase Configuration
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")

if not supabase_url or not supabase_key:
    print("ERROR: SUPABASE_URL and SUPABASE_KEY must be set in environment variables")
    print("Create a .env file with:")
    print("   SUPABASE_URL=your_supabase_url")
    print("   SUPABASE_KEY=your_supabase_key")
    sys.exit(1)

# Initialize Supabase
try:
    from supabase import create_client, Client
    supabase: Client = create_client(supabase_url, supabase_key)
    print("Supabase client initialized successfully")
except ImportError:
    print("ERROR: Supabase package not installed")
    print("Install with: pip install supabase")
    sys.exit(1)
except Exception as e:
    print(f"ERROR: Failed to initialize Supabase: {e}")
    sys.exit(1)

# Security
security = HTTPBearer()

# ===== MODELS =====

class UserSignUp(BaseModel):
    email: str
    password: str

class UserSignIn(BaseModel):
    email: str
    password: str

class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    user_id: str
    email: str

class InvestmentCreate(BaseModel):
    asset_type: str
    ticker: str
    quantity: float
    buy_price: float
    buy_date: str

    @field_validator('asset_type')
    @classmethod
    def validate_asset_type(cls, v):
        if v not in ['Stock', 'Crypto']:
            raise ValueError('Asset type must be Stock or Crypto')
        return v

    @field_validator('quantity')
    @classmethod
    def validate_quantity(cls, v):
        if v <= 0:
            raise ValueError('Quantity must be greater than 0')
        return v

    @field_validator('buy_price')
    @classmethod
    def validate_buy_price(cls, v):
        if v <= 0:
            raise ValueError('Buy price must be greater than 0')
        return v

    @field_validator('ticker')
    @classmethod
    def validate_ticker(cls, v):
        if not v or not v.strip():
            raise ValueError('Ticker cannot be empty')
        return v.upper().strip()

class InvestmentUpdate(BaseModel):
    quantity: Optional[float] = None
    buy_price: Optional[float] = None

    @field_validator('quantity')
    @classmethod
    def validate_quantity(cls, v):
        if v is not None and v <= 0:
            raise ValueError('Quantity must be greater than 0')
        return v

    @field_validator('buy_price')
    @classmethod
    def validate_buy_price(cls, v):
        if v is not None and v <= 0:
            raise ValueError('Buy price must be greater than 0')
        return v

class Investment(BaseModel):
    id: int
    asset_type: str
    ticker: str
    quantity: float
    buy_price: float
    buy_date: str
    current_price: Optional[float] = None
    gain_loss: Optional[float] = None
    gain_loss_pct: Optional[float] = None

class InvestmentResponse(BaseModel):
    id: int
    message: str

class PortfolioSummary(BaseModel):
    total_invested: float
    current_value: float
    gain_loss: float
    gain_loss_pct: float

class PriceResponse(BaseModel):
    ticker: str
    price: Optional[float]
    timestamp: str

# ===== AUTHENTICATION FUNCTIONS =====

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Extract and validate user from JWT token"""
    try:
        token = credentials.credentials
        user = supabase.auth.get_user(token)
        if user.user is None:
            raise HTTPException(status_code=401, detail="Invalid authentication token")
        return user.user, token
    except Exception as e:
        print(f"Auth error: {e}")
        raise HTTPException(status_code=401, detail="Invalid authentication token")

def get_user_supabase_client(token: str):
    """Create a Supabase client with user's JWT token for RLS"""
    try:
        # Create a new client instance
        client = create_client(supabase_url, supabase_key)

        # Set the auth session for RLS
        client.auth.session = {
            "access_token": token,
            "refresh_token": "",
            "expires_in": 3600,
            "token_type": "bearer",
            "user": None
        }

        # Set the authorization header for requests
        client.auth._headers = {"Authorization": f"Bearer {token}"}

        return client
    except Exception as e:
        print(f"Error creating user client: {e}")
        raise HTTPException(status_code=500, detail="Failed to create authenticated session")

# ===== PRICE FETCHING FUNCTIONS =====

def get_stock_price(ticker: str) -> Optional[float]:
    """Fetch current stock price using yfinance"""
    try:
        # Try Indian stock first (with .NS suffix)
        stock = yf.Ticker(f"{ticker}.NS")
        hist = stock.history(period="1d")
        if not hist.empty:
            return float(hist['Close'].iloc[-1])

        # Try international stock
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1d")
        if not hist.empty:
            return float(hist['Close'].iloc[-1])

        return None
    except Exception as e:
        print(f"Error fetching stock price for {ticker}: {e}")
        return None

def get_crypto_price(symbol: str) -> Optional[float]:
    """Fetch current crypto price using CoinGecko API"""
    try:
        # Mapping for common crypto symbols to CoinGecko IDs
        crypto_mapping = {
            'BTC': 'bitcoin',
            'ETH': 'ethereum',
            'ADA': 'cardano',
            'DOT': 'polkadot',
            'SOL': 'solana',
            'MATIC': 'polygon',
            'AVAX': 'avalanche-2',
            'LINK': 'chainlink',
            'UNI': 'uniswap'
        }

        coin_id = crypto_mapping.get(symbol.upper(), symbol.lower())
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"

        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        return float(data[coin_id]['usd'])
    except Exception as e:
        print(f"Error fetching crypto price for {symbol}: {e}")
        return None

def calculate_investment_metrics(investment):
    """Calculate current price, gain/loss for an investment"""
    current_price = None

    if investment["asset_type"] == "Stock":
        current_price = get_stock_price(investment["ticker"])
    elif investment["asset_type"] == "Crypto":
        current_price = get_crypto_price(investment["ticker"])

    investment_dict = dict(investment)
    investment_dict["current_price"] = current_price

    if current_price:
        invested_value = investment["quantity"] * investment["buy_price"]
        current_value = investment["quantity"] * current_price
        gain_loss = current_value - invested_value
        gain_loss_pct = (gain_loss / invested_value) * 100 if invested_value > 0 else 0

        investment_dict["gain_loss"] = gain_loss
        investment_dict["gain_loss_pct"] = gain_loss_pct
    else:
        investment_dict["gain_loss"] = None
        investment_dict["gain_loss_pct"] = None

    return investment_dict

# ===== API ENDPOINTS =====

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Investment Portfolio Tracker API",
        "version": "3.0.0",
        "status": "running",
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Test Supabase connection
        result = supabase.table("investments").select("count", count="exact").execute()
        return {
            "status": "healthy",
            "message": "Investment Portfolio Tracker API is running",
            "database": "connected",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "message": "Database connection failed",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

# ===== AUTHENTICATION ENDPOINTS =====

@app.post("/auth/signup", response_model=AuthResponse)
async def sign_up(user_data: UserSignUp):
    """User registration"""
    try:
        response = supabase.auth.sign_up({
            "email": user_data.email,
            "password": user_data.password
        })

        if response.user is None:
            raise HTTPException(status_code=400, detail="Failed to create user")

        return AuthResponse(
            access_token=response.session.access_token,
            refresh_token=response.session.refresh_token,
            user_id=response.user.id,
            email=response.user.email
        )
    except Exception as e:
        print(f"Signup error: {e}")
        raise HTTPException(status_code=400, detail=f"Sign up failed: {str(e)}")

@app.post("/auth/signin", response_model=AuthResponse)
async def sign_in(user_data: UserSignIn):
    """User login"""
    try:
        response = supabase.auth.sign_in_with_password({
            "email": user_data.email,
            "password": user_data.password
        })

        if response.user is None:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        return AuthResponse(
            access_token=response.session.access_token,
            refresh_token=response.session.refresh_token,
            user_id=response.user.id,
            email=response.user.email
        )
    except Exception as e:
        print(f"Signin error: {e}")
        raise HTTPException(status_code=401, detail=f"Sign in failed: {str(e)}")

@app.post("/auth/signout")
async def sign_out(current_user_data=Depends(get_current_user)):
    """User logout"""
    try:
        return {"message": "Successfully signed out"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sign out failed: {str(e)}")

# ===== INVESTMENT ENDPOINTS =====

@app.post("/investments/", response_model=InvestmentResponse)
async def add_investment(investment: InvestmentCreate, current_user_data=Depends(get_current_user)):
    """Add new investment with RLS security"""
    try:
        current_user, token = current_user_data
        user_client = get_user_supabase_client(token)

        result = user_client.table("investments").insert({
            "user_id": current_user.id,
            "asset_type": investment.asset_type,
            "ticker": investment.ticker,
            "quantity": investment.quantity,
            "buy_price": investment.buy_price,
            "buy_date": investment.buy_date
        }).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create investment")

        return InvestmentResponse(
            id=result.data[0]["id"],
            message="Investment added successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Add investment error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to add investment: {str(e)}")

@app.get("/investments/", response_model=List[Investment])
async def get_investments(current_user_data=Depends(get_current_user)):
    """Get user's investments with current prices (RLS secured)"""
    try:
        current_user, token = current_user_data
        user_client = get_user_supabase_client(token)

        result = user_client.table("investments").select("*").execute()

        investments_with_prices = []
        for investment in result.data:
            investment_with_metrics = calculate_investment_metrics(investment)
            investments_with_prices.append(investment_with_metrics)

        return investments_with_prices
    except HTTPException:
        raise
    except Exception as e:
        print(f"Get investments error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch investments: {str(e)}")

@app.get("/investments/{investment_id}", response_model=Investment)
async def get_investment(investment_id: int, current_user_data=Depends(get_current_user)):
    """Get specific investment (RLS secured)"""
    try:
        current_user, token = current_user_data
        user_client = get_user_supabase_client(token)

        result = user_client.table("investments").select("*").eq("id", investment_id).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Investment not found")

        investment_with_metrics = calculate_investment_metrics(result.data[0])
        return investment_with_metrics
    except HTTPException:
        raise
    except Exception as e:
        print(f"Get investment error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch investment: {str(e)}")

@app.put("/investments/{investment_id}", response_model=InvestmentResponse)
async def update_investment(investment_id: int, investment_update: InvestmentUpdate, current_user_data=Depends(get_current_user)):
    """Update investment (RLS secured)"""
    try:
        current_user, token = current_user_data
        user_client = get_user_supabase_client(token)

        update_data = {}
        if investment_update.quantity is not None:
            update_data["quantity"] = investment_update.quantity
        if investment_update.buy_price is not None:
            update_data["buy_price"] = investment_update.buy_price

        if not update_data:
            raise HTTPException(status_code=400, detail="No valid fields to update")

        result = user_client.table("investments").update(update_data).eq("id", investment_id).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Investment not found or not authorized")

        return InvestmentResponse(
            id=investment_id,
            message="Investment updated successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Update investment error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update investment: {str(e)}")

@app.delete("/investments/{investment_id}", response_model=InvestmentResponse)
async def delete_investment(investment_id: int, current_user_data=Depends(get_current_user)):
    """Delete investment (RLS secured)"""
    try:
        current_user, token = current_user_data
        user_client = get_user_supabase_client(token)

        result = user_client.table("investments").delete().eq("id", investment_id).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Investment not found or not authorized")

        return InvestmentResponse(
            id=investment_id,
            message="Investment deleted successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Delete investment error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete investment: {str(e)}")

@app.get("/summary/", response_model=PortfolioSummary)
async def get_portfolio_summary(current_user_data=Depends(get_current_user)):
    """Get portfolio summary (RLS secured)"""
    try:
        current_user, token = current_user_data
        user_client = get_user_supabase_client(token)

        result = user_client.table("investments").select("*").execute()

        total_invested = 0
        current_value = 0

        for investment in result.data:
            investment_with_metrics = calculate_investment_metrics(investment)
            invested_amount = investment["quantity"] * investment["buy_price"]
            total_invested += invested_amount

            if investment_with_metrics.get("current_price"):
                current_amount = investment["quantity"] * investment_with_metrics["current_price"]
                current_value += current_amount
            else:
                current_value += invested_amount

        gain_loss = current_value - total_invested
        gain_loss_pct = (gain_loss / total_invested) * 100 if total_invested > 0 else 0

        return PortfolioSummary(
            total_invested=total_invested,
            current_value=current_value,
            gain_loss=gain_loss,
            gain_loss_pct=gain_loss_pct
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Portfolio summary error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to calculate portfolio summary: {str(e)}")

# ===== PRICE ENDPOINTS =====

@app.get("/price/stock/{ticker}", response_model=PriceResponse)
async def get_stock_price_endpoint(ticker: str):
    """Get current stock price"""
    try:
        price = get_stock_price(ticker)
        return PriceResponse(
            ticker=ticker,
            price=price,
            timestamp=datetime.now().isoformat()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch stock price: {str(e)}")

@app.get("/price/crypto/{symbol}", response_model=PriceResponse)
async def get_crypto_price_endpoint(symbol: str):
    """Get current crypto price"""
    try:
        price = get_crypto_price(symbol)
        return PriceResponse(
            ticker=symbol,
            price=price,
            timestamp=datetime.now().isoformat()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch crypto price: {str(e)}")

# ===== STARTUP AND MAIN =====

@app.on_event("startup")
async def startup_event():
    """Application startup event"""
    print("🚀 Investment Portfolio Tracker Backend Starting...")
    print(f"📊 FastAPI version: {app.version}")
    print(f"🔗 Docs available at: http://localhost:8000/docs")
    print(f"🔍 Health check: http://localhost:8000/health")

if __name__ == "__main__":
    # Check for port availability
    import socket

    ports_to_try = [8000, 8001, 8002, 8003]
    selected_port = None

    for port in ports_to_try:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('localhost', port))
                selected_port = port
                break
        except OSError:
            continue

    if selected_port is None:
        print("❌ No available ports found")
        sys.exit(1)

    print(f"🌐 Starting backend on port {selected_port}")
    uvicorn.run(app, host="0.0.0.0", port=selected_port, reload=True)