-- Auto-Promo AI Media System Schema
-- Audio information and publishing information management

-- Audio information for videos
CREATE TABLE IF NOT EXISTS public.audio_info (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    short_id UUID REFERENCES public.shorts(id) ON DELETE CASCADE NOT NULL,
    voice_id TEXT NOT NULL,
    voice_name TEXT,
    speed NUMERIC DEFAULT 1.0,
    volume NUMERIC DEFAULT 1.0,
    generated_audio_url TEXT,
    subtitles JSONB DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    status TEXT DEFAULT 'pending',
    metadata JSONB DEFAULT '{}',
    audio_file_path TEXT,
    audio_file_url TEXT,
    audio_file_size BIGINT,
    audio_file_mime_type TEXT
);

-- Publishing information for social media platforms
CREATE TABLE IF NOT EXISTS public.publishing_info (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    short_id UUID REFERENCES public.shorts(id) ON DELETE CASCADE NOT NULL,
    platform TEXT NOT NULL, -- tiktok, youtube, instagram, etc.
    description TEXT,
    schedule_time TIMESTAMP WITH TIME ZONE,
    settings JSONB DEFAULT '{}',
    published_at TIMESTAMP WITH TIME ZONE,
    platform_video_id TEXT,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    final_video_path TEXT,
    final_video_url TEXT,
    final_video_size BIGINT,
    final_video_mime_type TEXT
);

-- Indexes for media system tables
CREATE INDEX IF NOT EXISTS idx_audio_info_user_id ON public.audio_info(user_id);
CREATE INDEX IF NOT EXISTS idx_audio_info_short_id ON public.audio_info(short_id);

CREATE INDEX IF NOT EXISTS idx_publishing_info_user_id ON public.publishing_info(user_id);
CREATE INDEX IF NOT EXISTS idx_publishing_info_short_id ON public.publishing_info(short_id);
CREATE INDEX IF NOT EXISTS idx_publishing_info_platform ON public.publishing_info(platform); 