-- Migration: Add RLS policies for credit_adjustments table
-- This allows admins to insert/manage credit adjustments

-- Enable RLS on credit_adjustments table
ALTER TABLE public.credit_adjustments ENABLE ROW LEVEL SECURITY;

-- Drop existing policies if they exist (for idempotency)
DROP POLICY IF EXISTS "Admins can manage credit_adjustments" ON public.credit_adjustments;
DROP POLICY IF EXISTS "Users can view their own credit_adjustments" ON public.credit_adjustments;

-- Allow admins to do everything on credit_adjustments
CREATE POLICY "Admins can manage credit_adjustments" ON public.credit_adjustments
FOR ALL
USING (
    EXISTS (
        SELECT 1 FROM public.user_profiles
        WHERE user_profiles.user_id = auth.uid()
        AND user_profiles.role = 'admin'
    )
)
WITH CHECK (
    EXISTS (
        SELECT 1 FROM public.user_profiles
        WHERE user_profiles.user_id = auth.uid()
        AND user_profiles.role = 'admin'
    )
);

-- Allow users to view their own credit adjustments (for transparency)
CREATE POLICY "Users can view their own credit_adjustments" ON public.credit_adjustments
FOR SELECT
USING (user_id = auth.uid());

-- Add comment
COMMENT ON TABLE public.credit_adjustments IS 'Admin credit adjustments with audit trail. RLS enabled: admins can manage, users can view their own.';

