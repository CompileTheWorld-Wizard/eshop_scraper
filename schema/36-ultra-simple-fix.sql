-- ============================================================================
-- ULTRA SIMPLE FIX: Remove admin checks entirely (temporary)
-- This will get registration working, then we can add admin back later
-- ============================================================================

-- Drop ALL policies on user_profiles
DO $$ 
DECLARE
    r RECORD;
BEGIN
    FOR r IN (SELECT policyname FROM pg_policies WHERE tablename = 'user_profiles' AND schemaname = 'public')
    LOOP
        EXECUTE 'DROP POLICY IF EXISTS ' || quote_ident(r.policyname) || ' ON public.user_profiles';
        RAISE NOTICE 'Dropped policy: %', r.policyname;
    END LOOP;
END $$;

-- Create SIMPLE policies WITHOUT any admin checks
-- Users can only see and edit their own profile
CREATE POLICY "user_profiles_select" ON public.user_profiles 
FOR SELECT 
USING ((select auth.uid()) = user_id);

CREATE POLICY "user_profiles_insert" ON public.user_profiles 
FOR INSERT 
WITH CHECK ((select auth.uid()) = user_id);

CREATE POLICY "user_profiles_update" ON public.user_profiles 
FOR UPDATE 
USING ((select auth.uid()) = user_id) 
WITH CHECK ((select auth.uid()) = user_id);

-- Verify the new policies
SELECT 
    policyname,
    cmd as operation,
    qual as using_expression
FROM pg_policies
WHERE tablename = 'user_profiles' AND schemaname = 'public'
ORDER BY policyname;
