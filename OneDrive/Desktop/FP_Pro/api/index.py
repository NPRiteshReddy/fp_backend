from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Hello from Vercel FastAPI!"}

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "FP Backend"}

# Try to import the full app
try:
    from .main import app as main_app
    # If successful, replace with the main app
    app = main_app
except Exception as e:
    # Keep the simple app for debugging
    @app.get("/error")
    def get_error():
        return {"error": str(e)}