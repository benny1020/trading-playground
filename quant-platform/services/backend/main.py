from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.routers import strategies, backtests, market_data, research

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Quant Platform API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(strategies.router, prefix="/api/strategies", tags=["Strategies"])
app.include_router(backtests.router, prefix="/api/backtests", tags=["Backtests"])
app.include_router(market_data.router, prefix="/api/market-data", tags=["Market Data"])
app.include_router(research.router, prefix="/api/research", tags=["Research"])


@app.get("/health")
def health():
    return {"status": "ok"}
