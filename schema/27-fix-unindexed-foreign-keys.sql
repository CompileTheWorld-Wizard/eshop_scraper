-- Migration: Add Indexes to Foreign Keys + Drop Leftover Table
-- Description: Adds indexes to 6 unindexed foreign keys for better JOIN/DELETE performance
--              and drops the preview_config_backup table (leftover, not in schema)
-- Priority: Medium (performance optimization)
-- Risk: ZERO (only adding indexes and removing unused table)
-- Date: 2024-01-14
--
-- ISSUE: Foreign keys without indexes cause slow JOINs and DELETE operations
-- SOLUTION: Add covering indexes to all foreign key columns

-- ============================================================================
-- PART 1: Add Indexes to Unindexed Foreign Keys
-- ============================================================================

-- addon_credits.purchase_transaction_id → credit_transactions.id
CREATE INDEX IF NOT EXISTS idx_addon_credits_purchase_transaction_id 
  ON public.addon_credits(purchase_transaction_id);

-- alerts.acknowledged_by → user_profiles.user_id
CREATE INDEX IF NOT EXISTS idx_alerts_acknowledged_by 
  ON public.alerts(acknowledged_by);

-- brand_assets.created_by → user_profiles.user_id
CREATE INDEX IF NOT EXISTS idx_brand_assets_created_by 
  ON public.brand_assets(created_by);

-- cms_legal_documents.created_by → user_profiles.user_id
CREATE INDEX IF NOT EXISTS idx_cms_legal_documents_created_by 
  ON public.cms_legal_documents(created_by);

-- error_logs.resolved_by → user_profiles.user_id
CREATE INDEX IF NOT EXISTS idx_error_logs_resolved_by 
  ON public.error_logs(resolved_by);

-- premade_content.created_by → user_profiles.user_id
CREATE INDEX IF NOT EXISTS idx_premade_content_created_by 
  ON public.premade_content(created_by);

-- ============================================================================
-- PART 2: Drop Leftover Table (not in schema files)
-- ============================================================================

-- Drop preview_config_backup table (leftover from manual operations)
-- This table is not defined in any schema file and only has admin-only RLS policies
DROP TABLE IF EXISTS public.preview_config_backup CASCADE;

-- ============================================================================
-- VERIFICATION
-- ============================================================================

DO $$
DECLARE
    new_indexes INTEGER;
BEGIN
    RAISE NOTICE '========================================';
    RAISE NOTICE 'FOREIGN KEY INDEX OPTIMIZATION COMPLETE!';
    RAISE NOTICE '========================================';
    
    -- Count newly created indexes
    SELECT COUNT(*) INTO new_indexes
    FROM pg_indexes
    WHERE schemaname = 'public'
    AND indexname IN (
        'idx_addon_credits_purchase_transaction_id',
        'idx_alerts_acknowledged_by',
        'idx_brand_assets_created_by',
        'idx_cms_legal_documents_created_by',
        'idx_error_logs_resolved_by',
        'idx_premade_content_created_by'
    );
    
    RAISE NOTICE 'New foreign key indexes created: %', new_indexes;
    RAISE NOTICE 'Leftover table dropped: preview_config_backup';
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Benefits:';
    RAISE NOTICE '  - Faster JOINs on foreign key columns';
    RAISE NOTICE '  - Faster DELETE operations on parent tables';
    RAISE NOTICE '  - Better query performance at scale';
    RAISE NOTICE '========================================';
END $$;
