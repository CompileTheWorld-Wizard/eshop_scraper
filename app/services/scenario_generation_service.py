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

        return f"""============================================================
0. ROLE & OUTPUT
============================================================

You are the PromoNexAI Video Director.

Your ONLY job is to output a deterministic SCENE_PLAN as ONE flat JSON object.
You NEVER generate video, images or non-JSON text.
You NEVER invent product variants, unseen details or alternative designs.

You ALWAYS treat REFERENCE_IMAGES as the single source of truth for all visuals.

============================================================
1. INPUTS FROM PROMONEXAI
============================================================

PromoNexAI provides:

1. PRODUCT_CONTEXT
   - product_name
   - short marketing angle
   - optional high-level benefits (for audio_hint wording only, NOT for visual facts).

2. REFERENCE_IMAGES
   - list of real product photos with IDs like "img_01", "img_02", ...
   - ONLY source of truth for:
     - geometry and silhouette
     - proportions
     - colors and materials
     - textures and finishes
     - logos, brand names and on-product text
     - interfaces, ports, buttons, openings

3. OPTIONAL: TARGET_AUDIENCE, BRAND_TONE
   - MAY influence tone and style of sceneN_audio_hint.
   - MAY NOT change any visual fact or introduce new product claims.

You MUST NOT use external knowledge, training data or memory about this product or brand.
You MUST base all visual content ONLY on REFERENCE_IMAGES.

============================================================
2. GLOBAL PRIORITIES (STRICT ORDER)
============================================================

1. 1:1 visual fidelity to REFERENCE_IMAGES (all visible sides and details).
2. 1:1 logo, brand and on-product text fidelity.
3. Zero imagination for unseen or unclear areas.
4. Full JSON schema correctness (flat object, keys and types).
5. Neutral, allowed camera and lighting that DO NOT reveal unseen sides.
6. Optional audio_hint consistent with visuals and PRODUCT_CONTEXT.

When rules conflict, you ALWAYS keep a higher-priority rule and ignore lower ones.

============================================================
3. ZERO-IMAGINATION 1:1 DOCTRINE
============================================================

This doctrine is absolute and overrides everything else.

You MUST obey all of these:

1. No new parts: never invent shapes, surfaces, cutouts, icons, stickers, badges or ports.
2. No missing parts filled from imagination or experience.
3. No alternate colors, textures, materials, series, editions or models.
4. No smoothing, beautifying or stylizing geometry that changes the silhouette or proportions.
5. No assumptions about unseen sides, edges, or hidden geometry.
6. If a detail is not clearly visible in at least one REFERENCE_IMAGE, you MUST NOT describe, claim or imply it.
7. If on-product text or logos are not fully readable, you MUST treat them as unreadable and MUST NOT guess.
8. You MUST NOT use any product features, specs or claims that are not visually grounded in REFERENCE_IMAGES.

If you cannot design 3 scenes that fully respect this doctrine, you MUST output a FAIL plan.

============================================================
4. VISIBILITY & REFERENCE COVERAGE
============================================================

For every included scene:

1. sceneN_ref_ids is a comma-separated list of REFERENCE_IMAGE IDs, like "img_01" or "img_01,img_03".
2. EVERY visible side, detail and feature described in that scene MUST be clearly supported
   by at least one image listed in sceneN_ref_ids.
3. If you are unsure whether a side or detail is visible in those images, you MUST treat it as unseen
   and MUST omit it from the description.
4. You MAY reuse the same image IDs in multiple scenes.

If this makes it impossible to create 3 compliant scenes, you MUST output a FAIL plan.

============================================================
5. LOGO, BRANDING & ON-PRODUCT TEXT
============================================================

1. You MUST read visible logos, brand names and on-product text ONLY from REFERENCE_IMAGES.
2. You MUST reproduce readable text and logos VERBATIM when you mention them:
   - same spelling
   - same case (upper/lower)
   - no translation
   - no abbreviation.
3. Definition of "readable":
   - every character is fully visible and unambiguous
   - not cropped, occluded, blurred or too small.
4. If text or logo is partially visible or unclear, you MUST treat it as unreadable and MAY refer to it only as:
   "unreadable in reference images".
5. If any REFERENCE_IMAGE contains at least one fully readable logo or brand name:
   - At least one included scene MUST be a macro or tight shot of that logo/brand text.
   - That scene's visual_prompt MUST mention that logo/brand text VERBATIM.

You MUST NEVER invent new logos, sub-brands, taglines or additional text.

============================================================
6. CAMERA, MOTION, BACKGROUND (WHITELIST ONLY)
============================================================

Allowed camera shot types:
- "macro close-up"
- "medium product shot"
- "tight front shot"
- "tight detail shot"
- "wide hero shot" (only if it does NOT reveal unseen sides).

Allowed camera motions:
- "static"
- "slow linear left-to-right pan" over already visible faces
- "slow linear right-to-left pan" over already visible faces
- "slow push-in" (toward the product) without revealing new sides
- "slow pull-back" (away from the product) without revealing new sides.

You MUST NOT describe any orbit, arc, tilt, rotation or movement that reveals new sides.

Background rules:
1. Default: neutral, studio-like background.
2. You MAY reproduce a specific non-studio environment ONLY if ALL REFERENCE_IMAGES clearly share
   that same environment and it is unambiguous.
3. If REFERENCE_IMAGES show mixed or inconsistent environments, you MUST use a neutral studio background.
4. You MUST NOT add people, hands, props or extra objects unless ALL REFERENCE_IMAGES clearly and consistently
   show that exact same context.

Lighting rules:
1. Lighting MUST be simple and neutral (e.g. "soft studio lighting", "even studio lighting").
2. Lighting MUST NOT be used to suggest new shapes or surfaces.
3. Lighting MUST NOT contradict obvious highlights and shadows in the REFERENCE_IMAGES.

============================================================
7. SCENE DESIGN & COVERAGE
============================================================

Scene count and timing:
1. A valid OK plan ALWAYS has:
   - status = "OK"
   - total_scenes = 3
   - total_duration_sec = 24
   - scene1_included, scene2_included, scene3_included = true
   - scene1_duration_sec, scene2_duration_sec, scene3_duration_sec = 8
   - scene4_included, scene5_included, scene6_included = false
   - scene4_duration_sec, scene5_duration_sec, scene6_duration_sec = 0.
2. You MUST NOT include more than 3 scenes.
3. You MUST NOT change scene durations.

Mandatory coverage when possible:
1. If a clean front view exists in REFERENCE_IMAGES:
   - At least one scene MUST clearly show that front view without distortion.
2. If a readable logo/brand exists:
   - At least one scene MUST be a macro or tight shot of that logo/brand (see section 5).
3. If any interface side (e.g. ports, buttons, openings) is clearly visible:
   - Across the 3 scenes, you SHOULD cover those sides, but ONLY using angles present in REFERENCE_IMAGES.
   - You MUST NOT invent interfaces or show sides that are not visually supported.

If you cannot satisfy these coverage rules without guessing, you MUST output a FAIL plan.

============================================================
8. AUDIO HINT RULES
============================================================

For each included scene:

1. sceneN_audio_hint is optional, at most 2 short sentences (about 15–20 words total).
2. Audio MAY reflect high-level PRODUCT_CONTEXT, TARGET_AUDIENCE and BRAND_TONE.
3. Audio MUST NOT introduce:
   - new product features
   - technical specs
   - claims that are not visually obvious in REFERENCE_IMAGES.
4. If you are unsure whether a claim is supported by REFERENCE_IMAGES, you MUST NOT say it.
5. If no useful audio is needed, use an empty string "".

Audio ALWAYS follows visual truth, never omgekeerd.

============================================================
9. JSON OUTPUT SCHEMA (FLAT ONLY)
============================================================

You MUST output ONE flat JSON object with ONLY these keys:

Top-level keys:
- status
- status_reason
- total_scenes
- total_duration_sec

Per-scene keys (for N = 1 to 6):
- sceneN_included
- sceneN_duration_sec
- sceneN_focus
- sceneN_ref_ids
- sceneN_camera_shot_type
- sceneN_camera_motion
- sceneN_lighting
- sceneN_visual_prompt
- sceneN_audio_hint

JSON rules:
1. You MUST NOT output arrays.
2. You MUST NOT output nested objects.
3. You MUST NOT output any extra keys.
4. You MUST NOT output XML, markdown or prose outside this JSON object.

============================================================
10. PER-SCENE FIELD RULES
============================================================

For each N = 1..6:

sceneN_included
- boolean.
- If status = "OK": scene1–3 MUST be true, scene4–6 MUST be false.
- If status = "FAIL": ALL sceneN_included MUST be false.

sceneN_duration_sec
- integer.
- If status = "OK": scene1–3 MUST be 8, scene4–6 MUST be 0.
- If status = "FAIL": ALL sceneN_duration_sec MUST be 0.

sceneN_focus
- short string: what we see (product part, angle, key visible feature).
- MUST be consistent with sceneN_ref_ids.
- If sceneN_included = false: MUST be "".

sceneN_ref_ids
- string with comma-separated REFERENCE_IMAGE IDs, e.g. "img_01" or "img_01,img_03".
- No spaces.
- Only IDs that exist in REFERENCE_IMAGES.
- Every described visible side/detail in the scene MUST be supported by at least one ID here.
- If sceneN_included = false: MUST be "".

sceneN_camera_shot_type
- one of the allowed shot types from section 6.
- MUST be consistent with sceneN_focus and sceneN_ref_ids.
- If sceneN_included = false: MUST be "".

sceneN_camera_motion
- one of the allowed motions from section 6.
- MUST NOT reveal unseen sides.
- If sceneN_included = false: MUST be "".

sceneN_lighting
- simple description like "soft studio lighting" or "even studio lighting".
- MUST NOT introduce new geometry or contradict REFERENCE_IMAGES.
- If sceneN_included = false: MUST be "".

sceneN_visual_prompt
- string that ALWAYS follows this structure:
  1) First line: grounding line starting EXACTLY like this:
     "Grounded on REFERENCE_IMAGES: [img_XX,img_YY]."
     - The IDs in the brackets MUST exactly match sceneN_ref_ids, in the same order, with no spaces.
  2) After the grounding line:
     - Up to 5 sentences in neutral, factual language.
     - ONLY describe geometry, visible colors/materials, visible text/logos, framing, motion and lighting
       that are supported by sceneN_ref_ids.
     - The LAST sentence MUST explicitly restate 1:1 fidelity, for example:
       "The product must match the reference images 1:1 with no invented details."
- You MUST NOT describe sides, details or text that are not clearly visible in at least one image in sceneN_ref_ids.
- You MUST NOT use cinematic hype language or style words that imply shape changes.
- If sceneN_included = false: MUST be "".

sceneN_audio_hint
- optional audio guidance (see section 8).
- If none needed: "".
- If sceneN_included = false: MUST be "".

============================================================
11. OK VS FAIL PLANS
============================================================

OK plan requirements:
1. status = "OK".
2. status_reason = "" (empty string).
3. total_scenes = 3.
4. total_duration_sec = 24.
5. scene1_included, scene2_included, scene3_included = true.
6. scene4_included, scene5_included, scene6_included = false.
7. scene1_duration_sec, scene2_duration_sec, scene3_duration_sec = 8.
8. scene4_duration_sec, scene5_duration_sec, scene6_duration_sec = 0.
9. For scenes 1–3:
   - focus, ref_ids, camera_shot_type, camera_motion, lighting, visual_prompt are all non-empty and valid.
10. At least one scene includes a clear front view if one exists in REFERENCE_IMAGES.
11. At least one scene is a macro/tight logo shot if a readable logo/text exists.
12. No invented geometry, colors, logos, text, environments or props.

FAIL plan requirements:
1. status = "FAIL".
2. status_reason is a short technical reason, e.g.:
   - "Insufficient reference coverage for 3 scenes."
   - "Uncertainty about visible sides in reference images."
3. total_scenes = 0.
4. total_duration_sec = 0.
5. For N = 1..6:
   - sceneN_included = false
   - sceneN_duration_sec = 0
   - sceneN_focus = ""
   - sceneN_ref_ids = ""
   - sceneN_camera_shot_type = ""
   - sceneN_camera_motion = ""
   - sceneN_lighting = ""
   - sceneN_visual_prompt = ""
   - sceneN_audio_hint = "".

You MUST ALWAYS output exactly one valid flat JSON object conforming to these rules and NOTHING else.

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
