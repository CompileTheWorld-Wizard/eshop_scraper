-- Migration: CMS Homepage Content from i18n
-- Description: Inserts homepage hero, features, and brands content from i18n/locales/en.json
-- Date: 2024-01-14
-- Note: This ensures all i18n homepage content is included when cloning database

-- This migration creates CMS pages, sections, and content blocks for the homepage
-- based on src/i18n/locales/en.json translations

DO $$
DECLARE
    v_page_id UUID;
    v_hero_section_id UUID;
    v_features_section_id UUID;
    v_brands_section_id UUID;
    v_cta_section_id UUID;
BEGIN
    RAISE NOTICE 'Creating homepage CMS structure from i18n...';

    -- Create or update homepage
    INSERT INTO public.cms_pages (slug, name, description, is_active, metadata)
    VALUES (
        'home',
        'Homepage',
        'Main landing page with hero, features, brands, and CTA sections',
        true,
        '{"locale": "en", "source": "i18n"}'::jsonb
    )
    ON CONFLICT (slug) DO UPDATE SET
        updated_at = NOW()
    RETURNING id INTO v_page_id;

    RAISE NOTICE 'Created/Updated homepage: %', v_page_id;

    -- Create Hero Section
    SELECT id INTO v_hero_section_id FROM public.cms_sections WHERE page_id = v_page_id AND type = 'hero' AND name = 'Hero Section';
    IF v_hero_section_id IS NULL THEN
        INSERT INTO public.cms_sections (page_id, type, name, order_index, is_visible, config)
        VALUES (v_page_id, 'hero', 'Hero Section', 0, true, '{}'::jsonb)
        RETURNING id INTO v_hero_section_id;
    ELSE
        UPDATE public.cms_sections SET updated_at = NOW() WHERE id = v_hero_section_id;
    END IF;

    -- Insert Hero content blocks
    INSERT INTO public.cms_content_blocks (section_id, key, content, content_type, order_index)
    VALUES
        (v_hero_section_id, 'badge', '{"text": "AI-Powered Video Generation"}'::jsonb, 'text', 0),
        (v_hero_section_id, 'title', '{"text": "Transform Product Links into"}'::jsonb, 'text', 1),
        (v_hero_section_id, 'titleHighlight', '{"text": "Viral Videos"}'::jsonb, 'text', 2),
        (v_hero_section_id, 'subtitle', '{"text": "PromoNexAI turns your product URLs into engaging short-form videos for"}'::jsonb, 'text', 3),
        (v_hero_section_id, 'tiktok', '{"text": "TikTok"}'::jsonb, 'text', 4),
        (v_hero_section_id, 'instagramReels', '{"text": "Instagram Reels"}'::jsonb, 'text', 5),
        (v_hero_section_id, 'youtubeShorts', '{"text": "YouTube Shorts"}'::jsonb, 'text', 6),
        (v_hero_section_id, 'subtitleEnd', '{"text": "— all powered by AI. Save hours of content creation time with automated script generation, captions, and hashtags."}'::jsonb, 'text', 7),
        (v_hero_section_id, 'ctaPrimary', '{"text": "Start Creating Free"}'::jsonb, 'text', 8),
        (v_hero_section_id, 'ctaSecondary', '{"text": "See How It Works"}'::jsonb, 'text', 9),
        (v_hero_section_id, 'rating', '{"text": "4.8/5"}'::jsonb, 'text', 10),
        (v_hero_section_id, 'reviews', '{"text": "(127 Reviews)"}'::jsonb, 'text', 11)
    ON CONFLICT (section_id, key) DO UPDATE SET
        content = EXCLUDED.content,
        updated_at = NOW();

    RAISE NOTICE 'Created hero section with 12 content blocks';

    -- Create Features Section
    SELECT id INTO v_features_section_id FROM public.cms_sections WHERE page_id = v_page_id AND type = 'features' AND name = 'Features Section';
    IF v_features_section_id IS NULL THEN
        INSERT INTO public.cms_sections (page_id, type, name, order_index, is_visible, config)
        VALUES (v_page_id, 'features', 'Features Section', 1, true, '{}'::jsonb)
        RETURNING id INTO v_features_section_id;
    ELSE
        UPDATE public.cms_sections SET updated_at = NOW() WHERE id = v_features_section_id;
    END IF;

    -- Insert Features content blocks
    INSERT INTO public.cms_content_blocks (section_id, key, content, content_type, order_index)
    VALUES
        (v_features_section_id, 'badge', '{"text": "Powerful Features"}'::jsonb, 'text', 0),
        (v_features_section_id, 'title', '{"text": "Everything you need to"}'::jsonb, 'text', 1),
        (v_features_section_id, 'titleHighlight', '{"text": "create viral content"}'::jsonb, 'text', 2),
        (v_features_section_id, 'subtitle', '{"text": "Transform your product links into engaging social media content in minutes, not hours. Let AI handle the heavy lifting while you focus on growing your business."}'::jsonb, 'text', 3),
        (v_features_section_id, 'aiScript', '{"text": "AI Script Generation"}'::jsonb, 'text', 4),
        (v_features_section_id, 'aiScriptDesc', '{"text": "Generate compelling scripts with hooks and CTAs from any product URL in seconds"}'::jsonb, 'text', 5),
        (v_features_section_id, 'voiceovers', '{"text": "Professional Voiceovers"}'::jsonb, 'text', 6),
        (v_features_section_id, 'voiceoversDesc', '{"text": "Convert your scripts into natural-sounding voiceovers with multiple voice options and languages"}'::jsonb, 'text', 7),
        (v_features_section_id, 'autoVideo', '{"text": "Auto Video Creation"}'::jsonb, 'text', 8),
        (v_features_section_id, 'autoVideoDesc', '{"text": "Automatically match your content with relevant stock footage or use your own videos seamlessly"}'::jsonb, 'text', 9),
        (v_features_section_id, 'captions', '{"text": "Smart Captions"}'::jsonb, 'text', 10),
        (v_features_section_id, 'captionsDesc', '{"text": "Generate and sync captions automatically with perfect timing and multiple styles"}'::jsonb, 'text', 11),
        (v_features_section_id, 'posting', '{"text": "Direct Platform Posting"}'::jsonb, 'text', 12),
        (v_features_section_id, 'postingDesc', '{"text": "Post directly to TikTok, Instagram, and YouTube with our integrated API and scheduling"}'::jsonb, 'text', 13),
        (v_features_section_id, 'analytics', '{"text": "Performance Analytics"}'::jsonb, 'text', 14),
        (v_features_section_id, 'analyticsDesc', '{"text": "Track your video performance and optimize your content strategy with detailed insights"}'::jsonb, 'text', 15),
        (v_features_section_id, 'bottomCta', '{"text": "Ready to start creating? Join thousands of creators already using PromoNexAI"}'::jsonb, 'text', 16)
    ON CONFLICT (section_id, key) DO UPDATE SET
        content = EXCLUDED.content,
        updated_at = NOW();

    RAISE NOTICE 'Created features section with 17 content blocks';

    -- Create Brands Section
    SELECT id INTO v_brands_section_id FROM public.cms_sections WHERE page_id = v_page_id AND type = 'custom' AND name = 'Brands Section';
    IF v_brands_section_id IS NULL THEN
        INSERT INTO public.cms_sections (page_id, type, name, order_index, is_visible, config)
        VALUES (v_page_id, 'custom', 'Brands Section', 2, true, '{}'::jsonb)
        RETURNING id INTO v_brands_section_id;
    ELSE
        UPDATE public.cms_sections SET updated_at = NOW() WHERE id = v_brands_section_id;
    END IF;

    -- Insert Brands content blocks
    INSERT INTO public.cms_content_blocks (section_id, key, content, content_type, order_index)
    VALUES
        (v_brands_section_id, 'badge', '{"text": "Supported Platforms"}'::jsonb, 'text', 0),
        (v_brands_section_id, 'title', '{"text": "Works with all major"}'::jsonb, 'text', 1),
        (v_brands_section_id, 'titleHighlight', '{"text": "e-commerce platforms"}'::jsonb, 'text', 2),
        (v_brands_section_id, 'subtitle', '{"text": "Automatically scrape product information from your favorite online stores"}'::jsonb, 'text', 3),
        (v_brands_section_id, 'comingSoon', '{"text": "More platforms coming soon..."}'::jsonb, 'text', 4)
    ON CONFLICT (section_id, key) DO UPDATE SET
        content = EXCLUDED.content,
        updated_at = NOW();

    RAISE NOTICE 'Created brands section with 5 content blocks';

    -- Create CTA Section
    SELECT id INTO v_cta_section_id FROM public.cms_sections WHERE page_id = v_page_id AND type = 'cta' AND name = 'Call to Action Section';
    IF v_cta_section_id IS NULL THEN
        INSERT INTO public.cms_sections (page_id, type, name, order_index, is_visible, config)
        VALUES (v_page_id, 'cta', 'Call to Action Section', 3, true, '{}'::jsonb)
        RETURNING id INTO v_cta_section_id;
    ELSE
        UPDATE public.cms_sections SET updated_at = NOW() WHERE id = v_cta_section_id;
    END IF;

    -- Insert CTA content blocks
    INSERT INTO public.cms_content_blocks (section_id, key, content, content_type, order_index)
    VALUES
        (v_cta_section_id, 'badge', '{"text": "Join 10,000+ creators"}'::jsonb, 'text', 0),
        (v_cta_section_id, 'title', '{"text": "Ready to transform your"}'::jsonb, 'text', 1),
        (v_cta_section_id, 'titleHighlight', '{"text": "content creation?"}'::jsonb, 'text', 2),
        (v_cta_section_id, 'subtitle', '{"text": "Join thousands of creators and brands using PromoNexAI to generate engaging content that converts. Start free today and scale as you grow."}'::jsonb, 'text', 3),
        (v_cta_section_id, 'ctaPrimary', '{"text": "Start Creating for Free"}'::jsonb, 'text', 4),
        (v_cta_section_id, 'ctaSecondary', '{"text": "View All Plans"}'::jsonb, 'text', 5)
    ON CONFLICT (section_id, key) DO UPDATE SET
        content = EXCLUDED.content,
        updated_at = NOW();

    RAISE NOTICE 'Created CTA section with 6 content blocks';

    RAISE NOTICE '✅ Homepage CMS content migration completed successfully!';
END $$;
