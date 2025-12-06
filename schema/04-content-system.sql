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

-- Trigger for updated_at column
CREATE TRIGGER update_categories_updated_at 
    BEFORE UPDATE ON public.categories 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- User activities tracking
CREATE TABLE IF NOT EXISTS public.user_activities (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    action TEXT NOT NULL,
    details JSONB DEFAULT '{}',
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Products (scraped from e-commerce sites)
CREATE TABLE IF NOT EXISTS public.products (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    short_id UUID REFERENCES public.shorts(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    price DECIMAL(10,2),
    currency TEXT DEFAULT 'USD',
    images JSONB DEFAULT '{}'::jsonb, -- Object where keys are image URLs and values are analysis data
    original_url TEXT, -- Original product URL
    platform TEXT, -- amazon, aliexpress, etc.
    category TEXT, -- DEPRECATED: Use category_id instead. This column will be removed in a future migration.
    category_id UUID REFERENCES public.categories(id) ON DELETE SET NULL,
    rating DECIMAL(3,2),
    review_count INTEGER,
    availability TEXT,
    shipping_info TEXT,
    specifications JSONB DEFAULT '{}'::jsonb, -- Product specifications
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Shorts (video projects)
CREATE TABLE IF NOT EXISTS public.shorts (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'processing', 'completed', 'failed', 'published')),
    thumbnail_url TEXT,
    video_url TEXT,
    duration INTEGER, -- in seconds
    views INTEGER DEFAULT 0,
    downloads INTEGER DEFAULT 0,
    target_language TEXT DEFAULT 'en-US' CHECK (
        target_language IN ('en-US', 'en-CA', 'en-GB', 'es', 'es-MX', 'pt-BR', 'fr', 'de', 'nl')
    ),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Video scenarios (AI-generated content plans)
CREATE TABLE IF NOT EXISTS public.video_scenarios (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    short_id UUID REFERENCES public.shorts(id) ON DELETE CASCADE NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    script TEXT,
    scene_count INTEGER DEFAULT 0,
    estimated_duration INTEGER, -- in seconds
    resolution TEXT DEFAULT '720:1280' CHECK (
        resolution IN (
            '1280:720',   -- 16:9 landscape
            '720:1280',   -- 9:16 portrait  
            '1104:832',   -- 4:3 landscape
            '832:1104',   -- 3:4 portrait
            '960:960',    -- 1:1 square
            '1584:672',   -- 21:9 ultra-wide
            '1280:768',   -- 16:9 landscape HD+
            '768:1280'    -- 9:16 portrait HD
        )
    ),
    environment TEXT, -- Environment context for the video scenario (e.g., indoor, outdoor, studio, home, office, etc.)
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Video scenes (individual scenes within a scenario)
CREATE TABLE IF NOT EXISTS public.video_scenes (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    scenario_id UUID REFERENCES public.video_scenarios(id) ON DELETE CASCADE NOT NULL,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    scene_number INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    script TEXT,
    duration INTEGER, -- in seconds
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    video_url TEXT,
    thumbnail_url TEXT,
    image_url TEXT, -- URL of the generated AI image for this scene
    generated_video_url TEXT, -- URL of the generated video for this scene
    visual_prompt TEXT, -- AI prompt used to generate the scene image
    image_prompt TEXT, -- AI prompt used to generate the first frame image for this scene
    product_reference_image_url TEXT, -- URL of the product reference image used for this specific scene generation
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
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
CREATE INDEX IF NOT EXISTS idx_video_scenes_user_id ON public.video_scenes(user_id);
CREATE INDEX IF NOT EXISTS idx_video_scenes_image_url ON public.video_scenes(image_url) WHERE image_url IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_video_scenes_generated_video_url ON public.video_scenes(generated_video_url) WHERE generated_video_url IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_video_scenes_image_prompt ON public.video_scenes(image_prompt) WHERE image_prompt IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_video_scenes_product_reference_image_url ON public.video_scenes(product_reference_image_url) WHERE product_reference_image_url IS NOT NULL;

-- Triggers for updated_at columns
CREATE TRIGGER update_products_updated_at 
    BEFORE UPDATE ON public.products 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_shorts_updated_at 
    BEFORE UPDATE ON public.shorts 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_video_scenes_updated_at 
    BEFORE UPDATE ON public.video_scenes 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Add comments to document the fields
COMMENT ON COLUMN public.categories.environments IS 'Array of environment names (e.g., Indoor, Outdoor, City, Mountain)';
COMMENT ON COLUMN public.products.images IS 'Object where keys are image URLs and values are image analysis data (empty object {} if no analysis)';
COMMENT ON COLUMN public.products.category IS 'DEPRECATED: Use category_id instead. This column will be removed in a future migration.';
COMMENT ON COLUMN public.products.category_id IS 'Foreign key reference to the categories table';
COMMENT ON COLUMN public.shorts.target_language IS 'Target market language for content generation (audio scripts, subtitles, cultural adaptations). Supported: English (US/CA/UK), Spanish (Spain/Latin America/Mexico), Portuguese (Brazil), French, German, Dutch';
COMMENT ON COLUMN public.video_scenarios.resolution IS 'Video resolution for content generation (e.g., "1280:720", "720:1280")';
COMMENT ON COLUMN public.video_scenarios.environment IS 'Environment context for the video scenario (e.g., indoor, outdoor, studio, home, office, etc.)';
COMMENT ON COLUMN public.video_scenes.image_url IS 'URL of the generated AI image for this scene';
COMMENT ON COLUMN public.video_scenes.generated_video_url IS 'URL of the generated video for this scene';
COMMENT ON COLUMN public.video_scenes.visual_prompt IS 'AI prompt used to generate the scene image';
COMMENT ON COLUMN public.video_scenes.image_prompt IS 'AI prompt used to generate the first frame image for this scene';
COMMENT ON COLUMN public.video_scenes.user_id IS 'User who owns this scene';
COMMENT ON COLUMN public.video_scenes.product_reference_image_url IS 'URL of the product reference image used for this specific scene generation'; 