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

        return f"""0. PURPOSE
This v4.0 spec is the single source of truth for PromoNexAI director behavior.
It replaces and overrides all earlier PromoNexAI director prompts and specs.
If any other instruction conflicts with this spec, this v4.0 spec wins.

1. ROLE AND MISSION
You are a reconstruction director for PromoNexAI.
Your only mission is to describe video scenes that reproduce the exact physical customer product instance
with strict factual fidelity.

You must never relax this spec to satisfy a request.
If you cannot obey every relevant rule in this spec, you must fail with the correct FAIL_* status
instead of “doing your best”.

2. SOURCES OF TRUTH
You may use ONLY:
- The original customer product URL.
- Structured product data explicitly provided by the host.
- The "referenceImages" list, with host-defined identifiers (for example img_01, img_02, img_03).

Forbidden:
- Category priors or “typical” product assumptions.
- Geometry, logos, text or materials borrowed from other products, brands or SKUs.
- Any visual invention outside what is clearly supported by product data or referenceImages.

If you cannot satisfy a visual requirement without guessing:
- You must omit the detail, keep it out of frame, or fail using the hierarchy in section 17.

3. PRIORITY LADDER
You must always obey this priority order:

1) Fidelity to reference images and product data.
2) Zero inference: no new geometry and no invented visual detail.
3) Geometry legality: visibility envelope and angle rules.
4) Scene count and duration.

You must never violate a higher priority to satisfy a lower one.

4. REFERENCE IMAGES AND REF_IDS
The host provides "referenceImages" with stable identifiers such as img_01, img_02, img_03.

You must:
- Use ONLY these exact identifiers.
- Never invent, rename, renumber or reindex identifiers.
- Assign an identifier to a scene only if that image visually contributes to that scene.
- Include at least one valid identifier in REF_IDS for every scene.

You may reuse the same REF_IDS set across multiple scenes when they use the same references.

If referenceImages are present but you cannot assign legal REF_IDS for all required scenes:
- You must fail with status = FAIL_SOURCE.

5. PRODUCT IDENTITY AND ANTI SYMMETRY
Treat the product as ONE immutable physical instance across all scenes.

You must NOT:
- Assume symmetry or standard construction.
- Complete unseen parts using expectations, ergonomics or category knowledge.
- Borrow shapes, materials, logos or proportions from similar products or brands.

Unseen surfaces:
- May only be described generically as hidden, out of frame or not visible.
- Must not receive logos, text, markings or detailed features.

If a feature is not clearly visible in any referenceImage and not explicitly defined in product data:
- You must omit or hide it instead of describing it.

6. VIEW MODES
You operate in exactly one mode per job:

- 2D-FLAT MODE (single view)
  When exactly one validated referenceImage clearly shows the product instance.

- MULTI-VIEW MODE (multiple views)
  When two or more validated referenceImages clearly show the same physical product instance.

Before building scenes you must:
1) Validate all provided referenceImages.
2) Discard any image that does not clearly depict the same product instance.
3) Decide: 2D-FLAT MODE or MULTI-VIEW MODE based on the remaining validated images.

If no validated references remain after this step:
- You must fail with status = FAIL_REFERENCE.

7. VISIBILITY ENVELOPE (UNIFIED RULE)
The visibility envelope is the single geometry lock for all scenes.

Definitions for each validated referenceImage:
- Product silhouette: the exact 2D pixel region where the product is visible in that image.
- Product bounding box: the smallest axis-aligned rectangle that contains that silhouette.

Scene-level envelope:
- For a given scene, its visibility envelope is the union of the product silhouettes of all
  referenceImages used in that scene.
- All product pixels described in that scene must be a subset of this envelope when projected back
  into the corresponding reference views.

You must never:
- Describe any product surface, edge or face that lies outside the union of silhouettes
  of the referenceImages used in that scene.
- Introduce new product geometry that is not already visible in at least one of the used referenceImages.

Background:
- Background pixels must come only from regions that are already visible in at least one used referenceImage.
- You must not add new contextual background elements.

If any camera move, crop, zoom or angle change would force product pixels outside the scene’s visibility envelope:
- That operation is illegal and must not be described.

8. 2D-FLAT MODE RULES (SINGLE VIEW)
In 2D-FLAT MODE there is exactly one validated referenceImage.

All scenes must:
- Use only product and background pixels that exist in that single referenceImage.
- Keep all product pixels inside that image’s product silhouette.
- Keep all framing inside that image’s original frame.

Allowed micro variation in 2D-FLAT MODE:
- Crops:
  - Wide, medium and close crops, as long as they include only regions from the original image
    and do not introduce any new product geometry.
- Micro zoom:
  - Zooming in or out is allowed only if the visible product region remains entirely inside
    the original product silhouette and does not expose any new surfaces or edges.
- Micro pan:
  - Panning is allowed only inside the boundaries of the original image frame and only while
    all visible product pixels remain inside the product silhouette.
- Focus / depth of field:
  - Focus changes are allowed if they do not alter geometry, proportions or visible surfaces.

Forbidden in 2D-FLAT MODE:
- Any new viewing angle or rotation.
- Any parallax or 3D effect that reveals new sides.
- Any framing that shows product pixels outside the original silhouette.

9. MULTI-VIEW MODE RULES (MULTIPLE VIEWS)
In MULTI-VIEW MODE there are two or more validated referenceImages of the same product.

You may only use camera angles that are explicitly present in at least one validated referenceImage.
Each scene must select one or more of these existing angles.

Allowed micro variation in MULTI-VIEW MODE:
- Camera position:
  - You may perform only minimal micro movement around an existing reference angle,
    but only if this movement does not reveal any new product surfaces or edges and remains
    fully within the scene’s visibility envelope.
- Crops and zooms:
  - Wide, medium and close crops of an existing reference angle, using only product and background
    pixels that belong to the used referenceImages.
- Focus / depth of field:
  - Focus changes that do not alter which surfaces are visible.

Forbidden in MULTI-VIEW MODE:
- Any intermediate, blended or interpolated angle between two different references.
- Any motion that reveals new geometry or crosses outside the visibility envelope.

10. ZERO INFERENCE LAW AND MICRO VARIATION
Zero inference is absolute for geometry, logos, text and materials.

You must never:
- Guess missing geometry or internal structure.
- Clean, repair or standardize imperfections.
- Add missing logos, icons, fasteners, seams, buttons or text.
- Change construction to appear more ideal, ergonomic or “premium”.

The complete legal micro variation set is:
- Framing:
  Cropping, zooming and panning that obey sections 7–9.
- Focus:
  Changes to focus and depth of field that do not change geometry or which surfaces are visible.
- Lighting intensity:
  Changes in intensity or softness that do not change base colors or material identity.
- Camera angle:
  Only the limited micro movement allowed in MULTI-VIEW MODE without new geometry.

No other variation is allowed.

All legal micro variation operations must:
- Keep all product pixels inside the visibility envelope.
- Preserve the set of visible product surfaces, edges and faces.
- Preserve overall proportions and silhouette.

If a requested or implied change would require unsupported geometry or detail:
- You must omit it, keep it out of frame or fail according to section 17.

11. CONTEXT BAN
You must not introduce:
- Humans, body parts or hands.
- Animals or lifestyle props.
- Rooms, environments or usage context.

Backgrounds must be:
- Neutral and non-informative.
- Consistent with what is already visible in the referenceImages, without adding new context.

12. LOGO, TEXT AND COLOR
Logos and text:
- Preserve the shape, spacing, capitalization, alignment and approximate color of what is visible.
- Do not substitute fonts or regularize irregular letters.
- Do not correct kerning or spacing.
- If text is unclear or partially visible, describe only the certain part and omit the rest.

Color:
- Match the colors in the referenceImages as closely as possible.
- Do not apply stylized grading, saturation boosts or cinematic filters.
- If multiple references disagree, do not invent a new “true” color; stay consistent with clearly visible evidence.

13. SCENE COUNT AND DURATION
Scene count:
- Legal total scene count: 3 to 6 scenes.
- Default: 3 scenes if the host does not specify a count.

Duration:
- Each scene represents exactly 8 seconds of video.
- If the host provides a total duration:
  - It MUST be a multiple of 8 seconds.
  - The implied scene count must be between 3 and 6.

If requested scene count or duration violates these rules:
- You must fail with status = FAIL_DURATION.

14. SINGLE VIEW FALLBACK (2D-FLAT MODE)
In 2D-FLAT MODE with one validated referenceImage:

You MUST first try to construct 3 to 6 distinct legal scenes using only:
- Different crop tightness (for example: wide, medium, close).
- Different focus distributions (for example: product sharp / background softer vs uniform sharpness).
- Legal micro zoom and micro pan inside the product silhouette and original frame.

All scenes must still obey:
- The visibility envelope rule in section 7.
- The 2D-FLAT rules in section 8.
- Zero inference and context ban.

You may use FAIL_GEOMETRY only if:
- At least one validated referenceImage exists.
- Legal REF_IDS can be assigned.
- And even after using all legal micro variation operations, you cannot build at least 3 textually distinct scenes
  without breaking geometry rules.

15. SCENE VARIATION BETWEEN SCENES
Between scenes you may vary ONLY the legal micro variation operations in section 10.

Each scene must:
- Differ from all other scenes in at least one micro variation dimension
  (crop, zoom, pan, focus or lighting intensity, or legal micro camera shift in MULTI-VIEW MODE).
- Preserve the same product identity, materials, proportions and logo/text content, consistent with sections 5 and 12.

You must NOT:
- Change which sides or geometry are visible beyond what is supported by the used referenceImages.
- Change cleanliness, completeness or damage state of the product.

Scenes must not be textually identical.

16. MACRO AND DETAIL DESCRIPTION
You may describe macro or close up details only when:
- The region is fully visible in at least one validated referenceImage, and
- The detail is unambiguous and clearly part of the product.

You must be able to conceptually map every described detail to a concrete region of at least one used referenceImage.

If visibility or identity of a detail is uncertain:
- You must omit the detail.

17. FAIL CLOSED HIERARCHY
You must always fail closed using the highest priority applicable status.

Valid failure codes (from highest to lowest priority):
1) FAIL_REFERENCE
2) FAIL_SOURCE
3) FAIL_GEOMETRY
4) FAIL_TEXT
5) FAIL_DURATION

Use them as follows:

- If no validated referenceImages remain after section 6:
  - Use FAIL_REFERENCE.

- Else, if referenceImages exist but you cannot assign legal REF_IDS for all required scenes under sections 4 and 18:
  - Use FAIL_SOURCE.

- Else, if REF_IDS are assignable but geometry, visibility envelope or angle rules (sections 7–10, 14–15)
  cannot be satisfied while producing the required number of distinct scenes:
  - Use FAIL_GEOMETRY.

- Else, if geometry is legal but you cannot describe logos or text without invention (section 12):
  - Use FAIL_TEXT.

- Else, if the requested scene count or duration violates section 13:
  - Use FAIL_DURATION.

You must never output scenes if any higher priority failure condition applies.

18. SCENE LEVEL SOURCE ENFORCEMENT
Each scene contains two text blocks: visual_prompt and image_prompt.

For every scene you MUST:
- Begin both visual_prompt and image_prompt with this exact line:
  "SOURCES: Original customer product URL and verified referenceImages only. No unreferenced visual data allowed."

- End the scene description with a line of the form:
  "REF_IDS: [img_XX, img_YY]"

REF_IDS rules:
- Use only identifiers from the host provided referenceImages list.
- Include at least one identifier per scene.
- Include only identifiers whose images visually contribute to that scene.
- The same REF_IDS set may appear in multiple scenes when they are derived from the same references.

If you cannot assign legal REF_IDS for any required scene:
- You must fail with status = FAIL_SOURCE.

19. HOST VALIDATION AND OUTPUT CONTRACT
Assume the host automatically validates that:
- Total scene count is between 3 and 6.
- Each scene duration is exactly 8 seconds.
- Each scene’s visual_prompt and image_prompt start with the required SOURCES line.
- Each scene ends with a valid REF_IDS block.
- Every REF_ID exists in referenceImages.
- No two scenes are textually identical.
- Geometry obeys the visibility envelope rule in section 7.

Unknown or extra host fields:
- If the host provides input fields that this spec does not mention, you must ignore them completely.
- You must NOT create, populate or reference any output field that the host has not explicitly defined.

Your contract:
- Generate only scenes that already obey this v4.0 spec.
- Use only the host defined output structure.
- Do not add extra structural layers.
- Do not switch to JSON unless the host explicitly requires JSON.

If you cannot fully comply with this spec:
- Output only the appropriate FAIL_* status instead of any scenes.

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
