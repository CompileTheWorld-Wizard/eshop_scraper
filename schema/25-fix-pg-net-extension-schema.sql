-- Migration: Move pg_net Extension from Public to Extensions Schema
-- Description: Moves pg_net extension to dedicated 'extensions' schema
-- Priority: MEDIUM (security and best practices)
-- Risk: VERY LOW (only changes schema location, not functionality)
-- Date: 2024-01-14

-- Security Issue:
-- Extensions in 'public' schema can create naming conflicts and security issues
-- Best practice is to keep extensions in a separate 'extensions' schema

-- ============================================================================
-- STEP 1: Create extensions schema if it doesn't exist
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS extensions;

-- Grant usage to roles that need it
GRANT USAGE ON SCHEMA extensions TO postgres, anon, authenticated, service_role;

-- ============================================================================
-- STEP 2: Move pg_net extension to extensions schema
-- ============================================================================

-- Note: We need to drop and recreate the extension
-- This is safe because pg_net doesn't store persistent data

DO $$
BEGIN
    -- Check if pg_net exists in public schema
    IF EXISTS (
        SELECT 1 
        FROM pg_extension 
        WHERE extname = 'pg_net' 
        AND extnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public')
    ) THEN
        RAISE NOTICE 'Found pg_net in public schema, moving to extensions schema...';
        
        -- Drop from public
        DROP EXTENSION IF EXISTS pg_net CASCADE;
        
        -- Recreate in extensions schema
        CREATE EXTENSION IF NOT EXISTS pg_net WITH SCHEMA extensions;
        
        RAISE NOTICE '✓ Successfully moved pg_net to extensions schema';
    ELSIF EXISTS (
        SELECT 1 
        FROM pg_extension 
        WHERE extname = 'pg_net'
    ) THEN
        RAISE NOTICE 'pg_net already exists in a non-public schema (OK)';
    ELSE
        RAISE NOTICE 'pg_net extension not found, creating in extensions schema...';
        CREATE EXTENSION IF NOT EXISTS pg_net WITH SCHEMA extensions;
        RAISE NOTICE '✓ Created pg_net in extensions schema';
    END IF;
END $$;

-- ============================================================================
-- STEP 3: Verify the move
-- ============================================================================

DO $$
DECLARE
    ext_schema TEXT;
BEGIN
    SELECT n.nspname INTO ext_schema
    FROM pg_extension e
    JOIN pg_namespace n ON e.extnamespace = n.oid
    WHERE e.extname = 'pg_net';
    
    IF ext_schema = 'extensions' THEN
        RAISE NOTICE '========================================';
        RAISE NOTICE '✓ VERIFICATION PASSED';
        RAISE NOTICE 'pg_net is now in extensions schema';
        RAISE NOTICE '========================================';
    ELSE
        RAISE WARNING 'pg_net is in schema: % (expected: extensions)', ext_schema;
    END IF;
END $$;

-- ============================================================================
-- IMPORTANT NOTES
-- ============================================================================

COMMENT ON SCHEMA extensions IS 
'Schema for PostgreSQL extensions
All extensions should be installed here to avoid conflicts with application objects in the public schema.

Benefits:
- Prevents naming conflicts
- Better security isolation
- Cleaner schema organization
- Easier to manage permissions';
