# Image Processing API Testing Guide

Quick reference for testing the new image processing endpoints.

## Prerequisites

1. **Start the FastAPI server**:
   ```bash
   python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

2. **Verify server is running**:
   ```bash
   curl http://localhost:8000/api/v1/health
   ```

## Test Endpoints

### 1. Remove Background

**Endpoint**: `POST http://localhost:8000/api/v1/image/remove-background`

#### Using curl:
```bash
curl -X POST "http://localhost:8000/api/v1/image/remove-background" \
  -H "Content-Type: application/json" \
  -d '{
    "image_url": "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=400",
    "user_id": "test-user-123",
    "scene_id": "test-scene-456"
  }'
```

#### Using PowerShell:
```powershell
$body = @{
    image_url = "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=400"
    user_id = "test-user-123"
    scene_id = "test-scene-456"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/api/v1/image/remove-background" `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

#### Expected Response:
```json
{
  "success": true,
  "image_url": "https://hdixvjydwaslnzyrokrd.supabase.co/storage/v1/object/public/generated-content/background-removed/test-scene-456/uuid.png",
  "message": "Background removed successfully",
  "error": null
}
```

---

### 2. Composite Images

**Endpoint**: `POST http://localhost:8000/api/v1/image/composite`

#### Using curl:
```bash
curl -X POST "http://localhost:8000/api/v1/image/composite" \
  -H "Content-Type: application/json" \
  -d '{
    "background_url": "https://images.unsplash.com/photo-1557683316-973673baf926?w=800",
    "overlay_url": "https://hdixvjydwaslnzyrokrd.supabase.co/storage/v1/object/public/generated-content/background-removed/test-scene-456/uuid.png",
    "scene_id": "test-scene-456",
    "user_id": "test-user-123"
  }'
```

#### Using PowerShell:
```powershell
$body = @{
    background_url = "https://images.unsplash.com/photo-1557683316-973673baf926?w=800"
    overlay_url = "https://hdixvjydwaslnzyrokrd.supabase.co/storage/v1/object/public/generated-content/background-removed/test-scene-456/uuid.png"
    scene_id = "test-scene-456"
    user_id = "test-user-123"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/api/v1/image/composite" `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

#### Expected Response:
```json
{
  "success": true,
  "image_url": "https://hdixvjydwaslnzyrokrd.supabase.co/storage/v1/object/public/generated-content/composited-images/test-user-123/test-scene-456/uuid.png",
  "message": "Images composited successfully",
  "error": null
}
```

---

### 3. Replace Background (Complete Workflow)

**Endpoint**: `POST http://localhost:8000/api/v1/image/replace-background`

#### Using curl:
```bash
curl -X POST "http://localhost:8000/api/v1/image/replace-background" \
  -H "Content-Type: application/json" \
  -d '{
    "product_image_url": "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=400",
    "background_image_url": "https://images.unsplash.com/photo-1557683316-973673baf926?w=800",
    "scene_id": "test-scene-456",
    "user_id": "test-user-123"
  }'
```

#### Using PowerShell:
```powershell
$body = @{
    product_image_url = "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=400"
    background_image_url = "https://images.unsplash.com/photo-1557683316-973673baf926?w=800"
    scene_id = "test-scene-456"
    user_id = "test-user-123"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/api/v1/image/replace-background" `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

#### Expected Response:
```json
{
  "success": true,
  "image_url": "https://hdixvjydwaslnzyrokrd.supabase.co/storage/v1/object/public/generated-content/composited-images/test-user-123/test-scene-456/uuid.png",
  "message": "Background replaced successfully",
  "error": null
}
```

---

## Using with Real Scene Data

### Get Scene Data from Database

First, query the database to get a real scene with an image:

```sql
SELECT id, image_url, scenario_id 
FROM video_scenes 
WHERE image_url IS NOT NULL 
LIMIT 1;
```

### Use the Scene Data

Replace the test values with real data:

```bash
# Replace these with your actual values
SCENE_ID="your-scene-uuid-from-database"
USER_ID="your-user-uuid"
PRODUCT_IMAGE_URL="url-from-image_url-column"
NEW_BACKGROUND_URL="https://example.com/your-background.jpg"

curl -X POST "http://localhost:8000/api/v1/image/replace-background" \
  -H "Content-Type: application/json" \
  -d "{
    \"product_image_url\": \"$PRODUCT_IMAGE_URL\",
    \"background_image_url\": \"$NEW_BACKGROUND_URL\",
    \"scene_id\": \"$SCENE_ID\",
    \"user_id\": \"$USER_ID\"
  }"
```

---

## Postman Collection

Import this JSON into Postman for easy testing:

```json
{
  "info": {
    "name": "Image Processing API",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "item": [
    {
      "name": "Remove Background",
      "request": {
        "method": "POST",
        "header": [
          {
            "key": "Content-Type",
            "value": "application/json"
          }
        ],
        "body": {
          "mode": "raw",
          "raw": "{\n  \"image_url\": \"https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=400\",\n  \"user_id\": \"test-user-123\",\n  \"scene_id\": \"test-scene-456\"\n}"
        },
        "url": {
          "raw": "http://localhost:8000/api/v1/image/remove-background",
          "protocol": "http",
          "host": ["localhost"],
          "port": "8000",
          "path": ["api", "v1", "image", "remove-background"]
        }
      }
    },
    {
      "name": "Composite Images",
      "request": {
        "method": "POST",
        "header": [
          {
            "key": "Content-Type",
            "value": "application/json"
          }
        ],
        "body": {
          "mode": "raw",
          "raw": "{\n  \"background_url\": \"https://images.unsplash.com/photo-1557683316-973673baf926?w=800\",\n  \"overlay_url\": \"{{removed_bg_url}}\",\n  \"scene_id\": \"test-scene-456\",\n  \"user_id\": \"test-user-123\"\n}"
        },
        "url": {
          "raw": "http://localhost:8000/api/v1/image/composite",
          "protocol": "http",
          "host": ["localhost"],
          "port": "8000",
          "path": ["api", "v1", "image", "composite"]
        }
      }
    },
    {
      "name": "Replace Background",
      "request": {
        "method": "POST",
        "header": [
          {
            "key": "Content-Type",
            "value": "application/json"
          }
        ],
        "body": {
          "mode": "raw",
          "raw": "{\n  \"product_image_url\": \"https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=400\",\n  \"background_image_url\": \"https://images.unsplash.com/photo-1557683316-973673baf926?w=800\",\n  \"scene_id\": \"test-scene-456\",\n  \"user_id\": \"test-user-123\"\n}"
        },
        "url": {
          "raw": "http://localhost:8000/api/v1/image/replace-background",
          "protocol": "http",
          "host": ["localhost"],
          "port": "8000",
          "path": ["api", "v1", "image", "replace-background"]
        }
      }
    }
  ]
}
```

---

## JavaScript/Fetch Example

```javascript
// Replace Background
async function replaceBackground() {
  const response = await fetch('http://localhost:8000/api/v1/image/replace-background', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      product_image_url: 'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=400',
      background_image_url: 'https://images.unsplash.com/photo-1557683316-973673baf926?w=800',
      scene_id: 'test-scene-456',
      user_id: 'test-user-123'
    })
  });

  const result = await response.json();
  console.log('Result:', result);
  
  if (result.success) {
    console.log('New image URL:', result.image_url);
  } else {
    console.error('Error:', result.error);
  }
}

replaceBackground();
```

---

## Python Requests Example

```python
import requests

# Replace Background
def test_replace_background():
    url = "http://localhost:8000/api/v1/image/replace-background"
    payload = {
        "product_image_url": "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=400",
        "background_image_url": "https://images.unsplash.com/photo-1557683316-973673baf926?w=800",
        "scene_id": "test-scene-456",
        "user_id": "test-user-123"
    }
    
    response = requests.post(url, json=payload)
    result = response.json()
    
    print("Result:", result)
    
    if result.get('success'):
        print("New image URL:", result['image_url'])
    else:
        print("Error:", result.get('error'))

test_replace_background()
```

---

## Troubleshooting

### Error: "Remove.bg API key not configured"
**Solution**: Add your API key to `.env`:
```
REMOVEBG_API_KEY=your_api_key_here
```

### Error: "Supabase connection not available"
**Solution**: Check your Supabase credentials in `.env`:
```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
```

### Error: Connection refused
**Solution**: Make sure the FastAPI server is running:
```bash
python -m uvicorn app.main:app --reload
```

### Error: 422 Unprocessable Entity
**Solution**: Check your request body matches the expected format. All URLs must be valid HTTP(S) URLs.

---

## Sample Test Images

Free sample images from Unsplash for testing:

**Product Images**:
- Watch: `https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=400`
- Shoes: `https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400`
- Headphones: `https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=400`

**Background Images**:
- Gradient: `https://images.unsplash.com/photo-1557683316-973673baf926?w=800`
- Abstract: `https://images.unsplash.com/photo-1557682224-5b8590cd9ec5?w=800`
- Nature: `https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800`

---

## Next Steps

1. Test each endpoint individually
2. Verify images are uploaded to Supabase storage
3. Check that `video_scenes.image_url` is updated in the database
4. Integrate the `replace-background` endpoint into your frontend
5. Test with real product images from your `video_scenes` table

For more details, see:
- `IMAGE_PROCESSING_README.md` - Complete documentation
- `IMPLEMENTATION_SUMMARY.md` - Implementation overview
- `test_image_processing.py` - Python test script
