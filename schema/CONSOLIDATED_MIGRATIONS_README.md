# Consolidated Security Migrations

## Overview

The security fixes have been consolidated into 4 main migration files for easier management.

## Consolidated Migrations

### 27-fix-all-rls-policies.sql
**Replaces:** Migrations 28-44 (17 individual RLS fixes)

**What it does:**
- Enables Row Level Security (RLS) on 14 tables
- Creates access control policies for all tables
- Tables affected:
  - Credit System: `credit_actions`, `credit_packages`, `plan_credit_configs`, `addon_credits`, `credit_usage_tracking`
  - Subscription System: `subscription_plans`
  - Referral System: `user_referrals`, `referral_commissions`
  - Monitoring System: `health_checks`, `error_logs`, `retry_attempts`, `alert_rules`, `alerts`
  - Content System: `categories`

**How to apply:**
```sql
-- Run in Supabase SQL Editor:
-- schema/27-fix-all-rls-policies.sql
```

---

### 28-fix-admin-views-security.sql
**Replaces:** Migrations 27, 32, 33 (admin view security fixes)

**What it does:**
- Creates SECURITY DEFINER helper functions (`get_user_email`, `is_admin_user`)
- Recreates 3 admin views without SECURITY DEFINER property
- Views fixed:
  - `admin_user_overview`
  - `admin_platform_analytics`
  - `admin_subscription_analytics`

**How to apply:**
```sql
-- Run in Supabase SQL Editor:
-- schema/28-fix-admin-views-security.sql
```

---

### 29-fix-all-functions-search-path.sql
**Replaces:** Migrations 45-51 (function search_path fixes)

**What it does:**
- Adds `SET search_path = public` to all functions
- 34 total functions fixed:
  - 21 functions in `schema/06-functions.sql`
  - 1 function in `schema/15-cms-audit-logging.sql`
  - 2 functions in `schema/17-cms-locale-content-fields.sql`
  - 3 functions in `schema/26-brand-kit-system.sql`
  - 1 trigger function in `schema/06-functions.sql`
  - 8 functions created manually in Supabase

**How to apply:**
```bash
# Step 1: Run these complete schema files in Supabase SQL Editor:
1. schema/06-functions.sql
2. schema/15-cms-audit-logging.sql
3. schema/17-cms-locale-content-fields.sql
4. schema/26-brand-kit-system.sql

# Step 2: Run the migration for manually created functions:
5. schema/29-fix-all-functions-search-path.sql
```

---

### 52-fix-pg-net-extension-schema.sql
**Standalone** (not consolidated, only 1 file)

**What it does:**
- Moves `pg_net` extension from `public` schema to `extensions` schema
- Creates `extensions` schema if it doesn't exist

**How to apply:**
```sql
-- Run in Supabase SQL Editor:
-- schema/52-fix-pg-net-extension-schema.sql
```

---

## Full Application Process

### Option 1: Use Consolidated Migrations (Recommended)

```bash
# Run these in Supabase SQL Editor in order:

1. schema/27-fix-all-rls-policies.sql
2. schema/28-fix-admin-views-security.sql
3. schema/06-functions.sql
4. schema/15-cms-audit-logging.sql
5. schema/17-cms-locale-content-fields.sql
6. schema/26-brand-kit-system.sql
7. schema/29-fix-all-functions-search-path.sql
8. schema/52-fix-pg-net-extension-schema.sql
```

### Option 2: Use Individual Migrations (Original)

If you prefer the original individual migrations, you can still use migrations 27-52 as they were originally created.

---

## What Changed

**NO table structures changed**
**NO columns changed**
**NO function logic changed**

**ONLY security controls added:**
- ✅ Row Level Security (RLS) enabled
- ✅ Access control policies created
- ✅ `SET search_path = public` added to functions
- ✅ Admin views recreated with secure pattern
- ✅ Extension moved to dedicated schema

---

## Old Individual Migrations (Can be deleted)

These individual migrations are now replaced by consolidated versions:

**RLS fixes (replaced by 27-fix-all-rls-policies.sql):**
- 28-fix-credit-actions-rls.sql
- 29-fix-credit-packages-rls.sql
- 30-fix-plan-credit-configs-rls.sql
- 31-fix-subscription-plans-rls.sql
- 34-fix-health-checks-rls.sql
- 35-fix-user-referrals-rls.sql
- 36-fix-referral-commissions-rls.sql
- 37-fix-addon-credits-rls.sql
- 38-fix-error-logs-rls.sql
- 39-fix-categories-rls.sql
- 40-fix-retry-attempts-rls.sql
- 41-fix-alert-rules-rls.sql
- 42-fix-alerts-rls.sql
- 43-fix-credit-usage-tracking-rls.sql
- 44-fix-preview-config-backup-rls.sql

**Admin view fixes (replaced by 28-fix-admin-views-security.sql):**
- 27-fix-admin-views-security.sql (old version)
- 32-fix-admin-subscription-analytics-security-definer.sql
- 33-fix-all-admin-views-security-definer.sql

**Function fixes (replaced by 29-fix-all-functions-search-path.sql):**
- 45-fix-update-updated-at-column-search-path.sql
- 46-fix-brand-kit-functions-search-path.sql
- 47-fix-all-main-functions-search-path.sql
- 48-fix-cms-functions-search-path.sql
- 49-verify-all-functions-search-path.sql
- 50-comprehensive-fix-all-functions-search-path.sql
- 51-fix-remaining-8-functions-search-path.sql

---

## Verification

After applying all migrations, verify security in Supabase Dashboard:

1. Go to **Security Advisor**
2. Check that these warnings are resolved:
   - ✅ Exposed Auth Users
   - ✅ Policy Exists RLS Disabled
   - ✅ Security Definer View
   - ✅ Function Search Path Mutable
   - ✅ Extension in Public

---

## Manual Configuration Still Needed

These cannot be fixed via SQL migrations:

1. **Enable Leaked Password Protection**
   - Go to: Dashboard → Authentication → Policies
   - Enable: "Check for leaked passwords"

2. **Upgrade Postgres Version**
   - Go to: Dashboard → Settings → Database
   - Click: "Upgrade Database" button

---

## Questions?

Check `SECURITY_FIXES_VERIFICATION_REPORT.txt` for full details on all changes made.
