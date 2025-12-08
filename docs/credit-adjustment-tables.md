# Credit Adjustment - Related Tables

## Overview
When adjusting (adding) user credits, the system interacts with specific tables. This document outlines which tables are involved and how they relate to credit actions.

---

## Tables Involved in Credit Adjustment

### 1. **user_credits** (Primary Table)
**Purpose:** Stores the user's credit balance

**Always Modified:** ✅ Yes (always updated/inserted)

**Operations:**
- **UPDATE** - If user_credits record exists:
  ```sql
  UPDATE public.user_credits
  SET 
      total_credits = total_credits + amount,
      credits_remaining = credits_remaining + amount,
      updated_at = NOW()
  WHERE user_id = user_uuid;
  ```

- **INSERT** - If user_credits record doesn't exist:
  ```sql
  INSERT INTO public.user_credits (user_id, total_credits, credits_remaining)
  VALUES (user_uuid, amount, amount);
  ```

**Columns Modified:**
- `total_credits` - Incremented by amount
- `credits_remaining` - Incremented by amount
- `updated_at` - Set to current timestamp

**Relationship:** Direct - No foreign key to credit_actions

---

### 2. **credit_actions** (Lookup Table)
**Purpose:** Defines available credit actions and their metadata

**Conditionally Queried:** ⚠️ Only if `reference_type` is provided AND not 'admin'

**Operations:**
- **SELECT** - To get action_id for transaction recording:
  ```sql
  SELECT id FROM public.credit_actions 
  WHERE action_name = reference_type 
  LIMIT 1;
  ```

**When Used:**
- ✅ When `reference_type` is provided (e.g., 'purchase', 'refund', 'bonus')
- ✅ When `reference_type != 'admin'`
- ❌ When `reference_type` is NULL
- ❌ When `reference_type = 'admin'` (admin adjustments skip transaction recording)

**Purpose:**
- Maps `reference_type` (action name string) to `action_id` (UUID)
- Used to link the credit addition to a specific action type
- Required for creating a transaction record in `credit_transactions`

**Relationship:** 
- `credit_transactions.action_id` → `credit_actions.id` (Foreign Key)

---

### 3. **credit_transactions** (Audit Trail)
**Purpose:** Records all credit transactions for audit and history

**Conditionally Inserted:** ⚠️ Only if `reference_type` is provided AND not 'admin'

**Operations:**
- **INSERT** - Records the credit addition transaction:
  ```sql
  INSERT INTO public.credit_transactions (
      user_id, 
      action_id, 
      transaction_type, 
      credits_amount, 
      reference_id, 
      reference_type, 
      description,
      metadata
  ) 
  SELECT 
      user_uuid,
      (SELECT id FROM public.credit_actions WHERE action_name = reference_type LIMIT 1),
      'addition',
      amount,
      reference_uuid,
      reference_type,
      description,
      metadata
  WHERE EXISTS (SELECT 1 FROM public.credit_actions WHERE action_name = reference_type);
  ```

**When Used:**
- ✅ When `reference_type` is provided
- ✅ When `reference_type != 'admin'`
- ✅ When matching `credit_action` exists for `reference_type`
- ❌ When `reference_type` is NULL
- ❌ When `reference_type = 'admin'` (admin adjustments skip transaction recording)

**Transaction Record Contains:**
- `user_id` - Who received the credits
- `action_id` - What action triggered this (from credit_actions)
- `transaction_type` - Always 'addition' for credit adjustments
- `credits_amount` - Amount of credits added
- `reference_id` - Related entity ID (e.g., purchase_id, refund_id)
- `reference_type` - Type of reference (e.g., 'purchase', 'refund')
- `description` - Human-readable description
- `metadata` - Additional JSON data

**Relationship:**
- `credit_transactions.action_id` → `credit_actions.id` (Foreign Key, NOT NULL)
- `credit_transactions.user_id` → `auth.users.id` (Foreign Key)

---

## Decision Flow: When to Record Transaction

```
┌─────────────────────────────────────┐
│ add_user_credits() called           │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│ 1. Update user_credits               │
│    (ALWAYS)                          │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│ reference_type provided?            │
│ AND reference_type != 'admin'?      │
└──────────────┬──────────────────────┘
               │
        ┌──────┴──────┐
        │             │
       YES           NO
        │             │
        ▼             ▼
┌──────────────┐  ┌──────────────┐
│ Query        │  │ Skip         │
│ credit_actions│  │ transaction  │
│ for action_id│  │ recording    │
└──────┬───────┘  └──────────────┘
       │
       ▼
┌──────────────┐
│ Action found?│
└──────┬───────┘
       │
  ┌────┴────┐
  │         │
 YES       NO
  │         │
  ▼         ▼
┌──────┐  ┌──────┐
│Insert│  │Skip  │
│trans-│  │trans-│
│action│  │action│
└──────┘  └──────┘
```

---

## Example Scenarios

### Scenario 1: Admin Adjustment (No Transaction Record)
```python
add_user_credits(
    user_uuid="...",
    amount=100,
    reference_type="admin",  # Special case
    description="Admin credit adjustment"
)
```

**Tables Modified:**
1. ✅ `user_credits` - Credits added
2. ❌ `credit_actions` - NOT queried
3. ❌ `credit_transactions` - NOT inserted

**Reason:** Admin adjustments skip transaction recording to avoid requiring action_id.

---

### Scenario 2: Purchase Credits (With Transaction Record)
```python
add_user_credits(
    user_uuid="...",
    amount=100,
    reference_type="purchase",  # Must exist in credit_actions
    reference_id="purchase_123",
    description="Credit package purchase"
)
```

**Tables Modified:**
1. ✅ `user_credits` - Credits added
2. ✅ `credit_actions` - Queried to get action_id for 'purchase'
3. ✅ `credit_transactions` - Transaction record inserted

**Prerequisites:**
- `credit_actions` table must have a row with `action_name = 'purchase'`

---

### Scenario 3: No Reference Type (No Transaction Record)
```python
add_user_credits(
    user_uuid="...",
    amount=100,
    reference_type=None,  # NULL
    description="Credit adjustment"
)
```

**Tables Modified:**
1. ✅ `user_credits` - Credits added
2. ❌ `credit_actions` - NOT queried
3. ❌ `credit_transactions` - NOT inserted

**Reason:** No reference_type means no action to link to.

---

### Scenario 4: Refund Credits (With Transaction Record)
```python
add_user_credits(
    user_uuid="...",
    amount=50,
    reference_type="refund",  # Must exist in credit_actions
    reference_id="order_456",
    description="Refund for canceled order"
)
```

**Tables Modified:**
1. ✅ `user_credits` - Credits added
2. ✅ `credit_actions` - Queried to get action_id for 'refund'
3. ✅ `credit_transactions` - Transaction record inserted

---

## Table Relationships Diagram

```
┌─────────────────────┐
│   credit_actions    │
│  (Lookup Table)     │
│                     │
│ - id (PK)           │
│ - action_name (UK)  │
│ - base_credit_cost  │
└──────────┬──────────┘
           │
           │ (1:N)
           │ action_id
           │
           ▼
┌─────────────────────┐
│credit_transactions  │
│  (Audit Trail)      │
│                     │
│ - id (PK)           │
│ - user_id (FK)      │
│ - action_id (FK)───┐│
│ - transaction_type ││
│ - credits_amount   ││
└────────────────────┘│
                      │
                      │
┌──────────────────────┐
│    user_credits      │
│  (Balance Table)     │
│                      │
│ - id (PK)            │
│ - user_id (FK, UK)   │
│ - total_credits      │
│ - credits_remaining  │
└──────────────────────┘
```

---

## Summary Table

| Table | Always Used | Conditionally Used | Purpose |
|-------|-------------|-------------------|---------|
| **user_credits** | ✅ Yes | ❌ No | Stores user's credit balance |
| **credit_actions** | ❌ No | ✅ Yes | Maps action names to IDs (only if recording transaction) |
| **credit_transactions** | ❌ No | ✅ Yes | Audit trail (only if reference_type provided and not 'admin') |

---

## Key Points

1. **user_credits is always modified** - Every credit adjustment updates this table
2. **credit_actions is conditionally queried** - Only when recording a transaction
3. **credit_transactions is conditionally inserted** - Only when:
   - `reference_type` is provided
   - `reference_type != 'admin'`
   - Matching `credit_action` exists
4. **Admin adjustments skip transaction recording** - To avoid requiring action_id for admin operations
5. **Transaction recording requires valid action** - The `reference_type` must exist in `credit_actions` table

---

## Function Signatures

### add_user_credits (Version 1 - With reference_type)
```sql
CREATE OR REPLACE FUNCTION add_user_credits(
    user_uuid UUID,
    amount INTEGER,
    description TEXT DEFAULT NULL,
    reference_id TEXT DEFAULT NULL,
    reference_type TEXT DEFAULT NULL,  -- Used to lookup credit_actions
    metadata JSONB DEFAULT '{}'::JSONB
)
RETURNS TABLE(
    credits_total INTEGER,
    credits_remaining INTEGER
)
```

### add_user_credits (Version 2 - With action_name)
```sql
CREATE OR REPLACE FUNCTION add_user_credits(
    user_uuid UUID,
    action_name TEXT,  -- Direct action name
    credits_amount INTEGER,
    reference_id UUID DEFAULT NULL,
    reference_type TEXT DEFAULT NULL,
    description TEXT DEFAULT NULL
)
RETURNS BOOLEAN
```

---

## Notes

- **No usage tracking for additions** - Unlike deductions, credit additions don't update `credit_usage_tracking`
- **Admin adjustments are special** - They bypass transaction recording to simplify admin operations
- **Action validation** - If `reference_type` doesn't exist in `credit_actions`, transaction is not recorded
- **Idempotency** - Multiple calls will add credits multiple times (not idempotent)

