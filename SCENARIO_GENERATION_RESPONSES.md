# Scenario Generation API Response Samples

This document shows the response samples that will be sent to the frontend endpoint after implementing retry logic with validation.

## Endpoint
`GET /api/scenario/generate/tasks/{task_id}`

## Response Model
```typescript
interface ScenarioGenerationResponse {
  task_id: string;
  status: TaskStatus; // "pending" | "running" | "completed" | "failed"
  short_id: string;
  user_id: string;
  message: string;
  created_at: string; // ISO datetime
  progress?: number; // 0-100
  current_step?: string;
  error_message?: string;
  scenario?: GeneratedScenario; // Only present when completed
  completed_at?: string; // ISO datetime
}
```

---

## Case 1: ✅ Successful Generation (First Attempt)

**Scenario**: OpenAI returns valid response with correct number of scenes on first attempt.

**Response**:
```json
{
  "task_id": "task_scenario_generation_1234567890",
  "status": "completed",
  "short_id": "short_abc123",
  "user_id": "user_xyz789",
  "message": "Task completed successfully",
  "created_at": "2026-01-24T10:00:00Z",
  "progress": 100.0,
  "current_step": "Finalizing scenario",
  "error_message": null,
  "completed_at": "2026-01-24T10:00:35Z",
  "scenario": {
    "title": "Premium Wireless Headphones Showcase",
    "description": "An engaging video showcasing premium wireless headphones with cinematic effects",
    "detected_demographics": {
      "target_gender": "unisex",
      "age_group": "adults",
      "product_type": "electronics",
      "demographic_context": "Modern tech-savvy audience"
    },
    "scenes": [
      {
        "scene_id": "scene_1",
        "scene_number": 1,
        "description": "Hero shot of the headphones",
        "duration": 8,
        "image_prompt": "Premium wireless headphones centered...",
        "visual_prompt": "Cinematic reveal with soft lighting...",
        "image_reasoning": "Establishing shot to showcase product",
        "generated_image_url": null,
        "text_overlay_prompt": "Premium Sound"
      },
      {
        "scene_id": "scene_2",
        "scene_number": 2,
        "description": "Macro detail of premium materials",
        "duration": 8,
        "image_prompt": "Close-up of leather ear cushions...",
        "visual_prompt": "Smooth camera movement highlighting quality...",
        "image_reasoning": "Show craftsmanship and quality",
        "generated_image_url": null,
        "text_overlay_prompt": "Crafted Quality"
      },
      {
        "scene_id": "scene_3",
        "scene_number": 3,
        "description": "Dynamic showcase with effects",
        "duration": 8,
        "image_prompt": "Product with subtle particle effects...",
        "visual_prompt": "Premium atmosphere with controlled effects...",
        "image_reasoning": "Create emotional connection",
        "generated_image_url": null,
        "text_overlay_prompt": "Experience Excellence"
      }
    ],
    "total_duration": 24,
    "style": "cinematic-storytelling",
    "mood": "luxury",
    "resolution": "1920x1080",
    "environment": "studio",
    "thumbnail_prompt": "Eye-catching thumbnail with headphones...",
    "thumbnail_url": "https://storage.supabase.co/.../thumbnail.png",
    "thumbnail_text_overlay_prompt": "Premium Audio"
  }
}
```

**Log Output**:
```
[INFO] Scenario generation attempt 1/3
[INFO] Sending request to OpenAI...
[INFO] OpenAI response received
[INFO] 🔍 OpenAI returned 3 scenes
[INFO] ✅ Attempt 1 validation passed!
[INFO] Successfully created GeneratedScenario with 3 scenes
```

---

## Case 2: ✅ Successful After Retry

**Scenario**: OpenAI returns invalid response (wrong scene count) on attempts 1-2, but succeeds on attempt 3.

**Response** (same structure as Case 1, but with different timing):
```json
{
  "task_id": "task_scenario_generation_1234567891",
  "status": "completed",
  "short_id": "short_abc124",
  "user_id": "user_xyz789",
  "message": "Task completed successfully",
  "created_at": "2026-01-24T10:05:00Z",
  "progress": 100.0,
  "current_step": "Finalizing scenario",
  "error_message": null,
  "completed_at": "2026-01-24T10:05:52Z",
  "scenario": { /* ... full scenario object ... */ }
}
```

**Log Output**:
```
[INFO] Scenario generation attempt 1/3
[INFO] Sending request to OpenAI...
[INFO] 🔍 OpenAI returned 1 scenes
[WARN] ❌ Attempt 1 validation failed: Expected 3 scenes but got 1 scenes
[INFO] ⏳ Retrying in 2 seconds...

[INFO] Scenario generation attempt 2/3
[INFO] Sending request to OpenAI...
[INFO] 🔍 OpenAI returned 2 scenes
[WARN] ❌ Attempt 2 validation failed: Expected 3 scenes but got 2 scenes
[INFO] ⏳ Retrying in 4 seconds...

[INFO] Scenario generation attempt 3/3
[INFO] Sending request to OpenAI...
[INFO] 🔍 OpenAI returned 3 scenes
[INFO] ✅ Attempt 3 validation passed!
[INFO] Successfully created GeneratedScenario with 3 scenes
```

---

## Case 3: ❌ Failed After All Retries (Wrong Scene Count)

**Scenario**: OpenAI consistently returns wrong number of scenes after 3 attempts.

**Response**:
```json
{
  "task_id": "task_scenario_generation_1234567892",
  "status": "failed",
  "short_id": "short_abc125",
  "user_id": "user_xyz789",
  "message": "Task failed",
  "created_at": "2026-01-24T10:10:00Z",
  "progress": 60.0,
  "current_step": "Generating AI scenario",
  "error_message": "Failed to generate scenario with OpenAI. Scenario validation failed after 3 attempts. Last error: Expected 3 scenes but got 1 scenes",
  "completed_at": "2026-01-24T10:10:18Z",
  "scenario": null
}
```

**Log Output**:
```
[INFO] Scenario generation attempt 1/3
[INFO] 🔍 OpenAI returned 1 scenes
[WARN] ❌ Attempt 1 validation failed: Expected 3 scenes but got 1 scenes
[INFO] ⏳ Retrying in 2 seconds...

[INFO] Scenario generation attempt 2/3
[INFO] 🔍 OpenAI returned 1 scenes
[WARN] ❌ Attempt 2 validation failed: Expected 3 scenes but got 1 scenes
[INFO] ⏳ Retrying in 4 seconds...

[INFO] Scenario generation attempt 3/3
[INFO] 🔍 OpenAI returned 1 scenes
[WARN] ❌ Attempt 3 validation failed: Expected 3 scenes but got 1 scenes
[ERROR] ❌ Failed to generate valid scenario after 3 attempts
```

---

## Case 4: ❌ Failed After All Retries (Missing Required Fields)

**Scenario**: OpenAI returns response without required fields.

**Response**:
```json
{
  "task_id": "task_scenario_generation_1234567893",
  "status": "failed",
  "short_id": "short_abc126",
  "user_id": "user_xyz789",
  "message": "Task failed",
  "created_at": "2026-01-24T10:15:00Z",
  "progress": 60.0,
  "current_step": "Generating AI scenario",
  "error_message": "Failed to generate scenario with OpenAI. Scenario validation failed after 3 attempts. Last error: Missing required fields: scenes, detectedDemographics",
  "completed_at": "2026-01-24T10:15:18Z",
  "scenario": null
}
```

**Log Output**:
```
[INFO] Scenario generation attempt 1/3
[INFO] Generated scenario keys: ['title', 'description', 'thumbnailPrompt']
[WARN] ❌ Attempt 1 validation failed: Missing required fields: scenes, detectedDemographics
[INFO] ⏳ Retrying in 2 seconds...

[INFO] Scenario generation attempt 2/3
[INFO] Generated scenario keys: ['title', 'description', 'scenes']
[WARN] ❌ Attempt 2 validation failed: Missing required fields: detectedDemographics
[INFO] ⏳ Retrying in 4 seconds...

[INFO] Scenario generation attempt 3/3
[INFO] Generated scenario keys: ['title', 'description']
[WARN] ❌ Attempt 3 validation failed: Missing required fields: scenes, detectedDemographics, thumbnailPrompt
[ERROR] ❌ Failed to generate valid scenario after 3 attempts
```

---

## Case 5: ❌ Failed Due to API Error

**Scenario**: OpenAI API returns error (rate limit, network issue, etc.).

**Response**:
```json
{
  "task_id": "task_scenario_generation_1234567894",
  "status": "failed",
  "short_id": "short_abc127",
  "user_id": "user_xyz789",
  "message": "Task failed",
  "created_at": "2026-01-24T10:20:00Z",
  "progress": 60.0,
  "current_step": "Generating AI scenario",
  "error_message": "Failed to generate scenario with OpenAI. Rate limit exceeded. Please try again later.",
  "completed_at": "2026-01-24T10:20:18Z",
  "scenario": null
}
```

**Log Output**:
```
[INFO] Scenario generation attempt 1/3
[ERROR] ❌ Attempt 1 failed: Rate limit exceeded
[INFO] ⏳ Retrying in 2 seconds...

[INFO] Scenario generation attempt 2/3
[ERROR] ❌ Attempt 2 failed: Rate limit exceeded
[INFO] ⏳ Retrying in 4 seconds...

[INFO] Scenario generation attempt 3/3
[ERROR] ❌ Attempt 3 failed: Rate limit exceeded
[ERROR] ❌ Failed to generate scenario after 3 attempts. Last error: Rate limit exceeded
```

---

## Case 6: ❌ Failed Due to Invalid JSON

**Scenario**: OpenAI returns malformed JSON that cannot be parsed.

**Response**:
```json
{
  "task_id": "task_scenario_generation_1234567895",
  "status": "failed",
  "short_id": "short_abc128",
  "user_id": "user_xyz789",
  "message": "Task failed",
  "created_at": "2026-01-24T10:25:00Z",
  "progress": 60.0,
  "current_step": "Generating AI scenario",
  "error_message": "Failed to generate scenario with OpenAI. Invalid JSON in function call arguments: Expecting ',' delimiter: line 15 column 5 (char 234)",
  "completed_at": "2026-01-24T10:25:18Z",
  "scenario": null
}
```

---

## Frontend Integration Tips

### Success Handling
```typescript
if (response.status === "completed" && response.scenario) {
  // Display the scenario to user
  displayScenario(response.scenario);
}
```

### Error Handling
```typescript
if (response.status === "failed") {
  // Show error message to user
  showError(response.error_message || "Failed to generate scenario");
  
  // Parse error for user-friendly message
  if (response.error_message?.includes("validation failed")) {
    showMessage("AI generated invalid content. Please try again.");
  } else if (response.error_message?.includes("Rate limit")) {
    showMessage("Service is busy. Please try again in a few moments.");
  } else {
    showMessage("Something went wrong. Please try again.");
  }
}
```

### Progress Polling
```typescript
// Poll every 2 seconds until completion
const pollStatus = async (taskId: string) => {
  const response = await fetch(`/api/scenario/generate/tasks/${taskId}`);
  const data = await response.json();
  
  updateProgress(data.progress);
  updateCurrentStep(data.current_step);
  
  if (data.status === "completed") {
    handleSuccess(data.scenario);
  } else if (data.status === "failed") {
    handleError(data.error_message);
  } else {
    // Continue polling
    setTimeout(() => pollStatus(taskId), 2000);
  }
};
```

---

## Key Changes Summary

### What Changed
1. **Retry Logic**: 3 attempts with exponential backoff (2s, 4s, 6s)
2. **Strict Validation**: 
   - Validates scene count matches expected (video_length / 8)
   - Validates all required fields present
   - Validates data types (scenes is array, each scene is dict)
3. **Clear Error Messages**: Detailed error messages explain what went wrong
4. **No Silent Failures**: No more accepting 1 scene when 3 expected

### What Didn't Change
- API endpoint URLs remain the same
- Response model structure unchanged
- Task management flow unchanged
- Frontend integration remains compatible
