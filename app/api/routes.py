from fastapi import APIRouter, HTTPException, BackgroundTasks, Request, Depends, Query
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from typing import Optional, List
from datetime import datetime, timezone
import os

from app.models import (
    ScrapeRequest, TaskStatusResponse, HealthResponse,
    TaskStatus, TaskPriority, VideoGenerationRequest, VideoGenerationResponse,
    FinalizeShortRequest, FinalizeShortResponse, ImageAnalysisRequest, ImageAnalysisResponse,
    ScenarioGenerationRequest, ScenarioGenerationResponse, SaveScenarioRequest, SaveScenarioResponse,
    TestAudioRequest, TestAudioResponse, AudioGenerationRequest, AudioGenerationResponse,
    RemoveBackgroundRequest, RemoveBackgroundResponse, CompositeImagesRequest, CompositeImagesResponse,
    ReplaceBackgroundRequest, ReplaceBackgroundResponse, MergeImageWithVideoRequest, MergeImageWithVideoResponse
)
from app.services.scraping_service import scraping_service
from app.services.video_generation_service import video_generation_service
from app.services.merging_service import merging_service
from app.services.image_analysis_service import image_analysis_service
from app.services.scenario_generation_service import scenario_generation_service
from app.services.save_scenario_service import save_scenario_service
from app.services.test_audio_service import test_audio_service
from app.services.audio_generation_service import audio_generation_service
from app.services.image_processing_service import image_processing_service
from app.services.scheduler_service import get_scheduler_status, run_cleanup_now
from app.services.session_service import session_service
from app.config import settings
from app.security import (
    get_api_key, validate_request_security, validate_scrape_request,
    get_security_stats, security_manager, API_KEYS
)
from app.logging_config import get_logger
from app.utils.credit_utils import can_perform_action

logger = get_logger(__name__)

router = APIRouter()

@router.post("/scrape", response_model=TaskStatusResponse)
def scrape_product(
    request: ScrapeRequest,
    http_request: Request = None,
    api_key: Optional[str] = Depends(get_api_key)
) -> TaskStatusResponse:
    """
    Scrape product information from a URL
    
    This endpoint accepts a URL and starts scraping asynchronously using threads.
    Returns immediately with a task ID for polling.
    
    Authentication: Optional API key via Bearer token
    Rate Limits: 
    - With API key: Based on key configuration
    - Without API key: 10 requests per minute
    """
    try:
        # Security validation - DISABLED FOR DEVELOPMENT
        # TODO: Re-enable security checks for production by uncommenting the lines below
        # validate_request_security(http_request, api_key)
        # validate_scrape_request(str(request.url), api_key)
        
        # Check user's credit before starting scraping
        credit_check = can_perform_action(request.user_id, "scraping")
        if credit_check.get("error"):
            logger.error(f"Credit check failed for user {request.user_id}: {credit_check['error']}")
            raise HTTPException(status_code=400, detail=f"Credit check failed: {credit_check['error']}")
        
        if not credit_check.get("can_perform", False):
            reason = credit_check.get("reason", "Insufficient credits")
            current_credits = credit_check.get("current_credits", 0)
            required_credits = credit_check.get("required_credits", 1)
            logger.warning(f"Credit check failed for user {request.user_id}: {reason}. Current: {current_credits}, Required: {required_credits}")
            raise HTTPException(
                status_code=402, 
                detail={
                    "error": "Insufficient credits",
                    "reason": reason,
                    "current_credits": current_credits,
                    "required_credits": required_credits,
                    "message": f"You need {required_credits} credit(s) to perform this action. You currently have {current_credits} credit(s)."
                }
            )
        
        logger.info(f"Credit check passed for user {request.user_id}. Can perform scraping action.")
        
        # Start scraping using threads (no need for background tasks with threading)
        response = scraping_service.start_scraping_task(
            url=str(request.url),
            user_id=request.user_id,
            proxy=request.proxy,
            user_agent=request.user_agent,
            target_language=request.target_language
        )
        
        # Convert response to TaskStatusResponse format
        detail = {}
        # Note: target_language is not included in detail for scraping tasks
        if hasattr(response, 'supabase_product_id') and response.supabase_product_id:
            detail['supabase_product_id'] = response.supabase_product_id
        if hasattr(response, 'short_id') and response.short_id:
            detail['short_id'] = response.short_id
        
        task_response = TaskStatusResponse(
            task_id=response.task_id,
            status=response.status,
            url=response.url,
            task_type="scraping",
            progress=getattr(response, 'progress', None),
            message=getattr(response, 'message', None),
            created_at=response.created_at,
            updated_at=getattr(response, 'completed_at', response.created_at),
            priority=getattr(response, 'priority', TaskPriority.NORMAL),
            user_id=getattr(response, 'user_id', None),
            session_id=getattr(response, 'session_id', None),
            detail=detail
        )
        
        logger.info(f"Started scraping task {task_response.task_id} for {request.url} by user {request.user_id}")
        
        return task_response
        
    except Exception as e:
        logger.error(f"Error in scrape endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Scraping failed: {str(e)}")


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
def get_task_status(task_id: str) -> TaskStatusResponse:
    """
    Get the status of a scraping task. Returns simplified response with essential fields only.
    """
    task_info = scraping_service.get_task_status(task_id)
    
    if not task_info:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Build the response using the task info dictionary
    detail = {}
    
    # Add product_id to detail if it exists
    if task_info.get('product_id'):
        detail['product_id'] = task_info['product_id']
    
    # Add short_id to detail if it exists
    if task_info.get('short_id'):
        detail['short_id'] = task_info['short_id']
    
    # Add platform information to detail if available
    if task_info.get('platform'):
        detail['platform'] = task_info['platform']
    if task_info.get('platform_confidence'):
        detail['platform_confidence'] = task_info['platform_confidence']
    if task_info.get('platform_indicators'):
        detail['platform_indicators'] = task_info['platform_indicators']
    
    return TaskStatusResponse(
        task_id=task_id,
        status=task_info.get('status', 'unknown'),
        url=task_info.get('url') or "",  # Ensure url is never None
        task_type='scraping',
        progress=task_info.get('progress'),
        message=task_info.get('message'),
        created_at=task_info.get('created_at'),
        updated_at=task_info.get('updated_at'),
        priority=TaskPriority.NORMAL,
        user_id=task_info.get('user_id'),
        session_id=None,
        detail=detail
    )

@router.get("/health", response_model=HealthResponse)
def health_check():
    """
    Health check endpoint
    """
    try:
        # Get security stats
        security_stats = get_security_stats()
        
        # Get task stats
        all_tasks = scraping_service.get_all_tasks()
        task_stats = {
            'total_tasks': len(all_tasks),
            'pending_tasks': len([t for t in all_tasks.values() if t['status'] == TaskStatus.PENDING]),
            'running_tasks': len([t for t in all_tasks.values() if t['status'] == TaskStatus.RUNNING]),
            'completed_tasks': len([t for t in all_tasks.values() if t['status'] == TaskStatus.COMPLETED]),
            'failed_tasks': len([t for t in all_tasks.values() if t['status'] == TaskStatus.FAILED])
        }
        
        # Get cache stats
        
        health_response = HealthResponse(
            status="healthy",
            timestamp=datetime.now(),
            version=settings.VERSION,
            uptime=0,  # TODO: Implement uptime tracking
            memory_usage=0,  # TODO: Implement memory usage tracking
            security_stats=security_stats,
            task_stats=task_stats,
        )
        
        return health_response
        
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


@router.get("/stats")
def get_stats():
    """
    Get detailed statistics about the scraper
    """
    try:
        # Get all available stats
        all_tasks = scraping_service.get_all_tasks()
        security_stats = get_security_stats()
        
        stats = {
            'tasks': {
                'total': len(all_tasks),
                'by_status': {}
            },
            'security': security_stats,
            'timestamp': datetime.now().isoformat()
        }
        
        # Count tasks by status
        for task in all_tasks.values():
            status = task['status'].value if hasattr(task['status'], 'value') else str(task['status'])
            if status not in stats['tasks']['by_status']:
                stats['tasks']['by_status'][status] = 0
            stats['tasks']['by_status'][status] += 1
        
        return JSONResponse(content=stats)
        
    except Exception as e:
        logger.error(f"Error getting stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


@router.delete("/tasks/{task_id}")
def cancel_task(task_id: str):
    """
    Cancel a running task
    """
    try:
        task_info = scraping_service.get_task_status(task_id)
        
        if not task_info:
            raise HTTPException(status_code=404, detail="Task not found")
        
        if task_info['status'] not in [TaskStatus.PENDING, TaskStatus.RUNNING]:
            raise HTTPException(status_code=400, detail="Cannot cancel completed or failed task")
        
        # Update task status to cancelled
        scraping_service._update_task_status(task_id, TaskStatus.FAILED, "Task cancelled by user")
        
        return {"message": f"Task {task_id} cancelled successfully"}
        
    except Exception as e:
        logger.error(f"Error cancelling task {task_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to cancel task: {str(e)}")


@router.delete("/tasks")
def cleanup_tasks():
    """
    Clean up old completed/failed tasks
    """
    try:
        scraping_service.cleanup_completed_tasks()
        return {"message": "Task cleanup completed"}
        
    except Exception as e:
        logger.error(f"Error cleaning up tasks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to cleanup tasks: {str(e)}")





# ============================================================================
# Video Generation Endpoints
# ============================================================================

@router.post("/video/generate", response_model=VideoGenerationResponse)
def generate_video_from_scene(
    request: VideoGenerationRequest,
    http_request: Request = None,
    api_key: Optional[str] = Depends(get_api_key)
) -> VideoGenerationResponse:
    """
    Generate video from a scene using AI generation.
    
    This endpoint accepts a scene_id and starts video generation asynchronously using threads.
    Returns immediately with a task ID for polling.
    
    The process includes:
    1. Image generation (if no image exists) using Vertex AI or Flux API
    2. Video generation from the image using Vertex AI
    3. Storage of both image and video in Supabase
    4. Credit deduction for each generation step
    
    Authentication: Optional API key via Bearer token
    Rate Limits: Based on API key configuration
    """
    try:
        # Security validation - DISABLED FOR DEVELOPMENT
        # TODO: Re-enable security checks for production by uncommenting the lines below
        # validate_request_security(http_request, api_key)
        
        logger.info(f"Starting video generation for scene {request.scene_id} by user {request.user_id}")
        
        # Start video generation using threads
        response = video_generation_service.start_video_generation_task(
            scene_id=request.scene_id,
            user_id=request.user_id,
            force_regenerate_first_frame=request.force_regenerate_first_frame
        )
        
        # Convert response to VideoGenerationResponse format
        video_generation_response = VideoGenerationResponse(
            task_id=response['task_id'],
            status=response['status'],
            scene_id=response['scene_id'],
            user_id=response['user_id'],
            message=response['message'],
            created_at=response['created_at'],
            progress=response.get('progress'),
            current_step=response.get('current_step'),
            error_message=response.get('error_message'),
            video_url=response.get('video_url'),
            image_url=response.get('image_url')
        )
        
        logger.info(f"Started video generation task {video_generation_response.task_id} for scene {request.scene_id}")
        
        return video_generation_response
        
    except Exception as e:
        logger.error(f"Error in video generation endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Video generation failed: {str(e)}")


@router.get("/video/generate/tasks/{task_id}", response_model=VideoGenerationResponse)
def get_video_generation_task_status(task_id: str) -> VideoGenerationResponse:
    """
    Get the status of a video generation task.
    Returns VideoGenerationResponse with current status and progress.
    """
    try:
        task_info = video_generation_service.get_task_status(task_id)
        
        if not task_info:
            raise HTTPException(status_code=404, detail="Video generation task not found")
        
        # Convert task info to VideoGenerationResponse
        return VideoGenerationResponse(
            task_id=task_id,
            status=task_info['status'],
            scene_id=task_info['scene_id'],
            user_id=task_info['user_id'],
            message=task_info.get('message', ''),
            created_at=task_info['created_at'],
            progress=task_info.get('progress'),
            current_step=task_info.get('current_step'),
            error_message=task_info.get('error_message'),
            video_url=task_info.get('video_url'),
            image_url=task_info.get('image_url'),
            completed_at=task_info.get('updated_at') if task_info.get('status') == TaskStatus.COMPLETED else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting video generation task status {task_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get video generation task status: {str(e)}")



@router.delete("/video/generate/tasks/{task_id}")
def cancel_video_generation_task(task_id: str):
    """
    Cancel a running video generation task
    """
    try:
        task_info = video_generation_service.get_task_status(task_id)
        
        if not task_info:
            raise HTTPException(status_code=404, detail="Video generation task not found")
        
        if task_info['status'] not in [TaskStatus.PENDING, TaskStatus.RUNNING]:
            raise HTTPException(status_code=400, detail="Cannot cancel completed or failed video generation task")
        
        # Update task status to cancelled
        video_generation_service._update_task(task_id, status=TaskStatus.FAILED, message="Video generation task cancelled by user")
        
        return {"message": f"Video generation task {task_id} cancelled successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling video generation task {task_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to cancel video generation task: {str(e)}")


@router.delete("/video/generate/tasks")
def cleanup_video_generation_tasks():
    """
    Clean up old completed/failed video generation tasks
    """
    try:
        video_generation_service.cleanup()
        return {"message": "Video generation task cleanup completed"}
        
    except Exception as e:
        logger.error(f"Error cleaning up video generation tasks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to cleanup video generation tasks: {str(e)}")


# ============================================================================
# Short Finalization Endpoints
# ============================================================================

@router.post("/shorts/finalize", response_model=FinalizeShortResponse)
def finalize_short(
    request: FinalizeShortRequest,
    http_request: Request = None,
    api_key: Optional[str] = Depends(get_api_key)
) -> FinalizeShortResponse:
    """
    Finalize a short video by merging scenes, generating thumbnail, and optionally upscaling.
    
    This endpoint starts the finalization process asynchronously using threads.
    Returns immediately with a task ID for polling.
    
    Authentication: Optional API key via Bearer token
    Rate Limits: 
    - With API key: Based on key configuration
    - Without API key: 10 requests per minute
    """
    try:
        # Security validation - DISABLED FOR DEVELOPMENT
        # TODO: Re-enable security checks for production by uncommenting the lines below
        # validate_request_security(http_request, api_key)
        # validate_scrape_request(str(request.url), api_key)
        
        logger.info(f"Starting short finalization for user {request.user_id}, short {request.short_id}")
        
        # Start finalization using merging service
        response = merging_service.start_finalize_short_task(
            user_id=request.user_id,
            short_id=request.short_id
        )
        
        # Convert response to FinalizeShortResponse format
        finalize_response = FinalizeShortResponse(
            task_id=response['task_id'],
            status=TaskStatus.PENDING,
            short_id=request.short_id,
            user_id=request.user_id,
            message=response['message'],
            created_at=datetime.fromisoformat(response['created_at']),
            progress=0.0,
            current_step="Initializing"
        )
        
        logger.info(f"Started short finalization task {finalize_response.task_id} for short {request.short_id}")
        
        return finalize_response
        
    except Exception as e:
        logger.error(f"Error in short finalization endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Short finalization failed: {str(e)}")


@router.get("/shorts/finalize/tasks/{task_id}", response_model=FinalizeShortResponse)
def get_short_finalization_task_status(task_id: str) -> FinalizeShortResponse:
    """
    Get the status of a short finalization task.
    Returns FinalizeShortResponse with current status and progress.
    """
    try:
        task_info = merging_service.get_task_status(task_id)
        
        if not task_info:
            raise HTTPException(status_code=404, detail="Short finalization task not found")
        
        # Convert task info to FinalizeShortResponse
        # Handle both Task object and dict formats
        if hasattr(task_info, 'task_status'):
            # Task object
            status = task_info.task_status
            created_at = task_info.created_at
            progress = task_info.progress
            current_step = task_info.current_step_name
            error_message = task_info.error_message
            short_id = task_info.task_metadata.get('short_id', '') if task_info.task_metadata else ''
            user_id = task_info.user_id or ''
            message = task_info.task_status_message or ''
            thumbnail_url = task_info.task_metadata.get('thumbnail_url', '') if task_info.task_metadata else ''
            video_url = task_info.task_metadata.get('video_url', '') if task_info.task_metadata else ''
            final_video_url = task_info.task_metadata.get('final_video_url', '') if task_info.task_metadata else ''
            updated_at = task_info.updated_at
        else:
            # Dict format
            status = task_info['status']
            created_at = task_info['created_at']
            progress = task_info.get('progress')
            current_step = task_info.get('current_step')
            error_message = task_info.get('error_message')
            short_id = task_info.get('short_id', '')
            user_id = task_info.get('user_id', '')
            message = task_info.get('message', '')
            thumbnail_url = task_info.get('thumbnail_url', '')
            video_url = task_info.get('video_url', '')
            final_video_url = task_info.get('final_video_url', '')
            updated_at = task_info.get('updated_at')
        
        return FinalizeShortResponse(
            task_id=task_id,
            status=status,
            short_id=short_id,
            user_id=user_id,
            message=message,
            created_at=created_at,
            progress=progress,
            current_step=current_step,
            error_message=error_message,
            thumbnail_url=thumbnail_url,
            final_video_url=final_video_url,
            completed_at=updated_at if status == TaskStatus.COMPLETED else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting short finalization task status {task_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get short finalization task status: {str(e)}")


@router.delete("/shorts/finalize/tasks/{task_id}")
def cancel_short_finalization_task(task_id: str):
    """
    Cancel a running short finalization task
    """
    try:
        task_info = merging_service.get_task_status(task_id)
        
        if not task_info:
            raise HTTPException(status_code=404, detail="Short finalization task not found")
        
        # Handle both Task object and dict formats
        if hasattr(task_info, 'task_status'):
            status = task_info.task_status
        else:
            status = task_info['status']
            
        if status not in [TaskStatus.PENDING, TaskStatus.RUNNING]:
            raise HTTPException(status_code=400, detail="Cannot cancel completed or failed short finalization task")
        
        # Update task status to failed (cancelled)
        # Note: We'll need to add a cancel method to the merging service
        # For now, we'll mark it as failed
        logger.warning(f"Short finalization task {task_id} cancelled by user")
        
        return {"message": f"Short finalization task {task_id} cancelled successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling short finalization task {task_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to cancel short finalization task: {str(e)}")


@router.delete("/shorts/finalize/tasks")
def cleanup_short_finalization_tasks():
    """
    Clean up old completed/failed short finalization tasks
    """
    try:
        merging_service.cleanup()
        return {"message": "Short finalization task cleanup completed"}
        
    except Exception as e:
        logger.error(f"Error cleaning up short finalization tasks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to cleanup short finalization tasks: {str(e)}")


# ============================================================================
# Image Analysis Endpoints
# ============================================================================

@router.post("/image/analyze", response_model=ImageAnalysisResponse)
def analyze_image(
    request: ImageAnalysisRequest,
    http_request: Request = None,
    api_key: Optional[str] = Depends(get_api_key)
) -> ImageAnalysisResponse:
    """
    Analyze images for a product based on product_id.
    
    This endpoint accepts a product_id and starts image analysis asynchronously.
    Returns immediately with a task ID for polling.
    
    The analysis includes:
    1. Finding the product by product_id
    2. Identifying unanalyzed images
    3. Analyzing up to 4 images simultaneously using OpenAI Vision API
    4. Storing results in the product's images field
    
    Authentication: Optional API key via Bearer token
    Rate Limits: Based on API key configuration
    """
    try:
        # Security validation - DISABLED FOR DEVELOPMENT
        # TODO: Re-enable security checks for production by uncommenting the lines below
        # validate_request_security(http_request, api_key)
        
        logger.info(f"Starting image analysis for product_id {request.product_id} by user {request.user_id}")
        
        # Check if all images are already analyzed before creating a task
        product_data = image_analysis_service._get_product_by_id(request.product_id)
        if not product_data:
            raise HTTPException(status_code=404, detail=f"Product not found for product_id: {request.product_id}")
        
        images = product_data.get('images', {})
        if not images:
            raise HTTPException(status_code=400, detail="No images found for this product")
        
        # Check if all images already have analysis data
        unanalyzed_images = image_analysis_service._get_unanalyzed_images(images)
        if not unanalyzed_images:
            # All images already analyzed - return immediate response
            return ImageAnalysisResponse(
                task_id="",  # No task created
                status=TaskStatus.COMPLETED,
                product_id=request.product_id,
                user_id=request.user_id,
                message="All images already analyzed",
                created_at=datetime.now(),
                progress=100.0,
                current_step="Already completed",
                error_message=None,
                total_images=len(images),
                analyzed_images=len(images),
                failed_images=0,
                analyzedData=None,
                completed_at=datetime.now()
            )
        
        # Start image analysis using the service
        response = image_analysis_service.start_image_analysis_task(
            product_id=request.product_id,
            user_id=request.user_id
        )
        
        # Convert response to ImageAnalysisResponse format
        image_analysis_response = ImageAnalysisResponse(
            task_id=response['task_id'],
            status=TaskStatus.PENDING,
            product_id=request.product_id,
            user_id=request.user_id,
            message=response['message'],
            created_at=datetime.now(),
            progress=0.0,
            current_step="Task started",
            error_message=None,
            total_images=len(unanalyzed_images),
            analyzed_images=0,
            failed_images=0,
            analyzedData=None,
            completed_at=None
        )
        
        logger.info(f"Started image analysis task {image_analysis_response.task_id} for product_id {request.product_id}")
        
        return image_analysis_response
        
    except Exception as e:
        logger.error(f"Error in image analysis endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Image analysis failed: {str(e)}")


@router.get("/image/analyze/tasks/{task_id}", response_model=ImageAnalysisResponse)
def get_image_analysis_task_status(task_id: str) -> ImageAnalysisResponse:
    """
    Get the status of an image analysis task.
    Returns ImageAnalysisResponse with current status and progress.
    """
    try:
        # Get task status from task management system
        from app.utils.task_management import get_task_status
        task_info = get_task_status(task_id)
        
        if not task_info:
            raise HTTPException(status_code=404, detail="Image analysis task not found")
        
        # Convert task info to ImageAnalysisResponse
        return ImageAnalysisResponse(
            task_id=task_id,
            status=task_info.task_status,
            product_id=task_info.task_metadata.get('product_id', ''),
            user_id=task_info.user_id or '',
            message=task_info.task_status_message,
            created_at=task_info.created_at,
            progress=task_info.progress,
            current_step=task_info.current_step_name,
            error_message=task_info.error_message,
            total_images=task_info.task_metadata.get('total_images'),
            analyzed_images=task_info.task_metadata.get('analyzed_images'),
            failed_images=task_info.task_metadata.get('failed_images'),
            analyzedData=None,  # Don't include analyzed data in task response
            completed_at=task_info.completed_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting image analysis task status {task_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get image analysis task status: {str(e)}")


@router.delete("/image/analyze/tasks/{task_id}")
def cancel_image_analysis_task(task_id: str):
    """
    Cancel a running image analysis task
    """
    try:
        # Get task status from task management system
        from app.utils.task_management import get_task_status, fail_task
        task_info = get_task_status(task_id)
        
        if not task_info:
            raise HTTPException(status_code=404, detail="Image analysis task not found")
        
        if task_info.task_status not in [TaskStatus.PENDING, TaskStatus.RUNNING]:
            raise HTTPException(status_code=400, detail="Cannot cancel completed or failed image analysis task")
        
        # Update task status to failed with cancellation message
        fail_task(task_id, "Image analysis task cancelled by user")
        
        return {"message": f"Image analysis task {task_id} cancelled successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling image analysis task {task_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to cancel image analysis task: {str(e)}")


@router.delete("/image/analyze/tasks")
def cleanup_image_analysis_tasks():
    """
    Clean up old completed/failed image analysis tasks
    """
    try:
        # Use task management system cleanup
        from app.utils.task_management import task_manager
        deleted_count = task_manager.cleanup_old_tasks(days_old=30)
        return {"message": "Image analysis task cleanup completed", "deleted_tasks_count": deleted_count}
        
    except Exception as e:
        logger.error(f"Error cleaning up image analysis tasks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to cleanup image analysis tasks: {str(e)}")


# Scenario Generation Endpoints
@router.post("/scenario/generate", response_model=ScenarioGenerationResponse)
def generate_scenario(
    request: ScenarioGenerationRequest,
    http_request: Request = None,
    api_key: Optional[str] = Depends(get_api_key)
) -> ScenarioGenerationResponse:
    """
    Generate AI-powered video scenario for a product
    
    This endpoint accepts product information and generates a complete video scenario
    including scenes, audio script, and preview image using OpenAI and Vertex AI.
    Returns immediately with a task ID for polling.
    
    Authentication: Optional API key via Bearer token
    Rate Limits: 
    - With API key: Based on key configuration
    - Without API key: 10 requests per minute
    """
    try:
        # Security validation - DISABLED FOR DEVELOPMENT
        # TODO: Re-enable security checks for production by uncommenting the lines below
        # validate_request_security(http_request, api_key)
        # validate_scrape_request(str(request.product_id), api_key)
        
        # Check user's credit before starting scenario generation
        credit_check = can_perform_action(request.user_id, "generate_scenario")
        if credit_check.get("error"):
            logger.error(f"Credit check failed for user {request.user_id}: {credit_check['error']}")
            raise HTTPException(status_code=400, detail=f"Credit check failed: {credit_check['error']}")
        
        if not credit_check.get("can_perform", False):
            reason = credit_check.get("reason", "Insufficient credits")
            current_credits = credit_check.get("current_credits", 0)
            required_credits = credit_check.get("required_credits", 1)
            logger.warning(f"Credit check failed for user {request.user_id}: {reason}. Current: {current_credits}, Required: {required_credits}")
            raise HTTPException(
                status_code=402, 
                detail={
                    "error": "Insufficient credits",
                    "reason": reason,
                    "current_credits": current_credits,
                    "required_credits": required_credits,
                    "message": f"You need {required_credits} credit(s) to perform this action. You currently have {current_credits} credit(s)."
                }
            )
        
        logger.info(f"Credit check passed for user {request.user_id}. Can perform scenario generation action.")
        
        # Start scenario generation using threads
        response = scenario_generation_service.start_scenario_generation_task(request)
        
        # Convert response to ScenarioGenerationResponse format
        return ScenarioGenerationResponse(
            task_id=response["task_id"],
            status=TaskStatus.PENDING,
            short_id="",  # Will be populated when task completes
            user_id=request.user_id,
            message=response["message"],
            created_at=datetime.now(timezone.utc),
            progress=0.0,
            current_step="Starting scenario generation",
            error_message=None,
            scenario=None,
            completed_at=None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting scenario generation for user {request.user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start scenario generation: {str(e)}")


@router.get("/scenario/generate/tasks/{task_id}", response_model=ScenarioGenerationResponse)
def get_scenario_generation_task_status(task_id: str):
    """
    Get the status of a scenario generation task
    """
    try:
        # Get task status from task management system
        from app.utils.task_management import get_task_status
        task_info = get_task_status(task_id)
        
        if not task_info:
            raise HTTPException(status_code=404, detail="Scenario generation task not found")
        
        # Convert task info to ScenarioGenerationResponse
        return ScenarioGenerationResponse(
            task_id=task_id,
            status=task_info.task_status,
            short_id=task_info.task_metadata.get('short_id', ''),
            user_id=task_info.user_id or '',
            message=task_info.task_status_message,
            created_at=task_info.created_at,
            progress=task_info.progress,
            current_step=task_info.current_step_name,
            error_message=task_info.error_message,
            scenario=task_info.task_metadata.get('scenario') if task_info.task_metadata else None,
            completed_at=task_info.completed_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting scenario generation task status {task_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get scenario generation task status: {str(e)}")


@router.delete("/scenario/generate/tasks/{task_id}")
def cancel_scenario_generation_task(task_id: str):
    """
    Cancel a running scenario generation task
    """
    try:
        # Get task status from task management system
        from app.utils.task_management import get_task_status, fail_task
        task_info = get_task_status(task_id)
        
        if not task_info:
            raise HTTPException(status_code=404, detail="Scenario generation task not found")
        
        if task_info.task_status not in [TaskStatus.PENDING, TaskStatus.RUNNING]:
            raise HTTPException(status_code=400, detail="Cannot cancel completed or failed scenario generation task")
        
        # Update task status to failed with cancellation message
        fail_task(task_id, "Scenario generation task cancelled by user")
        
        return {"message": f"Scenario generation task {task_id} cancelled successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling scenario generation task {task_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to cancel scenario generation task: {str(e)}")


# Save Scenario Endpoints
@router.post("/scenario/save", response_model=SaveScenarioResponse)
def save_scenario(
    request: SaveScenarioRequest,
    http_request: Request = None,
    api_key: Optional[str] = Depends(get_api_key)
) -> SaveScenarioResponse:
    """
    Save AI-generated scenario and generate images for scenes
    
    This endpoint accepts a scenario JSON string and saves it to the database,
    then generates images for all scenes (except the first one which is already generated).
    Returns immediately with a task ID for polling.
    
    Authentication: Optional API key via Bearer token
    Rate Limits: 
    - With API key: Based on key configuration
    - Without API key: 10 requests per minute
    """
    try:
        # Security validation - DISABLED FOR DEVELOPMENT
        # TODO: Re-enable security checks for production by uncommenting the lines below
        # validate_request_security(http_request, api_key)
        # validate_scrape_request(str(request.short_id), api_key)
        
        # No credit check needed for save_scenario itself
        # Credits will be deducted for each image generation (scene_count * generate_image)
        logger.info(f"Starting save scenario for user {request.user_id}")
        
        # Start save scenario using threads
        response = save_scenario_service.start_save_scenario_task(request)
        
        # Convert response to SaveScenarioResponse format
        return SaveScenarioResponse(
            task_id=response["task_id"],
            status=TaskStatus.PENDING,
            short_id=request.short_id,
            user_id=request.user_id,
            message=response["message"],
            created_at=datetime.now(timezone.utc),
            progress=0.0,
            current_step="Starting scenario save process",
            error_message=None,
            completed_at=None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting save scenario for user {request.user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start save scenario: {str(e)}")


@router.get("/scenario/save/tasks/{task_id}", response_model=SaveScenarioResponse)
def get_save_scenario_task_status(task_id: str):
    """
    Get the status of a save scenario task
    """
    try:
        # Get task status from task management system
        from app.utils.task_management import get_task_status
        task_info = get_task_status(task_id)
        
        if not task_info:
            raise HTTPException(status_code=404, detail="Save scenario task not found")
        
        # Convert task info to SaveScenarioResponse
        return SaveScenarioResponse(
            task_id=task_id,
            status=task_info.task_status,
            short_id=task_info.task_metadata.get('short_id', ''),
            user_id=task_info.user_id or '',
            message=task_info.task_status_message,
            created_at=task_info.created_at,
            progress=task_info.progress,
            current_step=task_info.current_step_name,
            error_message=task_info.error_message,
            completed_at=task_info.completed_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting save scenario task status {task_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get save scenario task status: {str(e)}")


@router.delete("/scenario/save/tasks/{task_id}")
def cancel_save_scenario_task(task_id: str):
    """
    Cancel a running save scenario task
    """
    try:
        # Get task status from task management system
        from app.utils.task_management import get_task_status, fail_task
        task_info = get_task_status(task_id)
        
        if not task_info:
            raise HTTPException(status_code=404, detail="Save scenario task not found")
        
        if task_info.task_status not in [TaskStatus.PENDING, TaskStatus.RUNNING]:
            raise HTTPException(status_code=400, detail="Cannot cancel completed or failed save scenario task")
        
        # Update task status to failed with cancellation message
        fail_task(task_id, "Save scenario task cancelled by user")
        
        return {"message": f"Save scenario task {task_id} cancelled successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling save scenario task {task_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to cancel save scenario task: {str(e)}")


# Scheduler Management Endpoints
@router.get("/scheduler/status")
def get_scheduler_status_endpoint():
    """
    Get the current status of the scheduler service
    """
    try:
        status = get_scheduler_status()
        return status
    except Exception as e:
        logger.error(f"Error getting scheduler status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get scheduler status: {str(e)}")


@router.post("/scheduler/cleanup/now")
def trigger_cleanup_now():
    """
    Manually trigger cleanup of old tasks now
    """
    try:
        deleted_count = run_cleanup_now()
        return {
            "message": "Manual cleanup completed successfully",
            "deleted_tasks_count": deleted_count,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Error triggering manual cleanup: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to trigger cleanup: {str(e)}")


# ============================================================================
# Session Management Endpoints
# ============================================================================

@router.get("/sessions/{short_id}")
def get_sessions_by_short_id(short_id: str):
    """
    Get all sessions for a specific short_id
    
    This endpoint returns all active and completed sessions associated with a short_id.
    Useful for tracking task progress and session management.
    
    Authentication: Optional API key via Bearer token
    """
    try:
        sessions = session_service.get_sessions_by_short_id(short_id)
        
        # Convert sessions to response format
        session_data = []
        for session in sessions:
            session_data.append({
                "short_id": session.short_id,
                "task_type": session.task_type,
                "task_id": session.task_id,
                "user_id": session.user_id,
                "status": session.status,
                "created_at": session.created_at.isoformat() if session.created_at else None,
                "updated_at": session.updated_at.isoformat() if session.updated_at else None
            })
        
        return {
            "short_id": short_id,
            "sessions": session_data,
            "total_sessions": len(session_data),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting sessions for short_id {short_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get sessions: {str(e)}")


@router.get("/sessions/task/{task_id}")
def get_session_by_task_id(task_id: str):
    """
    Get session information for a specific task_id
    
    This endpoint returns session information for a specific task.
    Useful for checking if a task has an associated session.
    
    Authentication: Optional API key via Bearer token
    """
    try:
        session = session_service.get_session(task_id)
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return {
            "short_id": session.short_id,
            "task_type": session.task_type,
            "task_id": session.task_id,
            "user_id": session.user_id,
            "status": session.status,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "updated_at": session.updated_at.isoformat() if session.updated_at else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session for task_id {task_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get session: {str(e)}")


@router.delete("/sessions/task/{task_id}")
def remove_session(task_id: str):
    """
    Remove a session for a specific task_id
    
    This endpoint manually removes a session. This is typically done automatically
    when tasks complete, but can be used for manual cleanup if needed.
    
    Authentication: Optional API key via Bearer token
    """
    try:
        success = session_service.remove_session(task_id)
        
        if success:
            return {
                "message": f"Session for task {task_id} removed successfully",
                "task_id": task_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        else:
            raise HTTPException(status_code=404, detail="Session not found or already removed")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing session for task_id {task_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to remove session: {str(e)}")

@router.get("/sessions/user/{user_id}")
def get_sessions_by_user_id(user_id: str):
    """
    Get all sessions for a specific user_id
    
    This endpoint returns all active and completed sessions associated with a user_id.
    Useful for tracking all tasks for a specific user.
    """
    try:
        sessions = session_service.get_sessions_by_user_id(user_id)
        
        # Convert sessions to response format
        session_data = []
        for session in sessions:
            session_data.append({
                "short_id": session.short_id,
                "task_type": session.task_type,
                "task_id": session.task_id,
                "user_id": session.user_id,
                "status": session.status,
                "created_at": session.created_at.isoformat() if session.created_at else None,
                "updated_at": session.updated_at.isoformat() if session.updated_at else None
            })
        
        return {
            "sessions": session_data,
            "total_sessions": len(session_data),
            "user_id": user_id
        }
        
    except Exception as e:
        logger.error(f"Error getting sessions for user_id {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get sessions: {str(e)}")


# ============================================================================
# Test Audio Endpoints
# ============================================================================

@router.post("/test-audio", response_model=TestAudioResponse)
def get_test_audio(
    request: TestAudioRequest,
    http_request: Request = None,
    api_key: Optional[str] = Depends(get_api_key)
) -> TestAudioResponse:
    """
    Get or generate test audio for a specific voice and language.
    
    This endpoint checks if test audio already exists in MongoDB for the given
    voice_id and language combination. If it exists, it returns the cached URL.
    If not, it generates new test audio using ElevenLabs and stores it for future use.
    
    Supported languages:
    - en-US, en-CA, en-GB (English variants)
    - es, es-MX (Spanish variants)
    - pt-BR (Portuguese - Brazil)
    - fr (French)
    - de (German)
    - nl (Dutch)
    
    Authentication: Optional API key via Bearer token
    Rate Limits: Based on API key configuration
    """
    try:
        # Security validation - DISABLED FOR DEVELOPMENT
        # TODO: Re-enable security checks for production by uncommenting the lines below
        # validate_request_security(http_request, api_key)
        
        logger.info(f"Getting test audio for voice {request.voice_id} in language {request.language} by user {request.user_id}")
        
        # Get test audio using the service
        response = test_audio_service.get_test_audio(request)
        
        logger.info(f"Test audio request completed for voice {request.voice_id}")
        
        return response
        
    except Exception as e:
        logger.error(f"Error in test audio endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Test audio request failed: {str(e)}")


@router.post("/generate-audio", response_model=AudioGenerationResponse)
def generate_audio(
    request: AudioGenerationRequest,
    http_request: Request = None,
    api_key: Optional[str] = Depends(get_api_key)
) -> AudioGenerationResponse:
    """
    Generate audio for a specific scenario using AI-powered script generation.
    
    This endpoint generates audio content for a video scenario by:
    1. Checking for existing test audio or generating it
    2. Analyzing the audio speed (words per minute)
    3. Generating an appropriate script using OpenAI
    4. Creating the final audio using ElevenLabs
    
    Returns the audio generation result directly.
    
    Authentication: Optional API key via Bearer token
    Rate Limits: Based on API key configuration
    """
    try:
        # Security validation - DISABLED FOR DEVELOPMENT
        # TODO: Re-enable security checks for production by uncommenting the lines below
        # validate_request_security(http_request, api_key)
        
        logger.info(f"Starting audio generation for short {request.short_id} with voice {request.voice_id} by user {request.user_id}")

        # Check if user has enough credits
        credit_check = can_perform_action(request.user_id, "generate_audio")
        if credit_check.get("error"):
            raise HTTPException(status_code=400, detail=f"Credit check failed: {credit_check['error']}")
        
        if not credit_check.get("can_perform", False):
            reason = credit_check.get("reason", "Insufficient credits")
            current_credits = credit_check.get("current_credits", 0)
            required_credits = credit_check.get("required_credits", 1)
            raise HTTPException(
                status_code=402, 
                detail={
                    "error": "Insufficient credits",
                    "reason": reason,
                    "current_credits": current_credits,
                    "required_credits": required_credits,
                    "message": f"You need {required_credits} credit(s) to perform this action. You currently have {current_credits} credit(s)."
                }
            )

        # Generate audio directly and return result
        result = audio_generation_service.generate_audio(request)
        
        logger.info(f"Successfully generated audio for short {request.short_id}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in audio generation endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Audio generation failed: {str(e)}")


# ============================================================================
# Image Processing Endpoints
# ============================================================================

@router.post("/image/remove-background", response_model=RemoveBackgroundResponse)
def remove_background(
    request: RemoveBackgroundRequest,
    http_request: Request = None,
    api_key: Optional[str] = Depends(get_api_key)
) -> RemoveBackgroundResponse:
    """
    Remove background from an image using Remove.bg API.
    
    This endpoint processes an image URL and removes its background using the Remove.bg service.
    The processed image is uploaded to Supabase storage and the URL is returned.
    
    Authentication: Optional API key via Bearer token
    Rate Limits: Based on API key configuration
    """
    try:
        # Security validation - DISABLED FOR DEVELOPMENT
        # TODO: Re-enable security checks for production by uncommenting the lines below
        # validate_request_security(http_request, api_key)
        
        logger.info(f"Starting background removal for image by user {request.user_id}")
        
        # Process the image
        result = image_processing_service.remove_background(
            image_url=request.image_url,
            scene_id=request.scene_id
        )
        
        if result['success']:
            logger.info(f"Background removal completed successfully for user {request.user_id}")
            return RemoveBackgroundResponse(
                success=True,
                image_url=result['image_url'],
                message="Background removed successfully",
                error=None
            )
        else:
            logger.error(f"Background removal failed for user {request.user_id}: {result['error']}")
            return RemoveBackgroundResponse(
                success=False,
                image_url=None,
                message="Background removal failed",
                error=result['error']
            )
        
    except Exception as e:
        logger.error(f"Error in remove background endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Background removal failed: {str(e)}")


@router.post("/image/composite", response_model=CompositeImagesResponse)
def composite_images(
    request: CompositeImagesRequest,
    http_request: Request = None,
    api_key: Optional[str] = Depends(get_api_key)
) -> CompositeImagesResponse:
    """
    Composite two images together (overlay on top of background).
    
    This endpoint merges a background image with an overlay/foreground image.
    Supports both foreground_url and overlay_url parameters (they are aliases).
    The composited image is uploaded to Supabase storage.
    
    If scene_id and user_id are provided, the scene's image_url will be updated in the database.
    
    Authentication: Optional API key via Bearer token
    Rate Limits: Based on API key configuration
    """
    try:
        # Security validation - DISABLED FOR DEVELOPMENT
        # TODO: Re-enable security checks for production by uncommenting the lines below
        # validate_request_security(http_request, api_key)
        
        # Handle both foreground_url and overlay_url (they're aliases)
        overlay_url = request.foreground_url or request.overlay_url
        if not overlay_url:
            raise HTTPException(
                status_code=400, 
                detail="Either foreground_url or overlay_url must be provided"
            )
        
        # Use defaults for optional parameters
        scene_id = request.scene_id or "temp"
        user_id = request.user_id or "anonymous"
        
        logger.info(f"Starting image compositing: background={request.background_url[:50]}..., overlay={overlay_url[:50]}...")
        
        # Composite the images
        result = image_processing_service.composite_images(
            background_url=request.background_url,
            overlay_url=overlay_url,
            scene_id=scene_id,
            user_id=user_id
        )
        
        if result['success']:
            logger.info(f"Image compositing completed successfully")
            return CompositeImagesResponse(
                success=True,
                image_url=result['image_url'],
                message="Images composited successfully",
                error=None
            )
        else:
            logger.error(f"Image compositing failed: {result['error']}")
            return CompositeImagesResponse(
                success=False,
                image_url=None,
                message="Image compositing failed",
                error=result['error']
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in composite images endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Image compositing failed: {str(e)}")


@router.post("/image/replace-background", response_model=ReplaceBackgroundResponse)
def replace_background(
    request: ReplaceBackgroundRequest,
    http_request: Request = None,
    api_key: Optional[str] = Depends(get_api_key)
) -> ReplaceBackgroundResponse:
    """
    Complete workflow: Remove background from product image and composite with new background.
    
    This endpoint performs the complete background replacement workflow:
    1. Removes background from the product image using Remove.bg API
    2. Downloads the new background image
    3. Composites the background-removed product onto the new background
    4. Uploads the final image to Supabase storage
    5. Updates the scene's image_url in the database
    
    Authentication: Optional API key via Bearer token
    Rate Limits: Based on API key configuration
    """
    try:
        # Security validation - DISABLED FOR DEVELOPMENT
        # TODO: Re-enable security checks for production by uncommenting the lines below
        # validate_request_security(http_request, api_key)
        
        logger.info(f"Starting background replacement for scene {request.scene_id} by user {request.user_id}")
        
        # Perform the complete background replacement workflow
        result = image_processing_service.replace_background(
            product_image_url=request.product_image_url,
            background_image_url=request.background_image_url,
            scene_id=request.scene_id,
            user_id=request.user_id
        )
        
        if result['success']:
            logger.info(f"Background replacement completed successfully for scene {request.scene_id}")
            return ReplaceBackgroundResponse(
                success=True,
                image_url=result['image_url'],
                message="Background replaced successfully",
                error=None
            )
        else:
            logger.error(f"Background replacement failed for scene {request.scene_id}: {result['error']}")
            return ReplaceBackgroundResponse(
                success=False,
                image_url=None,
                message="Background replacement failed",
                error=result['error']
            )
        
    except Exception as e:
        logger.error(f"Error in replace background endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Background replacement failed: {str(e)}")


@router.post("/image/merge-with-video", response_model=MergeImageWithVideoResponse)
def merge_image_with_video(
    request: MergeImageWithVideoRequest,
    http_request: Request = None,
    api_key: Optional[str] = Depends(get_api_key)
) -> MergeImageWithVideoResponse:
    """
    Start async image-video merge task (Scene2 generation).
    Returns immediately with a task_id for polling.
    
    This endpoint is designed for scene2 generation where the user selects:
    - A product image (without background/transparent PNG)
    - A background video from Storyblocks
    
    The service will (in background):
    1. Download both the product image and background video
    2. Composite the product onto the video with optional animations (zoom, floating)
    3. Upload the merged video to Supabase storage
    4. Update the scene's generated_video_url in the database
    
    Animation features:
    - Zoom animation: Product zooms from 5% to target scale over 3 seconds
    - Floating animation: Gentle up-down movement after zoom completes
    - Smooth position transitions
    
    **NEW**: Now returns task_id immediately and processes in background.
    Poll GET `/image/merge-with-video/tasks/{task_id}` to check status.
    
    Authentication: Optional API key via Bearer token
    Rate Limits: Based on API key configuration
    """
    try:
        # Security validation - DISABLED FOR DEVELOPMENT
        # TODO: Re-enable security checks for production by uncommenting the lines below
        # validate_request_security(http_request, api_key)
        
        logger.info(f"[SCENE2] Received async merge request for scene {request.scene_id} by user {request.user_id}")
        logger.info(f"[SCENE2] Request details:")
        logger.info(f"   - Product Image: {request.product_image_url[:80]}...")
        logger.info(f"   - Background Video: {request.background_video_url[:80]}...")
        logger.info(f"   - Scale: {request.scale}")
        logger.info(f"   - Position: {request.position}")
        logger.info(f"   - Duration: {request.duration}")
        logger.info(f"   - Animation: {request.add_animation}")
        
        # Get short_id from request (try multiple field names for compatibility)
        short_id = request.short_id or request.shortId or request.scene_id
        
        # Start async image-video merge task
        result = image_processing_service.start_image_merge_task(
            product_image_url=request.product_image_url,
            background_video_url=request.background_video_url,
            scene_id=request.scene_id,
            user_id=request.user_id,
            short_id=short_id,
            scale=request.scale,
            position=request.position,
            duration=request.duration,
            add_animation=request.add_animation
        )
        
        logger.info(f"[SCENE2] Started async merge task {result['task_id']} for scene {request.scene_id}")
        
        return MergeImageWithVideoResponse(
            success=True,
            task_id=result['task_id'],
            status=result['status'],
            video_url=None,  # Will be available after completion
            message=result['message'],
            error=None,
            created_at=result['created_at']
        )
        
    except Exception as e:
        logger.error(f"[SCENE2] Error starting image-video merge task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start image-video merge: {str(e)}")


@router.get("/image/merge-with-video/tasks/{task_id}", response_model=MergeImageWithVideoResponse)
def get_image_merge_task_status(
    task_id: str,
    api_key: Optional[str] = Depends(get_api_key)
) -> MergeImageWithVideoResponse:
    """
    Poll the status of an image-video merge task (Scene2 generation).
    
    Returns the current status of the task:
    - pending: Task is queued
    - processing: Task is being processed
    - completed: Task finished successfully (video_url available)
    - failed: Task failed (error message available)
    
    Authentication: Optional API key via Bearer token
    """
    try:
        task_info = image_processing_service.get_task_status(task_id)
        
        if not task_info:
            raise HTTPException(status_code=404, detail="Image merge task not found")
        
        # Check if completed and has video URL
        if task_info['status'] == 'completed' and task_info.get('video_url'):
            return MergeImageWithVideoResponse(
                success=True,
                task_id=task_id,
                status=task_info['status'],
                video_url=task_info['video_url'],
                message=task_info.get('message', 'Image-video merge completed successfully'),
                error=None,
                created_at=task_info.get('created_at')
            )
        elif task_info['status'] == 'failed':
            return MergeImageWithVideoResponse(
                success=False,
                task_id=task_id,
                status=task_info['status'],
                video_url=None,
                message=task_info.get('message', 'Image-video merge failed'),
                error=task_info.get('error_message'),
                created_at=task_info.get('created_at')
            )
        else:
            # Still pending or processing
            return MergeImageWithVideoResponse(
                success=True,
                task_id=task_id,
                status=task_info['status'],
                video_url=None,
                message=task_info.get('message', f"Task is {task_info['status']}"),
                error=None,
                created_at=task_info.get('created_at')
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting image merge task status {task_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get task status: {str(e)}")


@router.get("/scenes/generate-scene2", response_model=MergeImageWithVideoResponse)
def get_scene2_task_status_compat(
    taskId: str = Query(..., description="Task ID to check"),
    shortId: Optional[str] = Query(None, description="Short ID for logging"),
    sceneNumber: Optional[int] = Query(None, description="Scene number for logging"),
    api_key: Optional[str] = Depends(get_api_key)
) -> MergeImageWithVideoResponse:
    """
    Poll Scene2 task status (compatibility endpoint for Next.js).
    
    This is an alias for GET /image/merge-with-video/tasks/{task_id}
    that matches the URL pattern Next.js expects for Scene2 polling.
    
    Next.js calls: GET /api/v1/scenes/generate-scene2?taskId=xxx&shortId=yyy&sceneNumber=2
    
    Authentication: Optional API key via Bearer token
    """
    try:
        logger.info(f"[SCENE2-COMPAT] Polling task {taskId} (shortId={shortId}, scene={sceneNumber})")
        
        # Delegate to the main task status function
        return get_image_merge_task_status(task_id=taskId, api_key=api_key)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[SCENE2-COMPAT] Error getting task status {taskId}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get task status: {str(e)}")

