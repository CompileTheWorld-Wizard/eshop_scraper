-- ============================================================================
-- Verification Script: Check RLS Policies for Onboarding Process
-- Description: Verify all necessary policies exist for the onboarding flow
-- Date: 2026-01-19
-- ============================================================================

-- Check existing policies for user_profiles
SELECT 
    schemaname,
    tablename,
    policyname,
    permissive,
    roles,
    cmd,
    qual,
    with_check
FROM pg_policies
WHERE tablename = 'user_profiles'
ORDER BY cmd, policyname;

-- Expected policies:
-- 1. user_profiles_select (FOR SELECT)
-- 2. user_profiles_insert (FOR INSERT) <- THIS WAS MISSING
-- 3. user_profiles_update (FOR UPDATE)

-- Check policies for related tables used in onboarding
SELECT 
    tablename,
    policyname,
    cmd
FROM pg_policies
WHERE tablename IN ('user_activities', 'user_credits')
ORDER BY tablename, cmd, policyname;
