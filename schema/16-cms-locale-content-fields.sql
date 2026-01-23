-- CMS Locale-Aware Content Fields Migration
-- Restructure content_fields to support per-locale content storage
-- 
-- New structure: content_fields = {
--   "en": { "hero": { "title": "...", "subtitle": "..." }, ... },
--   "es": { "hero": { "title": "...", "subtitle": "..." }, ... },
--   "de": { ... }
-- }

-- Add comment to document the new structure
COMMENT ON COLUMN public.cms_pages.content_fields IS 
'Locale-aware content structure. Format: { "locale": { "section": { "field": "value" } } }. Example: { "en": { "hero": { "title": "Welcome" } }, "es": { "hero": { "title": "Bienvenido" } } }';

-- Create a function to migrate existing content_fields to locale-aware format
-- This wraps existing content under the "en" locale key
CREATE OR REPLACE FUNCTION migrate_content_fields_to_locale_aware()
RETURNS void AS $$
DECLARE
    page_record RECORD;
    current_content JSONB;
    migrated_content JSONB;
BEGIN
    FOR page_record IN 
        SELECT id, slug, content_fields 
        FROM public.cms_pages 
        WHERE content_fields IS NOT NULL 
          AND content_fields != '{}'::jsonb
          -- Only migrate if not already locale-aware (doesn't have 'en' at top level with nested sections)
          AND NOT (content_fields ? 'en' AND jsonb_typeof(content_fields->'en') = 'object')
    LOOP
        current_content := page_record.content_fields;
        
        -- Wrap existing content under 'en' locale
        migrated_content := jsonb_build_object('en', current_content);
        
        -- Update the page
        UPDATE public.cms_pages 
        SET content_fields = migrated_content,
            updated_at = NOW()
        WHERE id = page_record.id;
        
        RAISE NOTICE 'Migrated page % (%) to locale-aware format', page_record.slug, page_record.id;
    END LOOP;
END;
$$ LANGUAGE plpgsql
SET search_path = public;

-- Execute the migration
SELECT migrate_content_fields_to_locale_aware();

-- Drop the migration function after use (optional, can keep for re-running)
-- DROP FUNCTION IF EXISTS migrate_content_fields_to_locale_aware();

-- Create a helper function to get content for a specific locale with fallback
CREATE OR REPLACE FUNCTION get_cms_content_for_locale(
    page_slug TEXT,
    target_locale TEXT DEFAULT 'en',
    fallback_locale TEXT DEFAULT 'en'
)
RETURNS JSONB AS $$
DECLARE
    content JSONB;
    locale_content JSONB;
BEGIN
    -- Get the full content_fields
    SELECT content_fields INTO content
    FROM public.cms_pages
    WHERE slug = page_slug AND is_active = true;
    
    IF content IS NULL THEN
        RETURN '{}'::jsonb;
    END IF;
    
    -- Try target locale first
    locale_content := content->target_locale;
    
    IF locale_content IS NOT NULL AND locale_content != 'null'::jsonb THEN
        RETURN locale_content;
    END IF;
    
    -- Fallback to default locale
    locale_content := content->fallback_locale;
    
    IF locale_content IS NOT NULL AND locale_content != 'null'::jsonb THEN
        RETURN locale_content;
    END IF;
    
    -- Return empty object if no content found
    RETURN '{}'::jsonb;
END;
$$ LANGUAGE plpgsql
SET search_path = public;

-- Add index for faster locale-based queries
CREATE INDEX IF NOT EXISTS idx_cms_pages_content_fields_locale 
ON public.cms_pages USING GIN ((content_fields -> 'en'));

-- Example query to get Spanish content with English fallback:
-- SELECT get_cms_content_for_locale('home', 'es', 'en');

