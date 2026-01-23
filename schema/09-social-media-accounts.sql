-- Auto-Promo AI Social Media Accounts Schema
-- Social media account credentials and metadata management

-- Social media accounts table for storing OAuth credentials and account data
CREATE TABLE IF NOT EXISTS public.social_media_accounts (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    platform TEXT NOT NULL, -- youtube, tiktok, instagram, etc.
    account_name TEXT NOT NULL, -- Display name of the account
    account_id TEXT NOT NULL, -- Platform-specific account ID
    access_token TEXT, -- OAuth access token
    refresh_token TEXT, -- OAuth refresh token
    token_expires_at TIMESTAMP WITH TIME ZONE, -- Token expiration time
    is_active BOOLEAN DEFAULT true, -- Whether the account is active/connected
    error_message TEXT, -- Error message if account is inactive
    metadata JSONB DEFAULT '{}', -- Platform-specific account data (channel info, etc.)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, platform, account_id)
);

-- Indexes for social_media_accounts
CREATE INDEX IF NOT EXISTS idx_social_media_accounts_user_id ON public.social_media_accounts(user_id);
CREATE INDEX IF NOT EXISTS idx_social_media_accounts_platform ON public.social_media_accounts(platform);
CREATE INDEX IF NOT EXISTS idx_social_media_accounts_account_id ON public.social_media_accounts(account_id);
CREATE INDEX IF NOT EXISTS idx_social_media_accounts_is_active ON public.social_media_accounts(is_active);
CREATE INDEX IF NOT EXISTS idx_social_media_accounts_created_at ON public.social_media_accounts(created_at);

-- RLS (Row Level Security) policies
ALTER TABLE public.social_media_accounts ENABLE ROW LEVEL SECURITY;

-- Drop existing policies if they exist
DROP POLICY IF EXISTS "Users can view their own social media accounts" ON public.social_media_accounts;
DROP POLICY IF EXISTS "Users can insert their own social media accounts" ON public.social_media_accounts;
DROP POLICY IF EXISTS "Users can update their own social media accounts" ON public.social_media_accounts;
DROP POLICY IF EXISTS "Users can delete their own social media accounts" ON public.social_media_accounts;

-- Policy: Users can only access their own social media accounts
CREATE POLICY "Users can view their own social media accounts" ON public.social_media_accounts
    FOR SELECT USING (auth.uid() = user_id);

-- Policy: Users can insert their own social media accounts
CREATE POLICY "Users can insert their own social media accounts" ON public.social_media_accounts
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Policy: Users can update their own social media accounts
CREATE POLICY "Users can update their own social media accounts" ON public.social_media_accounts
    FOR UPDATE USING (auth.uid() = user_id);

-- Policy: Users can delete their own social media accounts
CREATE POLICY "Users can delete their own social media accounts" ON public.social_media_accounts
    FOR DELETE USING (auth.uid() = user_id);
