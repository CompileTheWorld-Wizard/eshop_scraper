-- ============================================================================
-- EMERGENCY FIX: Complete Reset of user_profiles Policies
-- This will temporarily disable RLS, fix everything, then re-enable
-- ============================================================================

-- STEP 1: Disable RLS temporarily to allow access
ALTER TABLE public.user_profiles DISABLE ROW LEVEL SECURITY;

-- STEP 2: Drop ALL existing policies on user_profiles
DO $$ 
DECLARE
    r RECORD;
BEGIN
    FOR r IN (SELECT policyname FROM pg_policies WHERE tablename = 'user_profiles' AND schemaname = 'public')
    LOOP
        EXECUTE 'DROP POLICY IF EXISTS ' || quote_ident(r.policyname) || ' ON public.user_profiles';
    END LOOP;
END $$;

-- STEP 3: Create the is_admin helper function (if not exists)
CREATE OR REPLACE FUNCTION public.is_admin(user_uuid UUID)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
BEGIN
    IF user_uuid IS NULL THEN
        RETURN false;
    END IF;
    
    RETURN EXISTS (
        SELECT 1 
        FROM public.user_profiles 
        WHERE user_id = user_uuid 
        AND role = 'admin'
    );
EXCEPTION
    WHEN OTHERS THEN
        RETURN false;
END;
$$;

GRANT EXECUTE ON FUNCTION public.is_admin(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION public.is_admin(UUID) TO anon;

-- STEP 4: Create NEW policies using the helper function
CREATE POLICY "user_profiles_select" ON public.user_profiles 
FOR SELECT 
USING (
    (select auth.uid()) = user_id 
    OR public.is_admin(auth.uid())
);

CREATE POLICY "user_profiles_insert" ON public.user_profiles 
FOR INSERT 
WITH CHECK ((select auth.uid()) = user_id);

CREATE POLICY "user_profiles_update" ON public.user_profiles 
FOR UPDATE 
USING ((select auth.uid()) = user_id) 
WITH CHECK ((select auth.uid()) = user_id);

-- STEP 5: Re-enable RLS
ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;

-- Verify
SELECT 'Function created:' as status, proname FROM pg_proc WHERE proname = 'is_admin'
UNION ALL
SELECT 'Policies created:' as status, policyname FROM pg_policies WHERE tablename = 'user_profiles';
