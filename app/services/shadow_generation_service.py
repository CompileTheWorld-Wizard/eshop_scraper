"""
Shadow Generation Service for adding realistic shadows to product images.
Uses OpenAI GPT-4 Vision for image analysis and shadow prompt extraction.
Uses Vertex AI Imagen 3.0 with Subject Customization to add shadow effects.
Now supports async/polling pattern with threading.

Process:
1. Extract shadow requirements from product description using OpenAI GPT-4o-mini
2. Describe the product image using OpenAI GPT-4o Vision
3. Generate new image with shadow using Vertex AI Imagen 3.0 Subject Customization
   - SubjectReferenceImage preserves the exact product appearance
   - Only adds shadow effect while keeping product identical
4. Upload result to Supabase storage
"""

import logging
import os
import uuid
import openai
import requests
import threading
from typing import Dict, Optional, Any
from pathlib import Path
from datetime import datetime, timezone
from app.models import ShadowGenerationRequest, ShadowGenerationResponse, TaskStatus
from app.config import settings
from app.utils.supabase_utils import supabase_manager
from app.utils.vertex_utils import vertex_manager
from app.logging_config import get_logger

logger = get_logger(__name__)


class ShadowGenerationService:
    """Service for adding shadow effects to product images with async task management"""

    def __init__(self):
        self.openai_client = None
        self.vertex_manager = vertex_manager  # Use global Vertex AI instance
        self.tasks = {}  # In-memory task storage {task_id: task_info}
        self.tasks_lock = threading.Lock()  # Thread-safe access to tasks
        self._initialize_openai()
        self._check_vertex_availability()

    def _initialize_openai(self):
        """Initialize OpenAI client for prompt extraction"""
        logger.info("Initializing Shadow Generation Service (Async + Vertex AI)...")
        try:
            logger.info("→ Checking for OpenAI API key...")
            if not settings.OPENAI_API_KEY:
                logger.warning("✗ OpenAI API key not configured in settings!")
                logger.warning("→ Shadow generation service will not be available")
                return

            logger.info("✓ OpenAI API key found")
            logger.info("→ Creating OpenAI client instance...")
            self.openai_client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
            logger.info("✓ OpenAI client initialized for prompt extraction")

        except Exception as e:
            logger.error(f"✗ Failed to initialize OpenAI client!")
            logger.error(f"→ Error: {str(e)}")
            self.openai_client = None
            logger.warning("→ Shadow generation service will not be available")
    
    def _check_vertex_availability(self):
        """Check if Vertex AI is available for image generation"""
        try:
            if self.vertex_manager and self.vertex_manager.is_available():
                logger.info("✓ Vertex AI Imagen initialized for image generation")
                logger.info("✓ Shadow Generation Service ready (Async mode: OpenAI + Vertex AI)")
            else:
                logger.warning("✗ Vertex AI is not available!")
                logger.warning("→ Shadow generation will not work without Vertex AI")
        except Exception as e:
            logger.error(f"✗ Failed to check Vertex AI availability: {e}")
            logger.warning("→ Shadow generation may not work properly")
    
    def start_shadow_generation_task(self, request: ShadowGenerationRequest) -> Dict[str, Any]:
        """
        Start an async shadow generation task.
        Returns immediately with task_id for polling.
        """
        task_id = f"shadow_task_{int(datetime.now().timestamp() * 1000)}_{uuid.uuid4().hex[:8]}"
        
        logger.info("=" * 80)
        logger.info(f"🚀 STARTING ASYNC SHADOW GENERATION TASK: {task_id}")
        logger.info("=" * 80)
        logger.info(f"User ID: {request.user_id}")
        logger.info(f"Image URL: {request.image_url[:80]}...")
        logger.info(f"Scene ID: {request.scene_id or 'N/A'}")
        
        # Create task record
        task_info = {
            'task_id': task_id,
            'status': TaskStatus.PENDING,
            'user_id': request.user_id,
            'scene_id': request.scene_id,
            'short_id': request.short_id,
            'image_url': request.image_url,
            'product_description': request.product_description,
            'result_image_url': None,
            'error_message': None,
            'progress': 0,
            'current_step': 'Initializing',
            'created_at': datetime.now(timezone.utc).isoformat(),
            'updated_at': datetime.now(timezone.utc).isoformat()
        }
        
        with self.tasks_lock:
            self.tasks[task_id] = task_info
        
        # Start processing in a background thread
        thread = threading.Thread(
            target=self._process_shadow_generation,
            args=(task_id, request),
            daemon=True
        )
        thread.start()
        
        logger.info(f"✅ Task created and started in background thread")
        logger.info("=" * 80)
        
        return {
            'task_id': task_id,
            'status': TaskStatus.PENDING,
            'message': 'Shadow generation task started successfully',
            'created_at': task_info['created_at']
        }
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get the current status of a shadow generation task"""
        with self.tasks_lock:
            return self.tasks.get(task_id)
    
    def _update_task(self, task_id: str, **kwargs):
        """Update task information thread-safely"""
        with self.tasks_lock:
            if task_id in self.tasks:
                self.tasks[task_id].update(kwargs)
                self.tasks[task_id]['updated_at'] = datetime.now(timezone.utc).isoformat()
    
    def _process_shadow_generation(self, task_id: str, request: ShadowGenerationRequest):
        """
        Background worker function that processes shadow generation.
        This runs in a separate thread.
        """
        try:
            logger.info(f"🔄 [Task {task_id}] Starting shadow generation process...")
            
            self._update_task(task_id, status=TaskStatus.RUNNING, current_step='Starting', progress=10)
            
            if not self.openai_client:
                raise Exception("OpenAI client not initialized")
            
            if not self.vertex_manager or not self.vertex_manager.is_available():
                raise Exception("Vertex AI is not available")
            
            # Step 1: Extract shadow prompt with OpenAI (30% progress)
            logger.info(f"[Task {task_id}] Step 1/4: Extracting shadow prompt with OpenAI GPT-4o-mini...")
            self._update_task(task_id, current_step='Generating shadow prompt with OpenAI', progress=30)
            shadow_prompt = self._extract_shadow_prompt(request.product_description)
            logger.info(f"[Task {task_id}] ✓ Shadow prompt extraction completed")
            logger.info(f"[Task {task_id}]   → Shadow prompt: {shadow_prompt[:100]}...")
            
            # Step 2: Describe product image with OpenAI Vision (50% progress)
            logger.info(f"[Task {task_id}] Step 2/4: Describing product image with OpenAI GPT-4o Vision...")
            self._update_task(task_id, current_step='Analyzing product image', progress=50)
            image_description = self._describe_product_image(request.image_url)
            logger.info(f"[Task {task_id}] ✓ Image description completed")
            logger.info(f"[Task {task_id}]   → Description: {image_description[:100]}...")
            
            # Step 3: Add shadow with Vertex AI Subject Customization (75% progress)
            logger.info(f"[Task {task_id}] Step 3/4: Adding shadow effect with Vertex AI Subject Customization...")
            self._update_task(task_id, current_step='Adding shadow effect with Vertex AI', progress=75)
            generated_image_path = self._generate_image_with_vertex_subject_customization(
                product_image_url=request.image_url,
                shadow_prompt=shadow_prompt,
                image_description=image_description
            )
            
            if not generated_image_path:
                raise Exception("Failed to add shadow using Vertex AI Subject Customization")
            
            logger.info(f"[Task {task_id}] ✓ Shadow effect added successfully (Vertex AI Subject Customization)")
            logger.info(f"[Task {task_id}]   → Local file path: {generated_image_path}")
            
            # Step 4: Upload to Supabase (95% progress)
            logger.info(f"[Task {task_id}] Step 4/4: Uploading to Supabase...")
            self._update_task(task_id, current_step='Uploading to storage', progress=95)
            final_image_url = self._upload_to_supabase(generated_image_path, request.user_id)
            
            if not final_image_url:
                raise Exception("Failed to upload image to storage")
            
            logger.info(f"[Task {task_id}] ✓ Image upload completed")
            
            # Cleanup temp files
            self._cleanup_temp_files([generated_image_path])
            
            # Update scene in database if scene_id provided
            if request.scene_id:
                logger.info(f"[Task {task_id}] Updating scene {request.scene_id} in database...")
                try:
                    import asyncio
                    asyncio.run(supabase_manager.update_record(
                        table='video_scenes',
                        filters={'id': request.scene_id},
                        updates={'image_url': final_image_url, 'updated_at': datetime.now(timezone.utc).isoformat()}
                    ))
                    logger.info(f"[Task {task_id}] ✓ Scene updated in database")
                except Exception as e:
                    logger.warning(f"[Task {task_id}] Failed to update scene in database: {e}")
            
            # Mark task as completed (100% progress)
            self._update_task(
                task_id,
                status=TaskStatus.COMPLETED,
                result_image_url=final_image_url,
                current_step='Completed',
                progress=100
            )
            
            logger.info("=" * 80)
            logger.info(f"✅ [Task {task_id}] SHADOW GENERATION COMPLETED SUCCESSFULLY!")
            logger.info(f"Final Image URL: {final_image_url}")
            logger.info("=" * 80)
            
        except Exception as e:
            logger.error("=" * 80)
            logger.error(f"❌ [Task {task_id}] SHADOW GENERATION FAILED!")
            logger.error(f"Error: {str(e)}")
            logger.error("=" * 80)
            
            self._update_task(
                task_id,
                status=TaskStatus.FAILED,
                error_message=str(e),
                current_step='Failed',
                progress=0
            )

    def generate_shadow_image(self, request: ShadowGenerationRequest) -> ShadowGenerationResponse:
        """
        Generate an image with shadow effect applied
        
        Args:
            request: ShadowGenerationRequest with image_url and product_description
            
        Returns:
            ShadowGenerationResponse with the new image URL or error
        """
        logger.info("=" * 80)
        logger.info("SHADOW GENERATION STARTED")
        logger.info("=" * 80)
        logger.info(f"User ID: {request.user_id}")
        logger.info(f"Image URL: {request.image_url}")
        logger.info(f"Product Description: {request.product_description}")
        logger.info("-" * 80)
        
        try:
            if not self.openai_client:
                logger.error("OpenAI client is not initialized!")
                raise Exception("OpenAI client not initialized")

            logger.info("OpenAI client is ready")
            
            # Step 1: Analyze the original image to understand its content
            logger.info("\n[STEP 1/5] Analyzing original image with GPT-4 Vision...")
            logger.info(f"Analyzing image from URL: {request.image_url}")
            image_description = self._analyze_image_with_vision(request.image_url)
            logger.info("✓ Image analysis completed")
            logger.info(f"Image Description: {image_description}")
            logger.info("-" * 80)
            
            # Step 2: Extract shadow prompt from product description
            logger.info("\n[STEP 2/5] Extracting shadow prompt from product description...")
            logger.info(f"Product Description: {request.product_description}")
            shadow_prompt = self._extract_shadow_prompt(request.product_description)
            logger.info("✓ Shadow prompt extraction completed")
            logger.info(f"Shadow Prompt: {shadow_prompt}")
            logger.info("-" * 80)
            
            # Step 3: Generate image with shadow using OpenAI DALL-E
            logger.info("\n[STEP 3/5] Generating new image with shadow effect using DALL-E 3...")
            generated_image_url = self._generate_image_with_openai(
                image_description=image_description,
                shadow_prompt=shadow_prompt
            )
            
            if not generated_image_url:
                logger.error("✗ Failed to generate image - no URL returned")
                raise Exception("Failed to generate image with shadow")
            
            logger.info("✓ Image generation completed")
            logger.info(f"Generated Image URL: {generated_image_url}")
            logger.info("-" * 80)
            
            # Step 4: Download the generated image
            logger.info("\n[STEP 4/5] Downloading generated image to local storage...")
            logger.info(f"Downloading from: {generated_image_url}")
            generated_image_path = self._download_image(generated_image_url)
            if not generated_image_path:
                logger.error("✗ Failed to download generated image")
                raise Exception("Failed to download generated image")
            
            logger.info("✓ Image download completed")
            logger.info(f"Downloaded to: {generated_image_path}")
            logger.info("-" * 80)
            
            # Step 5: Upload to Supabase storage
            logger.info("\n[STEP 5/5] Uploading image to Supabase storage...")
            logger.info(f"Uploading from local path: {generated_image_path}")
            logger.info(f"User ID for storage: {request.user_id}")
            final_image_url = self._upload_to_supabase(generated_image_path, request.user_id)
            
            if not final_image_url:
                logger.error("✗ Failed to upload image to Supabase")
                raise Exception("Failed to upload image to storage")
            
            logger.info("✓ Image upload completed")
            logger.info(f"Final Image URL: {final_image_url}")
            logger.info("-" * 80)
            
            # Clean up temporary files
            logger.info("\n[CLEANUP] Removing temporary files...")
            self._cleanup_temp_files([generated_image_path])
            logger.info("✓ Cleanup completed")
            
            logger.info("\n" + "=" * 80)
            logger.info("SHADOW GENERATION COMPLETED SUCCESSFULLY!")
            logger.info("=" * 80)
            logger.info(f"Final Result: {final_image_url}")
            logger.info("=" * 80 + "\n")
            
            return ShadowGenerationResponse(
                success=True,
                image_url=final_image_url,
                message="Shadow effect applied successfully"
            )

        except Exception as e:
            logger.error("\n" + "=" * 80)
            logger.error("SHADOW GENERATION FAILED!")
            logger.error("=" * 80)
            logger.error(f"Error Type: {type(e).__name__}")
            logger.error(f"Error Message: {str(e)}")
            logger.error("=" * 80 + "\n")
            
            return ShadowGenerationResponse(
                success=False,
                image_url=None,
                message="Failed to generate shadow image",
                error=str(e)
            )

    def _analyze_image_with_vision(self, image_url: str) -> str:
        """
        Analyze the image using GPT-4 Vision to get a detailed description
        
        Args:
            image_url: URL of the image to analyze
            
        Returns:
            Detailed description of the image
        """
        try:
            logger.info("  → Calling GPT-4 Vision API...")
            logger.info(f"  → Model: gpt-4o")
            logger.info(f"  → Max tokens: 500")
            logger.info(f"  → Image URL: {image_url}")
            
            response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": """Provide a detailed, professional description of this product image suitable for recreating it. 
Focus on:
- The main product and its key features
- Colors, materials, and textures
- Product positioning and angle
- Background style and color
- Overall composition and framing
- Any text or branding visible
- Lighting and atmosphere

Be precise and detailed. This description will be used to recreate the image."""
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": image_url
                                }
                            }
                        ]
                    }
                ],
                max_tokens=500
            )
            
            description = response.choices[0].message.content.strip()
            logger.info("  → Vision API call successful")
            logger.info(f"  → Response length: {len(description)} characters")
            logger.info(f"  → Description preview: {description[:100]}...")
            
            return description

        except Exception as e:
            logger.error(f"  → Vision API call failed!")
            logger.error(f"  → Error: {str(e)}")
            logger.warning("  → Using fallback generic description")
            # Return a generic description if vision fails
            return "A product photograph on a neutral background"

    def _describe_product_image(self, image_url: str) -> str:
        """
        Describe the product image using OpenAI GPT-4 Vision.
        This description is used as the subject_description for Vertex AI Subject Customization.
        
        Args:
            image_url: URL of the product image
            
        Returns:
            A detailed description of the product image
        """
        try:
            logger.info("  → Calling GPT-4o Vision for image description...")
            logger.info(f"  → Model: gpt-4o")
            logger.info(f"  → Temperature: 0.3")
            logger.info(f"  → Max tokens: 500")
            
            system_message = """You are an expert in product photography and image analysis. 
Your task is to describe product images in detail for use with AI image generation."""

            user_message = """Describe this product image concisely for AI subject customization. Focus on:
- Product type and specific details
- Colors, materials, textures
- Orientation and viewing angle
- Key visual features

Provide a clear, concise description (1-2 sentences) suitable for use as a subject description in AI image generation.
Example: "a pair of black leather sneakers with white soles, shown from a three-quarter angle on a white background" """

            logger.info("  → Sending request to OpenAI Vision API...")
            response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_message},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_message},
                            {"type": "image_url", "image_url": {"url": image_url}}
                        ]
                    }
                ],
                temperature=0.3,
                max_tokens=500
            )
            
            description = response.choices[0].message.content.strip()
            logger.info("  → Image description successful!")
            logger.info(f"  → Description: {description}")
            
            return description
            
        except Exception as e:
            logger.error(f"  → Image description failed: {str(e)}")
            # Return a generic description if vision fails
            return "a product on a clean white background"

    def _extract_shadow_prompt(self, product_description: str) -> str:
        """
        Extract a shadow generation prompt from the product description using OpenAI
        
        Args:
            product_description: The product description text
            
        Returns:
            A detailed prompt for shadow generation
        """
        try:
            logger.info("  → Calling GPT-4o-mini for shadow prompt extraction...")
            logger.info(f"  → Model: gpt-4o-mini")
            logger.info(f"  → Temperature: 0.7")
            logger.info(f"  → Max tokens: 300")
            
            system_message = """You are an expert in product photography and image editing. 
Your task is to create a detailed prompt for adding realistic shadows to product images."""

            user_message = f"""Using the following product description, generate a prompt to apply ONLY a realistic shadow effect to the image. 

CRITICAL REQUIREMENTS:
- DO NOT modify, change, or reshape the product itself
- DO NOT alter, change, or modify the background
- DO NOT change any colors, textures, or materials of the product
- ONLY add a natural shadow underneath or behind the product
- Keep the product's original shape, size, and proportions exactly as they are
- Keep the background exactly as it is

The shadow should:
- Be subtle and realistic, as if cast by natural or studio lighting
- Appear underneath or behind the product to ground it on the surface
- Have soft, natural edges with appropriate blur
- Be dark gray or semi-transparent black (not colored)
- Enhance depth without overwhelming the product
- Match the lighting direction naturally

Product Description:
{product_description}

Generate a clear, detailed prompt that focuses EXCLUSIVELY on adding a shadow effect while preserving everything else unchanged. Focus on:
- Shadow placement (underneath/behind the product)
- Shadow direction and angle
- Shadow softness and blur radius
- Shadow color (dark gray/semi-transparent black) and opacity
- How the shadow grounds the product on the surface

Provide ONLY the shadow prompt without any explanations or preamble. The prompt should emphasize adding ONLY a shadow while keeping the product and background unchanged."""

            logger.info(f"  → Sending product description: {product_description[:100]}...")
            
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.7,
                max_tokens=300
            )

            shadow_prompt = response.choices[0].message.content.strip()
            logger.info("  → Shadow prompt extraction successful")
            logger.info(f"  → Prompt length: {len(shadow_prompt)} characters")
            logger.info(f"  → Prompt preview: {shadow_prompt[:100]}...")
            
            return shadow_prompt

        except Exception as e:
            logger.error(f"  → Shadow prompt extraction failed!")
            logger.error(f"  → Error: {str(e)}")
            logger.warning("  → Using fallback default shadow prompt")
            # Return a default shadow prompt if extraction fails
            return "Add ONLY a realistic soft shadow beneath the product. Do not change the product shape, size, or any details. Do not modify the background. The shadow should be subtle, slightly blurred with soft edges, using dark gray or semi-transparent black color. The shadow should naturally ground the product as if placed on a surface with natural lighting from above."

    def _generate_image_with_vertex_subject_customization(
        self, 
        product_image_url: str, 
        shadow_prompt: str,
        image_description: str
    ) -> Optional[str]:
        """
        Generate an image with shadow effect using Vertex AI Imagen 3.0 Subject Customization.
        Uses SubjectReferenceImage to preserve the exact product while adding shadow effect.
        
        Args:
            product_image_url: URL of the original product image
            shadow_prompt: The shadow effect requirements
            image_description: Description of the product for subject configuration
            
        Returns:
            Path to the generated image file or None if failed
        """
        try:
            logger.info("  → Preparing Vertex AI Imagen 3.0 Subject Customization...")
            
            if not self.vertex_manager or not self.vertex_manager.is_available():
                raise RuntimeError("Vertex AI is not available")
            
            # Step 1: Download the product image
            logger.info("  → Downloading product image...")
            product_image_path = self._download_image(product_image_url)
            
            if not product_image_path:
                raise RuntimeError("Failed to download product image")
            
            logger.info(f"  → Product image downloaded: {product_image_path}")
            
            # Step 2: Create the edit prompt for adding shadow
            # Reference the subject with [1] to use subject customization
            edit_prompt = f"""A professional product photograph of {image_description}[1] with ONLY a realistic shadow effect added.

CRITICAL: Keep the product EXACTLY as shown in the reference image:
- DO NOT change the product's shape, size, or proportions
- DO NOT modify colors, textures, materials, or any product details
- DO NOT alter or change the background
- ONLY add a realistic shadow effect

{shadow_prompt}

The shadow should be subtle, natural, and placed beneath or behind the product to ground it on the surface.
The shadow should have soft edges with appropriate blur, using dark gray or semi-transparent black color.

Style: Professional product photography, commercial grade, studio lighting, clean background."""
            
            logger.info("  → Subject Customization Prompt:")
            logger.info("  " + "-" * 76)
            for line in edit_prompt.split('\n'):
                logger.info(f"  {line}")
            logger.info("  " + "-" * 76)
            
            # Step 3: Use Vertex AI Imagen 3.0 with Subject Customization
            use_model = os.getenv("SHADOW_IMAGEN_MODEL", "imagen-3.0-capability-001")
            
            logger.info(f"  → Model: {use_model}")
            logger.info(f"  → Method: edit_image with SubjectReferenceImage")
            logger.info(f"  → Subject: {image_description[:100]}...")
            logger.info(f"  → Output Resolution: 1920x1080 (16:9)")
            
            # Import required types
            try:
                from google.genai.types import (
                    EditImageConfig,
                    SubjectReferenceImage,
                    SubjectReferenceConfig,
                    Image
                )
            except ImportError:
                raise RuntimeError("Google Vertex AI types not available")
            
            # Load the product image
            with open(product_image_path, 'rb') as f:
                product_image_bytes = f.read()
            
            # Create subject reference from the product image
            subject_reference = SubjectReferenceImage(
                reference_id=1,
                reference_image=Image(image_bytes=product_image_bytes),
                config=SubjectReferenceConfig(
                    subject_description=image_description,
                    subject_type="SUBJECT_TYPE_PRODUCT"  # Product type for non-person subjects
                )
            )
            
            logger.info("  → Calling Vertex AI Imagen API with Subject Customization...")
            
            # Use edit_image with subject customization
            # Output will be 1920x1080 resolution (16:9 aspect ratio)
            result = self.vertex_manager.client.models.edit_image(
                model=use_model,
                prompt=edit_prompt,
                reference_images=[subject_reference],
                config=EditImageConfig(
                    edit_mode="EDIT_MODE_DEFAULT",  # Default mode for subject customization
                    number_of_images=1,
                    aspect_ratio="16:9",  # 1920x1080 resolution (Full HD)
                    safety_filter_level="BLOCK_ONLY_HIGH",
                    person_generation="ALLOW_ALL"
                )
            )
            
            if not result.generated_images:
                raise RuntimeError("No images were generated")
            
            generated_image = result.generated_images[0].image
            logger.info("  → Shadow effect added successfully with Subject Customization!")
            
            # Step 4: Save the generated image
            temp_dir = self._get_temp_dir()
            output_path = str(temp_dir / f"shadowed_image_{uuid.uuid4()}.png")
            generated_image.save(output_path)
            
            logger.info(f"  → Generated image saved: {output_path}")
            
            # Clean up the downloaded product image
            try:
                os.unlink(product_image_path)
                logger.info("  → Cleaned up temporary product image")
            except Exception as e:
                logger.warning(f"  → Failed to clean up temp image: {e}")
            
            # Return the local file path
            return output_path

        except Exception as e:
            logger.error(f"  → Vertex AI Subject Customization failed!")
            logger.error(f"  → Error: {str(e)}")
            logger.error(f"  → Error type: {type(e).__name__}")
            return None

    def _download_image(self, image_url: str, max_retries: int = 3) -> Optional[str]:
        """
        Download an image from URL to temporary storage with retry logic.
        
        Args:
            image_url: URL of the image to download
            max_retries: Maximum number of retry attempts (default: 3)
            
        Returns:
            Path to the downloaded image file or None if failed
        """
        import time
        
        temp_dir = self._get_temp_dir()
        image_uuid = uuid.uuid4()
        temp_image_path = str(temp_dir / f"temp_image_{image_uuid}.png")
        
        logger.info("  → Preparing to download image...")
        logger.info(f"  → Temp directory: {temp_dir}")
        logger.info(f"  → Target file path: {temp_image_path}")
        logger.info(f"  → Max retries: {max_retries}")
        
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"  → Attempt {attempt}/{max_retries}")
                logger.info(f"  → Sending HTTP GET request to: {image_url[:100]}...")
                logger.info(f"  → Timeout: 120 seconds (increased for large images)")
                
                # Use streaming to handle large files better
                response = requests.get(image_url, timeout=120, stream=True)
                response.raise_for_status()
                
                logger.info(f"  → HTTP Status: {response.status_code}")
                logger.info(f"  → Content-Type: {response.headers.get('Content-Type', 'unknown')}")
                
                # Get content length if available
                content_length = response.headers.get('Content-Length')
                if content_length:
                    logger.info(f"  → Content-Length: {int(content_length)} bytes ({int(content_length) / 1024 / 1024:.2f} MB)")
                
                logger.info("  → Writing image data to file (streaming)...")
                
                # Download in chunks for better memory handling
                downloaded_bytes = 0
                chunk_size = 8192  # 8KB chunks
                
                with open(temp_image_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if chunk:  # filter out keep-alive chunks
                            f.write(chunk)
                            downloaded_bytes += len(chunk)
                
                file_size = os.path.getsize(temp_image_path)
                logger.info(f"  → File saved successfully")
                logger.info(f"  → Downloaded: {downloaded_bytes} bytes ({downloaded_bytes / 1024 / 1024:.2f} MB)")
                logger.info(f"  → File size: {file_size} bytes")
                logger.info(f"  → Download completed: {temp_image_path}")
                
                # Verify the file is not empty
                if file_size == 0:
                    logger.error(f"  → Downloaded file is empty!")
                    if attempt < max_retries:
                        logger.warning(f"  → Retrying in 2 seconds...")
                        time.sleep(2)
                        continue
                    return None
                
                return temp_image_path

            except requests.exceptions.Timeout:
                logger.error(f"  → Download timeout after 120 seconds (Attempt {attempt}/{max_retries})")
                logger.error(f"  → URL: {image_url[:100]}...")
                
                if attempt < max_retries:
                    wait_time = 2 ** attempt  # Exponential backoff: 2, 4, 8 seconds
                    logger.warning(f"  → Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"  → All {max_retries} attempts failed due to timeout")
                    return None
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"  → Download failed - HTTP error (Attempt {attempt}/{max_retries})")
                logger.error(f"  → Error: {str(e)}")
                logger.error(f"  → URL: {image_url[:100]}...")
                
                if attempt < max_retries:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(f"  → Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"  → All {max_retries} attempts failed")
                    return None
                    
            except Exception as e:
                logger.error(f"  → Download failed - unexpected error (Attempt {attempt}/{max_retries})")
                logger.error(f"  → Error: {str(e)}")
                logger.error(f"  → Error type: {type(e).__name__}")
                
                if attempt < max_retries:
                    wait_time = 2
                    logger.warning(f"  → Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"  → All {max_retries} attempts failed")
                    return None
        
        return None

    def _upload_to_supabase(self, image_path: str, user_id: str) -> Optional[str]:
        """
        Upload the generated image to Supabase storage
        
        Args:
            image_path: Path to the image file to upload
            user_id: User ID for organizing uploads
            
        Returns:
            Public URL of the uploaded image or None if failed
        """
        try:
            logger.info("  → Checking Supabase connection...")
            if not supabase_manager.is_connected():
                logger.info("  → Supabase not connected, establishing connection...")
                supabase_manager.ensure_connection()
                logger.info("  → Supabase connection established")
            else:
                logger.info("  → Supabase already connected")
            
            # Read the image file
            logger.info(f"  → Reading image file from: {image_path}")
            with open(image_path, 'rb') as f:
                image_data = f.read()
            
            file_size = len(image_data)
            logger.info(f"  → File size to upload: {file_size} bytes")
            
            # Generate unique filename
            image_uuid = uuid.uuid4()
            filename = f"shadow-images/{user_id}/{image_uuid}.png"
            logger.info(f"  → Target storage path: {filename}")
            logger.info(f"  → Storage bucket: generated-content")
            
            # Upload to Supabase storage
            logger.info("  → Uploading to Supabase storage...")
            supabase_manager.client.storage.from_('generated-content').upload(
                path=filename,
                file=image_data,
                file_options={'content-type': 'image/png'}
            )
            logger.info("  → Upload successful")
            
            # Get public URL
            logger.info("  → Retrieving public URL...")
            public_url = supabase_manager.client.storage.from_('generated-content').get_public_url(filename)
            
            logger.info("  → Public URL generated successfully")
            logger.info(f"  → Public URL: {public_url}")
            
            return public_url

        except Exception as e:
            logger.error(f"  → Supabase upload failed!")
            logger.error(f"  → Error type: {type(e).__name__}")
            logger.error(f"  → Error message: {str(e)}")
            return None

    def _get_temp_dir(self) -> Path:
        """Get or create the temp directory for temporary files"""
        project_root = Path(__file__).parent.parent.parent
        temp_dir = project_root / "temp"
        temp_dir.mkdir(exist_ok=True)
        return temp_dir

    def _cleanup_temp_files(self, file_paths: list):
        """Clean up temporary files"""
        logger.info(f"  → Cleaning up {len(file_paths)} temporary file(s)...")
        
        for i, file_path in enumerate(file_paths, 1):
            try:
                if file_path and os.path.exists(file_path):
                    file_size = os.path.getsize(file_path)
                    logger.info(f"  → [{i}/{len(file_paths)}] Deleting: {file_path} ({file_size} bytes)")
                    os.unlink(file_path)
                    logger.info(f"  → [{i}/{len(file_paths)}] Deleted successfully")
                else:
                    logger.warning(f"  → [{i}/{len(file_paths)}] File not found or invalid: {file_path}")
            except Exception as e:
                logger.warning(f"  → [{i}/{len(file_paths)}] Failed to delete: {file_path}")
                logger.warning(f"  → Error: {str(e)}")
        
        logger.info(f"  → Cleanup process completed")


# Global service instance
shadow_generation_service = ShadowGenerationService()
