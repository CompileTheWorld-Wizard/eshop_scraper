"""
Save Scenario Service for saving AI-generated scenarios and generating images for scenes.
Handles database operations and Vertex AI image generation for video scenes.
"""

import threading
import time
import json
import logging
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from app.models import (
    SaveScenarioRequest, SaveScenarioResponse, GeneratedScenario,
    Scene, TaskStatus
)
from app.utils.supabase_utils import supabase_manager

from app.utils.task_management import (
    create_task, start_task, update_task_progress, 
    complete_task, fail_task, TaskType, TaskStatus as TMStatus
)
from app.services.session_service import session_service

from app.config import settings
from app.logging_config import get_logger
import requests
import tempfile
import os
from pydantic import ValidationError

logger = get_logger(__name__)


class SaveScenarioService:
    """Service for saving AI-generated scenarios and generating scene images"""
    
    def __init__(self):
        pass
        
    def start_save_scenario_task(self, request: SaveScenarioRequest) -> Dict[str, Any]:
        """Start a save scenario task"""
        try:
            # Parse the scenario string to a GeneratedScenario object
            try:
                scenario_data = json.loads(request.scenario)
                scenario = GeneratedScenario(**scenario_data)
            except (json.JSONDecodeError, ValidationError) as e:
                raise Exception(f"Invalid scenario format: {str(e)}")
            
            # No credit check needed for save_scenario itself
            # Credits will be deducted for each image generation (scene_count * generate_image)
            
            # Create task in task management system
            task_id = create_task(
                TaskType.SAVE_SCENARIO,
                user_id=request.user_id,
                task_metadata={
                    "short_id": request.short_id,
                    "scenario_title": scenario.title,
                    "scene_count": len(scenario.scenes)
                }
            )
            
            if not task_id:
                raise Exception("Failed to create save scenario task")
            
            # Start the task
            start_task(task_id)
            
            # Start background processing in a separate thread
            thread = threading.Thread(
                target=self._process_save_scenario_task,
                args=(task_id, request, scenario),
                daemon=True,
                name=f"save_scenario_{task_id}"
            )
            thread.start()
            
            logger.info(f"Started save scenario thread for task {task_id}")
            
            return {
                "task_id": task_id,
                "status": "pending",
                "message": "Save scenario task started"
            }
            
        except Exception as e:
            logger.error(f"Failed to start save scenario task: {e}")
            raise
    
    def _process_save_scenario_task(self, task_id: str, request: SaveScenarioRequest, scenario: GeneratedScenario):
        """Process the save scenario task in the background thread"""
        thread_name = threading.current_thread().name
        logger.info(f"[{thread_name}] Starting save scenario task {task_id} for short_id {request.short_id}")
        
        try:
            # Update task status to running
            update_task_progress(task_id, 0, "Starting scenario save process", 20.0)
            
            # Step 1: Save scenario to database
            update_task_progress(task_id, 20, "Saving scenario to database", 40.0)
            scenario_id = self._save_scenario_to_database(request, scenario)
            
            if not scenario_id:
                raise Exception("Failed to save scenario to database")
            
            logger.info(f"[{thread_name}] Scenario saved with ID: {scenario_id}")
            
            # Step 2: Save scenes to database
            update_task_progress(task_id, 40, "Saving scenes to database", 70.0)
            scene_ids = self._save_scenes_to_database(scenario_id, scenario.scenes, request.user_id)
            
            if not scene_ids:
                raise Exception("Failed to save scenes to database")
            
            logger.info(f"[{thread_name}] Scenes saved with IDs: {scene_ids}")
            
            # Step 3: Handle thumbnail image if available
            update_task_progress(task_id, 70, "Processing thumbnail image", 90.0)
            
            # Check if the scenario has a thumbnail URL (from scenario generation service)
            thumbnail_url = None
            if hasattr(scenario, 'thumbnail_url') and scenario.thumbnail_url:
                thumbnail_url = scenario.thumbnail_url
                logger.info(f"[{thread_name}] Found thumbnail URL in scenario: {thumbnail_url}")
            else:
                # Try to get thumbnail from the shorts table
                try:
                    short_result = supabase_manager.client.table('shorts').select('thumbnail_url').eq('id', request.short_id).single().execute()
                    if short_result.data and short_result.data.get('thumbnail_url'):
                        thumbnail_url = short_result.data['thumbnail_url']
                        logger.info(f"[{thread_name}] Found thumbnail URL in shorts table: {thumbnail_url}")
                except Exception as e:
                    logger.warning(f"[{thread_name}] Failed to get thumbnail from shorts table: {e}")
            
            # If we have a thumbnail URL, download and upload to Supabase
            if thumbnail_url:
                try:
                    supabase_thumbnail_url = self._upload_thumbnail_to_supabase(thumbnail_url, f"thumbnail_{request.short_id}")
                    if supabase_thumbnail_url:
                        # Update the shorts table with the new thumbnail URL
                        self._update_shorts_thumbnail(request.short_id, supabase_thumbnail_url)
                        logger.info(f"[{thread_name}] Successfully processed thumbnail: {supabase_thumbnail_url}")
                    else:
                        logger.warning(f"[{thread_name}] Failed to upload thumbnail to Supabase")
                except Exception as e:
                    logger.warning(f"[{thread_name}] Failed to process thumbnail: {e}")
            else:
                logger.info(f"[{thread_name}] No thumbnail URL found, skipping thumbnail processing")
            
            # Step 4: Update task completion
            update_task_progress(task_id, 90, "Finalizing scenario save", 100.0)
            
            # Complete the task
            complete_task(task_id, {
                "scenario_id": scenario_id,
                "scene_count": len(scene_ids),
                "thumbnail_processed": thumbnail_url is not None
            })
            
            # Remove session for scenario_generation tasks when save_scenario is triggered
            logger.info(f"[{thread_name}] Removing session for scenario_generation task with short_id {request.short_id}")
            # Find and remove sessions for scenario_generation tasks with this short_id
            sessions = session_service.get_sessions_by_short_id(request.short_id)
            for session in sessions:
                if session.task_type == "scenario_generation":
                    logger.info(f"[{thread_name}] Removing session for scenario_generation task {session.task_id}")
                    session_service.remove_session(session.task_id)
            
            logger.info(f"[{thread_name}] Save scenario task {task_id} completed successfully")
            
        except Exception as e:
            logger.error(f"[{thread_name}] Save scenario task {task_id} failed: {e}")
            fail_task(task_id, str(e))
    
    def _save_scenario_to_database(self, request: SaveScenarioRequest, scenario: GeneratedScenario) -> Optional[str]:
        """Save the scenario to the video_scenarios table"""
        try:
            # If a scenario already exists for this short, remove it (and its scenes) first
            try:
                existing = supabase_manager.client.table('video_scenarios').select('id').eq('short_id', request.short_id).execute()
                if existing.data and len(existing.data) > 0:
                    logger.info(f"Found existing scenario(s) for short {request.short_id}. Removing before insert...")
                    # Delete scenes for each existing scenario
                    for record in existing.data:
                        try:
                            supabase_manager.client.table('video_scenes').delete().eq('scenario_id', record['id']).execute()
                            logger.info(f"Deleted scenes for existing scenario {record['id']}")
                        except Exception as scene_delete_error:
                            logger.warning(f"Failed to delete scenes for scenario {record['id']}: {scene_delete_error}")
                            # Continue to attempt deleting scenario to avoid duplicates
                    # Delete existing scenarios
                    for record in existing.data:
                        try:
                            supabase_manager.client.table('video_scenarios').delete().eq('id', record['id']).execute()
                            logger.info(f"Deleted existing scenario {record['id']}")
                        except Exception as scenario_delete_error:
                            logger.warning(f"Failed to delete existing scenario {record['id']}: {scenario_delete_error}")
            except Exception as pre_delete_error:
                logger.error(f"Error checking/removing existing scenarios for short {request.short_id}: {pre_delete_error}")
                # Proceeding could cause duplicates; surface the error
                raise

            scenario_data = {
                "short_id": request.short_id,
                "title": scenario.title,
                "description": scenario.description,
                "style": scenario.style,
                "mood": scenario.mood,
                "audio_script": json.dumps(scenario.audio_script.dict()),
                "total_duration": scenario.total_duration,
                "resolution": scenario.resolution,  # Default resolution, can be made configurable
                "environment": scenario.environment,
                "thumbnail_text_overlay_prompt": scenario.thumbnail_text_overlay_prompt
            }
            
            result = supabase_manager.client.table('video_scenarios').insert(scenario_data).execute()
            
            if result.data and len(result.data) > 0:
                return result.data[0]['id']
            else:
                logger.error("No data returned from scenario insert")
                return None
                
        except Exception as e:
            logger.error(f"Failed to save scenario to database: {e}")
            raise
    
    def _save_scenes_to_database(self, scenario_id: str, scenes: List[Scene], user_id: str) -> List[str]:
        """Save all scenes to the video_scenes table"""
        try:
            scene_ids = []
            
            for i, scene in enumerate(scenes):
                scene_data = {
                    "scenario_id": scenario_id,
                    "scene_number": scene.scene_number,
                    "description": scene.description,  # Temporary: keep until DB schema is updated
                    "duration": scene.duration,
                    "status": "pending",
                    "image_prompt": scene.image_prompt,
                    "visual_prompt": scene.visual_prompt,
                    "image_url": None,  # No image generation needed
                    "text_overlay_prompt": scene.text_overlay_prompt
                }
                
                result = supabase_manager.client.table('video_scenes').insert(scene_data).execute()
                
                if result.data and len(result.data) > 0:
                    scene_ids.append(result.data[0]['id'])
                else:
                    logger.error(f"No data returned from scene {i + 1} insert")
                    raise Exception(f"Failed to insert scene {i + 1}")
            
            return scene_ids
            
        except Exception as e:
            logger.error(f"Failed to save scenes to database: {e}")
            raise
    
    def _upload_thumbnail_to_supabase(self, thumbnail_url: str, filename: str) -> Optional[str]:
        """Download thumbnail from URL and upload to Supabase storage"""
        try:
            # Download the thumbnail from the URL
            logger.info(f"Downloading thumbnail from: {thumbnail_url}")
            response = requests.get(thumbnail_url, timeout=30)
            response.raise_for_status()
            
            # Create a temporary file to store the thumbnail
            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp_file:
                temp_file.write(response.content)
                temp_file_path = temp_file.name
            
            try:
                # Upload to Supabase storage in the generated-content bucket
                bucket_name = "generated-content"
                file_path = f"thumbnails/{filename}_{uuid.uuid4().hex[:8]}.png"
                
                logger.info(f"Uploading thumbnail to Supabase storage: {bucket_name}/{file_path}")
                
                with open(temp_file_path, 'rb') as file:
                    result = supabase_manager.client.storage.from_(bucket_name).upload(
                        path=file_path,
                        file=file,
                        file_options={"content-type": "image/png"}
                    )
                
                if result:
                    # Get the public URL for the uploaded thumbnail
                    public_url = supabase_manager.client.storage.from_(bucket_name).get_public_url(file_path)
                    logger.info(f"Thumbnail uploaded successfully to: {public_url}")
                    return public_url
                else:
                    logger.error("Failed to upload thumbnail to Supabase storage")
                    return None
                    
            finally:
                # Clean up temporary file
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                    
        except Exception as e:
            logger.error(f"Failed to upload thumbnail to Supabase: {e}")
            return None
    

    
    def _update_shorts_thumbnail(self, short_id: str, thumbnail_url: str):
        """Update the shorts table with the thumbnail URL"""
        try:
            result = supabase_manager.client.table('shorts').update({
                "thumbnail_url": thumbnail_url,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }).eq('id', short_id).execute()
            
            if not result.data:
                logger.error(f"Failed to update short {short_id} with thumbnail URL")
                
        except Exception as e:
            logger.error(f"Failed to update short {short_id} with thumbnail URL: {e}")


# Global instance
save_scenario_service = SaveScenarioService()
