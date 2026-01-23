-- ============================================================================
-- Migration: Fix missing INSERT policy for user_profiles
-- Description: Add INSERT policy to allow users to create their profile during onboarding
-- Date: 2026-01-19
-- ============================================================================

-- Add INSERT policy for user_profiles
-- Allow authenticated users to insert their own profile
CREATE POLICY "user_profiles_insert" ON public.user_profiles 
FOR INSERT 
WITH CHECK ((select auth.uid()) = user_id);

-- Note: This policy allows users to create their profile only if the user_id matches their auth.uid()
-- This is essential for the onboarding process where users need to create their profile record
