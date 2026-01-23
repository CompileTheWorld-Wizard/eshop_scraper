-- Migration: Add SET search_path to All Functions
-- Description: Fixes mutable search_path security warning on all functions
-- Priority: MEDIUM (security hardening)
-- Risk: VERY LOW (only adds SET search_path parameter)
-- Date: 2024-01-14
-- This migration is idempotent - safe to run multiple times
--
-- CONSOLIDATED: Contains all function search_path fixes
--
-- NOTE: This migration file documents the fix but cannot be run directly.
-- The actual fix requires re-running the entire schema files that define the functions.
--
-- INSTRUCTIONS:
-- Run these schema files in Supabase SQL Editor to apply the fixes:
-- 1. schema/06-functions.sql (main application functions)
-- 2. schema/15-cms-audit-logging.sql (CMS audit function)
-- 3. schema/17-cms-locale-content-fields.sql (CMS locale functions)
-- 4. schema/26-brand-kit-system.sql (brand kit functions)
-- 5. Run this migration for 8 remaining functions not in schema files

-- ============================================================================
-- FUNCTIONS FIXED IN SCHEMA FILES (run those files to apply):
-- ============================================================================

-- From schema/06-functions.sql:
-- - initialize_user_on_signup
-- - increment_video_views
-- - increment_video_downloads
-- - sync_all_user_credits
-- - trigger_sync_user_credits
-- - get_user_credits
-- - get_user_status
-- - sync_user_credits_to_profile
-- - deduct_user_credits
-- - reset_subscription_credits_on_renewal
-- - get_plan_credit_configs_with_actions
-- - can_perform_action
-- - ensure_target_language_case

-- From schema/15-cms-audit-logging.sql:
-- - log_cms_change

-- From schema/17-cms-locale-content-fields.sql:
-- - migrate_content_fields_to_locale_aware
-- - get_cms_content_for_locale

-- From schema/26-brand-kit-system.sql:
-- - increment_brand_asset_downloads
-- - increment_premade_content_downloads
-- - increment_premade_content_shares

-- From schema/06-functions.sql (triggers):
-- - update_updated_at_column

-- ============================================================================
-- FIX FOR 8 REMAINING FUNCTIONS (not in schema files)
-- ============================================================================
-- These functions exist in Supabase but not in schema files (manual creation)

DO $$
DECLARE
    func_rec RECORD;
    func_def TEXT;
    new_func_def TEXT;
    func_count INTEGER := 0;
BEGIN
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Fixing Remaining 8 Functions...';
    RAISE NOTICE '========================================';
    
    -- Get all functions that need fixing
    FOR func_rec IN 
        SELECT 
            p.proname as name,
            pg_get_functiondef(p.oid) as definition
        FROM pg_proc p
        JOIN pg_namespace n ON p.pronamespace = n.oid
        WHERE n.nspname = 'public'
        AND p.proname IN (
            'ensure_user_has_credits',
            'ensure_user_has_free_plan', 
            'ensure_user_has_profile',
            'handle_new_user_signup',
            'get_plan_by_name',
            'get_all_active_plans',
            'get_plan_credit_configs_with_actions',
            'ensure_target_language_case'
        )
        AND (
            p.proconfig IS NULL 
            OR NOT EXISTS (
                SELECT 1 
                FROM unnest(p.proconfig) AS config
                WHERE config LIKE 'search_path=%'
            )
        )
    LOOP
        func_count := func_count + 1;
        RAISE NOTICE '';
        RAISE NOTICE 'Processing function #%: %', func_count, func_rec.name;
        
        -- Get the function definition
        func_def := func_rec.definition;
        RAISE NOTICE 'Original definition length: % chars', length(func_def);
        
        -- Add SET search_path = public
        -- The format from pg_get_functiondef is:
        -- LANGUAGE xxx
        --  SECURITY DEFINER (optional)
        -- AS $function$...
        
        new_func_def := func_def;
        
        -- Pattern 1: LANGUAGE xxx \n SECURITY DEFINER \n AS
        IF new_func_def ~ 'SECURITY\s+DEFINER\s+AS' THEN
            new_func_def := regexp_replace(
                new_func_def,
                '(SECURITY\s+DEFINER)\s+(AS)',
                E'\\1\n SET search_path = public\n\\2',
                'g'
            );
            RAISE NOTICE 'Applied pattern: SECURITY DEFINER AS';
        -- Pattern 2: LANGUAGE xxx \n AS (no SECURITY DEFINER)
        ELSIF new_func_def ~ 'LANGUAGE\s+\w+\s+AS' THEN
            new_func_def := regexp_replace(
                new_func_def,
                '(LANGUAGE\s+\w+)\s+(AS)',
                E'\\1\n SET search_path = public\n\\2',
                'g'
            );
            RAISE NOTICE 'Applied pattern: LANGUAGE xxx AS';
        ELSE
            RAISE WARNING 'Could not match pattern for function: %', func_rec.name;
            RAISE NOTICE 'Function definition: %', func_def;
            CONTINUE;
        END IF;
        
        RAISE NOTICE 'Modified definition length: % chars', length(new_func_def);
        
        -- Execute the modified function definition
        BEGIN
            EXECUTE new_func_def;
            RAISE NOTICE '✓ Successfully fixed function: %', func_rec.name;
        EXCEPTION WHEN OTHERS THEN
            RAISE WARNING '✗ Failed to fix function %: %', func_rec.name, SQLERRM;
            RAISE NOTICE 'Modified definition: %', new_func_def;
        END;
        
    END LOOP;
    
    RAISE NOTICE '';
    RAISE NOTICE '========================================';
    IF func_count = 0 THEN
        RAISE NOTICE 'No functions needed fixing (all already have search_path set)';
    ELSE
        RAISE NOTICE 'Processed % function(s)', func_count;
    END IF;
    RAISE NOTICE '========================================';
END $$;

-- ============================================================================
-- VERIFICATION
-- ============================================================================

DO $$
DECLARE
    func_count INTEGER;
    functions_with_search_path INTEGER;
    functions_without_search_path INTEGER;
BEGIN
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Verifying function search_path...';
    RAISE NOTICE '========================================';
    
    -- Count total functions
    SELECT COUNT(*) INTO func_count
    FROM pg_proc p
    JOIN pg_namespace n ON p.pronamespace = n.oid
    WHERE n.nspname = 'public'
    AND p.prokind = 'f';
    
    -- Count functions with search_path
    SELECT COUNT(*) INTO functions_with_search_path
    FROM pg_proc p
    JOIN pg_namespace n ON p.pronamespace = n.oid
    WHERE n.nspname = 'public'
    AND p.prokind = 'f'
    AND p.proconfig IS NOT NULL
    AND EXISTS (
        SELECT 1 
        FROM unnest(p.proconfig) AS config
        WHERE config LIKE 'search_path=%'
    );
    
    -- Count functions without search_path
    functions_without_search_path := func_count - functions_with_search_path;
    
    RAISE NOTICE 'Total functions: %', func_count;
    RAISE NOTICE 'With search_path: %', functions_with_search_path;
    RAISE NOTICE 'Without search_path: %', functions_without_search_path;
    RAISE NOTICE '========================================';
    
    IF functions_without_search_path = 0 THEN
        RAISE NOTICE '✓✓✓ All functions have search_path set!';
    ELSE
        RAISE WARNING '% functions still need search_path fix', functions_without_search_path;
    END IF;
    
    RAISE NOTICE '========================================';
END $$;
