-- Migration: Create Error & Stability System Tables
-- Description: Creates tables for error logging, health monitoring, retry tracking, and alert management
-- This migration is idempotent - safe to run multiple times
-- Date: 2024

-- ============================================================================
-- ERROR LOGS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.error_logs (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    error_type VARCHAR(50) NOT NULL, -- 'api', 'database', 'external_api', 'auth', 'validation', 'system'
    severity VARCHAR(20) NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    error_code VARCHAR(50),
    message TEXT NOT NULL,
    stack_trace TEXT,
    context JSONB DEFAULT '{}', -- Additional context data
    user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    endpoint VARCHAR(255),
    method VARCHAR(10),
    request_id VARCHAR(100),
    ip_address VARCHAR(45),
    user_agent TEXT,
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMPTZ,
    resolved_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for error_logs
CREATE INDEX IF NOT EXISTS idx_error_logs_severity ON public.error_logs(severity);
CREATE INDEX IF NOT EXISTS idx_error_logs_error_type ON public.error_logs(error_type);
CREATE INDEX IF NOT EXISTS idx_error_logs_created_at ON public.error_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_error_logs_user_id ON public.error_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_error_logs_resolved ON public.error_logs(resolved);
CREATE INDEX IF NOT EXISTS idx_error_logs_request_id ON public.error_logs(request_id) WHERE request_id IS NOT NULL;

-- Trigger for updated_at column
DROP TRIGGER IF EXISTS update_error_logs_updated_at ON public.error_logs;
CREATE TRIGGER update_error_logs_updated_at 
    BEFORE UPDATE ON public.error_logs 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Comments
COMMENT ON TABLE public.error_logs IS 'Centralized error logging table for tracking all application errors';
COMMENT ON COLUMN public.error_logs.error_type IS 'Type of error: api, database, external_api, auth, validation, system';
COMMENT ON COLUMN public.error_logs.severity IS 'Error severity: low, medium, high, critical';
COMMENT ON COLUMN public.error_logs.context IS 'Additional context data (request body, headers, etc.) - sanitized';

-- ============================================================================
-- HEALTH CHECKS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.health_checks (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    service_name VARCHAR(100) NOT NULL, -- 'database', 'stripe', 'scraping_api', 'runwayml', 'tiktok', 'youtube'
    status VARCHAR(20) NOT NULL CHECK (status IN ('healthy', 'degraded', 'down', 'unknown')),
    response_time_ms INTEGER,
    error_message TEXT,
    metadata JSONB DEFAULT '{}',
    checked_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for health_checks
CREATE INDEX IF NOT EXISTS idx_health_checks_service ON public.health_checks(service_name, checked_at DESC);
CREATE INDEX IF NOT EXISTS idx_health_checks_status ON public.health_checks(status);
CREATE INDEX IF NOT EXISTS idx_health_checks_checked_at ON public.health_checks(checked_at DESC);

-- Comments
COMMENT ON TABLE public.health_checks IS 'Health check results for all monitored services';
COMMENT ON COLUMN public.health_checks.service_name IS 'Name of the service being monitored';
COMMENT ON COLUMN public.health_checks.status IS 'Service status: healthy, degraded, down, unknown';

-- ============================================================================
-- RETRY ATTEMPTS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.retry_attempts (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    operation_type VARCHAR(50) NOT NULL, -- 'api_call', 'upload', 'external_api'
    operation_id VARCHAR(255), -- Task ID, request ID, etc.
    attempt_number INTEGER NOT NULL,
    success BOOLEAN NOT NULL,
    error_message TEXT,
    duration_ms INTEGER,
    retry_strategy VARCHAR(50), -- 'exponential', 'linear', 'fixed'
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for retry_attempts
CREATE INDEX IF NOT EXISTS idx_retry_attempts_operation ON public.retry_attempts(operation_type, operation_id);
CREATE INDEX IF NOT EXISTS idx_retry_attempts_created_at ON public.retry_attempts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_retry_attempts_success ON public.retry_attempts(success);

-- Comments
COMMENT ON TABLE public.retry_attempts IS 'Tracks retry attempts for operations to analyze retry patterns and success rates';
COMMENT ON COLUMN public.retry_attempts.operation_type IS 'Type of operation being retried';
COMMENT ON COLUMN public.retry_attempts.operation_id IS 'Unique identifier for the operation (task_id, request_id, etc.)';

-- ============================================================================
-- ALERT RULES TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.alert_rules (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    condition_type VARCHAR(50) NOT NULL CHECK (condition_type IN ('error_rate', 'error_count', 'health_status', 'response_time')),
    threshold_value NUMERIC NOT NULL,
    time_window_minutes INTEGER NOT NULL,
    severity VARCHAR(20) NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    enabled BOOLEAN DEFAULT TRUE,
    notification_channels JSONB DEFAULT '[]', -- ['email', 'slack', 'webhook']
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for alert_rules
CREATE INDEX IF NOT EXISTS idx_alert_rules_enabled ON public.alert_rules(enabled);
CREATE INDEX IF NOT EXISTS idx_alert_rules_condition_type ON public.alert_rules(condition_type);

-- Trigger for updated_at column
DROP TRIGGER IF EXISTS update_alert_rules_updated_at ON public.alert_rules;
CREATE TRIGGER update_alert_rules_updated_at 
    BEFORE UPDATE ON public.alert_rules 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Comments
COMMENT ON TABLE public.alert_rules IS 'Alert rules that define when alerts should be triggered';
COMMENT ON COLUMN public.alert_rules.condition_type IS 'Type of condition: error_rate, error_count, health_status, response_time';
COMMENT ON COLUMN public.alert_rules.notification_channels IS 'Array of notification channels: email, slack, webhook';

-- ============================================================================
-- ALERTS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.alerts (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    rule_id UUID REFERENCES public.alert_rules(id) ON DELETE SET NULL,
    severity VARCHAR(20) NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'acknowledged', 'resolved')),
    sent_at TIMESTAMPTZ,
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    resolved_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for alerts
CREATE INDEX IF NOT EXISTS idx_alerts_status ON public.alerts(status);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON public.alerts(severity);
CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON public.alerts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_rule_id ON public.alerts(rule_id);

-- Comments
COMMENT ON TABLE public.alerts IS 'Generated alerts based on alert rules';
COMMENT ON COLUMN public.alerts.status IS 'Alert status: pending, sent, acknowledged, resolved';

-- This migration is idempotent - safe to run multiple times
-- All CREATE TABLE IF NOT EXISTS and CREATE INDEX IF NOT EXISTS statements ensure no errors on re-run

