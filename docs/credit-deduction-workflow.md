# Credit Deduction Workflow Documentation

## Overview
This document describes the complete workflow for deducting credits from a user's account when they perform an action (e.g., scraping a product).

---

## Workflow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Application Code (Python)                                     │
│    deduct_credits(user_id, action_name, ...)                    │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. CreditManager.deduct_credits()                               │
│    - Validates Supabase connection                              │
│    - Calls database RPC function                                │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. Database Function: deduct_user_credits()                     │
│    - Checks if user can perform action                          │
│    - Validates action exists                                    │
│    - Deducts credits                                            │
│    - Records transaction                                        │
│    - Updates usage tracking                                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Step-by-Step Workflow

### Step 1: Application Code Call

**Location:** `app/services/scraping_service.py` (or other service files)

**Function Call:**
```python
from app.utils.credit_utils import deduct_credits

success = deduct_credits(
    user_id=user_id,              # UUID string
    action_name="scraping",       # Action identifier
    reference_id=product_id,      # Optional: Related entity ID
    reference_type="product",     # Optional: Type of reference
    description=f"Product scraping completed for {url}"  # Optional: Description
)
```

**Example Usage:**
```python
# After successful scraping
success = deduct_credits(
    user_id="afafdf9f-7c2e-415c-a84f-58d018b30e53",
    action_name="scraping",
    reference_id="40357084-fb79-439d-b7c0-8dab141bd50e",
    reference_type="product",
    description="Product scraping completed for https://www.amazon.com/..."
)
```

---

### Step 2: Python CreditManager Layer

**Location:** `app/utils/credit_utils.py`

**Function:** `CreditManager.deduct_credits()`

#### Parameters:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `user_id` | `str` | Yes | The user's UUID as a string |
| `action_name` | `str` | Yes | The action being performed (e.g., 'scraping', 'generate_scenario') |
| `reference_id` | `Optional[str]` | No | Optional reference ID for the action (e.g., product_id, short_id) |
| `reference_type` | `Optional[str]` | No | Optional reference type (e.g., 'product', 'short', 'purchase') |
| `description` | `Optional[str]` | No | Optional description of the action |

#### Return Value:
- **Type:** `bool`
- **Returns:**
  - `True` - Credits were deducted successfully
  - `False` - Failed to deduct credits (connection error, database error, etc.)

#### Implementation Details:
```python
def deduct_credits(
    self, 
    user_id: str, 
    action_name: str, 
    reference_id: Optional[str] = None, 
    reference_type: Optional[str] = None, 
    description: Optional[str] = None
) -> bool:
    """
    Deduct credits from user for performing an action.
    
    Returns:
        True if credits were deducted successfully, False otherwise
    """
    # 1. Check Supabase connection
    # 2. Call database RPC function: deduct_user_credits
    # 3. Handle response and return boolean
```

**RPC Call:**
```python
result = self.supabase.client.rpc(
    'deduct_user_credits',
    {
        'user_uuid': user_id,           # UUID
        'action_name': action_name,     # TEXT
        'reference_id': reference_id,   # UUID (nullable)
        'reference_type': reference_type, # TEXT (nullable)
        'description': description       # TEXT (nullable)
    }
).execute()
```

---

### Step 3: Database Function Execution

**Location:** `schema/22-remove-redundant-credit-transactions-columns.sql`

**Function:** `deduct_user_credits()`

#### Function Signature:
```sql
CREATE OR REPLACE FUNCTION deduct_user_credits(
    user_uuid UUID,
    action_name TEXT,
    reference_id UUID DEFAULT NULL,
    reference_type TEXT DEFAULT NULL,
    description TEXT DEFAULT NULL
)
RETURNS BOOLEAN
```

#### Parameters:
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `user_uuid` | `UUID` | Yes | - | The user's UUID |
| `action_name` | `TEXT` | Yes | - | The action name (e.g., 'scraping') |
| `reference_id` | `UUID` | No | `NULL` | Reference ID for the action |
| `reference_type` | `TEXT` | No | `NULL` | Type of reference |
| `description` | `TEXT` | No | `NULL` | Description of the action |

#### Return Value:
- **Type:** `BOOLEAN`
- **Returns:**
  - `TRUE` - Credits deducted successfully
  - **Exception** - If any validation fails (raises exception with error message)

---

## Detailed Database Function Workflow

### 3.1 Check if User Can Perform Action

**Calls:** `can_perform_action(user_uuid, action_name)`

**Returns:**
```sql
TABLE(
    can_perform BOOLEAN,      -- Whether user can perform the action
    reason TEXT,               -- Reason if cannot perform
    current_credits INTEGER,   -- User's current credit balance
    required_credits INTEGER,  -- Credits needed for this action
    monthly_limit INTEGER,     -- Monthly limit (NULL if unlimited)
    daily_limit INTEGER,       -- Daily limit (NULL if unlimited)
    monthly_used INTEGER,      -- Credits used this month
    daily_used INTEGER         -- Credits used today
)
```

**Validation Checks:**
1. ✅ User has sufficient credits
2. ✅ Subscription is active (not canceled past period end)
3. ✅ Monthly limit not exceeded (if plan has limit)
4. ✅ Daily limit not exceeded (if plan has limit)
5. ✅ Trial user preview check (for preview_render action)

**If validation fails:**
```sql
RAISE EXCEPTION 'Cannot perform action: %', reason_val;
-- Example: "Cannot perform action: Insufficient credits"
```

---

### 3.2 Get Action Details

**Query:**
```sql
SELECT ca.id, ca.base_credit_cost 
INTO action_id_val, credit_cost_val
FROM public.credit_actions ca
WHERE ca.action_name = deduct_user_credits.action_name;
```

**Returns:**
- `action_id_val` (UUID) - The action's ID
- `credit_cost_val` (INTEGER) - Base credit cost for this action

**If action not found:**
```sql
RAISE EXCEPTION 'Action not found: %', deduct_user_credits.action_name;
```

---

### 3.3 Special Handling: Preview Render for Trial Users

**If action is 'preview_render' and user is trial:**
```sql
UPDATE public.user_profiles
SET 
    trial_preview_used = true,
    trial_preview_used_at = NOW(),
    updated_at = NOW()
WHERE user_id = user_uuid
  AND is_trial_user = true
  AND trial_preview_used = false;
```

---

### 3.4 Get User's Active Plan

**Query:**
```sql
SELECT us.plan_id, us.current_period_start
INTO user_plan_id, current_period_start
FROM public.user_subscriptions us
WHERE us.user_id = user_uuid
  AND us.status = 'active'
ORDER BY us.created_at DESC
LIMIT 1;
```

**Returns:**
- `user_plan_id` (UUID) - User's active plan ID (NULL if no active subscription)
- `current_period_start` (TIMESTAMPTZ) - Current billing period start date

---

### 3.5 Deduct Credits from User Account

**Update existing user_credits record:**
```sql
UPDATE public.user_credits
SET 
    credits_remaining = credits_remaining - credit_cost_val,
    cycle_used_credits = CASE
        WHEN current_period_start IS NULL THEN cycle_used_credits
        WHEN cycle_start_at IS NULL OR cycle_start_at <> current_period_start
            THEN credit_cost_val
        ELSE cycle_used_credits + credit_cost_val
    END,
    cycle_start_at = CASE
        WHEN current_period_start IS NULL THEN cycle_start_at
        ELSE current_period_start
    END,
    updated_at = NOW()
WHERE user_id = user_uuid;
```

**If user_credits record doesn't exist:**
```sql
INSERT INTO public.user_credits (
    user_id,
    total_credits,
    credits_remaining,
    cycle_used_credits,
    cycle_start_at
)
VALUES (
    user_uuid,
    0,
    0 - credit_cost_val,  -- Start with 0, deduct credit_cost_val
    CASE WHEN current_period_start IS NULL THEN 0 ELSE credit_cost_val END,
    current_period_start
);
```

**What gets updated:**
- `credits_remaining` - Decremented by `credit_cost_val`
- `cycle_used_credits` - Tracks credits used in current billing cycle
- `cycle_start_at` - Set to current billing period start

---

### 3.6 Record Transaction

**Insert into credit_transactions:**
```sql
INSERT INTO public.credit_transactions (
    user_id, 
    action_id, 
    transaction_type, 
    credits_amount, 
    reference_id, 
    reference_type, 
    description
) VALUES (
    user_uuid, 
    action_id_val, 
    'deduction', 
    credit_cost_val,
    reference_id, 
    reference_type, 
    description
);
```

**Transaction Record Contains:**
- `user_id` - Who performed the action
- `action_id` - What action was performed (can JOIN to get action name)
- `transaction_type` - 'deduction'
- `credits_amount` - How many credits were deducted
- `reference_id` - Related entity ID (e.g., product_id)
- `reference_type` - Type of reference (e.g., 'product')
- `description` - Human-readable description
- `created_at` - Timestamp (auto-generated)

---

### 3.7 Update Usage Tracking

**Insert/Update credit_usage_tracking:**
```sql
INSERT INTO public.credit_usage_tracking (
    user_id, 
    action_id, 
    usage_date, 
    usage_month, 
    usage_count
) VALUES (
    user_uuid, 
    action_id_val, 
    CURRENT_DATE, 
    TO_CHAR(CURRENT_DATE, 'YYYY-MM'), 
    1
)
ON CONFLICT (user_id, action_id, usage_date)
DO UPDATE SET usage_count = credit_usage_tracking.usage_count + 1;
```

**Purpose:**
- Tracks daily usage for limit enforcement
- Tracks monthly usage for limit enforcement
- Used by `can_perform_action()` to check limits

**Error Handling:**
- If table doesn't exist, silently skip (no-op)
- Any other error, silently skip (no-op)

---

### 3.8 Return Success

**Returns:**
```sql
RETURN TRUE;
```

---

## Error Handling

### Python Layer Errors

**Connection Error:**
```python
if not self.supabase.is_connected():
    logger.error("Supabase not connected")
    return False
```

**Database Error:**
```python
except Exception as e:
    logger.error(f"Error deducting credits for user {user_id}, action {action_name}: {e}")
    return False
```

### Database Layer Errors

**Cannot Perform Action:**
```sql
RAISE EXCEPTION 'Cannot perform action: %', reason_val;
-- Examples:
-- "Cannot perform action: Insufficient credits"
-- "Cannot perform action: Daily limit exceeded"
-- "Cannot perform action: Subscription canceled"
```

**Action Not Found:**
```sql
RAISE EXCEPTION 'Action not found: %', deduct_user_credits.action_name;
-- Example: "Action not found: scraping"
```

---

## Return Value Flow

```
Database Function
    ↓
    Returns: TRUE (BOOLEAN)
    ↓
Python RPC Call
    ↓
    result.data[0] = TRUE
    ↓
CreditManager.deduct_credits()
    ↓
    Returns: True (bool)
    ↓
Application Code
    ↓
    success = True/False
```

---

## Example Complete Flow

### Input:
```python
deduct_credits(
    user_id="afafdf9f-7c2e-415c-a84f-58d018b30e53",
    action_name="scraping",
    reference_id="40357084-fb79-439d-b7c0-8dab141bd50e",
    reference_type="product",
    description="Product scraping completed for https://www.amazon.com/..."
)
```

### Database Operations:
1. ✅ Check: User has 10 credits, action costs 1 credit → Can perform
2. ✅ Get action: 'scraping' → action_id = '7e7c0d79-7a9d-4f63-a142-a66b6eec3399', cost = 1
3. ✅ Deduct: credits_remaining: 10 → 9
4. ✅ Record: Transaction created in credit_transactions
5. ✅ Track: Usage count incremented for today

### Output:
```python
success = True  # Credits deducted successfully
```

---

## Related Functions

### Check Credits
```python
credit_info = check_user_credits(user_id)
# Returns: {
#     "total_credits": 100,
#     "used_credits": 50,
#     "available_credits": 50,
#     "subscription_status": "active",
#     "plan_name": "pro",
#     "plan_display_name": "Pro Plan"
# }
```

### Check if Can Perform Action
```python
action_check = can_perform_action(user_id, "scraping")
# Returns: {
#     "can_perform": True,
#     "reason": "Can perform action",
#     "current_credits": 10,
#     "required_credits": 1,
#     "monthly_limit": 1000,
#     "daily_limit": 50,
#     "monthly_used": 25,
#     "daily_used": 5
# }
```

---

## Database Tables Involved

1. **user_credits** - Stores user's credit balance
2. **credit_actions** - Defines available actions and their costs
3. **credit_transactions** - Audit trail of all credit transactions
4. **credit_usage_tracking** - Tracks daily/monthly usage for limits
5. **user_subscriptions** - User's subscription information
6. **plan_credit_configs** - Plan-specific credit costs and limits
7. **user_profiles** - User profile (for trial user checks)

---

## Notes

- **Idempotency:** The function is not idempotent - calling it multiple times will deduct credits multiple times
- **Transaction Safety:** All operations happen in a single database transaction
- **Error Recovery:** If any step fails, the entire operation is rolled back
- **Preview Render:** Special handling for trial users - marks preview as used but doesn't deduct credits (cost = 0)

