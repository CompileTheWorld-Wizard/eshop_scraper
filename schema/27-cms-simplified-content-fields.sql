-- CMS Simplified Content Fields Migration
-- Add content_fields column to cms_pages for simplified flat content structure

-- Add content_fields column to cms_pages table
ALTER TABLE public.cms_pages 
ADD COLUMN IF NOT EXISTS content_fields JSONB DEFAULT '{}';

-- Add index for content_fields queries
CREATE INDEX IF NOT EXISTS idx_cms_pages_content_fields ON public.cms_pages USING GIN (content_fields);

-- Add comment
COMMENT ON COLUMN public.cms_pages.content_fields IS 'Simplified flat content structure for page editing (replaces sections/blocks hierarchy)';

-- Ensure the 4 required pages exist (create if they don't)
INSERT INTO public.cms_pages (slug, name, description, is_active, content_fields)
VALUES 
  ('dashboard', 'User Dashboard', 'Main user dashboard page', true, '{}'),
  ('subscription', 'Subscription Page', 'Subscription and billing management page', true, '{}'),
  ('billing-history', 'Billing History', 'Billing history and transaction records', true, '{}'),
  ('settings', 'Settings', 'User settings and preferences', true, '{}')
ON CONFLICT (slug) DO NOTHING;