-- Migration: Fix auth.users Permission Errors in Functions
-- Description: Adds SECURITY DEFINER to functions that query auth.users table
-- Priority: HIGH (fixes permission denied errors)
-- Risk: LOW (only adds SECURITY DEFINER to existing functions)
-- Date: 2026-01-20
-- Issue: Functions get_user_credits and get_user_status query auth.users but lack SECURITY DEFINER
-- Impact: Causes "permission denied for table users" errors when called from application
--
-- This migration is idempotent - safe to run multiple times

-- ============================================================================
-- Fix: get_user_credits - Add SECURITY DEFINER
-- ============================================================================
-- This function queries auth.users table and needs elevated privileges

CREATE OR REPLACE FUNCTION get_user_credits(user_uuid UUID)
RETURNS TABLE(
    credits_total INTEGER,
    credits_remaining INTEGER,
    subscription_status TEXT,
    plan_name TEXT,
    plan_display_name TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        COALESCE(uc.total_credits, 0) as credits_total,
        COALESCE(uc.credits_remaining, 0) as credits_remaining,
        COALESCE(us.status, 'no_subscription') as subscription_status,
        COALESCE(sp.name, 'no_plan') as plan_name,
        COALESCE(sp.display_name, 'No Plan') as plan_display_name
    FROM auth.users u
    LEFT JOIN public.user_credits uc ON u.id = uc.user_id
    LEFT JOIN public.user_subscriptions us ON u.id = us.user_id AND us.status = 'active'
    LEFT JOIN public.subscription_plans sp ON us.plan_id = sp.id
    WHERE u.id = user_uuid;
END;
$$ LANGUAGE plpgsql
SECURITY DEFINER  -- Added to allow querying auth.users
SET search_path = public;

-- ============================================================================
-- Fix: get_user_status - Add SECURITY DEFINER
-- ============================================================================
-- This function also queries auth.users table and needs elevated privileges

CREATE OR REPLACE FUNCTION get_user_status(user_uuid UUID)
RETURNS TABLE(
    user_id UUID,
    full_name TEXT,
    email TEXT,
    role TEXT,
    is_active BOOLEAN,
    onboarding_completed BOOLEAN,
    subscription_status TEXT,
    plan_name TEXT,
    plan_display_name TEXT,
    credits_total INTEGER,
    credits_remaining INTEGER,
    created_at TIMESTAMP WITH TIME ZONE,
    last_activity TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        u.id as user_id,
        up.full_name,
        u.email,
        up.role,
        up.is_active,
        up.onboarding_completed,
        COALESCE(us.status, 'no_subscription') as subscription_status,
        COALESCE(sp.name, 'no_plan') as plan_name,
        COALESCE(sp.display_name, 'No Plan') as plan_display_name,
        COALESCE(uc.total_credits, 0) as credits_total,
        COALESCE(uc.credits_remaining, 0) as credits_remaining,
        up.created_at,
        (SELECT MAX(created_at) FROM public.user_activities WHERE user_id = u.id) as last_activity
    FROM auth.users u
    LEFT JOIN public.user_profiles up ON u.id = up.user_id
    LEFT JOIN public.user_credits uc ON u.id = uc.user_id
    LEFT JOIN public.user_subscriptions us ON u.id = us.user_id AND us.status = 'active'
    LEFT JOIN public.subscription_plans sp ON us.plan_id = sp.id
    WHERE u.id = user_uuid;
END;
$$ LANGUAGE plpgsql
SECURITY DEFINER  -- Added to allow querying auth.users
SET search_path = public;

-- ============================================================================
-- Verification
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Migration 38: Fix auth.users Permission Functions';
    RAISE NOTICE '========================================';
    RAISE NOTICE '✓ Updated get_user_credits with SECURITY DEFINER';
    RAISE NOTICE '✓ Updated get_user_status with SECURITY DEFINER';
    RAISE NOTICE '';
    RAISE NOTICE 'These functions can now query auth.users table without permission errors.';
    RAISE NOTICE '========================================';
END $$;
