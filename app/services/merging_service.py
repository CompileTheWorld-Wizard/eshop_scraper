"""
Merging Service for Finalizing Shorts

This module provides functionality for:
- Merging generated video scenes into final videos
- Merging audio with videos
- Embedding subtitles into videos
- Adding watermarks for free plan users
- Managing the finalization process with task management
"""

import os
import uuid
import threading
import tempfile
import httpx
import subprocess
import json
import shutil
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path

from app.logging_config import get_logger
from app.utils.supabase_utils import supabase_manager
from app.utils.credit_utils import credit_manager
from app.utils.task_management import (
    create_task, start_task, update_task_progress,
    complete_task, fail_task, get_task_status,
    TaskType
)
from app.models import TaskStatus
from app.config import settings

logger = get_logger(__name__)

# Timeout configurations
HTTP_TIMEOUT = 300  # 5 minutes for HTTP operations
DOWNLOAD_TIMEOUT = 600  # 10 minutes for file downloads
UPLOAD_TIMEOUT = 900  # 15 minutes for file uploads
MAX_RETRIES = 3  # Maximum retry attempts for failed operations
RETRY_DELAY = 5  # Seconds to wait between retries


class MergingService:
    """Service for finalizing shorts by merging videos, audio, and processing final videos."""

    def __init__(self):
        self._active_threads: Dict[str, threading.Thread] = {}

    def start_finalize_short_task(
        self,
        user_id: str,
        short_id: str
    ) -> Dict[str, Any]:
        """
        Start the finalization process for a short video.

        Args:
            user_id: The user's UUID
            short_id: The short's UUID

        Returns:
            Dict containing task information
        """
        try:
            # Create task
            task_metadata = {
                "user_id": user_id,
                "short_id": short_id,
                "task_type": "finalize_short"
            }

            task_id = create_task(
                task_type=TaskType.FINALIZE_SHORT,
                task_metadata=task_metadata,
                user_id=user_id
            )

            # Start task in background thread
            thread = threading.Thread(
                target=self._finalize_short_worker,
                args=(task_id, user_id, short_id),
                daemon=True
            )

            self._active_threads[task_id] = thread
            thread.start()

            logger.info(
                f"Started finalize short task {task_id} for short {short_id}")

            return {
                "task_id": task_id,
                "status": "pending",
                "message": "Finalization task started",
                "created_at": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(
                f"Failed to start finalize short task: {e}", exc_info=True)
            raise

    def _finalize_short_worker(
        self,
        task_id: str,
        user_id: str,
        short_id: str
    ):
        """Background worker for finalizing shorts."""
        try:
            logger.info("=" * 80)
            logger.info(f"[MERGE FLOW] Starting merge process for short_id: {short_id}, task_id: {task_id}")
            logger.info("=" * 80)
            
            # Start task
            logger.info(f"[STEP 0] Initializing merge task...")
            start_task(task_id)
            update_task_progress(
                task_id, 0.1, "Fetching video scenes and audio data")
            logger.info(f"[STEP 0] ✓ Task initialized successfully")

            # Step 1: Fetch video scenes and audio data
            logger.info(f"[STEP 1] Fetching video scenes and audio data...")
            logger.info(f"[STEP 1.1] Fetching video scenes for short_id: {short_id}")
            scenes_data = self._fetch_video_scenes(short_id)
            if not scenes_data:
                raise Exception("No video scenes found for this short")
            logger.info(f"[STEP 1.1] ✓ Found {len(scenes_data)} video scenes")
            for i, scene in enumerate(scenes_data, 1):
                logger.info(f"[STEP 1.1]   Scene {i}: id={scene.get('id')}, number={scene.get('scene_number')}, "
                          f"duration={scene.get('duration')}s, url={scene.get('generated_video_url', 'N/A')[:80]}...")

            # Product info no longer needed since thumbnail generation is removed

            logger.info(f"[STEP 1.2] Fetching audio data for short_id: {short_id}")
            audio_data = self._fetch_audio_data(short_id)
            if audio_data:
                logger.info(f"[STEP 1.2] ✓ Audio data found: url={audio_data.get('generated_audio_url', 'N/A')[:80]}..., "
                          f"has_subtitles={bool(audio_data.get('subtitles'))}, status={audio_data.get('status')}")
            else:
                logger.info(f"[STEP 1.2] ⚠ No audio data found for this short")
            logger.info(f"[STEP 1] ✓ Completed fetching data")

            update_task_progress(task_id, 0.2, "Downloading videos and audio")

            # Step 2: Download videos and audio
            logger.info(f"[STEP 2] Downloading videos and audio...")
            logger.info(f"[STEP 2.1] Downloading {len(scenes_data)} video files...")
            video_files = self._download_videos(scenes_data, user_id)
            if not video_files:
                raise Exception("Failed to download videos")
            logger.info(f"[STEP 2.1] ✓ Successfully downloaded {len(video_files)} video files")
            for i, video_file in enumerate(video_files, 1):
                file_size = os.path.getsize(video_file) if os.path.exists(video_file) else 0
                logger.info(f"[STEP 2.1]   Video {i}: {video_file} ({file_size / 1024 / 1024:.2f} MB)")

            audio_file = None
            if audio_data and audio_data.get('generated_audio_url'):
                logger.info(f"[STEP 2.2] Downloading audio file...")
                audio_file = self._download_audio(
                    audio_data['generated_audio_url'], task_id)
                if audio_file:
                    file_size = os.path.getsize(audio_file) if os.path.exists(audio_file) else 0
                    logger.info(f"[STEP 2.2] ✓ Audio downloaded: {audio_file} ({file_size / 1024 / 1024:.2f} MB)")
                else:
                    logger.warning(f"[STEP 2.2] ⚠ Audio download returned None")
            else:
                logger.info(f"[STEP 2.2] ⚠ Skipping audio download (no audio URL available)")
            logger.info(f"[STEP 2] ✓ Completed downloading files")

            update_task_progress(task_id, 0.4, "Merging videos and audio")

            # Step 3: Merge videos
            logger.info(f"[STEP 3] Merging videos...")
            logger.info(f"[STEP 3] Merging {len(video_files)} video files into single video...")
            merged_video_path = self._merge_videos(video_files, task_id)
            if not merged_video_path:
                raise Exception("Failed to merge videos")
            merged_size = os.path.getsize(merged_video_path) if os.path.exists(merged_video_path) else 0
            logger.info(f"[STEP 3] ✓ Videos merged successfully: {merged_video_path} ({merged_size / 1024 / 1024:.2f} MB)")

            # Step 3.5: Fetch and download background music if available
            music_files = []
            logger.info(f"[STEP 3.5] Checking for background music...")
            music_metadata = self._get_music_metadata(short_id)
            if music_metadata:
                temp_music_dir = tempfile.mkdtemp()
                
                # Download track1 if available
                if music_metadata.get('track1'):
                    track1 = music_metadata['track1']
                    logger.info(f"[STEP 3.5] Downloading track1: {track1.get('name')} ({track1.get('genre')})")
                    track1_path = self._download_music_file(track1.get('path'), temp_music_dir)
                    if track1_path:
                        music_files.append(track1_path)
                        logger.info(f"[STEP 3.5] ✓ Track1 downloaded successfully")
                    else:
                        logger.warning(f"[STEP 3.5] ⚠ Failed to download track1")
                
                # Download track2 if available (for 48s videos)
                if music_metadata.get('track2'):
                    track2 = music_metadata['track2']
                    logger.info(f"[STEP 3.5] Downloading track2: {track2.get('name')} ({track2.get('genre')})")
                    track2_path = self._download_music_file(track2.get('path'), temp_music_dir)
                    if track2_path:
                        music_files.append(track2_path)
                        logger.info(f"[STEP 3.5] ✓ Track2 downloaded successfully")
                    else:
                        logger.warning(f"[STEP 3.5] ⚠ Failed to download track2")
                
                if music_files:
                    logger.info(f"[STEP 3.5] ✓ Downloaded {len(music_files)} background music track(s)")
                else:
                    logger.warning(f"[STEP 3.5] ⚠ No background music tracks downloaded")
            else:
                logger.info(f"[STEP 3.5] ⚠ No background music metadata found")

            # Step 4: Merge audio and/or background music if available
            if audio_file:
                logger.info(f"[STEP 4] Merging audio with video...")
                logger.info(f"[STEP 4] Combining audio file with merged video...")
                merged_video_path = self._merge_audio_with_video(
                    merged_video_path, audio_file, task_id, music_files
                )
                if merged_video_path:
                    merged_size = os.path.getsize(merged_video_path) if os.path.exists(merged_video_path) else 0
                    logger.info(f"[STEP 4] ✓ Audio merged successfully: {merged_video_path} ({merged_size / 1024 / 1024:.2f} MB)")
                else:
                    logger.warning(f"[STEP 4] ⚠ Audio merge returned None")
            elif music_files:
                # No voice audio but background music exists - merge music only
                logger.info(f"[STEP 4] No voice audio, but merging background music with video...")
                logger.info(f"[STEP 4] Adding {len(music_files)} background music track(s) to video...")
                merged_video_path = self._merge_music_with_video(
                    merged_video_path, task_id, music_files
                )
                if merged_video_path:
                    merged_size = os.path.getsize(merged_video_path) if os.path.exists(merged_video_path) else 0
                    logger.info(f"[STEP 4] ✓ Background music merged successfully: {merged_video_path} ({merged_size / 1024 / 1024:.2f} MB)")
                else:
                    logger.warning(f"[STEP 4] ⚠ Music merge returned None")
            else:
                logger.info(f"[STEP 4] ⚠ Skipping audio merge (no audio or music available)")

            update_task_progress(task_id, 0.5, "Processing final video")

            # Step 5: Add watermark if free plan
            logger.info(f"[STEP 5] Processing final video (watermark, subtitles)...")
            logger.info(f"[STEP 5.1] Checking user plan and adding watermark if needed...")
            final_video_path = self._add_watermark_if_needed(
                merged_video_path, user_id, task_id
            )
            if final_video_path != merged_video_path:
                final_size = os.path.getsize(final_video_path) if os.path.exists(final_video_path) else 0
                logger.info(f"[STEP 5.1] ✓ Watermark added: {final_video_path} ({final_size / 1024 / 1024:.2f} MB)")
            else:
                logger.info(f"[STEP 5.1] ✓ No watermark needed (user is not on free plan)")

            # Step 6: Add subtitles if available
            if audio_data and audio_data.get('subtitles'):
                logger.info(f"[STEP 5.2] Embedding subtitles into video...")
                try:
                    subtitle_count = len(audio_data.get('subtitles', []))
                    logger.info(f"[STEP 5.2] Found {subtitle_count} subtitle entries to embed")
                    final_video_path = self._embed_subtitles(
                        final_video_path, audio_data['subtitles'], task_id
                    )
                    if final_video_path:
                        final_size = os.path.getsize(final_video_path) if os.path.exists(final_video_path) else 0
                        logger.info(f"[STEP 5.2] ✓ Subtitles embedded successfully: {final_video_path} ({final_size / 1024 / 1024:.2f} MB)")
                    else:
                        logger.warning(f"[STEP 5.2] ⚠ Subtitle embedding returned None")
                except Exception as subtitle_error:
                    logger.warning(
                        f"[STEP 5.2] ⚠ Failed to embed subtitles, continuing without them: {subtitle_error}")
                    # Continue with the video without subtitles
            else:
                logger.info(f"[STEP 5.2] ⚠ Skipping subtitles (no subtitle data available)")
            logger.info(f"[STEP 5] ✓ Completed processing final video")

            update_task_progress(task_id, 0.7, "Uploading final video")

            # Step 7: Upload final video
            logger.info(f"[STEP 6] Uploading final video to Supabase...")
            final_size = os.path.getsize(final_video_path) if os.path.exists(final_video_path) else 0
            logger.info(f"[STEP 6] Uploading video: {final_video_path} ({final_size / 1024 / 1024:.2f} MB)")
            final_video_url = self._upload_final_video(
                final_video_path, short_id, task_id)
            if not final_video_url:
                raise Exception("Failed to upload final video")
            logger.info(f"[STEP 6] ✓ Final video uploaded successfully: {final_video_url}")

            # Update shorts table with final video URL
            logger.info(f"[STEP 7] Updating database with final video URL...")
            self._update_shorts_final_video(short_id, final_video_url)
            logger.info(f"[STEP 7] ✓ Database updated successfully")

            # Clean up temporary files
            logger.info(f"[STEP 8] Cleaning up temporary files...")
            temp_files = video_files + [merged_video_path, final_video_path]
            if audio_file:
                temp_files.append(audio_file)
            
            # Also clean up music files
            if music_files:
                temp_files.extend(music_files)
                logger.info(f"[STEP 8] Including {len(music_files)} music file(s) in cleanup")
            
            # Also clean up any subtitle temporary directories
            if audio_data and audio_data.get('subtitles'):
                try:
                    # Find and clean up subtitle temp directories
                    self._cleanup_subtitle_temp_dirs()
                    logger.info(f"[STEP 8] ✓ Subtitle temp directories cleaned")
                except Exception as cleanup_error:
                    logger.warning(f"[STEP 8] ⚠ Failed to cleanup subtitle temp directories: {cleanup_error}")
            
            self._cleanup_temp_files(temp_files)
            logger.info(f"[STEP 8] ✓ Cleaned up {len(temp_files)} temporary files")

            # Complete task
            logger.info(f"[STEP 9] Completing merge task...")
            complete_task(task_id, {
                "final_video_url": final_video_url,
                "short_id": short_id
            })
            logger.info(f"[STEP 9] ✓ Task marked as completed")

            logger.info("=" * 80)
            logger.info(f"[MERGE FLOW] ✓ Successfully completed merge process for short_id: {short_id}")
            logger.info(f"[MERGE FLOW] Final video URL: {final_video_url}")
            logger.info("=" * 80)

        except Exception as e:
            logger.error("=" * 80)
            logger.error(f"[MERGE FLOW] ✗ Failed to finalize short {short_id}: {e}", exc_info=True)
            logger.error("=" * 80)
            fail_task(task_id, str(e))
        finally:
            # Remove thread reference
            if task_id in self._active_threads:
                del self._active_threads[task_id]
                logger.info(f"[MERGE FLOW] Thread reference cleaned up for task_id: {task_id}")

    def _fetch_video_scenes(self, short_id: str) -> List[Dict[str, Any]]:
        """Fetch all video scenes for a short."""
        try:
            if not supabase_manager.is_connected():
                raise Exception("Supabase connection not available")

            # Get scenario_id from video_scenarios table
            scenario_result = supabase_manager.client.table('video_scenarios').select(
                'id'
            ).eq('short_id', short_id).execute()

            if not scenario_result.data:
                raise Exception(f"No scenario found for short {short_id}")

            scenario_id = scenario_result.data[0]['id']

            # Get all scenes with generated videos (only columns that exist in video_scenes table)
            scenes_result = supabase_manager.client.table('video_scenes').select(
                'id, scene_number, generated_video_url, duration'
            ).eq('scenario_id', scenario_id).eq('status', 'completed').not_.is_('generated_video_url', 'null').execute()

            if not scenes_result.data:
                raise Exception(
                    f"No completed video scenes found for scenario {scenario_id}")

            # Sort by scene number
            scenes = sorted(scenes_result.data,
                            key=lambda x: x['scene_number'])

            return scenes

        except Exception as e:
            logger.error(f"Failed to fetch video scenes: {e}")
            raise

    # def _fetch_product_info(self, short_id: str) -> Dict[str, Any]:
    #     """Fetch product information for thumbnail generation - REMOVED: No longer generating thumbnails."""
    #     # This method has been removed as thumbnail generation is no longer needed
    #     pass

    def _fetch_audio_data(self, short_id: str) -> Optional[Dict[str, Any]]:
        """Fetch audio data from audio_info table."""
        try:
            if not supabase_manager.is_connected():
                logger.warning(
                    "Supabase connection not available, skipping audio fetch")
                return None

            # Get audio info for the short
            audio_result = supabase_manager.client.table('audio_info').select(
                'generated_audio_url, subtitles, status'
            ).eq('short_id', short_id).eq('status', 'completed').execute()

            if not audio_result.data:
                logger.info(f"No completed audio found for short {short_id}")
                return None

            audio_data = audio_result.data[0]

            # Check if we have the required fields
            if not audio_data.get('generated_audio_url'):
                logger.info(
                    f"No generated audio URL found for short {short_id}")
                return None

            logger.info(f"Found audio data for short {short_id}")
            return audio_data

        except Exception as e:
            logger.error(f"Failed to fetch audio data: {e}")
            # Don't fail the entire process if audio fetch fails
            return None

    def _get_music_metadata(self, short_id: str) -> Optional[Dict[str, Any]]:
        """Get background music metadata from shorts table."""
        try:
            if not supabase_manager.is_connected():
                logger.warning("Supabase connection not available, skipping music metadata fetch")
                return None

            # Get shorts metadata for background music
            shorts_result = supabase_manager.client.table('shorts').select(
                'metadata'
            ).eq('id', short_id).execute()

            if not shorts_result.data:
                logger.info(f"No shorts record found for short_id {short_id}")
                return None

            metadata = shorts_result.data[0].get('metadata', {})
            
            # Extract music info from metadata (it's nested under 'musicInfo')
            music_info = metadata.get('musicInfo', {})
            
            # Check if metadata has music tracks
            if not music_info or (not music_info.get('track1') and not music_info.get('track2')):
                logger.info(f"No background music metadata found for short {short_id}")
                return None

            logger.info(f"Found background music metadata for short {short_id}: "
                       f"track1={music_info.get('track1', {}).get('name', 'N/A')}, "
                       f"track2={'Yes' if music_info.get('track2') else 'No'}")
            return music_info

        except Exception as e:
            logger.error(f"Failed to fetch music metadata: {e}")
            # Don't fail the entire process if music metadata fetch fails
            return None

    # def _generate_thumbnail(self, user_id: str, product_info: Dict[str, Any], task_id: str, short_id: str) -> str:
    #     """Generate thumbnail using Vertex AI - REMOVED: No longer generating thumbnails."""
    #     # This method has been removed as thumbnail generation is no longer needed
    #     pass

    # def _download_image(self, image_url: str, task_id: str) -> str:
    #     """Download generated image to temporary file - REMOVED: No longer generating thumbnails."""
    #     # This method has been removed as thumbnail generation is no longer needed
    #     pass

    # def _upload_thumbnail_from_url(self, image_url: str, user_id: str, task_id: str) -> str:
    #     """Upload thumbnail directly from URL to Supabase storage without saving to filesystem - REMOVED: No longer generating thumbnails."""
    #     # This method has been removed as thumbnail generation is no longer needed
    #     pass

    # def _upload_thumbnail(self, thumbnail_path: str, user_id: str, task_id: str) -> str:
    #     """Upload thumbnail from local file to Supabase storage - REMOVED: No longer generating thumbnails."""
    #     # This method has been removed as thumbnail generation is no longer needed
    #     pass

    # def _upload_thumbnail_fallback(self, image_url: str, user_id: str, task_id: str) -> str:
    #     """Fallback method: download image to temp file first, then upload - REMOVED: No longer generating thumbnails."""
    #     # This method has been removed as thumbnail generation is no longer needed
    #     pass

    # def _update_shorts_thumbnail(self, short_id: str, thumbnail_url: str):
    #     """Update shorts table with thumbnail URL - REMOVED: No longer generating thumbnails."""
    #     # This method has been removed as thumbnail generation is no longer needed
    #     pass

    def _download_music_file(self, music_path: str, temp_dir: str) -> Optional[str]:
        """
        Download background music file from Supabase storage.
        
        Args:
            music_path: Path to music file in Supabase (e.g., 'Music/Classical/Eternal.mp3')
            temp_dir: Temporary directory to save the downloaded file
            
        Returns:
            Path to temporary music file, or None if download fails
        """
        try:
            # Construct full Supabase URL for background music
            base_url = f"{settings.SUPABASE_URL}/storage/v1/object/public/background-music"
            music_url = f"{base_url}/{music_path}"
            
            logger.info(f"Downloading background music from: {music_url}")

            # Download music file
            with httpx.Client(timeout=DOWNLOAD_TIMEOUT) as client:
                response = client.get(music_url)
                response.raise_for_status()

                # Save to temp file
                music_filename = os.path.basename(music_path)
                temp_music_path = os.path.join(temp_dir, music_filename)
                
                with open(temp_music_path, 'wb') as f:
                    f.write(response.content)

            file_size = os.path.getsize(temp_music_path)
            logger.info(f"Successfully downloaded background music: {temp_music_path} ({file_size / 1024:.2f} KB)")
            return temp_music_path

        except Exception as e:
            logger.error(f"Failed to download background music from {music_path}: {e}")
            return None

    def _download_audio(self, audio_url: str, task_id: str) -> str:
        """
        Download audio file from Supabase storage.
        
        Converts public URL to signed URL and downloads the file.
        
        Args:
            audio_url: Public URL from database
            task_id: Task ID for logging
            
        Returns:
            Path to temporary audio file
            
        Raises:
            Exception: If URL conversion or download fails
        """
        try:
            # Convert Supabase public URL to signed URL for download
            # This will raise an exception if conversion fails (no fallback)
            try:
                download_url = self._get_signed_audio_url(audio_url)
            except Exception as url_error:
                raise Exception(
                    f"Failed to convert public URL to signed URL for audio download: {url_error}"
                )
            
            # Validate that we got a signed URL (not the original public URL)
            if download_url == audio_url:
                raise Exception(
                    f"Signed URL conversion returned original public URL. This should not happen. "
                    f"Audio URL: {audio_url}"
                )
            
            if 'token=' not in download_url:
                raise Exception(
                    f"Invalid signed URL received (missing token). Audio URL: {audio_url}, "
                    f"Signed URL: {download_url}"
                )
            
            # Create temporary file for audio
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_file:
                temp_path = temp_file.name

            # Download audio with retry logic
            download_success = False
            for attempt in range(MAX_RETRIES):
                try:
                    with httpx.Client(timeout=DOWNLOAD_TIMEOUT) as client:
                        response = client.get(download_url)
                        response.raise_for_status()

                        with open(temp_path, 'wb') as f:
                            f.write(response.content)

                    download_success = True
                    logger.info(
                        f"Successfully downloaded audio to {temp_path} on attempt {attempt + 1}"
                    )
                    break
                    
                except httpx.HTTPStatusError as e:
                    if e.response.status_code in [400, 403, 404] and 'supabase.co' in download_url:
                        logger.warning(
                            f"Attempt {attempt + 1}: Got {e.response.status_code} error for Supabase URL, "
                            f"trying to refresh signed URL: {e}"
                        )
                        # Try to refresh the signed URL (it may have expired)
                        try:
                            download_url = self._get_signed_audio_url(audio_url)
                            # Continue to next attempt with new signed URL
                        except Exception as refresh_error:
                            logger.error(
                                f"Failed to refresh signed URL on attempt {attempt + 1}: {refresh_error}"
                            )
                            if attempt == MAX_RETRIES - 1:
                                raise Exception(
                                    f"Failed to refresh signed URL after {MAX_RETRIES} attempts: {refresh_error}"
                                )
                    else:
                        logger.error(f"HTTP error downloading audio (attempt {attempt + 1}): {e}")
                        if attempt == MAX_RETRIES - 1:
                            raise Exception(
                                f"HTTP error downloading audio after {MAX_RETRIES} attempts: {e}"
                            )
                        break
                except Exception as e:
                    logger.error(f"Attempt {attempt + 1} failed: {e}")
                    if attempt < MAX_RETRIES - 1:
                        import time
                        time.sleep(RETRY_DELAY)
                    else:
                        raise Exception(
                            f"Failed to download audio after {MAX_RETRIES} attempts: {e}"
                        )
            
            if not download_success:
                raise Exception(f"Failed to download audio after {MAX_RETRIES} attempts")

            logger.info(f"Downloaded audio to {temp_path}")
            return temp_path

        except Exception as e:
            logger.error(f"Failed to download audio: {e}")
            raise

    def _get_signed_audio_url(self, audio_url: str) -> str:
        """
        Convert Supabase public storage URL to signed URL for download.
        
        This method ALWAYS converts public URLs to signed URLs. It never falls back
        to public URLs. If conversion fails, it raises an exception.
        
        Args:
            audio_url: Public URL from database (format: /storage/v1/object/public/bucket/path)
            
        Returns:
            Signed URL with token for downloading
            
        Raises:
            Exception: If URL format is invalid or signed URL creation fails
        """
        try:
            # Validate that this is a Supabase public URL
            if '/storage/v1/object/public/' not in audio_url:
                raise Exception(
                    f"Invalid audio URL format. Expected Supabase public URL with '/storage/v1/object/public/', "
                    f"got: {audio_url}"
                )
            
            # Extract bucket and path from the public URL
            # Format: https://project.supabase.co/storage/v1/object/public/bucket/path
            parts = audio_url.split('/storage/v1/object/public/')
            if len(parts) != 2:
                raise Exception(
                    f"Failed to parse audio URL. Expected format: .../storage/v1/object/public/bucket/path, "
                    f"got: {audio_url}"
                )
            
            bucket_path = parts[1]
            
            # Split bucket name and file path
            # bucket_path format: "audio-files/user_id/uuid.mp3"
            try:
                bucket_name, file_path = bucket_path.split('/', 1)
            except ValueError:
                raise Exception(
                    f"Failed to extract bucket and path from URL. "
                    f"Expected format: bucket/path, got: {bucket_path}"
                )
            
            if not bucket_name or not file_path:
                raise Exception(
                    f"Invalid bucket or path. Bucket: '{bucket_name}', Path: '{file_path}'"
                )
            
            logger.info(
                f"Converting public URL to signed URL - Bucket: {bucket_name}, Path: {file_path}"
            )
            
            # Create signed URL with 1 hour expiration
            # This works for both public and private buckets
            if not supabase_manager.is_connected():
                raise Exception("Supabase connection not available")
            
            signed_url_response = supabase_manager.client.storage.from_(bucket_name).create_signed_url(
                file_path, 3600
            )
            
            # Extract the signed URL string from the response
            signed_url = None
            if isinstance(signed_url_response, dict):
                if 'signedURL' in signed_url_response:
                    signed_url = signed_url_response['signedURL']
                elif 'signedUrl' in signed_url_response:
                    signed_url = signed_url_response['signedUrl']
                else:
                    # Try to find any URL-like property
                    for key, value in signed_url_response.items():
                        if isinstance(value, str) and value.startswith('http'):
                            signed_url = value
                            break
                    
                    if not signed_url:
                        raise Exception(
                            f"Invalid signed URL response format. Could not find signed URL in response: "
                            f"{signed_url_response}"
                        )
            elif isinstance(signed_url_response, str):
                signed_url = signed_url_response
            else:
                signed_url = str(signed_url_response)
            
            # Validate that we got a signed URL (should contain token parameter)
            if not signed_url or 'token=' not in signed_url:
                raise Exception(
                    f"Invalid signed URL received. Expected URL with token parameter, got: {signed_url}"
                )
            
            logger.info(
                f"Successfully created signed URL for audio file in bucket {bucket_name}, path: {file_path}"
            )
            return signed_url
            
        except Exception as e:
            logger.error(
                f"Failed to convert public URL to signed URL for audio. "
                f"URL: {audio_url}, Error: {e}"
            )
            raise Exception(
                f"Failed to create signed URL for audio download. "
                f"Public URL: {audio_url}, Error: {str(e)}"
            ) from e

    def _get_signed_video_url(self, video_url: str) -> str:
        """
        Convert Supabase public storage URL to signed URL for download.
        
        This method ALWAYS converts public URLs to signed URLs. It never falls back
        to public URLs. If conversion fails, it raises an exception.
        
        Args:
            video_url: Public URL from database (format: /storage/v1/object/public/bucket/path)
            
        Returns:
            Signed URL with token for downloading
            
        Raises:
            Exception: If URL format is invalid or signed URL creation fails
        """
        try:
            # Validate that this is a Supabase public URL
            if '/storage/v1/object/public/' not in video_url:
                raise Exception(
                    f"Invalid video URL format. Expected Supabase public URL with '/storage/v1/object/public/', "
                    f"got: {video_url}"
                )
            
            # Extract bucket and path from the public URL
            # Format: https://project.supabase.co/storage/v1/object/public/bucket/path
            parts = video_url.split('/storage/v1/object/public/')
            if len(parts) != 2:
                raise Exception(
                    f"Failed to parse video URL. Expected format: .../storage/v1/object/public/bucket/path, "
                    f"got: {video_url}"
                )
            
            bucket_path = parts[1]
            
            # Split bucket name and file path
            # bucket_path format: "video-files/user_id/scene_id/uuid.mp4"
            try:
                bucket_name, file_path = bucket_path.split('/', 1)
            except ValueError:
                raise Exception(
                    f"Failed to extract bucket and path from URL. "
                    f"Expected format: bucket/path, got: {bucket_path}"
                )
            
            if not bucket_name or not file_path:
                raise Exception(
                    f"Invalid bucket or path. Bucket: '{bucket_name}', Path: '{file_path}'"
                )
            
            logger.info(
                f"Converting public URL to signed URL - Bucket: {bucket_name}, Path: {file_path}"
            )
            
            # Create signed URL with 1 hour expiration
            # This works for both public and private buckets
            if not supabase_manager.is_connected():
                raise Exception("Supabase connection not available")
            
            signed_url_response = supabase_manager.client.storage.from_(bucket_name).create_signed_url(
                file_path, 3600
            )
            
            # Extract the signed URL string from the response
            signed_url = None
            if isinstance(signed_url_response, dict):
                if 'signedURL' in signed_url_response:
                    signed_url = signed_url_response['signedURL']
                elif 'signedUrl' in signed_url_response:
                    signed_url = signed_url_response['signedUrl']
                else:
                    # Try to find any URL-like property
                    for key, value in signed_url_response.items():
                        if isinstance(value, str) and value.startswith('http'):
                            signed_url = value
                            break
                    
                    if not signed_url:
                        raise Exception(
                            f"Invalid signed URL response format. Could not find signed URL in response: "
                            f"{signed_url_response}"
                        )
            elif isinstance(signed_url_response, str):
                signed_url = signed_url_response
            else:
                signed_url = str(signed_url_response)
            
            # Validate that we got a signed URL (should contain token parameter)
            if not signed_url or 'token=' not in signed_url:
                raise Exception(
                    f"Invalid signed URL received. Expected URL with token parameter, got: {signed_url}"
                )
            
            logger.info(
                f"Successfully created signed URL for video file in bucket {bucket_name}, path: {file_path}"
            )
            return signed_url
            
        except Exception as e:
            logger.error(
                f"Failed to convert public URL to signed URL for video. "
                f"URL: {video_url}, Error: {e}"
            )
            raise Exception(
                f"Failed to create signed URL for video download. "
                f"Public URL: {video_url}, Error: {str(e)}"
            ) from e

    def _handle_expired_url(self, url: str, user_id: str) -> str:
        """
        Handle expired signed URLs by converting them to public URLs or regenerating signed URLs.
        
        Args:
            url: The potentially expired URL
            user_id: The user ID for regenerating URLs if needed
            
        Returns:
            A working URL for the video
        """
        try:
            # Check if this is a Supabase signed URL
            if 'supabase.co' in url and 'token=' in url:
                logger.info(f"Detected potentially expired Supabase signed URL for user {user_id}, regenerating signed URL for private storage")
                
                # Extract the file path from the signed URL
                # URL format: https://.../storage/v1/object/sign/bucket/path?token=...
                if '/storage/v1/object/sign/' in url:
                    # Extract bucket and path from signed URL
                    parts = url.split('/storage/v1/object/sign/')
                    if len(parts) > 1:
                        bucket_path = parts[1].split('?')[0]  # Remove query parameters
                        bucket_parts = bucket_path.split('/', 1)
                        if len(bucket_parts) > 1:
                            bucket_name = bucket_parts[0]
                            file_path = bucket_parts[1]
                            
                            # For private storage, directly regenerate signed URL instead of trying public URL
                            try:
                                if not supabase_manager.is_connected():
                                    raise Exception("Supabase connection not available")
                                
                                # Regenerate signed URL for private storage
                                signed_url_response = supabase_manager.client.storage.from_(bucket_name).create_signed_url(
                                    file_path, 3600  # 1 hour expiration
                                )
                                
                                # Extract the signed URL string from the response
                                if isinstance(signed_url_response, dict):
                                    if 'signedURL' in signed_url_response:
                                        signed_url = signed_url_response['signedURL']
                                    elif 'signedUrl' in signed_url_response:
                                        signed_url = signed_url_response['signedUrl']
                                    else:
                                        # Try to find any URL-like property
                                        for key, value in signed_url_response.items():
                                            if isinstance(value, str) and value.startswith('http'):
                                                signed_url = value
                                                break
                                        else:
                                            raise Exception(f"Could not find signed URL in response: {signed_url_response}")
                                elif isinstance(signed_url_response, str):
                                    signed_url = signed_url_response
                                else:
                                    signed_url = str(signed_url_response)
                                
                                logger.info(f"Successfully regenerated signed URL for private storage: {signed_url}")
                                return signed_url
                                
                            except Exception as regen_error:
                                logger.error(f"Failed to regenerate signed URL for private storage: {regen_error}")
                                # Try to provide more specific error information
                                if "permission" in str(regen_error).lower():
                                    raise Exception(f"Permission denied when regenerating signed URL for private storage: {regen_error}")
                                elif "bucket" in str(regen_error).lower():
                                    raise Exception(f"Storage bucket access issue when regenerating signed URL: {regen_error}")
                                else:
                                    raise Exception(f"Could not regenerate signed URL for private storage: {regen_error}")
                
                # If we can't parse the URL or convert it, return the original
                logger.warning(f"Could not parse or convert expired URL for user {user_id}, returning original: {url}")
                return url
            else:
                # Not a Supabase signed URL, return as-is
                return url
                
        except Exception as e:
            logger.error(f"Error handling expired URL {url}: {e}")
            # Return original URL if we can't handle it
            return url

    def _download_videos(self, scenes_data: List[Dict[str, Any]], user_id: str) -> List[str]:
        """Download all video files from scenes."""
        try:
            video_files = []

            for scene in scenes_data:
                video_url = scene.get('generated_video_url')
                if not video_url:
                    logger.warning(f"Scene {scene.get('id')} has no generated_video_url, skipping")
                    continue

                # Convert Supabase public URL to signed URL for download
                # This will raise an exception if conversion fails (no fallback)
                try:
                    working_url = self._get_signed_video_url(video_url)
                except Exception as url_error:
                    raise Exception(
                        f"Failed to convert public URL to signed URL for scene {scene.get('id')}: {url_error}"
                    )
                
                # Validate that we got a signed URL (not the original public URL)
                if working_url == video_url:
                    raise Exception(
                        f"Signed URL conversion returned original public URL. This should not happen. "
                        f"Scene: {scene.get('id')}, URL: {video_url}"
                    )
                
                if 'token=' not in working_url:
                    raise Exception(
                        f"Invalid signed URL received (missing token). Scene: {scene.get('id')}, "
                        f"URL: {working_url}"
                    )
                
                # Create temporary file
                with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
                    temp_path = temp_file.name

                # Download video with retry logic
                download_success = False
                for attempt in range(MAX_RETRIES):
                    try:
                        with httpx.Client(timeout=DOWNLOAD_TIMEOUT) as client:
                            response = client.get(working_url)
                            response.raise_for_status()

                            with open(temp_path, 'wb') as f:
                                f.write(response.content)

                        download_success = True
                        logger.info(
                            f"Successfully downloaded video for scene {scene.get('id')} on attempt {attempt + 1}"
                        )
                        break
                        
                    except httpx.HTTPStatusError as e:
                        if e.response.status_code in [400, 403, 404] and 'supabase.co' in working_url:
                            logger.warning(
                                f"Attempt {attempt + 1}: Got {e.response.status_code} error for Supabase URL, "
                                f"trying to refresh signed URL: {e}"
                            )
                            # Try to refresh the signed URL (it may have expired)
                            try:
                                working_url = self._get_signed_video_url(video_url)
                                # Continue to next attempt with new signed URL
                            except Exception as refresh_error:
                                logger.error(
                                    f"Failed to refresh signed URL on attempt {attempt + 1}: {refresh_error}"
                                )
                                if attempt == MAX_RETRIES - 1:
                                    raise Exception(
                                        f"Failed to refresh signed URL after {MAX_RETRIES} attempts: {refresh_error}"
                                    )
                        else:
                            logger.error(f"HTTP error downloading video (attempt {attempt + 1}): {e}")
                            if attempt == MAX_RETRIES - 1:
                                raise Exception(
                                    f"HTTP error downloading video after {MAX_RETRIES} attempts: {e}"
                                )
                            break
                    except Exception as e:
                        logger.error(f"Attempt {attempt + 1} failed: {e}")
                        if attempt < MAX_RETRIES - 1:
                            import time
                            time.sleep(RETRY_DELAY)
                        else:
                            raise Exception(
                                f"Failed to download video after {MAX_RETRIES} attempts: {e}"
                            )

                if not download_success:
                    raise Exception(
                        f"Failed to download video for scene {scene.get('id')} after {MAX_RETRIES} attempts"
                    )

                video_files.append(temp_path)
                logger.info(
                    f"Downloaded video for scene {scene['id']} to {temp_path}")

            if not video_files:
                raise Exception("No videos were downloaded successfully")

            logger.info(f"Successfully downloaded {len(video_files)} videos")
            return video_files

        except Exception as e:
            logger.error(f"Failed to download videos: {e}")
            raise

    def _merge_videos(self, video_files: List[str], task_id: str) -> str:
        """Merge videos using FFmpeg."""
        try:
            if len(video_files) == 1:
                return video_files[0]

            # Create temporary directory for merged video
            temp_dir = tempfile.mkdtemp()
            merged_video_path = os.path.join(temp_dir, "merged.mp4")

            # Create file list for FFmpeg
            file_list_path = os.path.join(temp_dir, "file_list.txt")
            with open(file_list_path, 'w') as f:
                for video_file in video_files:
                    f.write(f"file '{video_file}'\n")

            # Merge videos using FFmpeg concat demuxer
            cmd = [
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', file_list_path,
                '-c', 'copy',
                merged_video_path
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes timeout
            )

            if result.returncode != 0:
                raise Exception(f"FFmpeg failed: {result.stderr}")

            if not os.path.exists(merged_video_path):
                raise Exception("Merged video file was not created")

            logger.info(
                f"Successfully merged {len(video_files)} videos to {merged_video_path}")
            return merged_video_path

        except Exception as e:
            logger.error(f"Failed to merge videos: {e}")
            raise

    def _add_watermark_if_needed(self, video_path: str, user_id: str, task_id: str) -> str:
        """Add watermark if user is on free plan."""
        try:
            # Check user's plan
            user_plan = self._get_user_plan(user_id)

            if user_plan == "free":
                logger.info(f"Adding watermark for free plan user {user_id}")
                return self._add_watermark_to_video(video_path, task_id)
            else:
                logger.info(
                    f"User {user_id} is on {user_plan} plan, no watermark needed")
                return video_path

        except Exception as e:
            logger.error(f"Failed to check user plan or add watermark: {e}")
            # Continue without watermark if there's an error
            return video_path

    def _get_user_plan(self, user_id: str) -> str:
        """Get user's subscription plan."""
        try:
            if not supabase_manager.is_connected():
                return "free"  # Default to free if can't check

            # Get user's subscription info
            result = supabase_manager.client.rpc(
                'get_user_credits',
                {'user_uuid': user_id}
            ).execute()

            if result.data:
                plan_name = result.data[0].get('plan_name', 'free')
                return plan_name if plan_name != 'no_plan' else 'free'

            return "free"

        except Exception as e:
            logger.error(f"Failed to get user plan: {e}")
            return "free"

    def _add_watermark_to_video(self, video_path: str, task_id: str) -> str:
        """Add watermark to video using FFmpeg."""
        try:
            # Create temporary directory for watermarked video
            temp_dir = tempfile.mkdtemp()
            watermarked_video_path = os.path.join(temp_dir, "watermarked.mp4")

            # Add watermark using FFmpeg with bigger, transparent gray text and subtle shadow
            cmd = [
                'ffmpeg', '-y',
                '-i', video_path,
                '-vf', 'drawtext=text=\'PromoNexAI\':fontcolor=gray@0.6:fontsize=120:x=(w-text_w)/2:y=(h-text_h)/2:shadowcolor=black@0.2:shadowx=1:shadowy=1',
                '-c:a', 'copy',
                watermarked_video_path
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes timeout
            )

            if result.returncode != 0:
                raise Exception(f"FFmpeg watermark failed: {result.stderr}")

            if not os.path.exists(watermarked_video_path):
                raise Exception("Watermarked video file was not created")

            logger.info(f"Successfully added watermark to video")
            return watermarked_video_path

        except Exception as e:
            logger.error(f"Failed to add watermark: {e}")
            raise


    def _check_video_has_audio(self, video_path: str) -> bool:
        """Check if video file has an audio stream using FFprobe."""
        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-select_streams', 'a',
                '-show_entries', 'stream=codec_type',
                '-of', 'csv=p=0',
                video_path
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                # If there's an audio stream, ffprobe will output "audio"
                has_audio = "audio" in result.stdout.strip()
                logger.info(f"Video {video_path} has audio: {has_audio}")
                return has_audio
            else:
                logger.warning(f"Could not check for audio stream, assuming no audio: {result.stderr}")
                return False

        except Exception as e:
            logger.warning(f"Failed to check for audio stream: {e}, assuming no audio")
            return False

    def _get_video_duration(self, video_path: str) -> int:
        """Get video duration in seconds using FFmpeg."""
        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-show_entries', 'format=duration',
                '-of', 'csv=p=0',
                video_path
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                duration = float(result.stdout.strip())
                return int(duration)
            else:
                logger.warning(
                    f"Could not get video duration, defaulting to 30 seconds: {result.stderr}")
                return 30

        except Exception as e:
            logger.warning(
                f"Failed to get video duration: {e}, defaulting to 30 seconds")
            return 30


    def _merge_audio_with_video(self, video_path: str, audio_path: str, task_id: str, music_files: List[str] = None) -> str:
        """
        Merge audio with video using FFmpeg, mixing video sound effects, voice script, and optional background music.
        
        Args:
            video_path: Path to the video file
            audio_path: Path to the voice audio file
            task_id: Task ID for logging
            music_files: Optional list of background music file paths (1 or 2 tracks)
            
        Returns:
            Path to the merged video file
        """
        try:
            # First check if the video has an audio stream
            has_audio = self._check_video_has_audio(video_path)
            
            if not has_audio:
                logger.info("Video has no audio stream, using voice-only approach")
                return self._merge_audio_with_video_basic(video_path, audio_path, task_id, music_files)

            # Create temporary directory for merged video
            temp_dir = tempfile.mkdtemp()
            merged_path = os.path.join(temp_dir, "video_with_audio.mp4")

            # Get video duration for proper audio mixing
            video_duration = self._get_video_duration(video_path)

            # Build FFmpeg command based on available inputs
            if music_files and len(music_files) > 0:
                logger.info(f"Merging with background music: {len(music_files)} track(s)")
                
                # Merge audio with video including background music
                if len(music_files) == 1:
                    # Single music track (24s video)
                    cmd = [
                        'ffmpeg', '-y',
                        '-i', video_path,      # Input 0: video with sound effects
                        '-i', audio_path,      # Input 1: voice script audio
                        '-i', music_files[0],  # Input 2: background music
                        '-c:v', 'copy',        # Copy video codec without re-encoding
                        '-filter_complex', 
                        '[0:a]volume=0.2[vid_audio];'
                        '[1:a]volume=1.0[voice_audio];'
                        '[2:a]volume=0.4[bg_music];'
                        '[vid_audio][voice_audio][bg_music]amix=inputs=3:duration=longest:dropout_transition=2[out]',
                        '-map', '0:v',         # Map video from first input
                        '-map', '[out]',       # Map the mixed audio output
                        '-c:a', 'aac',         # Convert mixed audio to AAC
                        merged_path
                    ]
                else:
                    # Two music tracks (48s video) - concatenate them first
                    cmd = [
                        'ffmpeg', '-y',
                        '-i', video_path,      # Input 0: video with sound effects
                        '-i', audio_path,      # Input 1: voice script audio
                        '-i', music_files[0],  # Input 2: background music track1
                        '-i', music_files[1],  # Input 3: background music track2
                        '-c:v', 'copy',        # Copy video codec without re-encoding
                        '-filter_complex',
                        '[2:a][3:a]concat=n=2:v=0:a=1[bgmusic];'
                        '[0:a]volume=0.2[vid_audio];'
                        '[1:a]volume=1.0[voice_audio];'
                        '[bgmusic]volume=0.4[bg_audio];'
                        '[vid_audio][voice_audio][bg_audio]amix=inputs=3:duration=longest:dropout_transition=2[out]',
                        '-map', '0:v',         # Map video from first input
                        '-map', '[out]',       # Map the mixed audio output
                        '-c:a', 'aac',         # Convert mixed audio to AAC
                        merged_path
                    ]
            else:
                # No background music - original behavior
                logger.info("Merging without background music")
                cmd = [
                    'ffmpeg', '-y',
                    '-i', video_path,      # Input 0: video with sound effects
                    '-i', audio_path,      # Input 1: voice script audio
                    '-c:v', 'copy',        # Copy video codec without re-encoding
                    '-filter_complex', 
                    '[0:a]volume=0.3[vid_audio];'
                    '[1:a]volume=1.0[voice_audio];'
                    '[vid_audio][voice_audio]amix=inputs=2:duration=longest:dropout_transition=2[out]',
                    '-map', '0:v',         # Map video from first input
                    '-map', '[out]',       # Map the mixed audio output
                    '-c:a', 'aac',         # Convert mixed audio to AAC
                    merged_path
                ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes timeout
            )

            if result.returncode != 0:
                # If the complex filter fails, try a simpler approach
                logger.warning(f"Complex audio mixing failed, trying simpler approach: {result.stderr}")
                return self._merge_audio_with_video_simple(video_path, audio_path, task_id, music_files)

            if not os.path.exists(merged_path):
                raise Exception("Audio-merged video file was not created")

            logger.info(f"Successfully merged audio with video using complex mixing")
            return merged_path

        except Exception as e:
            logger.error(f"Failed to merge audio with video: {e}")
            raise

    def _merge_audio_with_video_simple(self, video_path: str, audio_path: str, task_id: str, music_files: List[str] = None) -> str:
        """Fallback method for merging audio with video using a simpler approach."""
        try:
            # First check if the video has an audio stream
            has_audio = self._check_video_has_audio(video_path)
            
            if not has_audio:
                logger.info("Video has no audio stream, using voice-only approach")
                return self._merge_audio_with_video_basic(video_path, audio_path, task_id, music_files)

            # Create temporary directory for merged video
            temp_dir = tempfile.mkdtemp()
            merged_path = os.path.join(temp_dir, "video_with_audio_simple.mp4")

            # Build simpler FFmpeg command
            if music_files and len(music_files) > 0:
                logger.info(f"Simple merge with background music: {len(music_files)} track(s)")
                
                if len(music_files) == 1:
                    cmd = [
                        'ffmpeg', '-y',
                        '-i', video_path,
                        '-i', audio_path,
                        '-i', music_files[0],
                        '-c:v', 'copy',
                        '-filter_complex',
                        '[0:a]volume=0.3[vid_audio];'
                        '[1:a]volume=1.0[voice_audio];'
                        '[2:a]volume=0.4[bg_music];'
                        '[vid_audio][voice_audio][bg_music]amix=inputs=3[out]',
                        '-map', '0:v',
                        '-map', '[out]',
                        '-c:a', 'aac',
                        merged_path
                    ]
                else:
                    cmd = [
                        'ffmpeg', '-y',
                        '-i', video_path,
                        '-i', audio_path,
                        '-i', music_files[0],
                        '-i', music_files[1],
                        '-c:v', 'copy',
                        '-filter_complex',
                        '[2:a][3:a]concat=n=2:v=0:a=1[bgmusic];'
                        '[0:a]volume=0.3[vid_audio];'
                        '[1:a]volume=1.0[voice_audio];'
                        '[bgmusic]volume=0.4[bg_audio];'
                        '[vid_audio][voice_audio][bg_audio]amix=inputs=3[out]',
                        '-map', '0:v',
                        '-map', '[out]',
                        '-c:a', 'aac',
                        merged_path
                    ]
            else:
                # Simpler approach: mix audio streams using amix with volume adjustments
                cmd = [
                    'ffmpeg', '-y',
                    '-i', video_path,      # Input 0: video with sound effects
                    '-i', audio_path,      # Input 1: voice script audio
                    '-c:v', 'copy',        # Copy video codec
                    '-filter_complex', '[0:a]volume=0.5[vid_audio];[1:a]volume=1.0[voice_audio];[vid_audio][voice_audio]amix=inputs=2[out]',  # Mix with volume adjustments
                    '-map', '0:v',         # Map video from first input
                    '-map', '[out]',       # Map the mixed audio output
                    '-c:a', 'aac',         # Convert mixed audio to AAC
                    merged_path
                ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes timeout
            )

            if result.returncode != 0:
                # If even the simple approach fails, try the voice-priority method
                logger.warning(f"Simple audio mixing failed, trying voice-priority approach: {result.stderr}")
                return self._merge_audio_with_video_voice_priority(video_path, audio_path, task_id, music_files)

            if not os.path.exists(merged_path):
                raise Exception("Audio-merged video file was not created")

            logger.info(f"Successfully merged audio with video using simple mixing")
            return merged_path

        except Exception as e:
            logger.error(f"Failed to merge audio with video (simple): {e}")
            raise

    def _merge_audio_with_video_voice_priority(self, video_path: str, audio_path: str, task_id: str, music_files: List[str] = None) -> str:
        """Voice-priority fallback method for merging audio with video."""
        try:
            # First check if the video has an audio stream
            has_audio = self._check_video_has_audio(video_path)
            
            if not has_audio:
                logger.info("Video has no audio stream, using basic approach")
                return self._merge_audio_with_video_basic(video_path, audio_path, task_id, music_files)

            # Create temporary directory for merged video
            temp_dir = tempfile.mkdtemp()
            merged_path = os.path.join(temp_dir, "video_with_audio_voice_priority.mp4")

            # Build FFmpeg command based on whether we have background music
            if music_files and len(music_files) > 0:
                logger.info(f"Voice-priority merge with background music: {len(music_files)} track(s)")
                
                if len(music_files) == 1:
                    # Video sound + voice + single music track
                    cmd = [
                        'ffmpeg', '-y',
                        '-i', video_path,       # Input 0: video with sound effects
                        '-i', audio_path,       # Input 1: voice audio
                        '-i', music_files[0],   # Input 2: background music
                        '-filter_complex',
                        '[0:a]volume=0.15[vid_audio];'
                        '[1:a]volume=1.0[voice];'
                        '[2:a]volume=0.4[music];'
                        '[vid_audio][voice][music]amix=inputs=3:duration=longest:dropout_transition=2[out]',
                        '-map', '0:v',
                        '-map', '[out]',
                        '-c:v', 'copy',
                        '-c:a', 'aac',
                        merged_path
                    ]
                else:
                    # Video sound + voice + two music tracks
                    cmd = [
                        'ffmpeg', '-y',
                        '-i', video_path,       # Input 0: video with sound effects
                        '-i', audio_path,       # Input 1: voice audio
                        '-i', music_files[0],   # Input 2: background music track1
                        '-i', music_files[1],   # Input 3: background music track2
                        '-filter_complex',
                        '[2:a][3:a]concat=n=2:v=0:a=1[bgmusic];'
                        '[0:a]volume=0.15[vid_audio];'
                        '[1:a]volume=1.0[voice];'
                        '[bgmusic]volume=0.4[music];'
                        '[vid_audio][voice][music]amix=inputs=3:duration=longest:dropout_transition=2[out]',
                        '-map', '0:v',
                        '-map', '[out]',
                        '-c:v', 'copy',
                        '-c:a', 'aac',
                        merged_path
                    ]
            else:
                # No background music - voice-priority approach (original)
                logger.info("Voice-priority merge: video sound + voice (no background music)")
                cmd = [
                    'ffmpeg', '-y',
                    '-i', video_path,      # Input 0: video with sound effects
                    '-i', audio_path,      # Input 1: voice script audio
                    '-c:v', 'copy',        # Copy video codec
                    '-filter_complex', '[0:a]volume=0.2[vid_audio];[1:a]volume=1.0[voice_audio];[vid_audio][voice_audio]amix=inputs=2:duration=longest:dropout_transition=2[out]',
                    '-map', '0:v',         # Map video from first input
                    '-map', '[out]',       # Map the mixed audio output
                    '-c:a', 'aac',         # Convert mixed audio to AAC
                    merged_path
                ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes timeout
            )

            if result.returncode != 0:
                # If this fails too, try the basic approach
                logger.warning(f"Voice-priority mixing failed, trying basic approach: {result.stderr}")
                return self._merge_audio_with_video_basic(video_path, audio_path, task_id, music_files)

            if not os.path.exists(merged_path):
                raise Exception("Audio-merged video file was not created")

            if music_files and len(music_files) > 0:
                logger.info(f"Successfully merged audio with video using voice-priority (with {len(music_files)} music track(s))")
            else:
                logger.info(f"Successfully merged audio with video using voice-priority")
            return merged_path

        except Exception as e:
            logger.error(f"Failed to merge audio with video (voice-priority): {e}")
            raise

    def _merge_audio_with_video_basic(self, video_path: str, audio_path: str, task_id: str, music_files: List[str] = None) -> str:
        """Most basic fallback method for merging audio with video."""
        try:
            # Create temporary directory for merged video
            temp_dir = tempfile.mkdtemp()
            merged_path = os.path.join(temp_dir, "video_with_audio_basic.mp4")

            # Build FFmpeg command based on whether we have background music
            if music_files and len(music_files) > 0:
                logger.info(f"Basic merge with background music: {len(music_files)} track(s)")
                
                if len(music_files) == 1:
                    # Voice + single music track (24s video)
                    cmd = [
                        'ffmpeg', '-y',
                        '-i', video_path,       # Input 0: video (no audio or we ignore it)
                        '-i', audio_path,       # Input 1: voice audio
                        '-i', music_files[0],   # Input 2: background music
                        '-filter_complex',
                        '[1:a]volume=1.0[voice];'
                        '[2:a]volume=0.4[music];'
                        '[voice][music]amix=inputs=2:duration=longest[out]',
                        '-map', '0:v',          # Map video from first input
                        '-map', '[out]',        # Map mixed audio
                        '-c:v', 'copy',         # Copy video codec
                        '-c:a', 'aac',          # Convert audio to AAC
                        merged_path
                    ]
                else:
                    # Voice + two music tracks (48s video) - concatenate music first
                    cmd = [
                        'ffmpeg', '-y',
                        '-i', video_path,       # Input 0: video (no audio or we ignore it)
                        '-i', audio_path,       # Input 1: voice audio
                        '-i', music_files[0],   # Input 2: background music track1
                        '-i', music_files[1],   # Input 3: background music track2
                        '-filter_complex',
                        '[2:a][3:a]concat=n=2:v=0:a=1[bgmusic];'
                        '[1:a]volume=1.0[voice];'
                        '[bgmusic]volume=0.4[music];'
                        '[voice][music]amix=inputs=2:duration=longest[out]',
                        '-map', '0:v',          # Map video from first input
                        '-map', '[out]',        # Map mixed audio
                        '-c:v', 'copy',         # Copy video codec
                        '-c:a', 'aac',          # Convert audio to AAC
                        merged_path
                    ]
            else:
                # No background music - voice only (original behavior)
                logger.info("Basic merge: voice only (no background music)")
                cmd = [
                    'ffmpeg', '-y',
                    '-i', video_path,
                    '-i', audio_path,
                    '-c:v', 'copy',        # Copy video codec
                    '-c:a', 'aac',         # Convert audio to AAC
                    '-map', '0:v',         # Map video from first input
                    '-map', '1:a',         # Map audio from second input (voice script)
                    merged_path
                ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes timeout
            )

            if result.returncode != 0:
                raise Exception(f"FFmpeg audio merge failed (basic): {result.stderr}")

            if not os.path.exists(merged_path):
                raise Exception("Audio-merged video file was not created")

            if music_files and len(music_files) > 0:
                logger.info(f"Successfully merged audio with video using basic approach (voice + {len(music_files)} music track(s))")
            else:
                logger.info(f"Successfully merged audio with video using basic approach (voice only)")
            return merged_path

        except Exception as e:
            logger.error(f"Failed to merge audio with video (basic): {e}")
            raise

    def _merge_music_with_video(self, video_path: str, task_id: str, music_files: List[str]) -> str:
        """
        Merge only background music with video (no voice audio).
        Mixes video sound effects with background music.
        
        Args:
            video_path: Path to the video file
            task_id: Task ID for logging
            music_files: List of background music file paths (1 or 2 tracks)
            
        Returns:
            Path to the merged video file
        """
        try:
            # Create temporary directory for merged video
            temp_dir = tempfile.mkdtemp()
            merged_path = os.path.join(temp_dir, "video_with_music.mp4")

            # Check if video has audio stream
            has_audio = self._check_video_has_audio(video_path)
            
            if has_audio:
                # Video has audio (sound effects) - mix it with background music
                if len(music_files) == 1:
                    # Single music track (24s video)
                    logger.info(f"Merging video audio + 1 background music track")
                    cmd = [
                        'ffmpeg', '-y',
                        '-i', video_path,       # Input 0: video with sound effects
                        '-i', music_files[0],   # Input 1: background music
                        '-filter_complex',
                        '[0:a]volume=0.2[vid_audio];'
                        '[1:a]volume=0.4[bg_music];'
                        '[vid_audio][bg_music]amix=inputs=2:duration=longest:dropout_transition=2[out]',
                        '-map', '0:v',          # Map video from first input
                        '-map', '[out]',        # Map mixed audio
                        '-c:v', 'copy',         # Copy video codec
                        '-c:a', 'aac',          # Convert audio to AAC
                        merged_path
                    ]
                else:
                    # Two music tracks (48s video) - concatenate music first
                    logger.info(f"Merging video audio + 2 background music tracks")
                    cmd = [
                        'ffmpeg', '-y',
                        '-i', video_path,       # Input 0: video with sound effects
                        '-i', music_files[0],   # Input 1: background music track1
                        '-i', music_files[1],   # Input 2: background music track2
                        '-filter_complex',
                        '[1:a][2:a]concat=n=2:v=0:a=1[bgmusic];'
                        '[0:a]volume=0.2[vid_audio];'
                        '[bgmusic]volume=0.4[bg_music];'
                        '[vid_audio][bg_music]amix=inputs=2:duration=longest:dropout_transition=2[out]',
                        '-map', '0:v',          # Map video from first input
                        '-map', '[out]',        # Map mixed audio
                        '-c:v', 'copy',         # Copy video codec
                        '-c:a', 'aac',          # Convert audio to AAC
                        merged_path
                    ]
            else:
                # Video has no audio - just add background music
                if len(music_files) == 1:
                    # Single music track (24s video)
                    logger.info(f"Adding 1 background music track to silent video")
                    cmd = [
                        'ffmpeg', '-y',
                        '-i', video_path,       # Input 0: video (no audio)
                        '-i', music_files[0],   # Input 1: background music
                        '-filter_complex',
                        '[1:a]volume=0.4[out]',
                        '-map', '0:v',          # Map video from first input
                        '-map', '[out]',        # Map music as audio
                        '-c:v', 'copy',         # Copy video codec
                        '-c:a', 'aac',          # Convert audio to AAC
                        '-shortest',            # Match shortest stream duration
                        merged_path
                    ]
                else:
                    # Two music tracks (48s video) - concatenate music
                    logger.info(f"Adding 2 background music tracks to silent video")
                    cmd = [
                        'ffmpeg', '-y',
                        '-i', video_path,       # Input 0: video (no audio)
                        '-i', music_files[0],   # Input 1: background music track1
                        '-i', music_files[1],   # Input 2: background music track2
                        '-filter_complex',
                        '[1:a][2:a]concat=n=2:v=0:a=1[bgmusic];'
                        '[bgmusic]volume=0.4[out]',
                        '-map', '0:v',          # Map video from first input
                        '-map', '[out]',        # Map concatenated music as audio
                        '-c:v', 'copy',         # Copy video codec
                        '-c:a', 'aac',          # Convert audio to AAC
                        '-shortest',            # Match shortest stream duration
                        merged_path
                    ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes timeout
            )

            if result.returncode != 0:
                raise Exception(f"FFmpeg music merge failed: {result.stderr}")

            if not os.path.exists(merged_path):
                raise Exception("Music-merged video file was not created")

            logger.info(f"Successfully merged background music with video")
            return merged_path

        except Exception as e:
            logger.error(f"Failed to merge background music with video: {e}")
            raise

    def _embed_subtitles(self, video_path: str, subtitles: List[Dict[str, Any]], task_id: str) -> str:
        """Embed subtitles into video using FFmpeg with SRT format."""
        try:
            # Create temporary directory at the same level as the app directory
            app_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            temp_dir = os.path.join(app_dir, "temp_subtitles")
            
            # Create the temp directory if it doesn't exist
            if not os.path.exists(temp_dir):
                os.makedirs(temp_dir)
            
            subtitled_path = os.path.join(temp_dir, "video_with_subtitles.mp4")

            # Create SRT file from subtitles data
            srt_path = os.path.join(temp_dir, "subtitles.srt")
            self._create_srt_file(subtitles, srt_path)

            # Convert Windows path to proper format for FFmpeg
            # Use forward slashes for FFmpeg on Windows - it handles them better
            escaped_srt_path = srt_path.replace('\\', '/').replace(':', '\\:')
            
            # Get appropriate font for the language
            font_name = self._get_subtitle_font()
            
            cmd = [
                'ffmpeg', '-y',
                '-i', video_path,
                '-vf', f"subtitles='{escaped_srt_path}':force_style='FontSize=16,Bold=1,FontName={font_name},PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&,Outline=1,Shadow=1,BackColour=&H000000&'",
                '-c:a', 'copy',  # Copy audio codec
                subtitled_path
            ]

            # Log the command for debugging
            logger.info(f"FFmpeg command: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes timeout
            )

            if result.returncode != 0:
                raise Exception(f"FFmpeg subtitle embedding failed: {result.stderr}")

            if not os.path.exists(subtitled_path):
                raise Exception("Subtitled video file was not created")
            
            logger.info(f"Successfully embedded subtitles into video")

            # Don't clean up temporary directory here - let the caller handle cleanup
            # This ensures the file exists when the upload method tries to access it

            return subtitled_path

        except Exception as e:
            logger.error(f"Failed to embed subtitles: {e}")
            # Clean up temporary files
            try:
                if 'temp_dir' in locals() and os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
            except Exception as cleanup_error:
                logger.warning(
                    f"Failed to clean up temporary directory: {cleanup_error}")
            raise

    def _get_subtitle_font(self) -> str:
        """Get appropriate font for subtitles based on system."""
        try:
            # Common fonts that work well across different systems
            common_fonts = [
                'Arial',
                'Helvetica',
                'DejaVu Sans',
                'Liberation Sans',
                'FreeSans',
                'Verdana'
            ]
            
            # For Windows, Arial is usually available
            if os.name == 'nt':  # Windows
                return 'Arial'
            else:
                # For Unix-like systems, try to find a common font
                return 'DejaVu Sans'
                
        except Exception as e:
            logger.warning(f"Could not determine subtitle font, using default: {e}")
            return 'Arial'

    def _create_srt_file(self, subtitles: List[Dict[str, Any]], srt_path: str):
        """Create SRT file from subtitles data."""
        try:
            with open(srt_path, 'w', encoding='utf-8') as f:
                for i, subtitle in enumerate(subtitles, 1):
                    start_time = subtitle.get('start_time', 0)
                    end_time = subtitle.get('end_time', 0)
                    text = subtitle.get('text', '')

                    # Convert seconds to SRT time format (HH:MM:SS,mmm)
                    start_srt = self._seconds_to_srt_time(start_time)
                    end_srt = self._seconds_to_srt_time(end_time)

                    f.write(f"{i}\n")
                    f.write(f"{start_srt} --> {end_srt}\n")
                    f.write(f"{text}\n\n")

            logger.info(f"Created SRT file at {srt_path}")

        except Exception as e:
            logger.error(f"Failed to create SRT file: {e}")
            raise
        

    def _seconds_to_srt_time(self, seconds: float) -> str:
        """Convert seconds to SRT time format (HH:MM:SS,mmm)."""
        try:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            milliseconds = int((seconds % 1) * 1000)

            return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"

        except Exception as e:
            logger.error(f"Failed to convert seconds to SRT time: {e}")
            return "00:00:00,000"

    def _upload_final_video(self, video_path: str, short_id: str, task_id: str) -> str:
        """Upload final video to Supabase storage."""
        try:
            if not supabase_manager.is_connected():
                raise Exception("Supabase connection not available")

            # Validate that the video file exists before attempting upload
            if not os.path.exists(video_path):
                raise Exception(f"Video file not found at path: {video_path}")
            
            # Check file size to ensure it's not empty
            file_size = os.path.getsize(video_path)
            if file_size == 0:
                raise Exception(f"Video file is empty (0 bytes) at path: {video_path}")
            
            logger.info(f"Uploading video file: {video_path} (size: {file_size} bytes)")

            # Create storage path
            filename = f"final_videos/{short_id}/{uuid.uuid4()}.mp4"

            # Upload to Supabase storage
            with open(video_path, 'rb') as f:
                result = supabase_manager.client.storage.from_('generated-content').upload(
                    path=filename,
                    file=f,
                    file_options={"content-type": "video/mp4"}
                )

            # Check for upload errors
            if hasattr(result, 'error') and result.error:
                raise Exception(
                    f"Failed to upload final video: {result.error}")

            # Get public URL
            final_video_url = supabase_manager.client.storage.from_(
                'generated-content').get_public_url(filename)

            logger.info(
                f"Successfully uploaded final video to {final_video_url}")
            return final_video_url

        except Exception as e:
            logger.error(f"Failed to upload final video: {e}")
            raise

    def _update_shorts_final_video(self, short_id: str, final_video_url: str):
        """Update shorts table with final video URL."""
        try:
            if not supabase_manager.is_connected():
                raise Exception("Supabase connection not available")

            result = supabase_manager.client.table('shorts').update({
                'final_video_url': final_video_url,  # Using correct final_video_url field
                'status': 'completed',
                'updated_at': datetime.utcnow().isoformat()
            }).eq('id', short_id).execute()

            # Check for update errors
            if hasattr(result, 'error') and result.error:
                raise Exception(
                    f"Failed to update shorts final video: {result.error}")

            logger.info(
                f"Updated shorts {short_id} with final video URL and completed status")

        except Exception as e:
            logger.error(f"Failed to update shorts final video: {e}")
            raise

    def _cleanup_temp_files(self, file_paths: List[str]):
        """Clean up temporary files."""
        try:
            for file_path in file_paths:
                if os.path.exists(file_path):
                    os.remove(file_path)

                    # Also remove parent directory if empty
                    parent_dir = os.path.dirname(file_path)
                    if os.path.exists(parent_dir) and not os.listdir(parent_dir):
                        os.rmdir(parent_dir)
                        logger.info(f"Cleaned up empty directory: {parent_dir}")

        except Exception as e:
            logger.warning(f"Failed to cleanup some temporary files: {e}")

    def _cleanup_subtitle_temp_dirs(self):
        """Clean up subtitle temporary directories that may have been created."""
        try:
            # Clean up the subtitle temp directory at the same level as the app directory
            app_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            temp_dir = os.path.join(app_dir, "temp_subtitles")
            
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                    
        except Exception as e:
            logger.warning(f"Failed to cleanup subtitle temp directory: {e}")

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of a finalization task."""
        try:
            return get_task_status(task_id)
        except Exception as e:
            logger.error(f"Failed to get task status for {task_id}: {e}")
            return None

    def cleanup(self):
        """Clean up completed tasks and threads."""
        try:
            # Clean up completed threads
            completed_tasks = []
            for task_id, thread in self._active_threads.items():
                if not thread.is_alive():
                    completed_tasks.append(task_id)

            for task_id in completed_tasks:
                del self._active_threads[task_id]

            logger.info(
                f"Cleaned up {len(completed_tasks)} completed finalization tasks")

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    def test_supabase_connection(self) -> Dict[str, Any]:
        """Test Supabase connection and storage access."""
        try:
            logger.info("Testing Supabase connection...")

            if not supabase_manager.is_connected():
                return {"success": False, "error": "Supabase not connected"}

            # Test basic connection
            try:
                # Test a simple query
                result = supabase_manager.client.table(
                    'shorts').select('id').limit(1).execute()
                logger.info("Basic Supabase connection test passed")
            except Exception as e:
                logger.error(f"Basic connection test failed: {e}")
                return {"success": False, "error": f"Basic connection failed: {e}"}

            # Test storage access
            try:
                buckets = supabase_manager.client.storage.list_buckets()
                bucket_names = [bucket.name for bucket in buckets]
                logger.info(f"Available storage buckets: {bucket_names}")

                if 'generated-content' not in bucket_names:
                    return {"success": False, "error": "Storage bucket 'generated-content' not found"}

                logger.info("Storage access test passed")

            except Exception as e:
                logger.error(f"Storage access test failed: {e}")
                return {"success": False, "error": f"Storage access failed: {e}"}

            return {"success": True, "message": "All tests passed"}

        except Exception as e:
            logger.error(f"Supabase connection test failed: {e}")
            return {"success": False, "error": str(e)}


# Global instance
merging_service = MergingService()
