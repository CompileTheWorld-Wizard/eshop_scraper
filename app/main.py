import logging
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
import time
import json
import os
import asyncio
from contextlib import asynccontextmanager
import threading

from app.config import settings
from app.api.routes import router
from app.services.scraping_service import scraping_service
from app.services.scheduler_service import start_scheduler, stop_scheduler
from app.security import security_middleware, cleanup_security_data
from app.logging_config import setup_logging, get_logger
from app.utils import cleanup_windows_asyncio

# Setup comprehensive logging - this ensures logging is available
# for all subsequent imports and operations. The setup_logging function
# is designed to be idempotent and will only initialize once.
setup_logging()
logger = get_logger(__name__)


def monitor_database_connections():
    """Background task to monitor database connections"""
    while True:
        try:
            from app.utils.task_management import task_manager
            from app.utils.supabase_utils import supabase_manager
            
            # Monitor MongoDB connection
            task_manager.monitor_connections()
            
            # Monitor Supabase connection
            supabase_manager.ensure_connection()
            
            # Wait 5 minutes before next check
            time.sleep(300)
            
        except Exception as e:
            logger.error(f"Error in database connection monitoring: {e}")
            time.sleep(60)  # Wait 1 minute on error before retry


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("Starting E-commerce Scraper API...")
    
    # Initialize database connections
    try:
        from app.utils.task_management import initialize_task_manager
        from app.utils.supabase_utils import supabase_manager
        from app.services.session_service import initialize_session_service
        
        # Initialize Supabase
        if supabase_manager.is_connected():
            logger.info("Supabase connection established successfully")
        else:
            logger.warning("Supabase connection failed - Supabase operations will be disabled")
        
        # Initialize MongoDB
        if initialize_task_manager():
            logger.info("MongoDB connection established successfully")
        else:
            logger.warning("MongoDB connection failed - Task management will be disabled")
        
        # Initialize Session Service
        if initialize_session_service():
            logger.info("Session service connection established successfully")
        else:
            logger.warning("Session service connection failed - Session tracking will be disabled")
            
        # Start background connection monitoring
        threading.Thread(target=monitor_database_connections, daemon=True).start()
        logger.info("Database connection monitoring started")
        
        # Start scheduler service
        start_scheduler()
        logger.info("Scheduler service started")
            
    except Exception as e:
        logger.error(f"Failed to initialize database connections: {e}")
    
    # Clean up old security data on startup
    cleanup_security_data()
    
    yield
    
    # Shutdown
    logger.info("Shutting down E-commerce Scraper API...")
    
    # Cleanup database connections
    try:
        from app.utils.task_management import cleanup_task_manager
        from app.services.session_service import cleanup_session_service
        cleanup_task_manager()
        cleanup_session_service()
        logger.info("Database connections closed")
    except Exception as e:
        logger.error(f"Error closing database connections: {e}")
    
    # Stop scheduler service
    try:
        stop_scheduler()
        logger.info("Scheduler service stopped")
    except Exception as e:
        logger.error(f"Error stopping scheduler service: {e}")
    
    # Clean up Windows asyncio resources
    cleanup_windows_asyncio()


# Create FastAPI app with custom JSON encoder
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="A high-performance API for scraping product information from e-commerce websites",
    docs_url=None,
    redoc_url="/redoc",
    lifespan=lifespan
)

# Configure JSON responses to not escape Unicode characters
@app.middleware("http")
async def json_unicode_middleware(request: Request, call_next):
    """Middleware to handle Unicode characters in JSON responses"""
    response = await call_next(request)
    
    # If it's a JSON response, ensure Unicode characters are not escaped
    if hasattr(response, 'body') and response.headers.get('content-type', '').startswith('application/json'):
        try:
            # Parse the JSON response
            data = json.loads(response.body.decode('utf-8'))
            # Re-encode with ensure_ascii=False to preserve Unicode characters
            response.body = json.dumps(data, ensure_ascii=False, default=str).encode('utf-8')
        except:
            pass
    
    return response

# Add security middleware first
app.middleware("http")(security_middleware)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]  # Configure this properly for production
)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Add processing time header to responses"""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests"""
    start_time = time.time()
    
    # Log request
    logger.info(f"Request: {request.method} {request.url}")
    
    response = await call_next(request)
    
    # Log response
    process_time = time.time() - start_time
    logger.info(f"Response: {response.status_code} - {process_time:.3f}s")
    
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


# Include API routes
app.include_router(router, prefix=settings.API_V1_STR)

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "E-commerce Scraper API",
        "version": settings.VERSION,
        "health": f"{settings.API_V1_STR}/health"
    }

@app.get("/ping")
async def ping():
    """Simple ping endpoint"""
    return {"message": "pong"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        access_log=False  # Disable uvicorn's access logging since we have our own
    ) 