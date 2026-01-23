-- Auto-Promo AI Brand Kit System Schema
-- Brand Kit for Affiliates: Brand assets and pre-made content for referral marketing
-- Date: 2024

-- ============================================================================
-- PART 1: Brand Kit Categories
-- ============================================================================

-- Brand kit categories (logos, banners, social media templates, etc.)
CREATE TABLE IF NOT EXISTS public.brand_kit_categories (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    icon TEXT, -- Lucide icon name
    order_index INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================================
-- PART 2: Brand Assets (Logos, Colors, Fonts, Guidelines)
-- ============================================================================

-- Brand assets - downloadable assets for affiliates
CREATE TABLE IF NOT EXISTS public.brand_assets (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    category_id UUID REFERENCES public.brand_kit_categories(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    description TEXT,
    asset_type TEXT NOT NULL, -- logo, banner, image, color_palette, font, guideline
    file_url TEXT, -- Supabase storage URL
    storage_path TEXT, -- Path in storage bucket
    file_format TEXT, -- svg, png, jpg, pdf, zip
    file_size INTEGER, -- File size in bytes
    dimensions JSONB DEFAULT '{}', -- { width: 1920, height: 1080 }
    metadata JSONB DEFAULT '{}', -- Additional metadata (colors, usage notes)
    order_index INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    download_count INTEGER DEFAULT 0,
    created_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================================
-- PART 3: Pre-made Content (Ready-to-publish content)
-- ============================================================================

-- Pre-made content - ready to use content for affiliates
CREATE TABLE IF NOT EXISTS public.premade_content (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    category_id UUID REFERENCES public.brand_kit_categories(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    description TEXT,
    content_type TEXT NOT NULL, -- social_post, video, image, email_template, story, reel
    platform TEXT, -- tiktok, instagram, youtube, twitter, facebook, email, all
    
    -- Content data
    title TEXT,
    caption TEXT, -- Pre-written caption/text for social posts
    hashtags TEXT[], -- Array of recommended hashtags
    cta_text TEXT, -- Call to action text
    
    -- Media
    thumbnail_url TEXT,
    media_url TEXT, -- Main media file URL
    storage_path TEXT,
    media_type TEXT, -- image, video
    duration INTEGER, -- Duration in seconds for videos
    dimensions JSONB DEFAULT '{}', -- { width: 1080, height: 1920 }
    
    -- Metadata
    metadata JSONB DEFAULT '{}',
    tags TEXT[], -- Searchable tags
    order_index INTEGER DEFAULT 0,
    is_featured BOOLEAN DEFAULT false,
    is_active BOOLEAN DEFAULT true,
    download_count INTEGER DEFAULT 0,
    share_count INTEGER DEFAULT 0,
    
    created_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================================
-- PART 4: Pre-made Content Translations (Multilingual)
-- ============================================================================

-- Translations for pre-made content
CREATE TABLE IF NOT EXISTS public.premade_content_translations (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    content_id UUID REFERENCES public.premade_content(id) ON DELETE CASCADE NOT NULL,
    locale TEXT NOT NULL,
    title TEXT,
    caption TEXT,
    hashtags TEXT[],
    cta_text TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(content_id, locale)
);

-- ============================================================================
-- PART 5: Brand Kit Activity Tracking
-- ============================================================================

-- Track downloads and shares for analytics
CREATE TABLE IF NOT EXISTS public.brand_kit_activities (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    activity_type TEXT NOT NULL, -- download, share, copy_caption, copy_hashtags
    item_type TEXT NOT NULL, -- brand_asset, premade_content
    item_id UUID NOT NULL,
    platform TEXT, -- Platform where content was shared (optional)
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================================
-- PART 6: Indexes for Performance
-- ============================================================================

-- Brand kit categories indexes
CREATE INDEX IF NOT EXISTS idx_brand_kit_categories_slug ON public.brand_kit_categories(slug);
CREATE INDEX IF NOT EXISTS idx_brand_kit_categories_active ON public.brand_kit_categories(is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_brand_kit_categories_order ON public.brand_kit_categories(order_index);

-- Brand assets indexes
CREATE INDEX IF NOT EXISTS idx_brand_assets_category ON public.brand_assets(category_id);
CREATE INDEX IF NOT EXISTS idx_brand_assets_type ON public.brand_assets(asset_type);
CREATE INDEX IF NOT EXISTS idx_brand_assets_active ON public.brand_assets(is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_brand_assets_order ON public.brand_assets(category_id, order_index);

-- Pre-made content indexes
CREATE INDEX IF NOT EXISTS idx_premade_content_category ON public.premade_content(category_id);
CREATE INDEX IF NOT EXISTS idx_premade_content_type ON public.premade_content(content_type);
CREATE INDEX IF NOT EXISTS idx_premade_content_platform ON public.premade_content(platform);
CREATE INDEX IF NOT EXISTS idx_premade_content_active ON public.premade_content(is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_premade_content_featured ON public.premade_content(is_featured) WHERE is_featured = true;
CREATE INDEX IF NOT EXISTS idx_premade_content_order ON public.premade_content(category_id, order_index);
CREATE INDEX IF NOT EXISTS idx_premade_content_tags ON public.premade_content USING GIN(tags);

-- Translations indexes
CREATE INDEX IF NOT EXISTS idx_premade_content_translations_content ON public.premade_content_translations(content_id);
CREATE INDEX IF NOT EXISTS idx_premade_content_translations_locale ON public.premade_content_translations(locale);

-- Activity tracking indexes
CREATE INDEX IF NOT EXISTS idx_brand_kit_activities_user ON public.brand_kit_activities(user_id);
CREATE INDEX IF NOT EXISTS idx_brand_kit_activities_item ON public.brand_kit_activities(item_type, item_id);
CREATE INDEX IF NOT EXISTS idx_brand_kit_activities_created ON public.brand_kit_activities(created_at DESC);

-- ============================================================================
-- PART 7: Triggers (REMOVED - update_updated_at_column function doesn't exist)
-- ============================================================================
-- All update triggers have been removed as the update_updated_at_column() function
-- is not used in the original database

-- ============================================================================
-- PART 8: Row Level Security (RLS)
-- ============================================================================

ALTER TABLE public.brand_kit_categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.brand_assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.premade_content ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.premade_content_translations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.brand_kit_activities ENABLE ROW LEVEL SECURITY;

-- Admins can do everything
DROP POLICY IF EXISTS "Admins can manage brand_kit_categories" ON public.brand_kit_categories;
CREATE POLICY "Admins can manage brand_kit_categories" ON public.brand_kit_categories
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM public.user_profiles
            WHERE user_profiles.user_id = auth.uid()
            AND user_profiles.role = 'admin'
        )
    );

DROP POLICY IF EXISTS "Admins can manage brand_assets" ON public.brand_assets;
CREATE POLICY "Admins can manage brand_assets" ON public.brand_assets
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM public.user_profiles
            WHERE user_profiles.user_id = auth.uid()
            AND user_profiles.role = 'admin'
        )
    );

DROP POLICY IF EXISTS "Admins can manage premade_content" ON public.premade_content;
CREATE POLICY "Admins can manage premade_content" ON public.premade_content
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM public.user_profiles
            WHERE user_profiles.user_id = auth.uid()
            AND user_profiles.role = 'admin'
        )
    );

DROP POLICY IF EXISTS "Admins can manage premade_content_translations" ON public.premade_content_translations;
CREATE POLICY "Admins can manage premade_content_translations" ON public.premade_content_translations
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM public.user_profiles
            WHERE user_profiles.user_id = auth.uid()
            AND user_profiles.role = 'admin'
        )
    );

DROP POLICY IF EXISTS "Admins can manage brand_kit_activities" ON public.brand_kit_activities;
CREATE POLICY "Admins can manage brand_kit_activities" ON public.brand_kit_activities
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM public.user_profiles
            WHERE user_profiles.user_id = auth.uid()
            AND user_profiles.role = 'admin'
        )
    );

-- Authenticated users can read active content
DROP POLICY IF EXISTS "Users can read active brand_kit_categories" ON public.brand_kit_categories;
CREATE POLICY "Users can read active brand_kit_categories" ON public.brand_kit_categories
    FOR SELECT USING (is_active = true);

DROP POLICY IF EXISTS "Users can read active brand_assets" ON public.brand_assets;
CREATE POLICY "Users can read active brand_assets" ON public.brand_assets
    FOR SELECT USING (is_active = true);

DROP POLICY IF EXISTS "Users can read active premade_content" ON public.premade_content;
CREATE POLICY "Users can read active premade_content" ON public.premade_content
    FOR SELECT USING (is_active = true);

DROP POLICY IF EXISTS "Users can read premade_content_translations" ON public.premade_content_translations;
CREATE POLICY "Users can read premade_content_translations" ON public.premade_content_translations
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM public.premade_content
            WHERE premade_content.id = premade_content_translations.content_id
            AND premade_content.is_active = true
        )
    );

-- Users can create their own activity records
DROP POLICY IF EXISTS "Users can create own activities" ON public.brand_kit_activities;
CREATE POLICY "Users can create own activities" ON public.brand_kit_activities
    FOR INSERT WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can read own activities" ON public.brand_kit_activities;
CREATE POLICY "Users can read own activities" ON public.brand_kit_activities
    FOR SELECT USING (auth.uid() = user_id);

-- ============================================================================
-- PART 9: Initial Data (Default Categories)
-- ============================================================================

INSERT INTO public.brand_kit_categories (slug, name, description, icon, order_index) VALUES
    ('logos', 'Logos & Branding', 'Official logos in various formats and sizes', 'Palette', 1),
    ('banners', 'Banners & Covers', 'Social media banners, cover images, and headers', 'Image', 2),
    ('social-templates', 'Social Media Templates', 'Ready-to-use post templates for social platforms', 'Share2', 3),
    ('videos', 'Video Content', 'Pre-made promotional videos and reels', 'Video', 4),
    ('marketing-copy', 'Marketing Copy', 'Pre-written captions, descriptions, and email templates', 'FileText', 5),
    ('graphics', 'Graphics & Icons', 'Product showcases, infographics, and promotional graphics', 'Sparkles', 6)
ON CONFLICT (slug) DO NOTHING;

-- ============================================================================
-- PART 10: Helper Functions for Tracking
-- ============================================================================

-- Function to increment brand asset downloads
CREATE OR REPLACE FUNCTION increment_brand_asset_downloads(asset_id UUID)
RETURNS void AS $$
BEGIN
    UPDATE public.brand_assets 
    SET download_count = COALESCE(download_count, 0) + 1
    WHERE id = asset_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public;

-- Function to increment premade content downloads
CREATE OR REPLACE FUNCTION increment_premade_content_downloads(content_id UUID)
RETURNS void AS $$
BEGIN
    UPDATE public.premade_content 
    SET download_count = COALESCE(download_count, 0) + 1
    WHERE id = content_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public;

-- Function to increment premade content shares
CREATE OR REPLACE FUNCTION increment_premade_content_shares(content_id UUID)
RETURNS void AS $$
BEGIN
    UPDATE public.premade_content 
    SET share_count = COALESCE(share_count, 0) + 1
    WHERE id = content_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public;

-- Grant execute permissions to authenticated users
GRANT EXECUTE ON FUNCTION increment_brand_asset_downloads(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION increment_premade_content_downloads(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION increment_premade_content_shares(UUID) TO authenticated;

-- ============================================================================
-- PART 11: Comments
-- ============================================================================

COMMENT ON TABLE public.brand_kit_categories IS 'Categories for organizing brand kit content';
COMMENT ON TABLE public.brand_assets IS 'Downloadable brand assets (logos, banners, guidelines)';
COMMENT ON TABLE public.premade_content IS 'Pre-made content ready for affiliates to publish';
COMMENT ON TABLE public.premade_content_translations IS 'Multilingual translations for pre-made content';
COMMENT ON TABLE public.brand_kit_activities IS 'Activity tracking for downloads and shares';

