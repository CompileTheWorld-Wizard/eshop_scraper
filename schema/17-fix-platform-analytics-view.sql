-- Migration: Fix Admin Platform Analytics View
-- Description: Updates admin_platform_analytics view to aggregate user_activities by date
-- and return the structure expected by the frontend (date, active_users, action counts)
-- This migration is idempotent - safe to run multiple times

-- Drop existing view
DROP VIEW IF EXISTS admin_platform_analytics CASCADE;

-- Create new admin platform analytics view
-- Aggregates user_activities by date and action type
CREATE OR REPLACE VIEW admin_platform_analytics AS
WITH daily_activities AS (
    SELECT 
        DATE(ua.created_at) as date,
        COUNT(*) as total_activities,
        COUNT(DISTINCT ua.user_id) as active_users,
        COUNT(CASE WHEN ua.action = 'scraping' THEN 1 END) as scraping_actions,
        COUNT(CASE WHEN ua.action = 'generate_scenario' THEN 1 END) as scenario_generations,
        COUNT(CASE WHEN ua.action = 'generate_scene' THEN 1 END) as scene_generations,
        COUNT(CASE WHEN ua.action = 'generate_audio' THEN 1 END) as audio_generations
    FROM public.user_activities ua
    GROUP BY DATE(ua.created_at)
)
SELECT 
    date,
    COALESCE(total_activities, 0)::bigint as total_activities,
    COALESCE(active_users, 0)::bigint as active_users,
    COALESCE(scraping_actions, 0)::bigint as scraping_actions,
    COALESCE(scenario_generations, 0)::bigint as scenario_generations,
    COALESCE(scene_generations, 0)::bigint as scene_generations,
    COALESCE(audio_generations, 0)::bigint as audio_generations
FROM daily_activities
ORDER BY date DESC;

-- Grant necessary permissions
GRANT SELECT ON admin_platform_analytics TO authenticated;

-- Add comment for documentation
COMMENT ON VIEW admin_platform_analytics IS 'Platform-wide analytics aggregated by date from user_activities. Returns daily counts of activities, active users, and action types (scraping, scenario/scene/audio generations). Requires admin role to access via RLS on underlying tables.';

