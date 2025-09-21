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
import os

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

# Initialize Supabase
supabase = None
try:
    from supabase import create_client, Client
    if supabase_url and supabase_key:
        supabase: Client = create_client(supabase_url, supabase_key)
        print("Supabase client initialized successfully")
except ImportError:
    print("ERROR: Supabase package not installed")
except Exception as e:
    print(f"ERROR: Failed to initialize Supabase: {e}")

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
    buy_date: date

    @field_validator('asset_type')
    @classmethod
    def validate_asset_type(cls, v):
        if v not in ['Stock', 'Crypto']:
            raise ValueError('asset_type must be either "Stock" or "Crypto"')
        return v

class InvestmentUpdate(BaseModel):
    quantity: Optional[float] = None
    buy_price: Optional[float] = None

class InvestmentResponse(BaseModel):
    id: int
    asset_type: str
    ticker: str
    quantity: float
    buy_price: float
    buy_date: date
    current_price: Optional[float] = None
    gain_loss: Optional[float] = None
    gain_loss_pct: Optional[float] = None

class PortfolioSummary(BaseModel):
    total_invested: float
    current_value: float
    gain_loss: float
    gain_loss_pct: float

# ===== AUTHENTICATION FUNCTIONS =====

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Extract user from JWT token"""
    if not supabase:
        raise HTTPException(status_code=500, detail="Database not available")

    try:
        token = credentials.credentials
        # Verify JWT token with Supabase
        user = supabase.auth.get_user(token)
        if not user or not user.user:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        return user.user
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")

# ===== PRICE FETCHING FUNCTIONS =====

def get_stock_price(ticker: str) -> Optional[float]:
    """Fetch current stock price using yfinance"""
    try:
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
        # Map common symbols to CoinGecko IDs
        symbol_map = {
            'BTC': 'bitcoin',
            'ETH': 'ethereum',
            'ADA': 'cardano',
            'DOT': 'polkadot',
            'MATIC': 'polygon',
            'SOL': 'solana'
        }

        coin_id = symbol_map.get(symbol.upper(), symbol.lower())
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=inr"

        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if coin_id in data and 'inr' in data[coin_id]:
                return float(data[coin_id]['inr'])
        return None
    except Exception as e:
        print(f"Error fetching crypto price for {symbol}: {e}")
        return None

# ===== API ENDPOINTS =====

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Investment Portfolio Tracker API",
        "version": "3.0.0",
        "supabase_connected": supabase is not None
    }

@app.post("/auth/signup", response_model=AuthResponse)
async def signup(user_data: UserSignUp):
    """User registration endpoint"""
    if not supabase:
        raise HTTPException(status_code=500, detail="Database not available")

    try:
        # Sign up user with Supabase Auth
        auth_response = supabase.auth.sign_up({
            "email": user_data.email,
            "password": user_data.password
        })

        if not auth_response.user:
            raise HTTPException(status_code=400, detail="Failed to create user")

        return AuthResponse(
            access_token=auth_response.session.access_token,
            refresh_token=auth_response.session.refresh_token,
            user_id=auth_response.user.id,
            email=auth_response.user.email
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Sign up failed: {str(e)}")

@app.post("/auth/signin", response_model=AuthResponse)
async def signin(user_data: UserSignIn):
    """User login endpoint"""
    if not supabase:
        raise HTTPException(status_code=500, detail="Database not available")

    try:
        # Sign in user with Supabase Auth
        auth_response = supabase.auth.sign_in_with_password({
            "email": user_data.email,
            "password": user_data.password
        })

        if not auth_response.user:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        return AuthResponse(
            access_token=auth_response.session.access_token,
            refresh_token=auth_response.session.refresh_token,
            user_id=auth_response.user.id,
            email=auth_response.user.email
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Sign in failed: {str(e)}")

@app.post("/auth/signout")
async def signout(current_user=Depends(get_current_user)):
    """User logout endpoint"""
    if not supabase:
        raise HTTPException(status_code=500, detail="Database not available")

    try:
        supabase.auth.sign_out()
        return {"message": "Successfully signed out"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Sign out failed: {str(e)}")

@app.post("/investments/", response_model=InvestmentResponse)
async def add_investment(investment: InvestmentCreate, current_user=Depends(get_current_user)):
    """Add a new investment"""
    if not supabase:
        raise HTTPException(status_code=500, detail="Database not available")

    try:
        # Insert investment with user isolation
        result = supabase.table('investments').insert({
            'user_id': current_user.id,
            'asset_type': investment.asset_type,
            'ticker': investment.ticker.upper(),
            'quantity': investment.quantity,
            'buy_price': investment.buy_price,
            'buy_date': investment.buy_date.isoformat()
        }).execute()

        if not result.data:
            raise HTTPException(status_code=400, detail="Failed to add investment")

        investment_data = result.data[0]

        # Fetch current price
        current_price = None
        if investment.asset_type == 'Stock':
            current_price = get_stock_price(investment.ticker)
        elif investment.asset_type == 'Crypto':
            current_price = get_crypto_price(investment.ticker)

        # Calculate gain/loss
        gain_loss = None
        gain_loss_pct = None
        if current_price:
            total_invested = investment.quantity * investment.buy_price
            current_value = investment.quantity * current_price
            gain_loss = current_value - total_invested
            gain_loss_pct = (gain_loss / total_invested) * 100 if total_invested > 0 else 0

        return InvestmentResponse(
            id=investment_data['id'],
            asset_type=investment_data['asset_type'],
            ticker=investment_data['ticker'],
            quantity=investment_data['quantity'],
            buy_price=investment_data['buy_price'],
            buy_date=datetime.fromisoformat(investment_data['buy_date']).date(),
            current_price=current_price,
            gain_loss=gain_loss,
            gain_loss_pct=gain_loss_pct
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to add investment: {str(e)}")

@app.get("/investments/", response_model=List[InvestmentResponse])
async def get_investments(current_user=Depends(get_current_user)):
    """Get all investments for the current user"""
    if not supabase:
        raise HTTPException(status_code=500, detail="Database not available")

    try:
        # Fetch user's investments with RLS
        result = supabase.table('investments').select('*').eq('user_id', current_user.id).execute()

        investments = []
        for inv_data in result.data:
            # Fetch current price
            current_price = None
            if inv_data['asset_type'] == 'Stock':
                current_price = get_stock_price(inv_data['ticker'])
            elif inv_data['asset_type'] == 'Crypto':
                current_price = get_crypto_price(inv_data['ticker'])

            # Calculate gain/loss
            gain_loss = None
            gain_loss_pct = None
            if current_price:
                total_invested = inv_data['quantity'] * inv_data['buy_price']
                current_value = inv_data['quantity'] * current_price
                gain_loss = current_value - total_invested
                gain_loss_pct = (gain_loss / total_invested) * 100 if total_invested > 0 else 0

            investments.append(InvestmentResponse(
                id=inv_data['id'],
                asset_type=inv_data['asset_type'],
                ticker=inv_data['ticker'],
                quantity=inv_data['quantity'],
                buy_price=inv_data['buy_price'],
                buy_date=datetime.fromisoformat(inv_data['buy_date']).date(),
                current_price=current_price,
                gain_loss=gain_loss,
                gain_loss_pct=gain_loss_pct
            ))

        return investments
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch investments: {str(e)}")

@app.get("/investments/{investment_id}", response_model=InvestmentResponse)
async def get_investment(investment_id: int, current_user=Depends(get_current_user)):
    """Get a specific investment"""
    if not supabase:
        raise HTTPException(status_code=500, detail="Database not available")

    try:
        result = supabase.table('investments').select('*').eq('id', investment_id).eq('user_id', current_user.id).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Investment not found")

        inv_data = result.data[0]

        # Fetch current price
        current_price = None
        if inv_data['asset_type'] == 'Stock':
            current_price = get_stock_price(inv_data['ticker'])
        elif inv_data['asset_type'] == 'Crypto':
            current_price = get_crypto_price(inv_data['ticker'])

        # Calculate gain/loss
        gain_loss = None
        gain_loss_pct = None
        if current_price:
            total_invested = inv_data['quantity'] * inv_data['buy_price']
            current_value = inv_data['quantity'] * current_price
            gain_loss = current_value - total_invested
            gain_loss_pct = (gain_loss / total_invested) * 100 if total_invested > 0 else 0

        return InvestmentResponse(
            id=inv_data['id'],
            asset_type=inv_data['asset_type'],
            ticker=inv_data['ticker'],
            quantity=inv_data['quantity'],
            buy_price=inv_data['buy_price'],
            buy_date=datetime.fromisoformat(inv_data['buy_date']).date(),
            current_price=current_price,
            gain_loss=gain_loss,
            gain_loss_pct=gain_loss_pct
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch investment: {str(e)}")

@app.put("/investments/{investment_id}", response_model=InvestmentResponse)
async def update_investment(investment_id: int, investment_update: InvestmentUpdate, current_user=Depends(get_current_user)):
    """Update an investment"""
    if not supabase:
        raise HTTPException(status_code=500, detail="Database not available")

    try:
        # Build update data
        update_data = {}
        if investment_update.quantity is not None:
            update_data['quantity'] = investment_update.quantity
        if investment_update.buy_price is not None:
            update_data['buy_price'] = investment_update.buy_price

        if not update_data:
            raise HTTPException(status_code=400, detail="No update data provided")

        result = supabase.table('investments').update(update_data).eq('id', investment_id).eq('user_id', current_user.id).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Investment not found or update failed")

        # Return updated investment
        return await get_investment(investment_id, current_user)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to update investment: {str(e)}")

@app.delete("/investments/{investment_id}")
async def delete_investment(investment_id: int, current_user=Depends(get_current_user)):
    """Delete an investment"""
    if not supabase:
        raise HTTPException(status_code=500, detail="Database not available")

    try:
        result = supabase.table('investments').delete().eq('id', investment_id).eq('user_id', current_user.id).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Investment not found")

        return {"message": "Investment deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to delete investment: {str(e)}")

@app.get("/summary/", response_model=PortfolioSummary)
async def get_portfolio_summary(current_user=Depends(get_current_user)):
    """Get portfolio summary with totals"""
    if not supabase:
        raise HTTPException(status_code=500, detail="Database not available")

    try:
        # Fetch all investments
        investments = await get_investments(current_user)

        total_invested = 0
        current_value = 0

        for investment in investments:
            invested_amount = investment.quantity * investment.buy_price
            total_invested += invested_amount

            if investment.current_price:
                current_amount = investment.quantity * investment.current_price
                current_value += current_amount
            else:
                current_value += invested_amount  # Use invested amount if no current price

        gain_loss = current_value - total_invested
        gain_loss_pct = (gain_loss / total_invested) * 100 if total_invested > 0 else 0

        return PortfolioSummary(
            total_invested=total_invested,
            current_value=current_value,
            gain_loss=gain_loss,
            gain_loss_pct=gain_loss_pct
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to calculate summary: {str(e)}")

@app.get("/price/stock/{ticker}")
async def get_stock_price_endpoint(ticker: str):
    """Get current stock price"""
    price = get_stock_price(ticker)
    if price is None:
        raise HTTPException(status_code=404, detail=f"Price not found for ticker: {ticker}")
    return {"ticker": ticker, "price": price, "currency": "INR"}

@app.get("/price/crypto/{symbol}")
async def get_crypto_price_endpoint(symbol: str):
    """Get current crypto price"""
    price = get_crypto_price(symbol)
    if price is None:
        raise HTTPException(status_code=404, detail=f"Price not found for symbol: {symbol}")
    return {"symbol": symbol, "price": price, "currency": "INR"}

# For Vercel deployment
handler = app