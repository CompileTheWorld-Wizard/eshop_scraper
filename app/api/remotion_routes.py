"""
Remotion API Routes

Middleware endpoints that bridge Next.js and Remotion server.
These routes receive requests from Next.js, forward to Remotion server,
and return responses back to Next.js.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, Literal

from app.middleware.remotion_proxy import remotion_proxy
from app.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/remotion", tags=["remotion"])


# Request/Response Models
class ProductInfo(BaseModel):
    """Product information for video generation."""
    title: str
    price: str
    rating: float
    reviewCount: int
    currency: str = "USD"


class VideoMetadata(BaseModel):
    """Metadata for video generation."""
    short_id: str
    scene_id: str
    sceneNumber: int


class StartVideoRequest(BaseModel):
    """Request to start video generation."""
    template: Literal["product-modern-v1", "product-minimal-v1"]
    imageUrl: str
    product: ProductInfo
    metadata: VideoMetadata


class StartVideoResponse(BaseModel):
    """Response from starting video generation."""
    taskId: str
    status: str


class TaskStatusResponse(BaseModel):
    """Response from checking task status."""
    status: Literal["pending", "processing", "completed", "failed"]
    stage: Optional[Literal["downloading", "rendering", "uploading", "done"]] = None
    progress: Optional[int] = Field(None, ge=0, le=100)
    videoUrl: Optional[str] = None
    error: Optional[str] = None


# API Endpoints

@router.post("/videos", response_model=StartVideoResponse)
async def start_video_generation(request: StartVideoRequest):
    """
    Start video generation on Remotion server.
    
    This endpoint receives requests from Next.js and forwards them to Remotion server.
    
    **Next.js calls**: `/api/remotion/videos`
    **Forwards to**: `POST {REMOTION_SERVER}/videos`
    
    Example:
    ```
    POST /api/remotion/videos
    {
        "template": "product-modern-v1",
        "imageUrl": "https://...",
        "product": {
            "title": "Product Name",
            "price": "$99.99",
            "rating": 4.5,
            "reviewCount": 123,
            "currency": "USD"
        },
        "metadata": {
            "short_id": "abc123",
            "scene_id": "uuid",
            "sceneNumber": 1
        }
    }
    ```
    
    Returns:
    ```
    {
        "taskId": "task-uuid",
        "status": "pending"
    }
    ```
    """
    try:
        logger.info(
            f"[API] Received video generation request: "
            f"template={request.template}, scene={request.metadata.sceneNumber}"
        )
        
        # Forward request to Remotion server
        result = await remotion_proxy.start_video_generation(
            template=request.template,
            image_url=request.imageUrl,
            product=request.product.dict(),
            metadata=request.metadata.dict()
        )
        
        logger.info(f"[API] Video generation started successfully: taskId={result.get('taskId')}")
        return result
        
    except HTTPException:
        # Re-raise HTTP exceptions from proxy
        raise
    except Exception as e:
        logger.error(f"[API] Failed to start video generation: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start video generation: {str(e)}"
        )


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def check_task_status(
    task_id: str,
    shortId: Optional[str] = Query(None, description="Short ID for logging"),
    sceneNumber: Optional[int] = Query(None, description="Scene number for logging")
):
    """
    Check task status on Remotion server.
    
    This endpoint receives status check requests from Next.js and forwards them to Remotion server.
    
    **Next.js calls**: `/api/remotion/tasks/{taskId}?shortId=xxx&sceneNumber=1`
    **Forwards to**: `GET {REMOTION_SERVER}/tasks/{taskId}`
    
    Example:
    ```
    GET /api/remotion/tasks/task-uuid?shortId=abc123&sceneNumber=1
    ```
    
    Returns:
    ```
    {
        "status": "completed",
        "stage": "uploading",
        "progress": 100,
        "videoUrl": "https://..."
    }
    ```
    """
    try:
        logger.info(f"[API] Checking task status: taskId={task_id}")
        
        # Forward request to Remotion server
        result = await remotion_proxy.check_task_status(
            task_id=task_id,
            short_id=shortId,
            scene_number=sceneNumber
        )
        
        logger.info(f"[API] Task status retrieved: status={result.get('status')}")
        return result
        
    except HTTPException:
        # Re-raise HTTP exceptions from proxy
        raise
    except Exception as e:
        logger.error(f"[API] Failed to check task status: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check task status: {str(e)}"
        )


@router.get("/health")
async def health_check():
    """
    Check health of Remotion proxy and server connection.
    
    Returns:
    ```
    {
        "proxy": "healthy",
        "remotion_server": "connected",
        "base_url": "http://localhost:5050"
    }
    ```
    """
    try:
        remotion_status = await remotion_proxy.health_check()
        
        return {
            "proxy": "healthy",
            **remotion_status
        }
    except Exception as e:
        logger.error(f"[API] Health check failed: {e}", exc_info=True)
        return {
            "proxy": "unhealthy",
            "error": str(e)
        }
