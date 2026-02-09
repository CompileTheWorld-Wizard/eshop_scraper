# Remotion Middleware Documentation

## Overview

This Python service acts as a **middleware/proxy bridge** between your Next.js frontend and Remotion server. It receives requests from Next.js, forwards them to the Remotion server, and returns responses back to Next.js without modification.

## Architecture

```
Next.js Frontend  →  Python Middleware  →  Remotion Server (localhost:5050)
                  ←                    ←
```

## Configuration

### Environment Variables

Add to your `.env` file:

```env
# Remotion Server URL (default: http://localhost:5050)
REMOTION_SERVER_URL=http://localhost:5050
```

### Default Settings

- **Remotion Server URL**: `http://localhost:5050`
- **Request Timeout**: 300 seconds (5 minutes) for video generation
- **Status Check Timeout**: 30 seconds

## API Endpoints

### 1. Start Video Generation

**Endpoint**: `POST /api/remotion/videos`

**Purpose**: Starts video generation on Remotion server

**Request Format**:
```json
{
  "template": "product-modern-v1",
  "imageUrl": "https://example.com/image.jpg",
  "product": {
    "title": "Product Name",
    "price": "$99.99",
    "rating": 4.5,
    "reviewCount": 123,
    "currency": "USD"
  },
  "metadata": {
    "short_id": "abc123",
    "scene_id": "uuid-here",
    "sceneNumber": 1
  }
}
```

**Response Format**:
```json
{
  "taskId": "task-uuid-here",
  "status": "pending"
}
```

**Supported Templates**:
- `product-modern-v1`
- `product-minimal-v1`

---

### 2. Check Task Status

**Endpoint**: `GET /api/remotion/tasks/{taskId}`

**Purpose**: Checks the status of a video generation task

**Query Parameters**:
- `shortId` (optional): Short ID for logging
- `sceneNumber` (optional): Scene number for logging

**Example Request**:
```
GET /api/remotion/tasks/task-uuid-here?shortId=abc123&sceneNumber=1
```

**Response Format**:
```json
{
  "status": "completed",
  "stage": "uploading",
  "progress": 100,
  "videoUrl": "https://example.com/video.mp4"
}
```

**Status Values**:
- `pending`: Task is queued
- `processing`: Task is being processed
- `completed`: Task completed successfully
- `failed`: Task failed

**Stage Values** (when status is `processing`):
- `downloading`: Downloading assets
- `rendering`: Rendering video
- `uploading`: Uploading result

**Progress**: Integer 0-100 representing completion percentage

**Error Response** (when status is `failed`):
```json
{
  "status": "failed",
  "error": "Error message here"
}
```

---

### 3. Health Check

**Endpoint**: `GET /api/remotion/health`

**Purpose**: Check if middleware and Remotion server are reachable

**Response Format**:
```json
{
  "proxy": "healthy",
  "remotion_server": "connected",
  "base_url": "http://localhost:5050"
}
```

## Usage Examples

### From Next.js

#### 1. Start Video Generation

```typescript
// Next.js API Route or Server Action
const response = await fetch('http://localhost:8000/api/remotion/videos', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    template: 'product-modern-v1',
    imageUrl: 'https://example.com/product.jpg',
    product: {
      title: 'Amazing Product',
      price: '$99.99',
      rating: 4.5,
      reviewCount: 123,
      currency: 'USD'
    },
    metadata: {
      short_id: 'short123',
      scene_id: 'scene456',
      sceneNumber: 1
    }
  })
});

const data = await response.json();
console.log('Task ID:', data.taskId);
```

#### 2. Check Task Status (Polling)

```typescript
// Poll for status updates
const checkStatus = async (taskId: string) => {
  const response = await fetch(
    `http://localhost:8000/api/remotion/tasks/${taskId}?shortId=short123&sceneNumber=1`
  );
  
  const data = await response.json();
  
  if (data.status === 'completed') {
    console.log('Video URL:', data.videoUrl);
    return data.videoUrl;
  } else if (data.status === 'failed') {
    console.error('Video generation failed:', data.error);
    throw new Error(data.error);
  } else {
    console.log(`Progress: ${data.progress}% - Stage: ${data.stage}`);
    // Poll again after delay
    await new Promise(resolve => setTimeout(resolve, 2000));
    return checkStatus(taskId);
  }
};
```

#### 3. Complete Flow

```typescript
// Complete video generation flow
async function generateVideo(productData: any) {
  try {
    // 1. Start video generation
    const startResponse = await fetch('http://localhost:8000/api/remotion/videos', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(productData)
    });
    
    const { taskId } = await startResponse.json();
    console.log('Video generation started, task ID:', taskId);
    
    // 2. Poll for completion
    const videoUrl = await pollTaskStatus(taskId);
    console.log('Video ready:', videoUrl);
    
    return videoUrl;
    
  } catch (error) {
    console.error('Video generation error:', error);
    throw error;
  }
}

async function pollTaskStatus(taskId: string): Promise<string> {
  while (true) {
    const response = await fetch(
      `http://localhost:8000/api/remotion/tasks/${taskId}`
    );
    
    const data = await response.json();
    
    if (data.status === 'completed') {
      return data.videoUrl;
    }
    
    if (data.status === 'failed') {
      throw new Error(data.error || 'Video generation failed');
    }
    
    // Wait before next poll
    await new Promise(resolve => setTimeout(resolve, 2000));
  }
}
```

## Error Handling

The middleware handles the following errors:

### 503 Service Unavailable
```json
{
  "detail": "Cannot connect to Remotion server at http://localhost:5050: ..."
}
```
**Cause**: Remotion server is not running or unreachable

**Solution**: Ensure Remotion server is running on `localhost:5050`

### 500 Internal Server Error
```json
{
  "detail": "Failed to start video generation: ..."
}
```
**Cause**: Unexpected error during request processing

**Solution**: Check middleware logs for details

### 4xx Errors from Remotion
The middleware forwards error responses from the Remotion server directly to Next.js.

## Logging

The middleware logs all operations with the `[REMOTION PROXY]` prefix:

```
[REMOTION PROXY] Starting video generation: http://localhost:5050/videos
[REMOTION PROXY] Template: product-modern-v1, Scene: 1
[REMOTION PROXY] Video generation started: taskId=task-123
[REMOTION PROXY] Checking task status: http://localhost:5050/tasks/task-123
[REMOTION PROXY] Task task-123: status=processing, stage=rendering, progress=50%
[REMOTION PROXY] Task completed: videoUrl=https://...
```

## Running the Middleware

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# .env file
REMOTION_SERVER_URL=http://localhost:5050
```

### 3. Start the Server

```bash
# Development
python -m uvicorn app.main:app --reload --port 8000

# Production
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 4. Verify Connection

```bash
curl http://localhost:8000/api/remotion/health
```

Expected response:
```json
{
  "proxy": "healthy",
  "remotion_server": "connected",
  "base_url": "http://localhost:5050"
}
```

## Testing

### Test Video Generation

```bash
curl -X POST http://localhost:8000/api/remotion/videos \
  -H "Content-Type: application/json" \
  -d '{
    "template": "product-modern-v1",
    "imageUrl": "https://example.com/image.jpg",
    "product": {
      "title": "Test Product",
      "price": "$99.99",
      "rating": 4.5,
      "reviewCount": 123,
      "currency": "USD"
    },
    "metadata": {
      "short_id": "test123",
      "scene_id": "scene456",
      "sceneNumber": 1
    }
  }'
```

### Test Status Check

```bash
curl http://localhost:8000/api/remotion/tasks/{taskId}?shortId=test123&sceneNumber=1
```

## Troubleshooting

### Remotion Server Not Reachable

**Problem**: `503 Service Unavailable` error

**Solutions**:
1. Check if Remotion server is running: `curl http://localhost:5050/health`
2. Verify REMOTION_SERVER_URL in `.env`
3. Check firewall settings

### Timeout Errors

**Problem**: Request times out after 5 minutes

**Solutions**:
1. Increase timeout in `remotion_proxy.py`:
   ```python
   REQUEST_TIMEOUT = 600  # 10 minutes
   ```
2. Check Remotion server performance

### Connection Refused

**Problem**: Cannot connect to localhost:5050

**Solutions**:
1. Ensure Remotion server is running
2. Check if port 5050 is available
3. Verify no firewall blocking localhost connections

## Next Steps

After setting up the middleware:

1. ✅ Configure Next.js to call middleware endpoints instead of Remotion directly
2. ✅ Update Next.js routes to use `http://localhost:8000/api/remotion/*`
3. ✅ Test complete flow from Next.js → Middleware → Remotion
4. ✅ Monitor logs for any issues
5. ✅ Implement error handling in Next.js

## API Documentation

Interactive API documentation is available at:
- **Swagger UI**: http://localhost:8000/docs (disabled by default)
- **ReDoc**: http://localhost:8000/redoc
