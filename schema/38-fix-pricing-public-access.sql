-- Migration: Fix pricing plans public access for landing page
-- Issue: Anonymous users cannot see subscription plans on landing page
-- Solution: Allow public read access to subscription_plans table

-- Drop the existing authenticated-only policy
DROP POLICY IF EXISTS "Authenticated users can view subscription plans" ON public.subscription_plans;

-- Create new policy that allows EVERYONE (including anonymous users) to view subscription plans
-- Pricing information should be public so visitors can see plans before signing up
CREATE POLICY "Anyone can view subscription plans" 
ON public.subscription_plans
FOR SELECT
USING (true);

-- Keep admin management policy unchanged
-- (Admins still need authentication to modify plans)

-- Grant SELECT permission to anonymous role
GRANT SELECT ON public.subscription_plans TO anon;

-- Grant SELECT permission to authenticated role (keep existing access)
GRANT SELECT ON public.subscription_plans TO authenticated;

-- Verify the policy is active
COMMENT ON POLICY "Anyone can view subscription plans" ON public.subscription_plans 
IS 'Allows public read access to subscription plans for landing page and pricing page. No authentication required for viewing pricing information.';
