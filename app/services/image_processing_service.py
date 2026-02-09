"""
Image Processing Service

This module provides image processing capabilities including:
- Background removal using Remove.bg API
- Image compositing (merging two images)
- Supabase storage integration
"""

import os
import uuid
import tempfile
import requests
import httpx
import subprocess
import math
from io import BytesIO
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from pathlib import Path
from PIL import Image
import cv2
import numpy as np

from app.logging_config import get_logger
from app.utils.supabase_utils import supabase_manager
from app.config import settings

logger = get_logger(__name__)

# Timeout configurations
HTTP_TIMEOUT = 300  # 5 minutes for HTTP operations
DOWNLOAD_TIMEOUT = 600  # 10 minutes for file downloads
UPLOAD_TIMEOUT = 900  # 15 minutes for file uploads
MAX_RETRIES = 3  # Maximum retry attempts for failed operations
RETRY_DELAY = 5  # Seconds to wait between retries

# Remove.bg API configuration
REMOVEBG_API_KEY = os.getenv("REMOVEBG_API_KEY", "")
REMOVEBG_API_URL = "https://api.remove.bg/v1.0/removebg"


class ImageProcessingService:
    """Service for processing images including background removal and compositing."""

    def __init__(self):
        self._temp_dir = self._get_temp_dir()
        self._check_ffmpeg()

    def _get_temp_dir(self) -> Path:
        """Get or create the temp directory for temporary files."""
        project_root = Path(__file__).parent.parent.parent
        temp_dir = project_root / "temp"
        temp_dir.mkdir(exist_ok=True)
        return temp_dir
    
    def _check_ffmpeg(self):
        """Check if FFmpeg is available."""
        try:
            result = subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                logger.info("✅ FFmpeg is available for video processing")
            else:
                logger.warning("⚠️  FFmpeg check returned non-zero exit code")
        except FileNotFoundError:
            logger.error("❌ FFmpeg not found! Video merge will fail. Install from: https://ffmpeg.org/download.html")
        except Exception as e:
            logger.warning(f"⚠️  Could not check FFmpeg availability: {e}")

    def remove_background(self, image_url: str, scene_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Remove background from an image using Remove.bg API.

        Args:
            image_url: URL of the image to process
            scene_id: Optional scene ID for organizing files

        Returns:
            Dict containing:
                - success (bool): Whether the operation succeeded
                - image_url (str): URL of the background-removed image in Supabase (if successful)
                - local_path (str): Local path of the processed image (if successful)
                - error (str): Error message (if failed)
        """
        temp_input_path = None
        temp_output_path = None

        try:
            logger.info(f"Starting background removal for image: {image_url}")

            # Validate API key
            if not REMOVEBG_API_KEY:
                raise Exception("Remove.bg API key not configured. Please set REMOVEBG_API_KEY in .env file")

            # Download the image from URL
            logger.info("Downloading image from URL...")
            temp_input_path = self._download_image_from_url(image_url)

            # Call Remove.bg API
            logger.info("Calling Remove.bg API...")
            temp_output_path = self._call_removebg_api(temp_input_path)

            # Upload to Supabase storage
            logger.info("Uploading processed image to Supabase...")
            supabase_url = self._upload_to_supabase(
                temp_output_path,
                folder="background-removed",
                scene_id=scene_id
            )

            logger.info(f"Background removal completed successfully. Image URL: {supabase_url}")

            return {
                'success': True,
                'image_url': supabase_url,
                'local_path': temp_output_path,
                'error': None
            }

        except Exception as e:
            error_msg = f"Background removal failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                'success': False,
                'image_url': None,
                'local_path': None,
                'error': error_msg
            }

        finally:
            # Clean up temporary input file
            if temp_input_path and os.path.exists(temp_input_path):
                try:
                    os.unlink(temp_input_path)
                    logger.debug(f"Cleaned up temporary input file: {temp_input_path}")
                except Exception as cleanup_error:
                    logger.warning(f"Failed to clean up temporary input file {temp_input_path}: {cleanup_error}")

    def _call_removebg_api(self, image_path: str) -> str:
        """
        Call Remove.bg API to remove background from image.

        Args:
            image_path: Path to the local image file

        Returns:
            Path to the output image file with background removed
        """
        try:
            # Prepare output path
            output_path = str(self._temp_dir / f"no-bg-{uuid.uuid4()}.png")

            # Call Remove.bg API
            with open(image_path, 'rb') as image_file:
                response = requests.post(
                    REMOVEBG_API_URL,
                    files={'image_file': image_file},
                    data={'size': 'auto'},
                    headers={'X-Api-Key': REMOVEBG_API_KEY},
                    timeout=HTTP_TIMEOUT
                )

            # Check response
            if response.status_code == requests.codes.ok:
                # Save the result
                with open(output_path, 'wb') as out_file:
                    out_file.write(response.content)
                logger.info(f"Background removed successfully. Output saved to: {output_path}")
                return output_path
            else:
                error_msg = f"Remove.bg API error: {response.status_code} - {response.text}"
                logger.error(error_msg)
                raise Exception(error_msg)

        except requests.exceptions.Timeout:
            raise Exception("Remove.bg API request timed out")
        except requests.exceptions.RequestException as e:
            raise Exception(f"Remove.bg API request failed: {str(e)}")
        except Exception as e:
            raise Exception(f"Failed to call Remove.bg API: {str(e)}")

    def composite_images(
        self,
        background_url: str,
        overlay_url: str,
        scene_id: str,
        user_id: str,
        position: Tuple[int, int] = (0, 0),
        resize_overlay: bool = True
    ) -> Dict[str, Any]:
        """
        Composite two images together (overlay on top of background).

        Args:
            background_url: URL of the background image
            overlay_url: URL of the overlay image (typically background-removed product)
            scene_id: Scene ID for organizing files and updating database
            user_id: User ID for organizing files
            position: (x, y) position to place overlay on background (default: centered)
            resize_overlay: Whether to resize overlay to fit background (default: True)

        Returns:
            Dict containing:
                - success (bool): Whether the operation succeeded
                - image_url (str): URL of the composited image in Supabase (if successful)
                - error (str): Error message (if failed)
        """
        temp_bg_path = None
        temp_overlay_path = None
        temp_output_path = None

        try:
            logger.info(f"Starting image compositing for scene {scene_id}")

            # Download both images
            logger.info("Downloading background image...")
            temp_bg_path = self._download_image_from_url(background_url)

            logger.info("Downloading overlay image...")
            temp_overlay_path = self._download_image_from_url(overlay_url)

            # Composite the images
            logger.info("Compositing images...")
            temp_output_path = self._composite_images_locally(
                temp_bg_path,
                temp_overlay_path,
                position,
                resize_overlay
            )

            # Upload to Supabase storage
            logger.info("Uploading composited image to Supabase...")
            supabase_url = self._upload_to_supabase(
                temp_output_path,
                folder="composited-images",
                scene_id=scene_id,
                user_id=user_id
            )

            # Update the scene's image_url in the database (only if real scene_id provided)
            if scene_id and scene_id not in ["temp", "anonymous", ""]:
                logger.info(f"Updating scene {scene_id} with new image URL...")
                self._update_scene_image_url(scene_id, supabase_url)

            logger.info(f"Image compositing completed successfully. Image URL: {supabase_url}")

            return {
                'success': True,
                'image_url': supabase_url,
                'error': None
            }

        except Exception as e:
            error_msg = f"Image compositing failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                'success': False,
                'image_url': None,
                'error': error_msg
            }

        finally:
            # Clean up temporary files
            for temp_path in [temp_bg_path, temp_overlay_path, temp_output_path]:
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.unlink(temp_path)
                        logger.debug(f"Cleaned up temporary file: {temp_path}")
                    except Exception as cleanup_error:
                        logger.warning(f"Failed to clean up temporary file {temp_path}: {cleanup_error}")

    def _composite_images_locally(
        self,
        background_path: str,
        overlay_path: str,
        position: Tuple[int, int] = (0, 0),
        resize_overlay: bool = True,
        force_landscape: bool = True,
        landscape_width: int = 1920,
        landscape_height: int = 1080
    ) -> str:
        """
        Composite two images locally using PIL.

        Args:
            background_path: Path to background image
            overlay_path: Path to overlay image (should have transparency/alpha channel)
            position: (x, y) position to place overlay. If (0, 0), will center the overlay
            resize_overlay: Whether to resize overlay to fit background
            force_landscape: Whether to force landscape output (default: True)
            landscape_width: Target width for landscape output (default: 1920)
            landscape_height: Target height for landscape output (default: 1080)

        Returns:
            Path to the composited image file
        """
        try:
            # Open both images
            background = Image.open(background_path)
            overlay = Image.open(overlay_path)

            # Force background to landscape if needed
            if force_landscape:
                bg_width, bg_height = background.size
                # Check if background is not already landscape or needs resizing
                if bg_width < bg_height or bg_width != landscape_width or bg_height != landscape_height:
                    logger.info(f"Resizing background from {bg_width}x{bg_height} to landscape {landscape_width}x{landscape_height}")
                    background = background.resize((landscape_width, landscape_height), Image.Resampling.LANCZOS)

            # Convert images to RGBA mode to handle transparency
            if background.mode != 'RGBA':
                background = background.convert('RGBA')
            if overlay.mode != 'RGBA':
                overlay = overlay.convert('RGBA')

            # Resize overlay if needed
            if resize_overlay:
                # Calculate scale to fit overlay within background while maintaining aspect ratio
                bg_width, bg_height = background.size
                overlay_width, overlay_height = overlay.size

                # Scale overlay to fit 80% of background size
                scale_factor = min(
                    (bg_width * 0.8) / overlay_width,
                    (bg_height * 0.8) / overlay_height
                )

                new_overlay_size = (
                    int(overlay_width * scale_factor),
                    int(overlay_height * scale_factor)
                )

                # Use LANCZOS for high-quality downsampling
                overlay = overlay.resize(new_overlay_size, Image.Resampling.LANCZOS)
                logger.info(f"Resized overlay from {overlay_width}x{overlay_height} to {new_overlay_size[0]}x{new_overlay_size[1]}")

            # Calculate position if centering is requested
            if position == (0, 0):
                bg_width, bg_height = background.size
                overlay_width, overlay_height = overlay.size
                position = (
                    (bg_width - overlay_width) // 2,
                    (bg_height - overlay_height) // 2
                )
                logger.info(f"Centered overlay at position: {position}")

            # Create a new image for compositing
            composited = Image.new('RGBA', background.size)
            composited.paste(background, (0, 0))

            # Paste overlay onto background with alpha channel as mask
            composited.paste(overlay, position, overlay)

            # Convert to RGB for final output (removing alpha channel)
            final_image = Image.new('RGB', composited.size, (255, 255, 255))
            final_image.paste(composited, mask=composited.split()[3])  # Use alpha channel as mask

            # Save the result
            output_path = str(self._temp_dir / f"composited-{uuid.uuid4()}.png")
            final_image.save(output_path, 'PNG', quality=95, optimize=True)

            logger.info(f"Images composited successfully. Output saved to: {output_path}")
            return output_path

        except Exception as e:
            raise Exception(f"Failed to composite images: {str(e)}")

    def _download_image_from_url(self, image_url: str) -> str:
        """
        Download image from URL to local file.

        Args:
            image_url: URL of the image to download

        Returns:
            Path to the downloaded image file
        """
        try:
            logger.info(f"Downloading image from URL: {image_url}")

            # Generate temp file path
            temp_path = str(self._temp_dir / f"download-{uuid.uuid4()}.png")

            with httpx.Client(timeout=DOWNLOAD_TIMEOUT) as client:
                response = client.get(image_url)
                response.raise_for_status()

                # Save to local file
                with open(temp_path, 'wb') as f:
                    f.write(response.content)

                logger.info(f"Successfully downloaded image to: {temp_path}")
                return temp_path

        except Exception as e:
            logger.error(f"Failed to download image from {image_url}: {e}")
            raise Exception(f"Failed to download image: {e}")

    def _upload_to_supabase(
        self,
        file_path: str,
        folder: str = "processed-images",
        scene_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> str:
        """
        Upload a local image file to Supabase storage.

        Args:
            file_path: Path to the local image file
            folder: Folder name in the bucket (e.g., "background-removed", "composited-images")
            scene_id: Optional scene ID for organizing files
            user_id: Optional user ID for organizing files

        Returns:
            Public URL of the uploaded image
        """
        for attempt in range(MAX_RETRIES):
            try:
                # Read the local image file
                with open(file_path, 'rb') as f:
                    image_data = f.read()

                # All images go to generated-content bucket
                bucket_name = 'generated-content'
                
                # Check if this is a composited image - use uploaded_images folder
                if folder == "composited-images":
                    # Upload to uploaded_images folder in generated-content bucket
                    filename = f"uploaded_images/{uuid.uuid4()}.png"
                else:
                    # Generate unique filename with optional user_id/scene_id structure
                    if user_id and scene_id:
                        filename = f"{folder}/{user_id}/{scene_id}/{uuid.uuid4()}.png"
                    elif scene_id:
                        filename = f"{folder}/{scene_id}/{uuid.uuid4()}.png"
                    else:
                        filename = f"{folder}/{uuid.uuid4()}.png"

                # Upload to Supabase storage
                if not supabase_manager.is_connected():
                    raise Exception("Supabase connection not available")

                try:
                    result = supabase_manager.client.storage.from_(bucket_name).upload(
                        path=filename,
                        file=image_data,
                        file_options={'content-type': 'image/png'}
                    )
                except Exception as bucket_error:
                    if "Bucket not found" in str(bucket_error):
                        logger.warning(f"Bucket '{bucket_name}' not found, trying to create it...")
                        try:
                            # Try to create the bucket
                            supabase_manager.client.storage.create_bucket(
                                bucket_name,
                                options={"public": True}
                            )
                            logger.info(f"Created '{bucket_name}' bucket")
                            # Retry upload
                            result = supabase_manager.client.storage.from_(bucket_name).upload(
                                path=filename,
                                file=image_data,
                                file_options={'content-type': 'image/png'}
                            )
                        except Exception as create_error:
                            logger.error(f"Failed to create bucket '{bucket_name}': {create_error}")
                            raise Exception(
                                f"Storage bucket '{bucket_name}' not available and could not be created: {create_error}"
                            )
                    else:
                        raise bucket_error

                # Get public URL
                public_url = supabase_manager.client.storage.from_(bucket_name).get_public_url(filename)

                logger.info(f"Uploaded image to Supabase: {public_url}")
                return public_url

            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    logger.warning(
                        f"Attempt {attempt + 1} failed for image upload: {e}. "
                        f"Retrying in {RETRY_DELAY} seconds..."
                    )
                    import time
                    time.sleep(RETRY_DELAY)
                else:
                    logger.error(f"Failed to upload image to Supabase after {MAX_RETRIES} attempts: {e}")
                    raise

    def _update_scene_image_url(self, scene_id: str, image_url: str):
        """
        Update the scene's image_url in the database.

        Args:
            scene_id: The UUID of the scene
            image_url: The public URL of the new image
        """
        try:
            if not supabase_manager.is_connected():
                raise Exception("Supabase connection not available")

            # Update scene with new image URL
            result = supabase_manager.client.table('video_scenes').update({
                'image_url': image_url,
                'updated_at': datetime.now().isoformat()
            }).eq('id', scene_id).execute()

            if not result.data:
                raise Exception("Failed to update scene with new image URL")

            logger.info(f"Updated scene {scene_id} with new image URL: {image_url}")

        except Exception as e:
            logger.error(f"Failed to update scene {scene_id} with image URL: {e}")
            raise

    def replace_background(
        self,
        product_image_url: str,
        background_image_url: str,
        scene_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Complete workflow: Remove background from product image and composite with new background.

        Args:
            product_image_url: URL of the product image
            background_image_url: URL of the new background image
            scene_id: Scene ID for organizing files and updating database
            user_id: User ID for organizing files

        Returns:
            Dict containing:
                - success (bool): Whether the operation succeeded
                - image_url (str): URL of the final composited image in Supabase (if successful)
                - error (str): Error message (if failed)
        """
        try:
            logger.info(f"Starting background replacement for scene {scene_id}")

            # Step 1: Remove background from product image
            logger.info("Step 1: Removing background from product image...")
            remove_result = self.remove_background(product_image_url, scene_id)

            if not remove_result['success']:
                raise Exception(f"Background removal failed: {remove_result['error']}")

            no_bg_local_path = remove_result['local_path']

            # Step 2: Download background image
            logger.info("Step 2: Downloading background image...")
            temp_bg_path = self._download_image_from_url(background_image_url)

            # Step 3: Composite the images
            logger.info("Step 3: Compositing images...")
            temp_output_path = self._composite_images_locally(
                temp_bg_path,
                no_bg_local_path,
                position=(0, 0),  # Center the product
                resize_overlay=True
            )

            # Step 4: Upload to Supabase
            logger.info("Step 4: Uploading final image to Supabase...")
            final_url = self._upload_to_supabase(
                temp_output_path,
                folder="composited-images",
                scene_id=scene_id,
                user_id=user_id
            )

            # Step 5: Update scene in database
            logger.info("Step 5: Updating scene with new image URL...")
            self._update_scene_image_url(scene_id, final_url)

            logger.info(f"Background replacement completed successfully. Final URL: {final_url}")

            return {
                'success': True,
                'image_url': final_url,
                'error': None
            }

        except Exception as e:
            error_msg = f"Background replacement failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                'success': False,
                'image_url': None,
                'error': error_msg
            }

        finally:
            # Clean up temporary files
            for temp_path in [no_bg_local_path, temp_bg_path, temp_output_path]:
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.unlink(temp_path)
                        logger.debug(f"Cleaned up temporary file: {temp_path}")
                    except Exception as cleanup_error:
                        logger.warning(f"Failed to clean up temporary file {temp_path}: {cleanup_error}")

    def merge_image_with_video(
        self,
        product_image_url: str,
        background_video_url: str,
        scene_id: str,
        user_id: str,
        scale: float = 0.4,
        position: str = "center",
        duration: Optional[int] = None,
        add_animation: bool = True
    ) -> Dict[str, Any]:
        """
        Merge a product image (without background) with a background video using OpenCV.
        
        Args:
            product_image_url: URL of the product image (should be PNG with transparent background)
            background_video_url: URL of the background video
            scene_id: Scene ID for organizing files and updating database
            user_id: User ID for organizing files
            scale: Scale of product relative to video width (default: 0.4 = 40%)
            position: Position of product ("center", "top", "bottom", "left", "right")
            duration: Optional duration in seconds (if None, uses full video duration)
            add_animation: Whether to add zoom and floating animations
        
        Returns:
            Dict containing:
                - success (bool): Whether the operation succeeded
                - video_url (str): URL of the final video in Supabase (if successful)
                - error (str): Error message (if failed)
        """
        temp_product_path = None
        temp_video_path = None
        temp_output_path = None
        
        try:
            print("\n" + "="*80)
            print("🎬 SCENE 2 GENERATION - VIDEO MERGE STARTED")
            print("="*80)
            logger.info(f"🚀 Starting image-video merge for scene {scene_id}")
            logger.info(f"📦 Parameters:")
            logger.info(f"   - Scene ID: {scene_id}")
            logger.info(f"   - User ID: {user_id}")
            logger.info(f"   - Product Scale: {scale * 100}%")
            logger.info(f"   - Position: {position}")
            logger.info(f"   - Duration Limit: {duration}s" if duration else "   - Duration Limit: Full video")
            logger.info(f"   - Animation: {'Enabled (zoom + float)' if add_animation else 'Disabled'}")
            
            # Step 1: Download product image
            print("\n📥 STEP 1/5: Downloading Product Image")
            print("-" * 80)
            logger.info(f"🖼️  Product image URL: {product_image_url[:80]}...")
            temp_product_path = self._download_image_from_url(product_image_url)
            logger.info(f"✅ Product image downloaded: {temp_product_path}")
            
            # Step 2: Download background video
            print("\n📥 STEP 2/5: Downloading Background Video")
            print("-" * 80)
            logger.info(f"🎥 Background video URL: {background_video_url[:80]}...")
            temp_video_path = self._download_video_from_url(background_video_url)
            logger.info(f"✅ Background video downloaded: {temp_video_path}")
            
            # Step 3: Merge using OpenCV
            print("\n🎨 STEP 3/5: Merging Product with Video (OpenCV Processing)")
            print("-" * 80)
            logger.info("🔄 Starting OpenCV video processing...")
            temp_output_path = self._merge_with_opencv(
                temp_product_path,
                temp_video_path,
                scale=scale,
                position=position,
                duration=duration,
                add_animation=add_animation
            )
            logger.info(f"✅ Video merge completed: {temp_output_path}")
            
            # Step 4: Upload to Supabase storage
            print("\n☁️  STEP 4/5: Uploading Merged Video to Supabase")
            print("-" * 80)
            logger.info("📤 Uploading video to Supabase storage...")
            video_url = self._upload_video_to_supabase(
                temp_output_path,
                scene_id=scene_id,
                user_id=user_id
            )
            logger.info(f"✅ Video uploaded successfully")
            logger.info(f"🔗 Video URL: {video_url}")
            
            # Step 5: Update scene in database
            print("\n💾 STEP 5/5: Updating Database")
            print("-" * 80)
            logger.info(f"📝 Updating scene {scene_id} in video_scenes table...")
            self._update_scene_video_url(scene_id, video_url)
            logger.info(f"✅ Database updated successfully")
            
            print("\n" + "="*80)
            print("✅ SCENE 2 GENERATION COMPLETED SUCCESSFULLY")
            print("="*80)
            logger.info(f"🎉 Image-video merge completed successfully for scene {scene_id}")
            logger.info(f"🔗 Final video URL: {video_url}")
            print()
            
            return {
                'success': True,
                'video_url': video_url,
                'error': None
            }
            
        except Exception as e:
            error_msg = f"Image-video merge failed: {str(e)}"
            print("\n" + "="*80)
            print("❌ SCENE 2 GENERATION FAILED")
            print("="*80)
            logger.error(f"❌ Error: {error_msg}", exc_info=True)
            print()
            return {
                'success': False,
                'video_url': None,
                'error': error_msg
            }
        
        finally:
            # Clean up temporary files
            for temp_path in [temp_product_path, temp_video_path, temp_output_path]:
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.unlink(temp_path)
                        logger.debug(f"Cleaned up temporary file: {temp_path}")
                    except Exception as cleanup_error:
                        logger.warning(f"Failed to clean up temporary file {temp_path}: {cleanup_error}")

    def _download_video_from_url(self, video_url: str) -> str:
        """
        Download video from URL to local file.
        
        Args:
            video_url: URL of the video to download
        
        Returns:
            Path to the downloaded video file
        """
        try:
            logger.info(f"Downloading video from URL: {video_url}")
            
            # Generate temp file path
            temp_path = str(self._temp_dir / f"download-video-{uuid.uuid4()}.mp4")
            
            with httpx.Client(timeout=DOWNLOAD_TIMEOUT) as client:
                response = client.get(video_url)
                response.raise_for_status()
                
                # Save to local file
                with open(temp_path, 'wb') as f:
                    f.write(response.content)
                
                logger.info(f"Successfully downloaded video to: {temp_path}")
                return temp_path
                
        except Exception as e:
            logger.error(f"Failed to download video from {video_url}: {e}")
            raise Exception(f"Failed to download video: {e}")

    def _merge_with_opencv(
        self,
        product_path: str,
        video_path: str,
        scale: float = 0.4,
        position: str = "center",
        duration: Optional[int] = None,
        add_animation: bool = True
    ) -> str:
        """
        Merge product image with background video using OpenCV.
        
        Args:
            product_path: Path to product image (PNG with transparency)
            video_path: Path to background video
            scale: Scale of product relative to video width
            position: Position of product on video
            duration: Optional duration limit in seconds
            add_animation: Whether to add zoom and floating animations
        
        Returns:
            Path to the output video file
        """
        try:
            # Open video
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise Exception("Cannot open video file")
            
            fps = cap.get(cv2.CAP_PROP_FPS)
            original_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            original_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            # Force output to 1920x1080 for high quality
            width = 1920
            height = 1080
            
            # Limit duration if specified
            if duration:
                max_frames = int(fps * duration)
                total_frames = min(total_frames, max_frames)
                logger.info(f"⏱️  Duration limited to {duration}s ({max_frames} frames)")
            
            video_duration = total_frames / fps
            logger.info(f"📹 Input Video Info:")
            logger.info(f"   - Original Resolution: {original_width}x{original_height}")
            logger.info(f"   - Output Resolution: {width}x{height} (1080p HD)")
            logger.info(f"   - FPS: {fps}")
            logger.info(f"   - Total Frames: {total_frames}")
            logger.info(f"   - Duration: {video_duration:.2f}s")
            
            # Load product image
            product_img = Image.open(product_path).convert("RGBA")
            product_np = np.array(product_img)
            
            logger.info(f"🖼️  Product Image: {product_np.shape[1]}x{product_np.shape[0]} pixels")
            
            # Create output video - use temp AVI first for better compatibility
            temp_output_path = str(self._temp_dir / f"merged-temp-{uuid.uuid4()}.avi")
            output_path = str(self._temp_dir / f"merged-video-{uuid.uuid4()}.mp4")
            
            # Use MJPEG codec for AVI (more reliable than mp4v)
            fourcc = cv2.VideoWriter_fourcc(*'MJPG')
            out = cv2.VideoWriter(temp_output_path, fourcc, fps, (width, height))
            
            logger.info(f"💾 Temp output file: {temp_output_path}")
            logger.info(f"💾 Final output file: {output_path}")
            
            # Animation parameters
            zoom_duration = 3.0 if add_animation else 0.0
            min_scale = 0.05 if add_animation else scale
            
            if add_animation:
                logger.info(f"✨ Animation enabled:")
                logger.info(f"   - Zoom: {min_scale*100}% → {scale*100}% over {zoom_duration}s")
                logger.info(f"   - Floating: ±30px sine wave after zoom")
            
            # Process frames
            frame_idx = 0
            smooth_x, smooth_y = None, None
            smooth_factor = 0.08
            last_log_time = 0
            
            if original_width != width or original_height != height:
                logger.info(f"🔄 Each frame will be upscaled: {original_width}x{original_height} → {width}x{height}")
            
            logger.info(f"🎬 Starting frame processing...")
            print(f"   Progress: [", end="", flush=True)
            
            while frame_idx < total_frames:
                ret, frame = cap.read()
                if not ret:
                    break
                
                # Resize frame to 1920x1080 if needed
                if frame.shape[1] != width or frame.shape[0] != height:
                    frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_LANCZOS4)
                
                t = frame_idx / fps
                
                # Calculate scale with zoom animation
                if add_animation and t < zoom_duration:
                    # Ease-out zoom animation
                    progress = t / zoom_duration
                    eased = 1 - (1 - progress) ** 3
                    current_scale = min_scale + eased * (scale - min_scale)
                else:
                    current_scale = scale
                
                # Calculate product size
                product_w = max(1, int(width * current_scale))
                ratio = product_w / product_np.shape[1]
                product_h = max(1, int(product_np.shape[0] * ratio))
                
                # Resize product
                product_resized = cv2.resize(product_np, (product_w, product_h), 
                                            interpolation=cv2.INTER_AREA)
                
                # Calculate position with optional floating animation
                dy = 0
                if add_animation and t >= zoom_duration:
                    # Floating animation
                    phase = t - zoom_duration
                    dy = int(30 * math.sin(phase * 0.8))
                
                # Position based on parameter
                if position == "center":
                    target_x = width // 2 - product_w // 2
                    target_y = int(height * 0.52 - product_h // 2 + dy)
                elif position == "top":
                    target_x = width // 2 - product_w // 2
                    target_y = int(height * 0.2 + dy)
                elif position == "bottom":
                    target_x = width // 2 - product_w // 2
                    target_y = int(height * 0.8 - product_h + dy)
                elif position == "left":
                    target_x = int(width * 0.2)
                    target_y = int(height * 0.52 - product_h // 2 + dy)
                elif position == "right":
                    target_x = int(width * 0.8 - product_w)
                    target_y = int(height * 0.52 - product_h // 2 + dy)
                else:
                    target_x = width // 2 - product_w // 2
                    target_y = int(height * 0.52 - product_h // 2 + dy)
                
                # Smooth position transition
                if smooth_x is None:
                    smooth_x, smooth_y = target_x, target_y
                smooth_x += (target_x - smooth_x) * smooth_factor
                smooth_y += (target_y - smooth_y) * smooth_factor
                
                x = int(smooth_x)
                y = int(smooth_y)
                
                # Ensure product stays within frame
                x = max(0, min(width - product_w, x))
                y = max(0, min(height - product_h, y))
                
                # Composite product onto frame using alpha channel
                alpha = product_resized[:, :, 3] / 255.0
                
                for c in range(3):
                    frame[y:y+product_h, x:x+product_w, c] = (
                        frame[y:y+product_h, x:x+product_w, c] * (1 - alpha)
                        + product_resized[:, :, c] * alpha
                    )
                
                # Write frame
                out.write(frame)
                frame_idx += 1
                
                # Log progress - show progress bar
                progress_pct = (frame_idx / total_frames) * 100
                
                # Update progress bar every 5%
                if progress_pct >= last_log_time + 5 or frame_idx == total_frames:
                    last_log_time = progress_pct
                    bar_length = int(progress_pct / 5)
                    print("=" * bar_length, end="", flush=True)
                
                # Detailed logging every 2 seconds
                if frame_idx % int(fps * 2) == 0 or frame_idx == total_frames:
                    elapsed_time = frame_idx / fps
                    remaining_frames = total_frames - frame_idx
                    estimated_remaining = remaining_frames / fps if fps > 0 else 0
                    
                    phase = "ZOOM" if (add_animation and elapsed_time < zoom_duration) else "FLOAT"
                    
                    logger.info(
                        f"   Frame {frame_idx}/{total_frames} | "
                        f"{progress_pct:.1f}% | "
                        f"Time: {elapsed_time:.1f}s/{video_duration:.1f}s | "
                        f"Phase: {phase} | "
                        f"ETA: {estimated_remaining:.1f}s"
                    )
            
            print("] 100%")
            
            cap.release()
            out.release()
            
            logger.info(f"✅ OpenCV processing complete")
            logger.info(f"💾 Temp AVI saved to: {temp_output_path}")
            
            # Convert to H.264 MP4 using FFmpeg for better compatibility
            logger.info(f"🎞️  Converting to H.264 MP4 with FFmpeg...")
            self._convert_to_h264(temp_output_path, output_path)
            
            # Clean up temp AVI file
            try:
                os.unlink(temp_output_path)
                logger.info(f"🗑️  Cleaned up temp AVI file")
            except Exception as e:
                logger.warning(f"Failed to clean up temp file: {e}")
            
            logger.info(f"💾 Final MP4 saved to: {output_path}")
            return output_path
            
        except Exception as e:
            raise Exception(f"Failed to merge video with OpenCV: {e}")

    def _convert_to_h264(self, input_path: str, output_path: str):
        """
        Convert video to H.264 MP4 format using FFmpeg for maximum compatibility.
        
        Args:
            input_path: Path to input video (AVI)
            output_path: Path to output video (MP4)
        """
        try:
            # FFmpeg command for high-quality H.264 encoding at 1920x1080
            cmd = [
                'ffmpeg',
                '-i', input_path,
                '-vf', 'scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2',  # Ensure 1920x1080
                '-c:v', 'libx264',          # H.264 video codec
                '-preset', 'slow',           # Better quality (slow = higher quality)
                '-crf', '18',                # High quality (18 = visually lossless)
                '-profile:v', 'high',        # H.264 high profile for better compression
                '-level', '4.2',             # H.264 level 4.2
                '-pix_fmt', 'yuv420p',      # Pixel format for compatibility
                '-movflags', '+faststart',   # Enable fast start for web streaming
                '-b:v', '8M',                # 8 Mbps bitrate for high quality 1080p
                '-maxrate', '10M',           # Max bitrate
                '-bufsize', '16M',           # Buffer size
                '-y',                        # Overwrite output file
                output_path
            ]
            
            logger.info(f"🎞️  FFmpeg Quality Settings:")
            logger.info(f"   - Resolution: 1920x1080 (forced)")
            logger.info(f"   - Codec: H.264 High Profile")
            logger.info(f"   - Bitrate: 8Mbps (high quality)")
            logger.info(f"   - CRF: 18 (visually lossless)")
            logger.info(f"   - Preset: slow (higher quality)")
            logger.debug(f"FFmpeg command: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode != 0:
                logger.error(f"FFmpeg stderr: {result.stderr}")
                raise Exception(f"FFmpeg conversion failed with code {result.returncode}")
            
            logger.info(f"✅ FFmpeg conversion complete")
            
        except FileNotFoundError:
            raise Exception("FFmpeg not found! Please install FFmpeg: https://ffmpeg.org/download.html")
        except subprocess.TimeoutExpired:
            raise Exception("FFmpeg conversion timed out after 5 minutes")
        except Exception as e:
            raise Exception(f"FFmpeg conversion failed: {e}")

    def _upload_video_to_supabase(
        self,
        file_path: str,
        scene_id: str,
        user_id: str
    ) -> str:
        """
        Upload a local video file to Supabase storage.
        
        Args:
            file_path: Path to the local video file
            scene_id: Scene ID for organizing files
            user_id: User ID for organizing files
        
        Returns:
            Public URL of the uploaded video
        """
        for attempt in range(MAX_RETRIES):
            try:
                # Read the local video file
                with open(file_path, 'rb') as f:
                    video_data = f.read()
                
                # Generate unique filename
                filename = f"scene-videos/{user_id}/{scene_id}/{uuid.uuid4()}.mp4"
                
                # Upload to Supabase storage
                if not supabase_manager.is_connected():
                    raise Exception("Supabase connection not available")
                
                bucket_name = 'generated-content'
                try:
                    result = supabase_manager.client.storage.from_(bucket_name).upload(
                        path=filename,
                        file=video_data,
                        file_options={'content-type': 'video/mp4'}
                    )
                except Exception as bucket_error:
                    if "Bucket not found" in str(bucket_error):
                        logger.warning(f"Bucket '{bucket_name}' not found, trying to create it...")
                        try:
                            supabase_manager.client.storage.create_bucket(
                                bucket_name,
                                options={"public": True}
                            )
                            logger.info(f"Created '{bucket_name}' bucket")
                            result = supabase_manager.client.storage.from_(bucket_name).upload(
                                path=filename,
                                file=video_data,
                                file_options={'content-type': 'video/mp4'}
                            )
                        except Exception as create_error:
                            logger.error(f"Failed to create bucket '{bucket_name}': {create_error}")
                            raise Exception(
                                f"Storage bucket '{bucket_name}' not available: {create_error}"
                            )
                    else:
                        raise bucket_error
                
                # Get public URL
                public_url = supabase_manager.client.storage.from_(bucket_name).get_public_url(filename)
                
                logger.info(f"Uploaded video to Supabase: {public_url}")
                return public_url
                
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    logger.warning(
                        f"Attempt {attempt + 1} failed for video upload: {e}. "
                        f"Retrying in {RETRY_DELAY} seconds..."
                    )
                    import time
                    time.sleep(RETRY_DELAY)
                else:
                    logger.error(f"Failed to upload video to Supabase after {MAX_RETRIES} attempts: {e}")
                    raise

    def _update_scene_video_url(self, scene_id: str, video_url: str):
        """
        Update the scene's generated_video_url in the database.
        
        Args:
            scene_id: The UUID of the scene
            video_url: The public URL of the video
        """
        try:
            if not supabase_manager.is_connected():
                raise Exception("Supabase connection not available")
            
            # Update scene with new video URL
            result = supabase_manager.client.table('video_scenes').update({
                'generated_video_url': video_url,
                'updated_at': datetime.now().isoformat()
            }).eq('id', scene_id).execute()
            
            if not result.data:
                raise Exception("Failed to update scene with new video URL")
            
            logger.info(f"Updated scene {scene_id} with new video URL: {video_url}")
            
        except Exception as e:
            logger.error(f"Failed to update scene {scene_id} with video URL: {e}")
            raise


# Global instance
image_processing_service = ImageProcessingService()
