-- Add text overlay support to video scenes and scenarios
-- This migration adds fields to support the new image generation workflow with text overlays

-- Add text overlay field to video_scenes table
ALTER TABLE public.video_scenes 
ADD COLUMN IF NOT EXISTS text_overlay_prompt TEXT;

-- Add text overlay field to video_scenarios table for thumbnail
ALTER TABLE public.video_scenarios 
ADD COLUMN IF NOT EXISTS thumbnail_text_overlay_prompt TEXT;

-- Add comments to document the new fields
COMMENT ON COLUMN public.video_scenes.text_overlay_prompt IS 'Text overlay prompt containing text, position, color and style information. NULL or empty if no text overlay needed.';
COMMENT ON COLUMN public.video_scenarios.thumbnail_text_overlay_prompt IS 'Thumbnail text overlay prompt containing text, position, color and style information. NULL or empty if no text overlay needed.';

-- Create indexes for the new fields
CREATE INDEX IF NOT EXISTS idx_video_scenes_text_overlay_prompt ON public.video_scenes(text_overlay_prompt) WHERE text_overlay_prompt IS NOT NULL AND text_overlay_prompt != '';
CREATE INDEX IF NOT EXISTS idx_video_scenarios_thumbnail_text_overlay_prompt ON public.video_scenarios(thumbnail_text_overlay_prompt) WHERE thumbnail_text_overlay_prompt IS NOT NULL AND thumbnail_text_overlay_prompt != '';
