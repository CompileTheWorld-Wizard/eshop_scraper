-- Migration: Create Credit Adjustments Table
-- Description: Creates the credit_adjustments table for tracking admin credit adjustments
-- This table stores all credit adjustments made by administrators with audit trail and notification tracking
-- Date: 2024

-- Create credit_adjustments table if it doesn't exist
CREATE TABLE IF NOT EXISTS public.credit_adjustments (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    admin_id UUID REFERENCES auth.users(id) ON DELETE SET NULL NOT NULL,
    adjustment_amount INTEGER NOT NULL, -- Can be positive or negative
    reason TEXT, -- Optional reason for adjustment
    description TEXT, -- Optional detailed description
    notification_sent BOOLEAN DEFAULT false,
    notification_sent_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for credit_adjustments table
CREATE INDEX IF NOT EXISTS idx_credit_adjustments_user_id ON public.credit_adjustments(user_id);
CREATE INDEX IF NOT EXISTS idx_credit_adjustments_admin_id ON public.credit_adjustments(admin_id);
CREATE INDEX IF NOT EXISTS idx_credit_adjustments_created_at ON public.credit_adjustments(created_at);
CREATE INDEX IF NOT EXISTS idx_credit_adjustments_notification_sent ON public.credit_adjustments(notification_sent);

-- Add comment to document the table
COMMENT ON TABLE public.credit_adjustments IS 'Admin credit adjustments with audit trail and notification tracking';

-- This migration is idempotent - safe to run multiple times
-- All CREATE TABLE IF NOT EXISTS and CREATE INDEX IF NOT EXISTS statements ensure no errors on re-run

