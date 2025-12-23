"""
Main FastAPI application entry point.

This module sets up the FastAPI application with all routes, middleware,
and database connections.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.database import engine, Base
from app.routers import auth, chat, integrations, tasks
from app.config import settings

# Global scheduler instance
scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.
    Creates database tables on startup and starts scheduled tasks.
    """
    # Create database tables
    Base.metadata.create_all(bind=engine)
    
    # Start scheduled email polling
    # Polls every 5 minutes for new emails
    from app.routers.integrations import scheduled_email_polling
    scheduler.add_job(
        scheduled_email_polling,
        trigger=IntervalTrigger(seconds=20),
        id="email_polling",
        replace_existing=True
    )
    scheduler.start()
    print("Scheduled email polling started (every 5 minutes)")
    
    yield
    
    # Shutdown scheduler on app shutdown
    scheduler.shutdown()
    print("Scheduled email polling stopped")


# Initialize FastAPI app
app = FastAPI(
    title="Financial Advisor AI Agent API",
    description="AI agent for Financial Advisors with Gmail, Calendar, and HubSpot integration",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(integrations.router, prefix="/api/integrations", tags=["integrations"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"message": "Financial Advisor AI Agent API", "status": "running"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler for unhandled errors."""
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)}
    )


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=True
    )

