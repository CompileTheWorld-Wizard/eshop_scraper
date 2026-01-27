-- Migration: Fix Credit Functions Permission Errors
-- Description: Adds SECURITY DEFINER to credit functions that query auth.users table
-- Priority: HIGH (fixes permission denied errors in credit system)
-- Risk: LOW (only adds SECURITY DEFINER to existing functions)
-- Date: 2026-01-24
-- Issue: Functions can_perform_action and deduct_user_credits query auth.users but lack SECURITY DEFINER
-- Impact: Causes "permission denied for table users" errors when checking/deducting credits
--
-- This migration is idempotent - safe to run multiple times

-- ============================================================================
-- METHOD 1: Simple ALTER (Recommended - Quick Fix)
-- ============================================================================
-- This adds SECURITY DEFINER without recreating the entire function

ALTER FUNCTION public.can_perform_action(UUID, TEXT) SECURITY DEFINER;
ALTER FUNCTION public.deduct_user_credits(UUID, TEXT, UUID, TEXT, TEXT) SECURITY DEFINER;

-- ============================================================================
-- Verification
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Migration 39: Fix Credit Functions Security';
    RAISE NOTICE '========================================';
    RAISE NOTICE '✓ Updated can_perform_action with SECURITY DEFINER';
    RAISE NOTICE '✓ Updated deduct_user_credits with SECURITY DEFINER';
    RAISE NOTICE '';
    RAISE NOTICE 'These functions can now query auth.users table without permission errors.';
    RAISE NOTICE '========================================';
END $$;

-- ============================================================================
-- Verification Query (Run separately to verify)
-- ============================================================================
-- Uncomment and run this to verify the functions now have SECURITY DEFINER:

/*
SELECT 
    p.proname as function_name,
    CASE 
        WHEN p.prosecdef THEN 'SECURITY DEFINER'
        ELSE 'SECURITY INVOKER'
    END as security_type
FROM pg_proc p
JOIN pg_namespace n ON p.pronamespace = n.oid
WHERE p.proname IN ('can_perform_action', 'deduct_user_credits', 'get_user_credits')
AND n.nspname = 'public'
ORDER BY p.proname;
*/
