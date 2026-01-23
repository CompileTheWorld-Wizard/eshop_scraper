-- ============================================================================
-- Migration: Fix Infinite Recursion in RLS Policies
-- Description: Create helper function to check admin status without circular dependency
-- Date: 2026-01-19
-- ============================================================================

-- First, create a function that checks if a user is an admin
-- This function uses SECURITY DEFINER to bypass RLS and prevent infinite recursion
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

-- Grant execute permission to authenticated users
GRANT EXECUTE ON FUNCTION public.is_admin(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION public.is_admin(UUID) TO anon;

-- Now update the user_profiles policies to use the function instead of direct query
DROP POLICY IF EXISTS "user_profiles_select" ON public.user_profiles;
DROP POLICY IF EXISTS "user_profiles_update" ON public.user_profiles;
DROP POLICY IF EXISTS "user_profiles_insert" ON public.user_profiles;

-- Recreate policies using the helper function
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
USING (
    (select auth.uid()) = user_id 
    OR public.is_admin(auth.uid())
) 
WITH CHECK (
    (select auth.uid()) = user_id 
    OR public.is_admin(auth.uid())
);

-- Note: The SECURITY DEFINER function bypasses RLS when checking the user_profiles table,
-- which breaks the circular dependency that was causing infinite recursion.
