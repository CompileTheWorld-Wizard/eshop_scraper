-- Migration: Ensure credit_usage_tracking table exists
-- Purpose: Create credit_usage_tracking table if it doesn't exist
-- This table is required for tracking daily/monthly usage limits
-- Date: 2024
-- This migration is idempotent - safe to run multiple times

-- Credit usage tracking (for analytics and limits)
CREATE TABLE IF NOT EXISTS public.credit_usage_tracking (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    action_id UUID REFERENCES public.credit_actions(id) NOT NULL,
    usage_date DATE NOT NULL DEFAULT CURRENT_DATE,
    usage_month TEXT NOT NULL DEFAULT TO_CHAR(CURRENT_DATE, 'YYYY-MM'),
    usage_count INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, action_id, usage_date)
);

-- Indexes for credit_usage_tracking
CREATE INDEX IF NOT EXISTS idx_credit_usage_tracking_user_id ON public.credit_usage_tracking(user_id);
CREATE INDEX IF NOT EXISTS idx_credit_usage_tracking_action_id ON public.credit_usage_tracking(action_id);
CREATE INDEX IF NOT EXISTS idx_credit_usage_tracking_date ON public.credit_usage_tracking(usage_date);
CREATE INDEX IF NOT EXISTS idx_credit_usage_tracking_month ON public.credit_usage_tracking(usage_month);

-- Trigger for updated_at column
DROP TRIGGER IF EXISTS update_credit_usage_tracking_updated_at ON public.credit_usage_tracking;
CREATE TRIGGER update_credit_usage_tracking_updated_at 
    BEFORE UPDATE ON public.credit_usage_tracking 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Add comment
COMMENT ON TABLE public.credit_usage_tracking IS 'Tracks credit usage per action for daily/monthly limits and analytics';

