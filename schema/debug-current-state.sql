-- Detailed verification of current state

-- 1. Check if is_admin function exists and its definition
SELECT 
    'is_admin function' as check_type,
    proname as name,
    prosecdef as security_definer,
    pg_get_functiondef(oid) as definition
FROM pg_proc 
WHERE proname = 'is_admin' AND pronamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public');

-- 2. Check ALL policies on user_profiles (including the problematic USING clause)
SELECT 
    'user_profiles policies' as check_type,
    policyname,
    cmd,
    CASE 
        WHEN qual LIKE '%SELECT user_id FROM public.user_profiles%' THEN 'HAS CIRCULAR REFERENCE - BAD!'
        WHEN qual LIKE '%is_admin%' THEN 'Uses is_admin function - GOOD!'
        ELSE 'Other'
    END as policy_type,
    qual as using_clause
FROM pg_policies
WHERE tablename = 'user_profiles' AND schemaname = 'public'
ORDER BY policyname;

-- 3. Check if RLS is enabled on user_profiles
SELECT 
    'RLS status' as check_type,
    schemaname, 
    tablename, 
    rowsecurity as rls_enabled
FROM pg_tables 
WHERE tablename = 'user_profiles' AND schemaname = 'public';
