-- Migration: Referral System Setup
-- Purpose: Complete referral system implementation
-- This migration includes:
--   1. Fix referral_link format to include full URL
--   2. Add referral_clicks tracking field
--   3. Create referral tables (user_referrals, referral_commissions)
-- Date: 2024
-- This migration is idempotent - safe to run multiple times

-- ============================================================================
-- PART 1: Fix referral_link format to include full URL
-- ============================================================================

-- Update all referral_links by regenerating them from user emails
-- This ensures all referral_links follow the correct format
UPDATE public.user_profiles up
SET referral_link = 'https://promonexai.com/en/register?ref=' || encode(convert_to(COALESCE(u.email, ''), 'UTF8'), 'base64')
FROM auth.users u
WHERE up.user_id = u.id
  AND u.email IS NOT NULL
  AND (
    -- Update if referral_link is NULL or empty
    up.referral_link IS NULL 
    OR trim(up.referral_link) = ''
    -- Or if referral_link doesn't start with the correct URL format
    OR NOT up.referral_link LIKE 'https://promonexai.com/en/register?ref=%'
    -- Or if referral_link has nested URLs (contains multiple http:// or https://)
    OR up.referral_link LIKE '%http://%http%' 
    OR up.referral_link LIKE '%https://%https%'
  );

-- ============================================================================
-- PART 2: Add referral_clicks field to user_profiles
-- ============================================================================

-- Add referral_clicks column to user_profiles
ALTER TABLE public.user_profiles 
ADD COLUMN IF NOT EXISTS referral_clicks INTEGER DEFAULT 0;

-- Add index for performance when querying by click count
CREATE INDEX IF NOT EXISTS idx_user_profiles_referral_clicks 
ON public.user_profiles(referral_clicks);

-- Add comment for documentation
COMMENT ON COLUMN public.user_profiles.referral_clicks IS 
'Total number of times this user''s referral link has been clicked';

-- Initialize existing users with 0 clicks (already default, but explicit for clarity)
UPDATE public.user_profiles 
SET referral_clicks = 0 
WHERE referral_clicks IS NULL;

-- ============================================================================
-- PART 3: Create referral tables
-- ============================================================================

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

-- Row Level Security for user_referrals table
ALTER TABLE public.user_referrals ENABLE ROW LEVEL SECURITY;

-- Users can view their own referral data
CREATE POLICY "Users can view their own referral data" ON public.user_referrals
FOR SELECT
USING (auth.uid() = referred_user OR auth.uid() = referrer_user);

-- Admins can manage referrals
CREATE POLICY "Admins can manage referrals" ON public.user_referrals
FOR ALL
USING (
    EXISTS (
        SELECT 1 FROM public.user_profiles
        WHERE user_profiles.user_id = auth.uid()
        AND user_profiles.role = 'admin'
    )
)
WITH CHECK (
    EXISTS (
        SELECT 1 FROM public.user_profiles
        WHERE user_profiles.user_id = auth.uid()
        AND user_profiles.role = 'admin'
    )
);

-- Grant permissions
GRANT SELECT ON public.user_referrals TO authenticated;
GRANT ALL ON public.user_referrals TO service_role;

-- Add comments for documentation
COMMENT ON TABLE public.user_referrals IS 'Tracks referral relationships between users';
COMMENT ON COLUMN public.user_referrals.referred_user IS 'The user who was referred (new user)';
COMMENT ON COLUMN public.user_referrals.referrer_user IS 'The user who made the referral (existing user)';
COMMENT ON COLUMN public.user_referrals.created_at IS 'When the referral relationship was created';

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

-- Add comments for documentation
COMMENT ON TABLE public.referral_commissions IS 'Tracks commissions earned by referrers when referred users make payments';
COMMENT ON COLUMN public.referral_commissions.referrer_user IS 'The user who earned the commission (referrer)';
COMMENT ON COLUMN public.referral_commissions.referred_user IS 'The user who made the payment (referred user)';
COMMENT ON COLUMN public.referral_commissions.amount IS 'Commission amount in USD with 2 decimal places';
COMMENT ON COLUMN public.referral_commissions.payment_id IS 'Stripe payment ID for tracking the payment that generated this commission';

-- Optional: Create a composite index for common queries
CREATE INDEX IF NOT EXISTS idx_referral_commissions_referrer_created 
ON public.referral_commissions(referrer_user, created_at DESC);

-- Optional: Create index for querying commissions by payment
CREATE INDEX IF NOT EXISTS idx_referral_commissions_payment_id_not_null 
ON public.referral_commissions(payment_id) 
WHERE payment_id IS NOT NULL;

