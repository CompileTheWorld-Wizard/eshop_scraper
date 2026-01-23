-- Migration: Insert CMS Initial Content from JSON
-- Description: Migrates content from data/cms-content.json into cms_pages table
-- Date: 2024-01-14
-- Note: This ensures CMS content is included when cloning database

-- Insert home page with content from cms-content.json
INSERT INTO public.cms_pages (slug, name, content_fields, is_active)
VALUES (
  'home',
  'Home Page',
  '{
    "hero": {
      "badge": "AI-Powered Video Generator",
      "title": "Transform Product URLs into",
      "titleHighlight": "Viral Videos",
      "subtitle": "Create professional videos with AI-powered script generation, automated captions, and hashtags. Perfect for e-commerce and social media marketing.",
      "ctaPrimary": "Get Started Free",
      "ctaSecondary": "See How It Works",
      "rating": "4.8/5",
      "reviews": "Based on 130+ reviews"
    },
    "brands": {
      "badge": "Trusted by Leading Brands",
      "title": "Powering Video Creation for",
      "titleHighlight": "Leading E-commerce Platforms",
      "subtitle": "Join thousands of businesses creating engaging content",
      "comingSoon": "More brands coming soon"
    },
    "features": {
      "badge": "Features",
      "title": "Everything You Need to Create",
      "titleHighlight": "Stunning Videos",
      "subtitle": "Powerful tools to transform your product URLs into engaging social media content"
    },
    "cta": {
      "badge": "Ready to Get Started?",
      "title": "Start Creating Videos Today",
      "subtitle": "Join thousands of businesses already using our platform",
      "ctaPrimary": "Get Started Free",
      "ctaSecondary": "View Pricing",
      "trustIndicators": "No credit card required • Free trial available • Cancel anytime"
    }
  }'::jsonb,
  true
)
ON CONFLICT (slug) DO UPDATE SET
  content_fields = EXCLUDED.content_fields,
  updated_at = NOW();

-- Verification
DO $$
DECLARE
    page_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO page_count
    FROM public.cms_pages
    WHERE slug = 'home';
    
    IF page_count > 0 THEN
        RAISE NOTICE '✅ CMS content migrated successfully!';
        RAISE NOTICE 'Home page content fields created';
    ELSE
        RAISE WARNING '⚠️ CMS content migration may have failed';
    END IF;
END $$;
