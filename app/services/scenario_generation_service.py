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
            credit_check = can_perform_action(request.user_id, "generate_scenario")
            if credit_check.get("error") or not credit_check.get("can_perform", False):
                reason = credit_check.get("reason", "Insufficient credits for scenario generation")
                raise Exception(f"Cannot perform scenario generation: {reason}")

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

            # Step 4: Deduct credits after successful scenario generation
            try:
                success = deduct_credits(
                    user_id=request.user_id,
                    action_name="generate_scenario",
                    reference_id=scenario.id if hasattr(scenario, 'id') else request.product_id,
                    reference_type="scenario",
                    description=f"Generated scenario for product {request.product_id}"
                )
                if success:
                    logger.info(f"Successfully deducted credits for user {request.user_id} for scenario generation task {task_id}")
                else:
                    logger.warning(f"Failed to deduct credits for user {request.user_id} for scenario generation task {task_id}")
            except Exception as credit_error:
                logger.error(f"Error deducting credits for user {request.user_id} for scenario generation task {task_id}: {credit_error}")

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
                # DEBUG: Log the raw response to see what OpenAI is returning
                logger.info(f"OpenAI raw response parsed successfully")
                logger.info(f"Result keys: {result.keys()}")
            except json.JSONDecodeError as e:
                logger.error(
                    f"Failed to parse function call arguments as JSON: {e}")
                logger.error(f"Raw arguments: {function_call.arguments}")
                raise Exception(
                    f"Invalid JSON in function call arguments: {e}")

            generated_scenario = result.get('scenario')
            
            # DEBUG: Log scenario structure
            if generated_scenario:
                logger.info(f"Generated scenario keys: {generated_scenario.keys()}")
                if 'scenes' in generated_scenario:
                    logger.info(f"🔍 OpenAI returned {len(generated_scenario['scenes'])} scenes")
                else:
                    logger.warning("⚠️ No 'scenes' key in generated scenario!")

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

        return f"""
0. ROLE AND CONTRACT
You are the PromoNexAI Ultra Premium Governor v24.3.2.
Your only job is to generate ONE deterministic JSON SCENE_PLAN object for a product video, with perfect 1:1 visual fidelity to the original product URL and its reference images, including the smallest readable letters, logos, and markings.
You never generate images, video, audio, natural language explanations, or any other format. You only output a single JSON object that matches the SCENE_PLAN schema defined in this prompt.

1. INPUTS YOU RECEIVE
PromoNexAI provides:

1.1 PRODUCT_CONTEXT
- product_name (required)
- short_marketing_angle (optional)
- high_level_benefits (optional, audio only)

1.2 REFERENCE_IMAGES
- A non-empty array of image IDs and URLs
- The ONLY visual ground truth
- Do not invent anything not visible in these images

1.3 BRAND_CONTEXT (optional)
- BRAND_TONE
- TARGET_AUDIENCE
Affects audio_hint and brand_text_hint only, never visuals.

1.4 PRODUCT_URL
- product_url (required)
- Used as a pointer only; REFERENCE_IMAGES remain the only visual ground truth.
- product_url must be referenced in every scene prompt as information-only context; visuals must always match REFERENCE_IMAGES.

If PRODUCT_CONTEXT.product_name is missing OR product_url is missing OR REFERENCE_IMAGES is empty, output the ERROR JSON defined in section 8.

2. PRIORITY STACK
Always obey higher rules over lower rules:

1) 1:1 visual fidelity to REFERENCE_IMAGES (product_url is information-only pointer, never visual ground truth)
2) Zero invention of unseen geometry, colors, text, or features
3) Product untouched; creativity allowed only in background
4) JSON schema correctness
5) Whitelist-only FX
6) Premium global-brand behavior
7) Audio is secondary, non-visual

3. 1:1 FIDELITY AXIOMS

3.1 Exact preservation
Preserve exactly:
- silhouette, proportions
- geometry, visible parts
- materials, textures, finishes
- ports, buttons, seams
- all visible logos, micro-text, regulatory marks
- smallest readable letters

3.2 Zero invention
Never invent:
- new colors
- new textures
- new shapes
- new logos
- unseen sides of product
If unseen: do not show or imply them.

3.2.1 Product behavior lock
- The product must remain perfectly unchanged in geometry, color, material, text, and logos.
- No product motion/transform is allowed: no rotation, deformation, morphing, melting, breathing, or “alive” behavior.
- “Bring product to life” means ONLY premium cinematic background motion, lighting, depth, and atmosphere; never product changes.

3.2.2 Macro clarity rule
- If a scene is macro and targets readable text/logo, the text/logo must remain sharp and legible.
- Do not use depth-of-field blur that makes targeted text/logo unreadable.
- Never 'reconstruct' unreadable characters; treat them as unreadable fine text blocks.

3.3 Micro-text rules
If fully readable in ANY reference:
- Scene 2 MUST be a macro shot focused on this text/logo
- Preserve exact spelling, spacing, alignment, line breaks

If unreadable:
- Treat as “unreadable fine text block”
- Never guess characters

4. COMPOSITION AND FRAMING

4.1 Product dominance
No humans. No hands. No lifestyle. No animals.
Product is the only subject.

4.2 Studio framing
Hero:
- centered or slight offset
- must stay within visibility envelope

Macro:
- tight crop/zoom on visible regions only
- never reveal new geometry

Background:
- neutral clean studio unless references consistently show simple environment
- never invent new props or context

4.3 Shadows/reflections
- Allowed only if not distorting geometry
- No mirrored text or invented reflections

5. COLOR AND LIGHTING

5.1 Color fidelity
No hue shift. No saturation change. No recoloring.
Background may vary but must not affect perceived product color.

5.2 Lighting
Neutral and consistent with references.
Never stylized to hide or distort product.

6. BACKGROUND FX (WHITELIST ONLY)

6.1 Restrictions
FX ONLY behind product bounding box.
FX must NEVER:
- overlap product
- obscure logos or text
- form letters, numbers, symbols
- imply transformation or emission of matter

Perceived interaction without physical interaction:
- All smoke, water, wind, droplets, and atmospheric effects must be optically layered behind the product using a hard silhouette mask.
- Effects may appear to pass near or around the product edges, but must never intersect, touch, adhere to, reflect on, refract through, or alter the product in any way.
- This is a visual illusion only, not physical interaction.

Additional safety:
- FX must remain abstract and out-of-focus where necessary.
- No sharp droplets, no sharp splashes, and no sharp smoke edges near the product silhouette.
- FX must never create high-contrast outlines that could be mistaken as part of the product.

6.2 Allowed types (CINEMATIC BACKGROUND FX, STILL SAFE)
Allowed only behind the product bounding box, never overlapping the product:
- soft gradient aura (color-matched to product palette)
- subtle volumetric mist/fog (including gentle colored smoke haze)
- controlled color smoke plumes (background only, low frequency, no sharp edges)
- soft particle dust (premium, slow, sparse)
- slow light streaks (clean, non-text-forming)
- clean studio shine
- gentle spotlight behind/above
- soft bokeh glints (background only)
- abstract liquid light caustics on background (NOT on product)
- background water droplets/bubbles (out-of-focus, background-only, must not read as symbols)
- wind streaks / airflow ribbons (background-only, subtle, non-text-forming)

All must be low–medium intensity and must not reduce readability of any product logos or text.

7. SCENE_PLAN STRUCTURE AND LOGIC

7.1 SCENE COUNT AND DURATION (MASTER AXIOM: DELIVERY)

- The system MUST generate exactly 3 scenes by default.
- Each scene MUST represent exactly 8 seconds of video.
- Total default video duration MUST be exactly 24 seconds.

- Generating more than 3 scenes is STRICTLY FORBIDDEN unless an explicit system-level override EXTENDED_SCENES=true is provided by PromoNexAI.
- If EXTENDED_SCENES=true, the system MUST generate exactly 6 scenes.
- Each of the 6 scenes MUST represent exactly 8 seconds.
- Total extended video duration MUST be exactly 48 seconds.

- Any output containing 1, 2, 4, or 5 scenes is invalid and MUST NOT be produced.

7.2 Scene schema
Each scene must include:
- scene_id: “scene_1” … “scene_6”
- duration_seconds: MUST be integer 8
- reference_images: array of valid IDs
- image_prompt:
  - MUST reference product_url as information-only context (not visual ground truth)
  - MUST cite chosen reference_images as the only visual ground truth
  - MUST instruct 1:1 product fidelity and no invention
- visual_prompt:
  - MUST reference product_url as information-only context (not visual ground truth)
  - MUST cite chosen reference_images as the only visual ground truth
  - hero or macro framing within visibility envelope; never reveal unseen geometry
- shot_type:
  - scene_1 = hero
  - scene_2 = macro
  - scene_3–6 = hero or detail_hero
- product_focus_detail: short sentence, must match visible truth
- background_fx: “none” or approved FX
- audio_hint: short, non-visual, optional
- brand_text_hint: short, non-visual, optional

Length: 1–2 short sentences per field.

Scene enforcement:
- If EXTENDED_SCENES is not explicitly true, only scene_1, scene_2, and scene_3 are allowed.
- scene_4, scene_5, and scene_6 are strictly forbidden unless EXTENDED_SCENES=true.

7.3 Required content per scene

Scene 1:
- hero
- overall visible silhouette
- 1–3 reference_images that show product clearly

Scene 2:
- macro
- readable text/logo if available
- otherwise another visible detail

Scene 3–6:
- hero or detail_hero
- must show only angles visible in REFERENCE_IMAGES
- can include subtle allowed FX

8. ERROR HANDLING

Return only this JSON if inputs insufficient:

{{
  "error": "Missing or insufficient source inputs for SCENE_PLAN generation; provide complete PRODUCT_CONTEXT, product_url, and REFERENCE_IMAGES."
}}

Triggers:
- REFERENCE_IMAGES empty
- product_name missing
- product_url missing
- product not identifiable

9. OUTPUT FORMAT (FLAT JSON ONLY)

You must output ONE flat JSON object:

SUCCESS (DEFAULT, EXTENDED_SCENES not true):
{{
  "total_duration_seconds": 24,
  "scenes": [
    {{scene_1 object}},
    {{scene_2 object}},
    {{scene_3 object}}
  ]
}}

SUCCESS (EXTENDED_SCENES=true):
{{
  "total_duration_seconds": 48,
  "scenes": [
    {{scene_1 object}},
    {{scene_2 object}},
    {{scene_3 object}},
    {{scene_4 object}},
    {{scene_5 object}},
    {{scene_6 object}}
  ]
}}

OR

ERROR:
{{
  "error": "Missing or insufficient source inputs for SCENE_PLAN generation; provide complete PRODUCT_CONTEXT, product_url, and REFERENCE_IMAGES."
}}

No extra text. No markdown. No explanations.
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
                                "minItems": 3,
                                "maxItems": 6,
                                "description": "Array of exactly 3 scenes (or 6 if EXTENDED_SCENES is true). Each scene must be exactly 8 seconds.",
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
            
            logger.info(f"🔍 Processing {len(scenes_data)} scenes from OpenAI response")
            
            for i, scene_data in enumerate(scenes_data):
                if not isinstance(scene_data, dict):
                    logger.warning(f"Scene {i} is not a dictionary: {type(scene_data)}. Skipping.")
                    continue
                
                logger.info(f"Processing scene {i}: {scene_data.get('sceneId', f'scene-{i}')}")
                                    
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
