"""
Google Vertex AI utility functions for AI-powered image generation.
Provides easy-to-use interfaces for creating images using Google's Vertex AI API.
"""

import os
import base64
import mimetypes
import logging
import tempfile
import requests
import time
import uuid
from typing import Dict, List, Any, Optional, Union, Tuple
from pathlib import Path
from io import BytesIO

try:
    from PIL import Image as PILImage
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logging.warning("Pillow package not available. Install with: pip install Pillow")

try:
    from google import genai
    from google.genai import types
    from google.genai.types import (
        EditImageConfig, GenerateImagesConfig, RecontextImageConfig,
        RecontextImageSource, ProductImage, Image, RawReferenceImage, 
        MaskReferenceImage, MaskReferenceConfig
    )
    from google.oauth2 import service_account
    VERTEX_AVAILABLE = True
except ImportError:
    VERTEX_AVAILABLE = False
    logging.warning("Google Vertex AI package not available. Install with: pip install google-generativeai")

from app.config import settings

logger = logging.getLogger(__name__)


class VertexManager:
    """Manages Google Vertex AI client and provides utility methods for AI generation."""
    
    def __init__(self):
        """Initialize Vertex AI client with API credentials."""
        self.client: Optional[genai.Client] = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize the Vertex AI client with API credentials."""
        if not VERTEX_AVAILABLE:
            logger.warning("Google Vertex AI package not available. AI generation will be disabled.")
            return
                        
        # Get the project root directory (parent of app directory)
        project_root = Path(__file__).parent.parent.parent
        key_file_path = project_root / "promo-nex-ai-vertex-ai-key.json"
        
        if not os.path.exists(key_file_path):
            logger.warning("Vertex AI service account key file not found. AI generation will be disabled.")
            return
        
        try:
            # Set the GOOGLE_APPLICATION_CREDENTIALS environment variable
            # This is required for Google Cloud libraries to find the service account key
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(key_file_path)
            os.environ['GOOGLE_CLOUD_PROJECT'] = 'promo-nex-ai-466218'
            
            logger.info(f"Set GOOGLE_APPLICATION_CREDENTIALS to: {key_file_path}")
            print(f"Set GOOGLE_APPLICATION_CREDENTIALS to: {key_file_path}")
            
            # Initialize Vertex AI client
            self.client = genai.Client(
                vertexai=True,
                http_options=types.HttpOptions(api_version='v1'),
                credentials=service_account.Credentials.from_service_account_file(
                    str(key_file_path),
                    scopes=['https://www.googleapis.com/auth/cloud-platform']
                )
            )
            logger.info("Vertex AI client initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Vertex AI client: {e}")
            self.client = None
    
    def is_available(self) -> bool:
        """Check if Vertex AI is available and properly configured."""
        # Get the project root directory (parent of app directory)
        project_root = Path(__file__).parent.parent.parent
        key_file_path = project_root / "promo-nex-ai-vertex-ai-key.json"
        
        return (VERTEX_AVAILABLE and 
                os.path.exists(key_file_path) and 
                self.client is not None)
    
    def is_pillow_available(self) -> bool:
        """Check if Pillow is available for image processing."""
        return PIL_AVAILABLE
    
    def _get_temp_dir(self) -> Path:
        """Get or create the temp directory for temporary files."""
        # Get the project root directory (parent of app directory)
        project_root = Path(__file__).parent.parent.parent
        temp_dir = project_root / "temp"
        temp_dir.mkdir(exist_ok=True)
        return temp_dir
    
    def _get_image_as_data_uri(self, image_path: Union[str, Path]) -> str:
        """Convert an image file to a data URI."""
        try:
            image_path = Path(image_path)
            if not image_path.exists():
                raise FileNotFoundError(f"Image file not found: {image_path}")
            
            with open(image_path, "rb") as f:
                base64_image = base64.b64encode(f.read()).decode("utf-8")
            
            # Get MIME type
            content_type = mimetypes.guess_type(str(image_path))[0] or "image/png"
            return f"data:{content_type};base64,{base64_image}"
            
        except Exception as e:
            logger.error(f"Failed to convert image to data URI: {e}")
            raise
    
    def _download_image_from_url(self, image_url: str, max_retries: int = 3) -> str:
        """
        Download image from URL to a temporary file and return the file path.
        Handles 403 Forbidden errors with different strategies and retries.
        
        Args:
            image_url: URL of the image to download
            max_retries: Maximum number of retry attempts
            
        Returns:
            Path to the temporary file containing the downloaded image
            
        Raises:
            Exception: If all download attempts fail
        """
        headers_list = [
            # Standard browser headers
            {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            },
            # Mobile browser headers
            {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1',
                'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
            },
            # Simple headers
            {
                'User-Agent': 'Mozilla/5.0 (compatible; ImageDownloader/1.0)',
                'Accept': '*/*',
            }
        ]
        
        last_exception = None
        
        for attempt in range(max_retries):
            headers = headers_list[attempt % len(headers_list)]
            
            try:
                logger.info(f"Downloading image from URL (attempt {attempt + 1}/{max_retries}): {image_url}")
                logger.debug(f"Using headers: {headers}")
                
                response = requests.get(image_url, headers=headers, timeout=30, allow_redirects=True)
                response.raise_for_status()
                
                # Check if response contains image data
                content_type = response.headers.get('content-type', '')
                if not content_type.startswith('image/'):
                    logger.warning(f"URL does not contain image data: {content_type}")
                    raise ValueError(f"URL does not contain image data: {content_type}")
                
                # Create temporary file
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
                temp_file.write(response.content)
                temp_file.close()
                
                logger.info(f"Successfully downloaded image to temporary file: {temp_file.name}")
                return temp_file.name
                
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 403:
                    logger.warning(f"403 Forbidden error on attempt {attempt + 1}: {e}")
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.info(f"Retrying with different headers...")
                        time.sleep(1)  # Brief delay before retry
                        continue
                else:
                    logger.error(f"HTTP error downloading image from URL {image_url}: {e}")
                    raise
            except requests.exceptions.RequestException as e:
                logger.error(f"Request error downloading image from URL {image_url} (attempt {attempt + 1}): {e}")
                last_exception = e
                if attempt < max_retries - 1:
                    time.sleep(1)  # Brief delay before retry
                    continue
            except Exception as e:
                logger.error(f"Unexpected error downloading image from URL {image_url} (attempt {attempt + 1}): {e}")
                last_exception = e
                if attempt < max_retries - 1:
                    time.sleep(1)  # Brief delay before retry
                    continue
        
        # If all attempts failed, raise the last exception
        logger.error(f"Failed to download image from URL {image_url} after {max_retries} attempts")
        raise last_exception or Exception(f"Failed to download image from URL {image_url} after {max_retries} attempts")
    
    def _get_image_bytes_from_url(self, image_url: str, max_retries: int = 3) -> Tuple[bytes, str]:
        """
        Download image from URL and return bytes data and MIME type.
        Handles 403 Forbidden errors with different strategies and retries.
        
        Args:
            image_url: URL of the image to download
            max_retries: Maximum number of retry attempts
            
        Returns:
            Tuple of (image_bytes, mime_type)
            
        Raises:
            Exception: If all download attempts fail
        """
        headers_list = [
            # Standard browser headers
            {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            },
            # Mobile browser headers
            {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1',
                'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
            },
            # Simple headers
            {
                'User-Agent': 'Mozilla/5.0 (compatible; ImageDownloader/1.0)',
                'Accept': '*/*',
            }
        ]
        
        last_exception = None
        
        for attempt in range(max_retries):
            headers = headers_list[attempt % len(headers_list)]
            
            try:
                logger.info(f"Downloading image bytes from URL (attempt {attempt + 1}/{max_retries}): {image_url}")
                logger.debug(f"Using headers: {headers}")
                
                response = requests.get(image_url, headers=headers, timeout=30, allow_redirects=True)
                response.raise_for_status()
                
                # Check if response contains image data
                content_type = response.headers.get('content-type', '')
                if not content_type.startswith('image/'):
                    logger.warning(f"URL does not contain image data: {content_type}")
                    raise ValueError(f"URL does not contain image data: {content_type}")
                
                logger.info(f"Successfully downloaded image bytes from URL: {image_url}")
                return response.content, content_type
                
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 403:
                    logger.warning(f"403 Forbidden error on attempt {attempt + 1}: {e}")
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.info(f"Retrying with different headers...")
                        time.sleep(1)  # Brief delay before retry
                        continue
                else:
                    logger.error(f"HTTP error downloading image bytes from URL {image_url}: {e}")
                    raise
            except requests.exceptions.RequestException as e:
                logger.error(f"Request error downloading image bytes from URL {image_url} (attempt {attempt + 1}): {e}")
                last_exception = e
                if attempt < max_retries - 1:
                    time.sleep(1)  # Brief delay before retry
                    continue
            except Exception as e:
                logger.error(f"Unexpected error downloading image bytes from URL {image_url} (attempt {attempt + 1}): {e}")
                last_exception = e
                if attempt < max_retries - 1:
                    time.sleep(1)  # Brief delay before retry
                    continue
        
        # If all attempts failed, raise the last exception
        logger.error(f"Failed to download image bytes from URL {image_url} after {max_retries} attempts")
        raise last_exception or Exception(f"Failed to download image bytes from URL {image_url} after {max_retries} attempts")
    
    def _compress_image(self, image_path: str, quality: int = 85, max_size_mb: float = 5.0) -> str:
        """
        Compress an image file to reduce file size while maintaining dimensions.
        
        Args:
            image_path: Path to the input image file
            quality: JPEG quality (1-100, default: 85)
            max_size_mb: Maximum file size in MB (default: 5.0)
            
        Returns:
            Path to the compressed image file (may be the same as input if already small enough)
        """
        try:
            if not PIL_AVAILABLE:
                logger.warning("Pillow not available, skipping image compression")
                return image_path
            
            # Check current file size
            current_size_mb = os.path.getsize(image_path) / (1024 * 1024)
            logger.info(f"Original image size: {current_size_mb:.2f} MB")
            
            # If already small enough, return original path
            if current_size_mb <= max_size_mb:
                logger.info(f"Image size ({current_size_mb:.2f} MB) is already within limit ({max_size_mb} MB)")
                return image_path
            
            # Open the image
            with PILImage.open(image_path) as img:
                # Convert to RGB if necessary (JPEG doesn't support RGBA)
                if img.mode in ('RGBA', 'LA', 'P'):
                    # Create white background for transparent images
                    background = PILImage.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = background
                elif img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Create compressed version
                compressed_path = image_path.replace('.', '_compressed.')
                
                # Try different quality levels until we get under the size limit
                current_quality = quality
                while current_quality > 10 and os.path.getsize(image_path) / (1024 * 1024) > max_size_mb:
                    img.save(compressed_path, 'JPEG', quality=current_quality, optimize=True)
                    
                    compressed_size_mb = os.path.getsize(compressed_path) / (1024 * 1024)
                    logger.info(f"Compressed with quality {current_quality}: {compressed_size_mb:.2f} MB")
                    
                    if compressed_size_mb <= max_size_mb:
                        break
                    
                    current_quality -= 10
                
                # Replace original with compressed version
                if os.path.exists(compressed_path):
                    os.replace(compressed_path, image_path)
                    final_size_mb = os.path.getsize(image_path) / (1024 * 1024)
                    logger.info(f"Image compressed successfully: {current_size_mb:.2f} MB -> {final_size_mb:.2f} MB")
                else:
                    logger.warning("Compression failed, using original image")
            
            return image_path
            
        except Exception as e:
            logger.error(f"Failed to compress image {image_path}: {e}")
            return image_path
    
    def create_centered_image_with_black_background(self, source_image: Image, target_width: int = 1920, target_height: int = 1080) -> Image:
        """
        Create an image with the source image centered and black background.
        
        Args:
            source_image: Google GenAI Image object
            target_width: Desired width of the output image
            target_height: Desired height of the output image
        
        Returns:
            PIL Image object
        """
        if not PIL_AVAILABLE:
            raise RuntimeError("PIL is required for image processing")
        
        # Load the source image from bytes
        source_img = PILImage.open(BytesIO(source_image.image_bytes))
        
        # Create a black background image
        background = PILImage.new('RGB', (target_width, target_height), (0, 0, 0))
        
        # Calculate position to center the source image
        x = (target_width - source_img.width) // 2
        y = (target_height - source_img.height) // 2
        
        # Paste the source image onto the black background
        background.paste(source_img, (x, y))
        
        return background

    def create_mask_image_with_black_area(self, source_image: Image, target_width: int = 1920, target_height: int = 1080) -> Image:
        """
        Create an image with black area where the source image was positioned.
        
        Args:
            source_image: Google GenAI Image object
            target_width: Desired width of the output image
            target_height: Desired height of the output image
        
        Returns:
            PIL Image object
        """
        if not PIL_AVAILABLE:
            raise RuntimeError("PIL is required for image processing")
        
        # Load the source image to get its dimensions
        source_img = PILImage.open(BytesIO(source_image.image_bytes))
        
        # Create a white background image
        background = PILImage.new('RGB', (target_width, target_height), (255, 255, 255))
        
        # Calculate position where the source image would be centered
        x = (target_width - source_img.width) // 2
        y = (target_height - source_img.height) // 2
        
        # Create a black rectangle where the source image would be
        black_area = PILImage.new('RGB', (source_img.width, source_img.height), (0, 0, 0))
        
        # Paste the black area onto the white background
        background.paste(black_area, (x, y))
        
        return background

    def generate_image_with_recontext_and_upscale(
        self,
        prompt: str,
        product_images: List[str],
        target_width: int = 1920,
        target_height: int = 1080,
        output_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate an image using Google Vertex AI recontext model and upscale it.
        
        Args:
            prompt: Text prompt for image generation
            product_images: List of product image URLs
            target_width: Desired width for the final image
            target_height: Desired height for the final image
            output_path: Optional path to save the final image
            
        Returns:
            Dictionary containing generation results and image path
        """
        if not self.is_available():
            raise RuntimeError("Vertex AI is not available or properly configured")
        
        if not PIL_AVAILABLE:
            raise RuntimeError("PIL is required for image processing")
        
        try:
            logger.info(f"Starting image generation with recontext model using {len(product_images)} product images")
            
            # Get temp directory and create output path if not provided
            temp_dir = self._get_temp_dir()
            if not output_path:
                output_path = str(temp_dir / f"temp_image_{uuid.uuid4()}.png")
            
            # Download and prepare product images (limit to 3)
            product_image_objects = []
            limited_images = product_images[:3]  # Limit to first 3 images
            logger.info(f"Processing {len(limited_images)} product images (limited from {len(product_images)} total)")
            
            for i, image_url in enumerate(limited_images):
                try:
                    product_image_bytes, mime_type = self._get_image_bytes_from_url(image_url)
                    source_image = Image(image_bytes=product_image_bytes, mime_type=mime_type)
                    product_image_objects.append(ProductImage(product_image=source_image))
                    logger.info(f"Successfully prepared product image {i+1}: {image_url}")
                except Exception as e:
                    logger.warning(f"Failed to prepare product image {i+1} ({image_url}): {e}")
                    continue
            
            if not product_image_objects:
                raise RuntimeError("No valid product images could be prepared")
            
            # Generate the recontext image (1024x1024)
            logger.info("Generating recontext image...")
            recontext_result = self.client.models.recontext_image(
                model="imagen-product-recontext-preview-06-30",
                source=RecontextImageSource(
                    prompt=prompt,
                    product_images=product_image_objects,
                ),
                config=RecontextImageConfig(
                    person_generation="ALLOW_ALL",
                )
            )
            
            recontext_image = recontext_result.generated_images[0].image
            
            # Create the two required images for upscaling
            logger.info("Creating centered image with black background...")
            centered_image = self.create_centered_image_with_black_background(
                recontext_image, target_width, target_height
            )
            
            logger.info("Creating mask image with black area...")
            mask_image = self.create_mask_image_with_black_area(
                recontext_image, target_width, target_height
            )
            
            # Convert PIL images to bytes
            centered_image_bytes = BytesIO()
            centered_image.save(centered_image_bytes, format='PNG')
            centered_image_bytes = centered_image_bytes.getvalue()
            
            mask_image_bytes = BytesIO()
            mask_image.save(mask_image_bytes, format='PNG')
            mask_image_bytes = mask_image_bytes.getvalue()
            
            # Create reference images for upscaling
            raw_ref = RawReferenceImage(
                reference_image=Image(image_bytes=centered_image_bytes, mime_type="image/png"),
                reference_id=0,
            )
            mask_ref = MaskReferenceImage(
                reference_id=1,
                reference_image=Image(image_bytes=mask_image_bytes, mime_type="image/png"),
                config=MaskReferenceConfig(
                    mask_mode="MASK_MODE_USER_PROVIDED",
                    mask_dilation=0.03,
                ),
            )
            
            # Generate the upscaled image using edit_image
            logger.info("Generating upscaled image...")
            upscaled_result = self.client.models.edit_image(
                model="imagen-3.0-capability-001",
                prompt=prompt,
                reference_images=[raw_ref, mask_ref],
                config=EditImageConfig(
                    edit_mode="EDIT_MODE_OUTPAINT",
                ),
            )
            
            upscaled_image = upscaled_result.generated_images[0].image
            
            # Save the final image if output path is provided
            if output_path:
                upscaled_image.save(output_path)
                logger.info(f"Saved upscaled image to: {output_path}")
            
            return {
                'success': True,
                'image_path': output_path,
                'image_saved': bool(output_path),
                'recontext_image': recontext_image,
                'upscaled_image': upscaled_image,
                'target_dimensions': f"{target_width}x{target_height}",
                'product_images_used': len(product_image_objects)
            }
            
        except Exception as e:
            logger.error(f"Failed to generate image with recontext and upscale: {e}")
            return {
                'success': False,
                'error': str(e),
                'image_path': None,
                'image_saved': False
            }
    
    def generate_video_with_prompt_and_image(
        self,
        prompt: str,
        image_url: str,
        model: str = "veo-3.0-generate-preview",
        file_path: Optional[str] = None,
        aspect_ratio: str = "16:9",
        number_of_videos: int = 1,
        negative_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a video using Google Vertex AI with a text prompt and image URL.
        
        Args:
            prompt: Text prompt for video generation
            image_url: URL of the input image
            model: Vertex AI model to use (default: veo-3.0-generate-preview)
            file_path: Optional path to save the generated video(s)
            aspect_ratio: Aspect ratio for the video (default: "16:9")
            number_of_videos: Number of videos to generate (default: 1)
            negative_prompt: Optional negative prompt
            
        Returns:
            Dictionary containing generation results and video paths
        """
        if not self.is_available():
            raise RuntimeError("Vertex AI is not available or properly configured")
        
        try:
            logger.info(f"Starting video generation with model {model}")
            
            # Get image bytes and MIME type from URL
            image_bytes, mime_type = self._get_image_bytes_from_url(image_url)
            
            # Create image object for the API
            image_obj = types.Image(image_bytes=image_bytes, mime_type=mime_type)
            
            # Create video generation operation
            operation = self.client.models.generate_videos(
                model=model,
                prompt=prompt,
                image=image_obj,
                config=types.GenerateVideosConfig(
                    # Split aspect_ratio and compare width/height to set 16:9 or 9:16
                    duration_seconds=8,
                    aspect_ratio = (
                        "9:16"
                        if (aspect_ratio and ":" in aspect_ratio and int(aspect_ratio.split(":")[0]) < int(aspect_ratio.split(":")[1]))
                        else "16:9"
                    ),
                    # aspect_ratio="16:9",
                    resolution="1080p",
                    generate_audio=False,
                    number_of_videos=number_of_videos,
                    negative_prompt=negative_prompt,
                    enhance_prompt=False
                ),
            )
            
            # Wait for the video(s) to be generated
            logger.info("Waiting for video generation to complete...")
            while not operation.done:
                time.sleep(3)
                operation = self.client.operations.get(operation)
                logger.info(f"Video generation status: {operation}")
            
            # Check if the operation completed successfully
            if operation.error:
                error_msg = f"Video generation failed: {operation.error.get('message', 'Unknown error')}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "status": "error"
                }
            
            # Check if result is available
            if not operation.result:
                error_msg = "Video generation completed but no result was returned"
                logger.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "status": "error"
                }
            
            logger.info("Video generation completed successfully")
            
            # Process generated videos
            generated_videos = operation.result.generated_videos
            video_paths = []
            
            for n, generated_video in enumerate(generated_videos):
                # Download the video file
                # operation.result.generated_videos[0].video.save(str(file_path))
                
                # Save video if file_path is provided
                if file_path:
                    if number_of_videos > 1:
                        # If multiple videos, add index to filename
                        base_path = Path(file_path)
                        video_filename = f"{base_path.stem}_{n}{base_path.suffix}"
                        video_path = base_path.parent / video_filename
                    else:
                        video_path = file_path
                    
                    generated_video.video.save(str(video_path))
                    video_paths.append(str(video_path))
                    logger.info(f"Video saved to: {video_path}")
                else:
                    # Just store the video object reference
                    video_paths.append(generated_video.video)
            
            return {
                "success": True,
                "model": model,
                "prompt": prompt,
                "image_url": image_url,
                "aspect_ratio": aspect_ratio,
                "number_of_videos": number_of_videos,
                "negative_prompt": negative_prompt,
                "generated_videos": generated_videos,
                "video_paths": video_paths,
                "status": "completed"
            }
            
        except Exception as e:
            logger.error(f"Video generation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "status": "error"
            }
    
    def add_text_overlay_to_image(
        self,
        image_path: str,
        text_overlay_prompt: str,
        target_width: int = 1920,
        target_height: int = 1080,
        output_path: Optional[str] = None,
        skip_upscale: bool = False
    ) -> Dict[str, Any]:
        """
        Add text overlay to an image using Google Vertex AI's gemini-2.5-flash-image model
        and then upscale it back to target resolution using imagen-3.0-capability-001
        
        Args:
            image_path: Path to the input image file
            text_overlay_prompt: Prompt describing the text overlay (text, position, style, color)
            target_width: Desired width for the final image
            target_height: Desired height for the final image
            output_path: Optional path to save the output image
            
        Returns:
            Dictionary containing the result and output path
        """
        if not self.is_available():
            raise RuntimeError("Vertex AI is not available or properly configured")
        
        if not PIL_AVAILABLE:
            raise RuntimeError("PIL is required for image processing")
        
        try:
            logger.info(f"Adding text overlay to image using Vertex AI: {image_path}")
            
            # Create output path if not provided
            if not output_path:
                temp_dir = self._get_temp_dir()
                output_path = str(temp_dir / f"text_overlay_{uuid.uuid4()}.png")
            
            # Load the image
            image = PILImage.open(image_path)
            
            # Step 1: Use Vertex AI gemini-2.5-flash-image model to add text overlay
            logger.info("Calling Vertex AI gemini-2.5-flash-image model...")
            response = self.client.models.generate_content(
                model="gemini-2.5-flash-image",
                contents=[text_overlay_prompt, image],
                config=types.GenerateContentConfig(response_modalities=["Text", "Image"]),
            )
            
            # Extract the generated image from the response
            generated_image = None
            for part in response.candidates[0].content.parts:
                if part.inline_data is not None:
                    generated_image = PILImage.open(BytesIO(part.inline_data.data))
                    break
            
            if generated_image is None:
                raise RuntimeError("No image was generated by Vertex AI")
            
            # Save the intermediate image with text overlay
            temp_dir = self._get_temp_dir()
            intermediate_path = str(temp_dir / f"intermediate_text_overlay_{uuid.uuid4()}.png")
            generated_image.save(intermediate_path)
            
            logger.info(f"Text overlay added successfully. Intermediate image saved to: {intermediate_path}")
            logger.info(f"Intermediate image size: {generated_image.size}")
            
            if skip_upscale:
                # Skip upscaling step - just save the intermediate image as final output
                logger.info("Skipping upscaling step as requested")
                generated_image.save(output_path)
                os.unlink(intermediate_path)
            else:
                # Step 2: Upscale the image back to target resolution using imagen-3.0-capability-001
                logger.info(f"Upscaling image from {generated_image.size} to {target_width}x{target_height}...")
                
                # Create the two required images for upscaling (following the same pattern as generate_image_with_recontext_and_upscale)
                centered_image = self.create_centered_image_with_black_background(
                    Image(image_bytes=open(intermediate_path, "rb").read(), mime_type="image/png"),
                    target_width, target_height
                )
                
                mask_image = self.create_mask_image_with_black_area(
                    Image(image_bytes=open(intermediate_path, "rb").read(), mime_type="image/png"),
                    target_width, target_height
                )
                
                # Convert PIL images to bytes
                centered_image_bytes = BytesIO()
                centered_image.save(centered_image_bytes, format='PNG')
                centered_image_bytes = centered_image_bytes.getvalue()
                
                mask_image_bytes = BytesIO()
                mask_image.save(mask_image_bytes, format='PNG')
                mask_image_bytes = mask_image_bytes.getvalue()
                
                # Create reference images for upscaling
                raw_ref = RawReferenceImage(
                    reference_image=Image(image_bytes=centered_image_bytes, mime_type="image/png"),
                    reference_id=0,
                )
                mask_ref = MaskReferenceImage(
                    reference_id=1,
                    reference_image=Image(image_bytes=mask_image_bytes, mime_type="image/png"),
                    config=MaskReferenceConfig(
                        mask_mode="MASK_MODE_USER_PROVIDED",
                        mask_dilation=0.03,
                    ),
                )
                
                # Generate the upscaled image using edit_image
                logger.info("Generating upscaled image with text overlay...")
                upscaled_result = self.client.models.edit_image(
                    model="imagen-3.0-capability-001",
                    prompt="Upscale the image to the target resolution while preserving all existing content, text, and visual elements exactly as they are. Do not modify, add, or remove any content.",
                    reference_images=[raw_ref, mask_ref],
                    config=EditImageConfig(
                        edit_mode="EDIT_MODE_OUTPAINT",
                    ),
                )
                
                upscaled_image = upscaled_result.generated_images[0].image
                
                # Save the final upscaled image
                upscaled_image.save(output_path)
                
                # Clean up intermediate file
                os.unlink(intermediate_path)
            
            logger.info(f"Text overlay and upscaling completed successfully. Final image saved to: {output_path}")
            
            return {
                'success': True,
                'output_path': output_path,
                'image_saved': True,
                'text_overlay_prompt': text_overlay_prompt,
                'target_dimensions': f"{target_width}x{target_height}"
            }
            
        except Exception as e:
            logger.error(f"Failed to add text overlay and upscale image: {e}")
            return {
                'success': False,
                'error': str(e),
                'output_path': None,
                'image_saved': False
            }


# Global instance for easy access
vertex_manager = VertexManager()

def generate_video_with_prompt_and_image(
    prompt: str,
    image_url: str,
    model: str = "veo-3.0-generate-preview",
    file_path: Optional[str] = None,
    aspect_ratio: str = "16:9",
    number_of_videos: int = 1,
    negative_prompt: Optional[str] = None
) -> Dict[str, Any]:
    """Convenience function to generate video with prompt and image URL."""
    return vertex_manager.generate_video_with_prompt_and_image(
        prompt, image_url, model, file_path, aspect_ratio, number_of_videos, negative_prompt
    )


def generate_image_with_recontext_and_upscale(
    prompt: str,
    product_images: List[str],
    target_width: int = 1920,
    target_height: int = 1080,
    output_path: Optional[str] = None
) -> Dict[str, Any]:
    """Convenience function to generate image with recontext and upscale."""
    return vertex_manager.generate_image_with_recontext_and_upscale(
        prompt, product_images, target_width, target_height, output_path
    )


def add_text_overlay_to_image(
    image_path: str,
    text_overlay_prompt: str,
    target_width: int = 1920,
    target_height: int = 1080,
    output_path: Optional[str] = None,
    skip_upscale: bool = False
) -> Dict[str, Any]:
    """Convenience function to add text overlay to an image and optionally upscale it."""
    return vertex_manager.add_text_overlay_to_image(
        image_path, text_overlay_prompt, target_width, target_height, output_path, skip_upscale
    )


def is_vertex_available() -> bool:
    """Check if Vertex AI is available and configured."""
    return vertex_manager.is_available()


def is_pillow_available() -> bool:
    """Check if Pillow is available for image processing."""
    return vertex_manager.is_pillow_available()


def get_vertex_status() -> Dict[str, Any]:
    """Get Vertex AI service status and configuration."""
    # Get the project root directory (parent of app directory)
    project_root = Path(__file__).parent.parent.parent
    key_file_path = project_root / "promo-nex-ai-vertex-ai-key.json"
    
    return {
        "available": vertex_manager.is_available(),
        "configured": os.path.exists(key_file_path),
        "package_available": VERTEX_AVAILABLE,
        "pillow_available": vertex_manager.is_pillow_available()
    }
