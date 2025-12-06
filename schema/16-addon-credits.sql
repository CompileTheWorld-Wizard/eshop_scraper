-- Migration: Add add-on credits tracking with expiration
-- Purpose: Implement Requirement 10 - Add-on credits expire at the end of current billing cycle
-- This migration creates a table to track individual add-on credit purchases with expiration dates

-- Table to track individual add-on credit purchases
CREATE TABLE IF NOT EXISTS public.addon_credits (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    credits_amount INTEGER NOT NULL,
    credits_remaining INTEGER NOT NULL, -- Track remaining credits from this purchase
    expires_at TIMESTAMPTZ NOT NULL, -- Set to current_period_end when purchased
    purchase_transaction_id UUID REFERENCES public.credit_transactions(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE public.addon_credits IS 'Tracks individual add-on credit purchases. Credits expire at the end of the current billing cycle and do NOT roll over.';
COMMENT ON COLUMN public.addon_credits.expires_at IS 'Expiration date set to user''s current_period_end at time of purchase. Credits expire at this date.';
COMMENT ON COLUMN public.addon_credits.credits_remaining IS 'Remaining credits from this specific add-on purchase. Used for FIFO expiration tracking.';

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_addon_credits_user_id ON public.addon_credits(user_id);
CREATE INDEX IF NOT EXISTS idx_addon_credits_expires_at ON public.addon_credits(expires_at);
CREATE INDEX IF NOT EXISTS idx_addon_credits_user_expires ON public.addon_credits(user_id, expires_at) 
WHERE credits_remaining > 0;

-- Trigger for updated_at column
CREATE TRIGGER update_addon_credits_updated_at 
    BEFORE UPDATE ON public.addon_credits 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

