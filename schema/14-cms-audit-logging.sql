-- CMS Audit Logging System
-- Tracks all changes to CMS content for security and compliance

-- CMS Audit Log table
CREATE TABLE IF NOT EXISTS public.cms_audit_log (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    action TEXT NOT NULL, -- 'create', 'update', 'delete', 'publish', 'unpublish'
    entity_type TEXT NOT NULL, -- 'page', 'section', 'content_block', 'asset', 'legal_document'
    entity_id UUID NOT NULL,
    changes JSONB DEFAULT '{}', -- What changed (before/after)
    metadata JSONB DEFAULT '{}', -- Additional context
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for audit log
CREATE INDEX IF NOT EXISTS idx_cms_audit_log_user_id ON public.cms_audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_cms_audit_log_entity ON public.cms_audit_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_cms_audit_log_action ON public.cms_audit_log(action);
CREATE INDEX IF NOT EXISTS idx_cms_audit_log_created_at ON public.cms_audit_log(created_at DESC);

-- Function to log CMS changes
CREATE OR REPLACE FUNCTION log_cms_change(
    p_user_id UUID,
    p_action TEXT,
    p_entity_type TEXT,
    p_entity_id UUID,
    p_changes JSONB DEFAULT '{}'::jsonb,
    p_metadata JSONB DEFAULT '{}'::jsonb,
    p_ip_address INET DEFAULT NULL,
    p_user_agent TEXT DEFAULT NULL
)
RETURNS UUID AS $$
DECLARE
    log_id UUID;
BEGIN
    INSERT INTO public.cms_audit_log (
        user_id,
        action,
        entity_type,
        entity_id,
        changes,
        metadata,
        ip_address,
        user_agent
    ) VALUES (
        p_user_id,
        p_action,
        p_entity_type,
        p_entity_id,
        p_changes,
        p_metadata,
        p_ip_address,
        p_user_agent
    )
    RETURNING id INTO log_id;
    
    RETURN log_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public;

-- RLS for audit log (admins can read, no one can write directly - only via function)
ALTER TABLE public.cms_audit_log ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Admins can read cms_audit_log" ON public.cms_audit_log;

CREATE POLICY "Admins can read cms_audit_log" ON public.cms_audit_log
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM public.user_profiles
            WHERE user_profiles.user_id = auth.uid()
            AND user_profiles.role = 'admin'
        )
    );

-- Comments
COMMENT ON TABLE public.cms_audit_log IS 'Audit log for all CMS content changes';
COMMENT ON FUNCTION log_cms_change IS 'Logs a CMS content change to the audit log';

