"""
Scenario Generation Service for creating AI-powered video scenarios.
Handles OpenAI API calls for scenario generation and Google Vertex AI for image generation.
"""

import threading
import time
import json
import logging
import os
import uuid
import openai
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from pathlib import Path
from app.models import (
    ScenarioGenerationRequest, ScenarioGenerationResponse, GeneratedScenario,
    Scene, DetectedDemographics, TaskStatus
)

from app.utils.vertex_utils import generate_image_with_recontext_and_upscale, add_text_overlay_to_image, vertex_manager
from app.utils.task_management import (
    create_task, start_task, update_task_progress,
    complete_task, fail_task, TaskType, TaskStatus as TMStatus
)
from app.utils.credit_utils import can_perform_action, deduct_credits
from app.utils.supabase_utils import supabase_manager
from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)


class ScenarioGenerationService:
    """Service for generating AI-powered video scenarios"""

    def __init__(self):
        self.openai_client = None
        self._initialize_openai()

    def _initialize_openai(self):
        """Initialize OpenAI client"""
        try:
            if not settings.OPENAI_API_KEY:
                logger.warning("OpenAI API key not configured")
                return

            self.openai_client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
            logger.info("OpenAI client initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            self.openai_client = None

    def start_scenario_generation_task(self, request: ScenarioGenerationRequest) -> Dict[str, Any]:
        """Start a scenario generation task"""
        try:
            if not self.openai_client:
                raise Exception("OpenAI client not initialized")

            task_id = create_task(
                TaskType.SCENARIO_GENERATION,
                user_id=request.user_id,
                product_id=request.product_id
            )

            if not task_id:
                raise Exception("Failed to create scenario generation task")

            start_task(task_id)

            # Start background processing in a separate thread with asyncio
            import asyncio

            def run_async_task():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(
                        self._process_scenario_generation_task(task_id, request))
                finally:
                    loop.close()

            thread = threading.Thread(
                target=run_async_task,
                daemon=True,
                name=f"scenario_generation_{task_id}"
            )
            thread.start()

            logger.info(
                f"Started scenario generation thread for task {task_id}")

            return {
                "task_id": task_id,
                "status": "pending",
                "message": "Scenario generation task started"
            }

        except Exception as e:
            logger.error(f"Failed to start scenario generation task: {e}")
            raise

    async def _process_scenario_generation_task(self, task_id: str, request: ScenarioGenerationRequest):
        """Process the scenario generation task in the background thread"""
        thread_name = threading.current_thread().name
        logger.info(
            f"[{thread_name}] Starting scenario generation task {task_id}")

        try:
            # Update task status to running
            update_task_progress(
                task_id, 0, "Starting scenario generation", 20.0)

            # Check if user has enough credits
            if not can_perform_action(request.user_id, "generate_scenario"):
                raise Exception("Insufficient credits for scenario generation")

            update_task_progress(task_id, 20, "Generating AI scenario", 60.0)

            # Step 1: Generate scenario using OpenAI
            scenario = await self._generate_scenario_with_openai(request)
            if not scenario:
                raise Exception("Failed to generate scenario with OpenAI")

            update_task_progress(
                task_id, 60, "Generating thumbnail image", 90.0)

            # Step 2: Generate thumbnail image using Vertex AI
            thumbnail_url = await self._generate_thumbnail_image(request, scenario)
            if not thumbnail_url:
                logger.warning(
                    "Failed to generate thumbnail image, continuing without it")

            # Set the thumbnail URL in the scenario object
            scenario.thumbnail_url = thumbnail_url

            update_task_progress(task_id, 90, "Finalizing scenario", 100.0)

            # Step 3: Complete the task with generated scenario and thumbnail
            complete_task(task_id, {
                "scenario": scenario.dict(),
                "thumbnail_url": thumbnail_url  # Pass thumbnail URL in response
            })

            logger.info(
                f"[{thread_name}] Scenario generation task {task_id} completed successfully")

        except Exception as e:
            logger.error(
                f"[{thread_name}] Scenario generation task {task_id} failed: {e}")
            fail_task(task_id, str(e))

    async def _get_product_by_id(self, product_id: str) -> Optional[Dict[str, Any]]:
        """Fetch product data from database"""
        try:
            if not supabase_manager.is_connected():
                supabase_manager.ensure_connection()

            result = supabase_manager.client.table(
                'products').select('*').eq('id', product_id).execute()

            if result.data and len(result.data) > 0:
                product = result.data[0]

                return {
                    "title": product.get('title', ''),
                    "description": product.get('description', ''),
                    "price": product.get('price', 0),
                    "currency": product.get('currency', 'USD'),
                    "specifications": product.get('specifications', {}),
                    "rating": product.get('rating'),
                    "review_count": product.get('review_count'),
                    "images": product.get('images', {})
                }

            return None

        except Exception as e:
            logger.error(f"Failed to fetch product data: {e}")
            return None

    async def _generate_scenario_with_openai(self, request: ScenarioGenerationRequest) -> Optional[GeneratedScenario]:
        """Generate scenario using OpenAI API"""
        try:
            system_message = await self._build_system_message(request)
            user_message = await self._build_user_message(request)

            logger.info("Sending request to OpenAI...")
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message}
                ],
                functions=[self._get_scenario_generation_function()],
                function_call={"name": "generate_single_scenario"},
                temperature=0.2,
                top_p=0.1
            )

            logger.info("OpenAI response received")
            logger.info(f"Response choices: {len(response.choices)}")

            if not response.choices:
                raise Exception("No choices in OpenAI response")

            function_call = response.choices[0].message.function_call
            if not function_call:
                raise Exception("No function call in OpenAI response")

            try:
                result = json.loads(function_call.arguments)
            except json.JSONDecodeError as e:
                logger.error(
                    f"Failed to parse function call arguments as JSON: {e}")
                logger.error(f"Raw arguments: {function_call.arguments}")
                raise Exception(
                    f"Invalid JSON in function call arguments: {e}")

            generated_scenario = result.get('scenario')

            if not generated_scenario:
                raise Exception("No scenario generated")

            if not isinstance(generated_scenario, dict):
                logger.warning(
                    f"AI returned unexpected format: {type(generated_scenario)}. Attempting to create fallback scenario...")
                # Try to create a basic scenario from the response
                if isinstance(generated_scenario, str):
                    # If it's a string, try to parse it as JSON
                    try:
                        generated_scenario = json.loads(generated_scenario)
                    except json.JSONDecodeError:
                        logger.error("Failed to parse string response as JSON")
                        raise Exception(
                            f"AI returned string instead of structured scenario: {generated_scenario}")
                else:
                    raise Exception(
                        f"Expected scenario to be a dictionary, got {type(generated_scenario)}: {generated_scenario}")

            # Validate that we have the required fields
            required_fields = ['title', 'description', 'scenes',
                'detectedDemographics', 'thumbnailPrompt']
            missing_fields = [
                field for field in required_fields if field not in generated_scenario]
            if missing_fields:
                logger.warning(
                    f"Missing required fields: {missing_fields}. Creating fallback values...")
                # Create fallback values for missing fields
                if 'title' not in generated_scenario:
                    generated_scenario['title'] = 'Generated Video Scenario'
                if 'description' not in generated_scenario:
                    generated_scenario['description'] = 'AI-generated video scenario'
                if 'scenes' not in generated_scenario:
                    generated_scenario['scenes'] = []
                if 'detectedDemographics' not in generated_scenario:
                    generated_scenario['detectedDemographics'] = {
                        'targetGender': 'unisex',
                        'ageGroup': 'all-ages',
                        'productType': 'general',
                        'demographicContext': 'gender-neutral characters/models throughout'
                    }
                if 'thumbnailPrompt' not in generated_scenario:
                    generated_scenario['thumbnailPrompt'] = 'Create an eye-catching thumbnail for this video content'

            return await self._transform_openai_response(generated_scenario, request)

        except Exception as e:
            logger.error(
                f"Failed to generate scenario with OpenAI: {e}", exc_info=True)
            return None

    async def _build_system_message(self, request: ScenarioGenerationRequest) -> str:
        """Build system message for OpenAI"""
        expected_scene_count = request.video_length // 8
        product_data = await self._get_product_by_id(request.product_id)

        environment_context = f"- Environment: \"{request.environment}\"" if request.environment else ""

        return f"""You are the PromoNexAI Video Director.
Your only job is to produce a deterministic SCENE_PLAN as FLAT JSON for Veo3,
based on product reference images and product data supplied by the host.

You do not generate video.
You do not invent product variants.
You must always respond with a single flat JSON object.
You must not output XML.
You must not output nested JSON objects.
You must not output JSON arrays.

--------------------------------------------------
1. CORE PURPOSE
--------------------------------------------------
Produce 3–6 scenes of exactly 8 seconds each (24–48 seconds total)
for a marketing-style product video, where:

- Product geometry, colors, logos, labels and text stay 1:1 consistent
  with the reference images.
- Camera, framing and motion are cinematic but never distort
  or hide the true product shape or design.
- Every scene is strictly grounded in the provided reference images.

If you cannot respect all constraints,
you must return status = "FAIL" with a short technical reason
and all scenes marked as not included.

--------------------------------------------------
2. NON-NEGOTIABLE CONSTRAINTS
--------------------------------------------------

2.1 Product Fidelity (Shape, Color, Structure)
- Do not invent or modify geometry.
- Do not add or remove buttons, ports, openings, curves, edges, handles, caps.
- Do not change dimensions or proportions.
- Do not change colors or finishes.
- If a side or surface is not visible in any reference image:
  - do not describe new features on that side
  - keep it neutral and consistent with visible parts
  - or keep it out of frame.

2.2 Text, Logos and Labels
- Read all visible text, logos and labels from the reference images.
- Reproduce them verbatim where relevant.
- Do not invent new text, slogans, badges, icons or certifications.
- Do not translate, rephrase or shorten on-product text.
- If text is unreadable, use the phrase: "unreadable in reference images".

2.3 Scene Count and Timing
- There must be between 3 and 6 included scenes.
- Every included scene must have duration_sec = 8.
- total_duration_sec must equal total_scenes * 8.
- If you cannot produce a valid plan with these constraints, set status = "FAIL".

2.4 Camera and Motion
Allowed:
- slow pans
- slow orbit or rotation
- smooth push-in or pull-back
- subtle parallax
- macro close-ups on real details

Forbidden:
- fast, chaotic movement
- camera motion that bends or distorts the product
- transitions that imply the product changes shape or size

2.5 Backgrounds and Context
- Use neutral, studio-like backgrounds unless the reference images
  clearly show a specific environment.
- Do not place the product into lifestyle scenes, hands, people,
  outdoor or room settings unless that environment is clearly present
  in the reference images.
- No extra props unless they are explicitly visible in the references.

2.6 People and Hands
- Do not add people, faces, hands or bodies unless clearly visible
  in the reference images and explicitly described by the host.

--------------------------------------------------
3. INPUTS FROM HOST
--------------------------------------------------
The host provides:

- PRODUCT_CONTEXT:
  - product name
  - short marketing angle
  - key benefits or features
- REFERENCE_IMAGES:
  - a set of images with IDs, for example: img_01, img_02, ...
- OPTIONAL: TARGET_AUDIENCE, BRAND_TONE (for style, not geometry)

You must use REFERENCE_IMAGES as ground truth for:
- geometry
- colors
- text and labels
- logos
- material and finish

--------------------------------------------------
4. FLAT JSON RESPONSE CONTRACT
--------------------------------------------------

You must respond with exactly one flat JSON object.
Flat JSON means:
- only top-level key-value pairs
- values may be strings, numbers or booleans
- no nested objects
- no arrays

Top-level keys:

status
- string, must be "OK" or "FAIL"

total_scenes
- integer
- if status = "OK": between 3 and 6
- if status = "FAIL": 0

total_duration_sec
- integer
- if status = "OK": total_scenes * 8
- if status = "FAIL": 0

status_reason
- string
- if status = "OK": empty string ""
- if status = "FAIL": short technical reason

For scenes you must use a flat, indexed naming pattern.
Support up to 6 scenes maximum.
For each index N from 1 to 6, you must output all of these keys:

sceneN_included
- boolean
- true if this scene is part of the plan
- false if this scene is not used

sceneN_duration_sec
- integer
- if sceneN_included = true: must be 8
- if sceneN_included = false: must be 0

sceneN_focus
- string
- short description of what we see: product part, angle, key feature
- if sceneN_included = false: must be empty string ""

sceneN_ref_ids
- string
- comma-separated list of reference image IDs used for this scene
  for example: "img_01" or "img_01,img_03"
- no spaces in this list
- only use IDs that exist in REFERENCE_IMAGES
- if sceneN_included = false: must be empty string ""

sceneN_camera_shot_type
- string
- examples: "macro close-up", "medium product shot", "wide hero shot"
- if sceneN_included = false: must be empty string ""

sceneN_camera_motion
- string
- examples: "slow left-to-right pan", "slow orbit", "static"
- if sceneN_included = false: must be empty string ""

sceneN_lighting
- string
- simple, factual description of lighting, no hype
- if sceneN_included = false: must be empty string ""

sceneN_visual_prompt
- string
- clear, objective description of what Veo3 should show in this scene
- describe only what is consistent with the reference images
- mention any visible on-product text or logos verbatim
- do not add new features, text, labels or variants
- if sceneN_included = false: must be empty string ""

sceneN_audio_hint
- string
- optional: up to 1–2 short sentences for voice-over timing
- maximum about 15–20 words
- aligned with the visual focus of this scene
- do not change any product facts
- if sceneN_included = false: must be empty string ""

Rules for a valid "OK" plan:
- status = "OK"
- total_scenes between 3 and 6
- scenes with sceneN_included = true must be N = 1, 2, ..., total_scenes
- for N > total_scenes: sceneN_included must be false
- every included scene must have:
  - sceneN_duration_sec = 8
  - non-empty focus, ref_ids, camera_shot_type, camera_motion, lighting, visual_prompt
- total_duration_sec = total_scenes * 8

Rules for a "FAIL" plan:
- status = "FAIL"
- total_scenes = 0
- total_duration_sec = 0
- status_reason is a short technical reason
- for N from 1 to 6:
  - sceneN_included = false
  - sceneN_duration_sec = 0
  - all other sceneN_* fields are empty strings ""

Do not output any other keys.

--------------------------------------------------
5. SCENE DESIGN PRINCIPLES
--------------------------------------------------

For each included scene:

1) Anchor to reference images
   - sceneN_ref_ids must only contain IDs that exist in REFERENCE_IMAGES.
   - Choose IDs that visually support the scene.

2) Product-first composition
   - The product must always be clearly readable in silhouette and detail.
   - Do not crop important structural parts unless explicitly required.

3) Feature coverage
   - Across all included scenes, cover the key visible sides and features
     in the reference images (front, back, sides, important details).
   - Do not invent sides that are never seen.

4) Consistent instance
   - Treat the product as a single, consistent master instance across all scenes:
     same variant, same color, same labeling.

5) Neutral language
   - Use factual, descriptive language in all sceneN_* fields.
   - No hype, no emotional or cinematic adjectives in sceneN_visual_prompt.
   - Marketing tone is allowed only in sceneN_audio_hint
     and must not modify product facts.

--------------------------------------------------
6. VALIDATION CHECKLIST BEFORE OUTPUT
--------------------------------------------------

Before you output the flat JSON SCENE_PLAN, verify:

- status is "OK" or "FAIL"
- If status = "OK":
  - total_scenes between 3 and 6
  - total_duration_sec = total_scenes * 8
  - for N = 1..total_scenes: sceneN_included = true
  - for N > total_scenes: sceneN_included = false
  - every included scene has duration_sec = 8
  - all used ref IDs exist in REFERENCE_IMAGES
  - no invented geometry, colors, text, logos or variants
  - all product text you mention is visible in the references
  - no people, hands or environments that are not in the references
- If status = "FAIL":
  - total_scenes = 0
  - total_duration_sec = 0
  - status_reason is non-empty
  - all sceneN_included = false
  - all other sceneN_* fields empty or zero as specified
 """
    
    async def _build_user_message(self, request: ScenarioGenerationRequest) -> str:
        """Build user message for OpenAI"""
        product_data = await self._get_product_by_id(request.product_id)
        
        return f"""Here’s the product information (PRODUCT_JSON):
- Title: {product_data.get('title', 'N/A') if product_data else 'N/A'}
- Description: {product_data.get('description', 'N/A') if product_data else 'N/A'}
- Price: {product_data.get('price', 'N/A') if product_data else 'N/A'} {product_data.get('currency', 'USD') if product_data else 'USD'}
- Specifications: {product_data.get('specifications', {}) if product_data else {}}
- Rating: {product_data.get('rating', 'N/A') if product_data else 'N/A'}
- Review Count: {product_data.get('review_count', 'N/A') if product_data else 'N/A'}

CRITICAL — FIXED PARAMETERS (DO NOT MODIFY):
- Style: "{request.style}"
- Mood: "{request.mood}"
- Video Length: {request.video_length} seconds
- Target Language: "{request.target_language}"

All scraped and runtime parameters must be treated as immutable reference input.
No summarization, rewriting, or interpretation is allowed.
The final video must visually and textually reflect the original scraped product exactly."""
    
    def _get_scenario_generation_function(self) -> Dict[str, Any]:
        """Get OpenAI function definition for scenario generation"""
        return {
            "name": "generate_single_scenario",
            "description": "Generate a single TikTok video scenario with the specified style and mood.",
            "parameters": {
                "type": "object",
                "required": ["scenario"],
                "properties": {
                    "scenario": {
                        "type": "object",
                        "required": ["title", "description", "scenes", "detectedDemographics", "thumbnailPrompt"],
                        "properties": {
                            "scenarioId": {"type": "string"},
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "thumbnailPrompt": {"type": "string", "description": "Front-facing still of final transformed product identical to scraped reference, isolated on clean or gradient background."},
                            "thumbnailTextOverlayPrompt": {"type": "string", "description": "A short caption (1-3 words) in target language, placed safely (top-right, top-left, bottom-right, etc.), using brand or neutral colors (white/black). Style: bold, elegant, modern, or minimal. Size: small or medium. Must never cover the product."},
                            "detectedDemographics": {
                                "type": "object",
                                "required": ["targetGender", "ageGroup", "productType", "demographicContext"],
                                "properties": {
                                    "targetGender": {"type": "string", "description":"male|female|child|senior|neutral"},
                                    "ageGroup": {"type": "string", "description": "kids|teens|adults|seniors|unknown"},
                                    "productType": {"type": "string"},
                                    "demographicContext": {"type": "string", "description": "<short rationale>"}
                                }
                            },
                            "scenes": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "required": ["sceneId", "description", "duration", "imagePrompt", "visualPrompt", "imageReasoning"],
                                    "properties": {
                                        "sceneId": {"type": "string"},
                                        "description": {"type": "string"},
                                        "duration": {"type": "integer"},
                                        "imagePrompt": {"type": "string", "description": "Exact 1:1 replication of scraped product — centered, sharp, 85%+ frame coverage, no humans."},
                                        "visualPrompt": {"type": "string", "description":"Cinematic alive transformation — product emerges from liquid energy and reforms into its exact real-world structure. Realistic lighting, reflections, and smooth camera motion. Logos and texts must be perfectly identical to the scraped reference."},
                                        "imageReasoning": {"type": "string"},
                                        "textOverlayPrompt": {"type": "string", "description": "1–3 word caption using brand font or neutral sans-serif, safe placement, never overlapping product pixels."}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    
    async def _transform_openai_response(self, openai_scenario: Dict[str, Any], request: ScenarioGenerationRequest) -> GeneratedScenario:
        """Transform OpenAI response to our GeneratedScenario model"""
        try:            
            # Ensure we have a dictionary
            if not isinstance(openai_scenario, dict):
                raise Exception(f"Expected openai_scenario to be a dictionary, got {type(openai_scenario)}: {openai_scenario}")
            
            scenes = []
            scenes_data = openai_scenario.get('scenes', [])
            if not isinstance(scenes_data, list):
                logger.warning(f"Expected scenes to be a list, got {type(scenes_data)}. Creating empty scenes list.")
                scenes_data = []
            
            for i, scene_data in enumerate(scenes_data):
                if not isinstance(scene_data, dict):
                    logger.warning(f"Scene {i} is not a dictionary: {type(scene_data)}. Skipping.")
                    continue
                                    
                # Create scene with fallback values for missing fields
                scene = Scene(
                    scene_id=scene_data.get('sceneId', f"scene-{i}"),
                    scene_number=i+1,
                    description=scene_data.get('description', f'Scene {i+1}'),
                    duration=scene_data.get('duration', 8),
                    image_prompt=scene_data.get('imagePrompt', f'Generate image for scene {i+1}'),
                    visual_prompt=scene_data.get('visualPrompt', f'Video content for scene {i+1}'),
                    image_reasoning=scene_data.get('imageReasoning', f'Generated for scene {i+1}'),
                    generated_image_url=None,  # Will be populated after image generation
                    text_overlay_prompt=scene_data.get('textOverlayPrompt', None)
                )
                scenes.append(scene)
                logger.info(f"Created scene: {scene.scene_number}")
            
            # If no scenes were created, create a default scene
            if not scenes:
                logger.warning("No valid scenes found, creating default scene")
                default_scene = Scene(
                    scene_id="scene-default",
                    scene_number=1,
                    description="Default scene for video",
                    duration=8,
                    image_prompt="Generate a compelling product image",
                    visual_prompt="Show the product in an engaging way",
                    image_reasoning="Default scene generation",
                    generated_image_url=None
                )
                scenes.append(default_scene)
                logger.info("Created default scene")
            
            # Validate and create demographics with fallbacks
            demographics_data = openai_scenario.get('detectedDemographics', {})
            if not isinstance(demographics_data, dict):
                logger.warning(f"Expected detectedDemographics to be a dictionary, got {type(demographics_data)}. Creating default.")
                demographics_data = {}
            
            demographics = DetectedDemographics(
                target_gender=demographics_data.get('targetGender', 'unisex'),
                age_group=demographics_data.get('ageGroup', 'all-ages'),
                product_type=demographics_data.get('productType', 'general'),
                demographic_context=demographics_data.get('demographicContext', 'gender-neutral characters/models throughout')
            )
            
            generated_scenario = GeneratedScenario(
                 title=openai_scenario.get('title', 'Generated Scenario'),
                 description=openai_scenario.get('description', ''),
                 detected_demographics=demographics,
                 scenes=scenes,
                 total_duration=request.video_length,
                 style=request.style,
                 mood=request.mood,
                 resolution=request.resolution,
                 environment=request.environment,
                 thumbnail_prompt=openai_scenario.get('thumbnailPrompt', 'Create an eye-catching thumbnail for this video content'),
                 thumbnail_url=None,  # Will be populated after thumbnail generation
                 thumbnail_text_overlay_prompt=openai_scenario.get('thumbnailTextOverlayPrompt', None)
             )
            
            logger.info(f"Successfully created GeneratedScenario with {len(scenes)} scenes")
            return generated_scenario
            
        except Exception as e:
            logger.error(f"Failed to transform OpenAI response: {e}", exc_info=True)
            raise

    async def _generate_thumbnail_image(self, request: ScenarioGenerationRequest, scenario: GeneratedScenario) -> Optional[str]:
        """Generate thumbnail image for the scenario using Google Vertex AI"""
        try:
            if not vertex_manager.is_available():
                logger.warning("Vertex AI not available, skipping thumbnail generation")
                return None
            
            # Use the AI-generated thumbnail prompt from the scenario
            thumbnail_prompt = scenario.thumbnail_prompt
            if not thumbnail_prompt:
                logger.warning("No thumbnail prompt found in scenario, using fallback")
                thumbnail_prompt = f"Create an eye-catching thumbnail for a video about {scenario.title}"
            
            # Enhance the prompt with style and mood
            enhanced_prompt = self._enhance_image_prompt(thumbnail_prompt, request.style, request.mood)
            
            # Get all product images from database
            product_data = await self._get_product_by_id(request.product_id)
            product_images = []
            if product_data and product_data.get('images'):
                images_data = product_data.get('images', {})
                if isinstance(images_data, dict):
                    product_images = list(images_data.keys())
                    logger.info(f"Found {len(product_images)} product images for thumbnail generation")
            
            if not product_images:
                logger.warning("No product images found, generating thumbnail without product reference")
            
            logger.info("Calling Vertex AI for thumbnail generation...")
            
            # Generate unique filename using UUID and save in temp directory
            thumbnail_uuid = uuid.uuid4()
            temp_dir = self._get_temp_dir()
            temp_thumbnail_path = str(temp_dir / f"temp_thumbnail_{thumbnail_uuid}.png")
            
            # Step 1: Generate base image using Vertex AI recontext and upscale
            result = generate_image_with_recontext_and_upscale(
                prompt=enhanced_prompt,
                product_images=product_images,
                target_width=1920,
                target_height=1080,
                output_path=temp_thumbnail_path
            )
            
            logger.info(f"Vertex AI thumbnail result: {result}")
            
            if result and result.get('success'):
                if result.get('image_saved') and result.get('image_path'):
                    base_image_path = result['image_path']
                    final_image_path = base_image_path
                    
                    # Step 2: Add text overlay if needed
                    if scenario.thumbnail_text_overlay_prompt and scenario.thumbnail_text_overlay_prompt.strip():
                        logger.info("Adding text overlay to thumbnail...")
                        text_overlay_result = add_text_overlay_to_image(
                            image_path=base_image_path,
                            text_overlay_prompt=scenario.thumbnail_text_overlay_prompt,
                            target_width=1920,
                            target_height=1080,
                            output_path=str(temp_dir / f"thumbnail_with_text_{thumbnail_uuid}.png")
                        )
                        
                        if text_overlay_result.get('success'):
                            final_image_path = text_overlay_result['output_path']
                            logger.info("Text overlay added successfully to thumbnail")
                        else:
                            logger.warning(f"Failed to add text overlay to thumbnail: {text_overlay_result.get('error')}")
                            # Continue with base image if text overlay fails
                    
                    # Step 3: Upload the final image to Supabase
                    try:
                        # Read the final image file
                        with open(final_image_path, 'rb') as f:
                            image_data = f.read()
                        
                        # Generate unique filename using the same UUID
                        filename = f"thumbnails/{thumbnail_uuid}.png"
                        
                        # Upload to Supabase storage
                        if supabase_manager.is_connected():
                            try:
                                supabase_manager.client.storage.from_('generated-content').upload(
                                    path=filename,
                                    file=image_data,
                                    file_options={'content-type': 'image/png'}
                                )
                                
                                # Get public URL
                                public_url = supabase_manager.client.storage.from_('generated-content').get_public_url(filename)
                                
                                # Clean up local files
                                os.unlink(base_image_path)
                                if final_image_path != base_image_path and os.path.exists(final_image_path):
                                    os.unlink(final_image_path)
                                
                                logger.info(f"Successfully generated and uploaded thumbnail: {public_url}")
                                return public_url
                                
                            except Exception as upload_error:
                                logger.error(f"Failed to upload thumbnail to Supabase: {upload_error}")
                                # Clean up local files
                                if os.path.exists(base_image_path):
                                    os.unlink(base_image_path)
                                if final_image_path != base_image_path and os.path.exists(final_image_path):
                                    os.unlink(final_image_path)
                        else:
                            logger.error("Supabase not connected, cannot upload thumbnail")
                            # Clean up local files
                            if os.path.exists(base_image_path):
                                os.unlink(base_image_path)
                            if final_image_path != base_image_path and os.path.exists(final_image_path):
                                os.unlink(final_image_path)
                    except Exception as upload_error:
                        logger.error(f"Failed to process generated thumbnail: {upload_error}")
                        # Clean up local files
                        if os.path.exists(base_image_path):
                            os.unlink(base_image_path)
                        if final_image_path != base_image_path and os.path.exists(final_image_path):
                            os.unlink(final_image_path)
                else:
                    logger.warning("Thumbnail generation succeeded but image was not saved locally")
            else:
                error_msg = result.get('error', 'Unknown error') if result else 'No result returned'
                logger.warning(f"Thumbnail generation failed: {error_msg}")
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to generate thumbnail image: {e}", exc_info=True)
            return None
    
    
    def _enhance_image_prompt(self, base_prompt: str, style: str, mood: str) -> str:
        """Enhance image prompt with style and mood specific details"""
        style_enhancements = {
            'trendy-influencer-vlog': 'modern aesthetic, clean lines, soft natural lighting, warm tones',
            'cinematic-storytelling': 'dramatic lighting, deep shadows, cinematic color grading, professional film look',
            'product-showcase': 'studio lighting, clean background, professional product photography, sharp details',
            'lifestyle-content': 'natural lighting, warm atmosphere, comfortable setting, relatable environment',
            'educational-tutorial': 'clear composition, well-lit subject, professional setup, clean background',
            'behind-the-scenes': 'candid lighting, natural atmosphere, documentary style, authentic feel',
            'fashion-beauty': 'fashion photography aesthetic, professional makeup lighting, editorial style',
            'food-cooking': 'appetizing lighting, warm food photography, professional kitchen setup',
            'fitness-wellness': 'energetic lighting, motivational atmosphere, gym or outdoor setting',
            'tech-review': 'modern tech aesthetic, clean lines, professional setup, tech-focused lighting'
        }
        
        mood_enhancements = {
            'energetic': 'dynamic composition, vibrant colors, high energy lighting, bold contrast',
            'calm': 'soft lighting, muted colors, peaceful atmosphere, gentle composition',
            'professional': 'business-like setting, formal composition, corporate aesthetic, polished appearance',
            'fun': 'playful lighting, bright colors, cheerful atmosphere, engaging composition',
            'luxury': 'premium lighting, sophisticated composition, high-end aesthetic, elegant atmosphere',
            'casual': 'relaxed lighting, comfortable setting, informal composition, everyday atmosphere',
            'dramatic': 'theatrical lighting, strong shadows, intense atmosphere, powerful composition',
            'minimalist': 'clean lines, simple composition, uncluttered background, essential elements only',
            'vintage': 'retro aesthetic, classic composition, nostalgic lighting, period-appropriate styling',
            'futuristic': 'modern tech aesthetic, sleek lines, contemporary lighting, cutting-edge composition'
        }
        
        # Camera positioning and technical enhancements
        camera_enhancements = {
            'trendy-influencer-vlog': 'medium shot, eye level, shallow depth of field, cinematic bokeh',
            'cinematic-storytelling': 'wide angle establishing shot, low angle, deep focus, motion blur',
            'product-showcase': 'close-up shot, overhead view, sharp focus, studio lighting setup',
            'lifestyle-content': 'medium shot, natural eye level, soft focus, handheld camera feel',
            'educational-tutorial': 'medium shot, eye level, clear focus, stable composition',
            'behind-the-scenes': 'handheld camera, natural angles, documentary style, authentic framing',
            'fashion-beauty': 'close-up shot, professional angles, soft focus, editorial lighting',
            'food-cooking': 'overhead view, close-up details, warm lighting, appetizing composition',
            'fitness-wellness': 'dynamic angles, medium shot, energetic framing, motivational composition',
            'tech-review': 'medium shot, clean angles, sharp focus, modern composition'
        }
        
        # Lighting enhancements based on style and mood
        lighting_enhancements = {
            'energetic': 'bright natural lighting, high contrast, dynamic shadows',
            'calm': 'soft diffused lighting, gentle shadows, warm tones',
            'professional': 'even studio lighting, minimal shadows, clean illumination',
            'fun': 'bright colorful lighting, playful shadows, vibrant atmosphere',
            'luxury': 'premium lighting, sophisticated shadows, elegant illumination',
            'casual': 'natural ambient lighting, comfortable shadows, relaxed atmosphere',
            'dramatic': 'theatrical lighting, strong shadows, dramatic contrast',
            'minimalist': 'clean lighting, minimal shadows, simple illumination',
            'vintage': 'warm nostalgic lighting, classic shadows, period-appropriate atmosphere',
            'futuristic': 'modern LED lighting, sleek shadows, contemporary illumination'
        }
        
        style_enhancement = style_enhancements.get(style, style_enhancements['trendy-influencer-vlog'])
        mood_enhancement = mood_enhancements.get(mood, mood_enhancements['energetic'])
        camera_enhancement = camera_enhancements.get(style, camera_enhancements['trendy-influencer-vlog'])
        lighting_enhancement = lighting_enhancements.get(mood, lighting_enhancements['energetic'])
        
        base_enhancement = "professional lighting, sharp focus, high quality, perfect composition, studio lighting, commercial grade"
        
        return f"{base_prompt}. {base_enhancement}, {style_enhancement}, {mood_enhancement}, {camera_enhancement}, {lighting_enhancement}."
    
    def _get_temp_dir(self) -> Path:
        """Get or create the temp directory for temporary files."""
        project_root = Path(__file__).parent.parent.parent
        temp_dir = project_root / "temp"
        temp_dir.mkdir(exist_ok=True)
        return temp_dir

# Global service instance
scenario_generation_service = ScenarioGenerationService()
