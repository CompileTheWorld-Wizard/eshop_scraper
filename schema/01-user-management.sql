-- Auto-Promo AI User Management Schema
-- User profiles table that extends Supabase auth.users

-- User profiles with additional metadata (extends Supabase auth.users)
CREATE TABLE IF NOT EXISTS public.user_profiles (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    full_name TEXT,
    username TEXT,
    company_name TEXT,
    company_url TEXT,
    referral_source TEXT,
    referral_source_other TEXT,
    referral_link TEXT, -- Unique referral link for this user
    onboarding_completed BOOLEAN DEFAULT false,
    avatar_url TEXT,
    phone TEXT,
    timezone TEXT DEFAULT 'UTC',
    language TEXT DEFAULT 'en',
    bio TEXT,
    website TEXT,
    social_links JSONB DEFAULT '{}',
    preferences JSONB DEFAULT '{}',
    role TEXT DEFAULT 'user', -- user, admin, moderator
    is_active BOOLEAN DEFAULT true, -- whether user account is active/enabled
    credits_total INTEGER DEFAULT 0,
    credits_remaining INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id)
);

-- Indexes for user_profiles
CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id ON public.user_profiles(user_id);
CREATE INDEX IF NOT EXISTS idx_user_profiles_created_at ON public.user_profiles(created_at);
CREATE INDEX IF NOT EXISTS idx_user_profiles_role ON public.user_profiles(role);
CREATE INDEX IF NOT EXISTS idx_user_profiles_referral_link ON public.user_profiles(referral_link);

-- Trigger for updated_at column
CREATE TRIGGER update_user_profiles_updated_at 
    BEFORE UPDATE ON public.user_profiles 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- User referrals table - tracks who referred whom
CREATE TABLE IF NOT EXISTS public.user_referrals (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    referred_user UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    referrer_user UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(referred_user) -- Each user can only be referred once
);

-- Indexes for user_referrals
CREATE INDEX IF NOT EXISTS idx_user_referrals_referred_user ON public.user_referrals(referred_user);
CREATE INDEX IF NOT EXISTS idx_user_referrals_referrer_user ON public.user_referrals(referrer_user);
CREATE INDEX IF NOT EXISTS idx_user_referrals_created_at ON public.user_referrals(created_at);

-- Referral commissions table - tracks earned commissions
CREATE TABLE IF NOT EXISTS public.referral_commissions (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    referrer_user UUID REFERENCES auth.users(id) ON DELETE SET NULL NOT NULL,
    referred_user UUID REFERENCES auth.users(id) ON DELETE SET NULL NOT NULL,
    amount NUMERIC(10, 2) NOT NULL, -- Commission amount with 2 decimal places
    payment_id TEXT, -- Stripe payment ID
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for referral_commissions
CREATE INDEX IF NOT EXISTS idx_referral_commissions_referrer_user ON public.referral_commissions(referrer_user);
CREATE INDEX IF NOT EXISTS idx_referral_commissions_referred_user ON public.referral_commissions(referred_user);
CREATE INDEX IF NOT EXISTS idx_referral_commissions_payment_id ON public.referral_commissions(payment_id);
CREATE INDEX IF NOT EXISTS idx_referral_commissions_created_at ON public.referral_commissions(created_at); 