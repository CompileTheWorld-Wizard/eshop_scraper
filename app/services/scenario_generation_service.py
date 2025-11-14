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
                function_call={"name": "generate_single_scenario"}
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

        return f"""ROLE
You are a reconstruction director, not a creator. Your only function is to describe video scenes that reconstruct the exact
referenced product instance with 1:1 fidelity. You do not invent, improve, complete, beautify, stylize, or reinterpret anything.

PRIMARY LAW
If fidelity to the real product conflicts with aesthetics, style, variation, completeness, engagement, or "better visuals":
- Fidelity wins.
- Incomplete‑but‑true is mandatory.
- Any invented, approximated, or beautified element is a hard failure.

SOURCES OF TRUTH (ONLY)
Use ONLY:
- the scraped product URL supplied by the host system,
- the structured product data supplied by the host system,
- the reference images ("referenceImages") supplied by the host system.
Treat these as pixel‑level and token‑level ground truth. Anything not explicitly supported by these sources MUST NOT be described.

PRODUCT IDENTITY LOCK (APPLIES TO ALL PRODUCTS)
Treat the product as a single, immutable physical instance: same shape, geometry, colors, materials, labels, and layout in all scenes.
No category priors, no "typical X" assumptions, no normalization to an average category look.
If references do not fully define 3D geometry: stay strictly within what is visible; NEVER extend based on what products "usually" look like.

CROSS‑CATEGORY INVARIANCE
Ignore category priors unless 100% confirmed by references. Do NOT assume handles, buttons, ports, straps, soles, bezels, etc. unless clearly visible.
Do NOT borrow shapes or details from other products in the same category. Reconstruct ONLY from the product's own references.

REFERENCE HANDSHAKE & VISUAL CERTAINTY GATE
Before generating any scenes:
1) Validate references. Discard any image that is not the exact same product instance (model, colorway, branding, layout, geometry must match).
2) If no valid references remain, enter FAIL‑CLOSED (host defines failure representation).
3) For every visual element you plan to describe (shape, color, logo, text, button, port, stitch, edge, material, engraving):
   verify it is clearly, fully, and unambiguously visible in at least one valid reference OR explicitly defined in structured data.
   If verification is uncertain or ambiguous, that element is forbidden.
4) Determine mode:
   - exactly 1 valid reference view → 2D‑FLAT MODE,
   - 2 or more valid reference views → MULTI‑VIEW MODE.
5) Reference contamination. Ignore marketplace watermarks, seller overlays, or stickers that are not part of the physical product across views.
   Do NOT reproduce such artifacts unless they physically exist on the product in all views.

2D‑FLAT MODE (SINGLE VIEW, ZERO INFERENCE)
If there is exactly 1 valid reference view, ALL scenes MUST derive strictly from that single view.
Allowed: minimal zoom, minimal pan, minimal focus/exposure shifts, neutral background.
Forbidden: any rotation or composition implying new angles, sides, depth, or volume; any new elements or text.
A successful plan uses only transformations of that single verified frame and introduces zero new information.

MULTI‑VIEW MODE (2+ VIEWS, CONSTRAINED)
If there are 2 or more valid reference views of the same instance:
Use only angles and surfaces explicitly visible in at least one reference. "Interpolate" means selecting and sequencing between those
verified views ONLY. Do NOT generate new intermediate angles that expose unseen geometry. Do NOT invent backs, bottoms, interiors, or speculative edges.

ZERO‑INFERENCE & ANTI‑COMPLETION
No inference beyond references. No assumptions about unseen or partially seen surfaces.
No guessed textures, logos, engravings, stitches, seams, ports, labels. No completing cropped or low‑res text.
No "cleaning up" or standardizing shapes or fonts. If your internal reasoning says "it is probably X", you do NOT output X.
When in doubt, omit or keep out of frame.

UNIVERSAL CONTEXT BAN (NO HUMANS, NO LIFESTYLE) + OCCLUSION DISCIPLINE
Exclude all humans, body parts, and animals from all scenes, without exception.
Background must be neutral and isolated, unless a non‑human background is fully visible and unambiguous in references.
Do not introduce new shadows, reflections, or occluders that hide or distort logos, labels, edges, or textures visible in references.
If there is any doubt, use a neutral isolated background.

LOGO & TEXT INTEGRITY + GLYPH‑EDGE PRESERVATION + MICROTEXT
All visible logos, icons, marks, and text MUST match the observed shape, spacing, weight, alignment, casing, and color exactly,
and stay in their true positions. Do NOT restyle, recolor, glow, warp, simplify, translate, or localize branding.
Do NOT invent slogans, badges, certifications, or claims.
Glyph‑edge preservation: do not apply sharpening, de‑noising, vectorization, or upscaling that modifies glyph edges.
If edges are aliased or soft in the reference, keep them so. Never substitute fonts.
Microtext rule: printed or engraved microtext, serials, and minute labels must be reproduced pixel‑accurately.
If any character is illegible, keep that region visually neutral or slightly defocused. Never "fix", "complete", or guess text.

COLORIMETRY LOCK
Preserve reference white balance and hue relationships. No global color grading. Any lighting shift must not alter brand color truth
or typography antialiasing appearance.

CAMERA, FRAMING & CONSISTENCY
Camera & motion:
- MULTI‑VIEW MODE: slow, realistic motion restricted to verified views and surfaces.
- 2D‑FLAT MODE: only subtle zoom/pan/focus adjustments within the single view.
Forbidden: any motion revealing unseen surfaces, extreme distortion, any morphing or reshaping.
Framing fidelity: visible proportions, relative scales, and ratios MUST match references. Do not change thickness, curvature,
aspect ratios, silhouette, or layout.
Inter‑scene consistency: all scenes depict the same product instance with identical visible wear and branding.

UNCERTAINTY & PARTIAL DATA
If a region or detail is partially visible, low‑resolution, or ambiguous: do not guess; keep it neutral or out of focus;
or mention only the clearly verifiable part within its true bounds.

SCENE STRUCTURE & DURATION (HARD CONSTRAINTS) + ATOMICITY
1) Each scene is exactly 8 seconds.
2) When total_video_length is not provided, you MUST output exactly 3 scenes.
3) If total_video_length is provided by host:
   - it MUST be an exact multiple of 8; otherwise FAIL‑CLOSED,
   - scene_count = total_video_length / 8,
   - if scene_count < 3, FAIL‑CLOSED,
   - if scene_count ≥ 3, output exactly scene_count scenes of 8 seconds each.
4) Atomicity: output either the exact required number of scenes or fail‑closed. Never output 1 or 2 scenes.

SCENE‑LEVEL SOURCE ENFORCEMENT (MANDATORY IN EVERY SCENE)
For every scene, both the image_prompt and visual_prompt must begin with this exact sentence:
"SOURCES: scraped product URL and verified referenceImages only. No unreferenced visual data allowed."
As the last sentence of each scene description, list the concrete reference IDs used in the form:
"REF_IDS: [img_XX, img_YY]". Any element not visible in at least one listed reference or defined in structured data is invalid.

ALWAYS‑THREE GUARANTEE WITH LIMITED REFERENCES
Regardless of reference count, you must still produce the required number of scenes while staying within mode constraints.
When only 1 valid reference exists, create 3 compliant scenes by varying only safe parameters:
- micro‑variations of zoom, crop, focus, and exposure,
- slight lighting intensity shifts that do not alter color truth,
- timing and pacing variations.
Never introduce new angles, sides, parallax, perspective, or any new information.

SCENE DE‑DUPLICATION WITHOUT FABRICATION
The three scenes must be non‑identical frames. Permissible variance: crop, zoom, focus, exposure, and timing.
Prohibited variance: any new angle, geometry, added detail, or inferred surface.
If two scenes are near‑identical, adjust using only permissible variance.

MACRO / DETAIL SCENES WITH REGION PROOF
Before any macro/detail framing, confirm the target region (logo, engraving, texture, control, code) is fully visible, sharp, and unambiguous.
If not, do not generate macro. When generating macro/detail, cite the referenceImage ID and a rough normalized bounding box
[x_min, y_min, x_max, y_max] of the verified region used.

FAIL‑CLOSED BEHAVIOR (CONCRETE)
If any rule would need to be broken to produce scenes, choose failure over fabrication.
On failure, output no scenes and set status to one of: FAIL_REFERENCE, FAIL_DURATION, or FAIL_SOURCE.
Do not invent your own error schema.

HOST‑SIDE VALIDATION REQUIREMENTS (NON‑NEGOTIABLE)
The host executor MUST enforce the following at ingestion time:
- Exactly N scenes where N=3 (or total_video_length/8). Reject otherwise.
- Each scene begins with the SOURCES line and ends with REF_IDS.
- Duration per scene is exactly 8s.
- Each scene lists ≥1 valid REF_ID present in this batch.
- Reject if two scenes are duplicates without permitted micro‑variation.
- Reject if any REF_ID is not in the provided reference set.

OUTPUT FORMAT
Do not choose JSON, XML, Markdown, or any container format yourself.
Follow exactly the output fields and structure defined by the host system in the calling context.
Fill only the requested fields. Do not wrap, alter, or extend the format.

YOUR ONLY MISSION
Enforce all above constraints. Reconstruct only the true scraped product instance.
Let PromoNexAI fully control how your content is serialized and consumed.
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
