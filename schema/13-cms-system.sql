-- Auto-Promo AI CMS System Schema
-- Content Management System for admin dashboard

-- CMS Pages (homepage, dashboard, etc.)
CREATE TABLE IF NOT EXISTS public.cms_pages (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT true,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    content_fields JSONB DEFAULT '{}'
);

-- CMS Sections (hero, features, pricing, etc.)
CREATE TABLE IF NOT EXISTS public.cms_sections (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    page_id UUID REFERENCES public.cms_pages(id) ON DELETE CASCADE NOT NULL,
    type TEXT NOT NULL, -- hero, features, pricing, cta, etc.
    name TEXT NOT NULL,
    order_index INTEGER DEFAULT 0,
    is_visible BOOLEAN DEFAULT true,
    config JSONB DEFAULT '{}', -- Section-specific configuration
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- CMS Content Blocks (individual content items within sections)
CREATE TABLE IF NOT EXISTS public.cms_content_blocks (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    section_id UUID REFERENCES public.cms_sections(id) ON DELETE CASCADE NOT NULL,
    key TEXT NOT NULL, -- Unique key within section (e.g., 'title', 'subtitle', 'cta_text')
    content_type TEXT NOT NULL DEFAULT 'text', -- text, rich_text, json, image_url, etc.
    content JSONB DEFAULT '{}', -- Flexible content storage
    order_index INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(section_id, key)
);

-- CMS Assets (images, videos, documents)
CREATE TABLE IF NOT EXISTS public.cms_assets (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    filename TEXT NOT NULL,
    url TEXT NOT NULL,
    storage_path TEXT, -- Path in storage bucket
    type TEXT NOT NULL, -- image, video, document
    mime_type TEXT,
    alt_text TEXT,
    description TEXT,
    metadata JSONB DEFAULT '{}', -- width, height, size, etc.
    created_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- CMS Legal Documents (Terms, Privacy, Cookies, DPA)
CREATE TABLE IF NOT EXISTS public.cms_legal_documents (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    document_type TEXT NOT NULL, -- terms, privacy, cookies, dpa
    locale TEXT NOT NULL DEFAULT 'en',
    version INTEGER DEFAULT 1,
    content TEXT NOT NULL, -- Full document content (HTML/Markdown)
    effective_date DATE,
    is_published BOOLEAN DEFAULT false,
    created_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(document_type, locale, version)
);

-- CMS Translations (multilingual content for content blocks)
CREATE TABLE IF NOT EXISTS public.cms_translations (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    content_block_id UUID REFERENCES public.cms_content_blocks(id) ON DELETE CASCADE NOT NULL,
    locale TEXT NOT NULL,
    translated_content JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(content_block_id, locale)
);

-- Indexes for CMS tables
CREATE INDEX IF NOT EXISTS idx_cms_pages_slug ON public.cms_pages(slug);
CREATE INDEX IF NOT EXISTS idx_cms_pages_is_active ON public.cms_pages(is_active);

CREATE INDEX IF NOT EXISTS idx_cms_sections_page_id ON public.cms_sections(page_id);
CREATE INDEX IF NOT EXISTS idx_cms_sections_type ON public.cms_sections(type);
CREATE INDEX IF NOT EXISTS idx_cms_sections_order ON public.cms_sections(page_id, order_index);
CREATE INDEX IF NOT EXISTS idx_cms_sections_visible ON public.cms_sections(is_visible) WHERE is_visible = true;

CREATE INDEX IF NOT EXISTS idx_cms_content_blocks_section_id ON public.cms_content_blocks(section_id);
CREATE INDEX IF NOT EXISTS idx_cms_content_blocks_key ON public.cms_content_blocks(section_id, key);
CREATE INDEX IF NOT EXISTS idx_cms_content_blocks_order ON public.cms_content_blocks(section_id, order_index);

CREATE INDEX IF NOT EXISTS idx_cms_assets_type ON public.cms_assets(type);
CREATE INDEX IF NOT EXISTS idx_cms_assets_created_by ON public.cms_assets(created_by);
CREATE INDEX IF NOT EXISTS idx_cms_assets_created_at ON public.cms_assets(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_cms_legal_documents_type ON public.cms_legal_documents(document_type);
CREATE INDEX IF NOT EXISTS idx_cms_legal_documents_locale ON public.cms_legal_documents(locale);
CREATE INDEX IF NOT EXISTS idx_cms_legal_documents_published ON public.cms_legal_documents(document_type, locale, is_published) WHERE is_published = true;
CREATE INDEX IF NOT EXISTS idx_cms_legal_documents_version ON public.cms_legal_documents(document_type, locale, version DESC);

CREATE INDEX IF NOT EXISTS idx_cms_translations_content_block_id ON public.cms_translations(content_block_id);
CREATE INDEX IF NOT EXISTS idx_cms_translations_locale ON public.cms_translations(locale);
CREATE INDEX IF NOT EXISTS idx_cms_translations_unique ON public.cms_translations(content_block_id, locale);

-- RLS Policies (admin-only access for now, will be refined in Phase 5)
ALTER TABLE public.cms_pages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cms_sections ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cms_content_blocks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cms_assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cms_legal_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cms_translations ENABLE ROW LEVEL SECURITY;

-- Policy: Admins can do everything
CREATE POLICY "Admins can manage cms_pages" ON public.cms_pages
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM public.user_profiles
            WHERE user_profiles.user_id = auth.uid()
            AND user_profiles.role = 'admin'
        )
    );

CREATE POLICY "Admins can manage cms_sections" ON public.cms_sections
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM public.user_profiles
            WHERE user_profiles.user_id = auth.uid()
            AND user_profiles.role = 'admin'
        )
    );

CREATE POLICY "Admins can manage cms_content_blocks" ON public.cms_content_blocks
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM public.user_profiles
            WHERE user_profiles.user_id = auth.uid()
            AND user_profiles.role = 'admin'
        )
    );

CREATE POLICY "Admins can manage cms_assets" ON public.cms_assets
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM public.user_profiles
            WHERE user_profiles.user_id = auth.uid()
            AND user_profiles.role = 'admin'
        )
    );

CREATE POLICY "Admins can manage cms_legal_documents" ON public.cms_legal_documents
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM public.user_profiles
            WHERE user_profiles.user_id = auth.uid()
            AND user_profiles.role = 'admin'
        )
    );

CREATE POLICY "Admins can manage cms_translations" ON public.cms_translations
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM public.user_profiles
            WHERE user_profiles.user_id = auth.uid()
            AND user_profiles.role = 'admin'
        )
    );

-- Policy: Public read access for published content (for frontend)
CREATE POLICY "Public can read active cms_pages" ON public.cms_pages
    FOR SELECT USING (is_active = true);

CREATE POLICY "Public can read visible cms_sections" ON public.cms_sections
    FOR SELECT USING (
        is_visible = true AND
        EXISTS (
            SELECT 1 FROM public.cms_pages
            WHERE cms_pages.id = cms_sections.page_id
            AND cms_pages.is_active = true
        )
    );

CREATE POLICY "Public can read cms_content_blocks" ON public.cms_content_blocks
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM public.cms_sections
            JOIN public.cms_pages ON cms_pages.id = cms_sections.page_id
            WHERE cms_sections.id = cms_content_blocks.section_id
            AND cms_sections.is_visible = true
            AND cms_pages.is_active = true
        )
    );

CREATE POLICY "Public can read cms_assets" ON public.cms_assets
    FOR SELECT USING (true);

CREATE POLICY "Public can read published cms_legal_documents" ON public.cms_legal_documents
    FOR SELECT USING (is_published = true);

CREATE POLICY "Public can read cms_translations" ON public.cms_translations
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM public.cms_content_blocks
            JOIN public.cms_sections ON cms_sections.id = cms_content_blocks.section_id
            JOIN public.cms_pages ON cms_pages.id = cms_sections.page_id
            WHERE cms_content_blocks.id = cms_translations.content_block_id
            AND cms_sections.is_visible = true
            AND cms_pages.is_active = true
        )
    );

-- Comments for documentation
COMMENT ON TABLE public.cms_pages IS 'CMS pages (homepage, dashboard, etc.)';
COMMENT ON TABLE public.cms_sections IS 'CMS sections within pages (hero, features, pricing, etc.)';
COMMENT ON TABLE public.cms_content_blocks IS 'Individual content blocks within sections';
COMMENT ON TABLE public.cms_assets IS 'Visual assets (images, videos, documents)';
COMMENT ON TABLE public.cms_legal_documents IS 'Legal documents (Terms, Privacy, Cookies, DPA) with versioning';
COMMENT ON TABLE public.cms_translations IS 'Multilingual translations for content blocks';

