-- Auto-Promo AI Content System Schema
-- Products, shorts, video scenarios, and scenes management

-- Categories (parent and sub-categories for products)
CREATE TABLE IF NOT EXISTS public.categories (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    parent_id UUID REFERENCES public.categories(id) ON DELETE CASCADE,
    description TEXT,
    environments TEXT[] DEFAULT '{}', -- Array of environment names (e.g., Indoor, Outdoor, City, Mountain)
    is_active BOOLEAN DEFAULT true,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for categories
CREATE INDEX IF NOT EXISTS idx_categories_parent_id ON public.categories(parent_id);
CREATE INDEX IF NOT EXISTS idx_categories_is_active ON public.categories(is_active);
CREATE INDEX IF NOT EXISTS idx_categories_sort_order ON public.categories(sort_order);
CREATE INDEX IF NOT EXISTS idx_categories_environments ON public.categories USING GIN (environments);

-- User activities tracking
CREATE TABLE IF NOT EXISTS public.user_activities (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    action TEXT NOT NULL,
    resource_type TEXT,
    resource_id TEXT,
    details JSONB DEFAULT '{}',
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Shorts (video projects)
CREATE TABLE IF NOT EXISTS public.shorts (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    title TEXT,
    description TEXT,
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'processing', 'completed', 'failed', 'published')),
    duration INTEGER, -- in seconds
    thumbnail_url TEXT,
    final_video_url TEXT,
    platform_urls JSONB DEFAULT '{}',
    view_count BIGINT DEFAULT 0,
    download_count INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    video_file_path TEXT,
    video_file_url TEXT,
    video_file_size BIGINT,
    video_file_mime_type TEXT,
    thumbnail_path TEXT,
    target_language TEXT DEFAULT 'en-US' CHECK (
        target_language IN ('en-US', 'en-CA', 'en-GB', 'es', 'es-MX', 'pt-BR', 'fr', 'de', 'nl', 'ar', 'zh', 'ja')
    )
);

-- Products (scraped from e-commerce sites)
CREATE TABLE IF NOT EXISTS public.products (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    price NUMERIC,
    currency TEXT DEFAULT 'USD',
    original_url TEXT, -- Original product URL
    rating NUMERIC,
    review_count INTEGER,
    specifications JSONB DEFAULT '{}', -- Product specifications
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    platform TEXT, -- amazon, aliexpress, etc.
    short_id UUID REFERENCES public.shorts(id) ON DELETE CASCADE,
    images JSONB DEFAULT '{}', -- Object where keys are image URLs and values are analysis data
    category_id UUID REFERENCES public.categories(id) ON DELETE SET NULL
);

-- Video scenarios (AI-generated content plans)
CREATE TABLE IF NOT EXISTS public.video_scenarios (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    short_id UUID REFERENCES public.shorts(id) ON DELETE CASCADE NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    style TEXT,
    mood TEXT,
    total_duration INTEGER,
    audio_script JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    resolution TEXT DEFAULT '720:1280' CHECK (
        resolution IN (
            '1280:720',   -- 16:9 landscape
            '720:1280',   -- 9:16 portrait  
            '1104:832',   -- 4:3 landscape
            '832:1104',   -- 3:4 portrait
            '960:960',    -- 1:1 square
            '1584:672',   -- 21:9 ultra-wide
            '1280:768',   -- 16:9 landscape HD+
            '768:1280',   -- 9:16 portrait HD
            '1920:1080',  -- 16:9 Full HD
            '1080:1920',  -- 9:16 Full HD portrait
            '1440:1440'   -- 1:1 square HD
        )
    ),
    environment TEXT, -- Environment context for the video scenario (e.g., indoor, outdoor, studio, home, office, etc.)
    thumbnail_text_overlay_prompt TEXT
);

-- Video scenes (individual scenes within a scenario)
CREATE TABLE IF NOT EXISTS public.video_scenes (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    scenario_id UUID REFERENCES public.video_scenarios(id) ON DELETE CASCADE NOT NULL,
    scene_number INTEGER NOT NULL,
    description TEXT NOT NULL,
    duration INTEGER NOT NULL,
    visual_prompt TEXT,
    image_url TEXT,
    generated_video_url TEXT,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    scene_file_path TEXT,
    scene_file_url TEXT,
    scene_file_size BIGINT,
    scene_file_mime_type TEXT,
    image_prompt TEXT,
    text_overlay_prompt TEXT
);

-- Indexes for content system tables
CREATE INDEX IF NOT EXISTS idx_user_activities_user_id ON public.user_activities(user_id);
CREATE INDEX IF NOT EXISTS idx_user_activities_created_at ON public.user_activities(created_at);
CREATE INDEX IF NOT EXISTS idx_user_activities_action ON public.user_activities(action);

CREATE INDEX IF NOT EXISTS idx_products_user_id ON public.products(user_id);
CREATE INDEX IF NOT EXISTS idx_products_short_id ON public.products(short_id);
CREATE INDEX IF NOT EXISTS idx_products_category_id ON public.products(category_id);
CREATE INDEX IF NOT EXISTS idx_products_images_gin ON public.products USING GIN (images);
CREATE INDEX IF NOT EXISTS idx_products_created_at ON public.products(created_at);

CREATE INDEX IF NOT EXISTS idx_shorts_user_id ON public.shorts(user_id);
CREATE INDEX IF NOT EXISTS idx_shorts_status ON public.shorts(status);
CREATE INDEX IF NOT EXISTS idx_shorts_created_at ON public.shorts(created_at);
CREATE INDEX IF NOT EXISTS idx_shorts_target_language ON public.shorts(target_language);

CREATE INDEX IF NOT EXISTS idx_video_scenarios_short_id ON public.video_scenarios(short_id);
CREATE INDEX IF NOT EXISTS idx_video_scenarios_resolution ON public.video_scenarios(resolution);
CREATE INDEX IF NOT EXISTS idx_video_scenarios_environment ON public.video_scenarios(environment) WHERE environment IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_video_scenes_scenario_id ON public.video_scenes(scenario_id);
CREATE INDEX IF NOT EXISTS idx_video_scenes_status ON public.video_scenes(status);
CREATE INDEX IF NOT EXISTS idx_video_scenes_image_url ON public.video_scenes(image_url) WHERE image_url IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_video_scenes_generated_video_url ON public.video_scenes(generated_video_url) WHERE generated_video_url IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_video_scenes_image_prompt ON public.video_scenes(image_prompt) WHERE image_prompt IS NOT NULL;

-- Add comments to document the fields
COMMENT ON COLUMN public.categories.environments IS 'Array of environment names (e.g., Indoor, Outdoor, City, Mountain)';
COMMENT ON COLUMN public.products.images IS 'Object where keys are image URLs and values are image analysis data (empty object {} if no analysis)';
COMMENT ON COLUMN public.products.category_id IS 'Foreign key reference to the categories table';
COMMENT ON COLUMN public.shorts.target_language IS 'Target market language for content generation (audio scripts, subtitles, cultural adaptations). Supported: English (US/CA/UK), Spanish (Spain/Latin America/Mexico), Portuguese (Brazil), French, German, Dutch, Arabic, Chinese, Japanese';
COMMENT ON COLUMN public.video_scenarios.resolution IS 'Video resolution for content generation (e.g., "1280:720", "720:1280")';
COMMENT ON COLUMN public.video_scenarios.environment IS 'Environment context for the video scenario (e.g., indoor, outdoor, studio, home, office, etc.)';
COMMENT ON COLUMN public.video_scenes.image_url IS 'URL of the generated AI image for this scene';
COMMENT ON COLUMN public.video_scenes.generated_video_url IS 'URL of the generated video for this scene';
COMMENT ON COLUMN public.video_scenes.visual_prompt IS 'AI prompt used to generate the scene image';
COMMENT ON COLUMN public.video_scenes.image_prompt IS 'AI prompt used to generate the first frame image for this scene'; 