# Remotion Middleware - Quick Start Guide

## 🚀 What Was Created

Your Python service now acts as a **middleware/bridge** between Next.js and Remotion server:

```
Next.js → Python Middleware (port 8000) → Remotion Server (port 5050)
```

## 📁 Files Created

1. **`app/middleware/remotion_proxy.py`** - Core proxy logic
2. **`app/api/remotion_routes.py`** - API endpoints for Next.js
3. **`app/middleware/__init__.py`** - Module initialization
4. **`app/config.py`** - Updated with `REMOTION_SERVER_URL` setting
5. **`app/main.py`** - Updated to include Remotion routes
6. **`REMOTION_MIDDLEWARE.md`** - Full documentation

## ⚙️ Configuration

### 1. Add to `.env` file:

```env
# Remotion Server URL (optional, defaults to http://localhost:5050)
REMOTION_SERVER_URL=http://localhost:5050
```

### 2. That's it! No other config needed.

## 🧪 Testing the Middleware

### Step 1: Start Remotion Server (Port 5050)

Make sure your Remotion server is running on `localhost:5050`

### Step 2: Start Python Middleware (Port 8000)

```bash
cd D:\Auto-Promo-AI\eshop_scraper
python -m uvicorn app.main:app --reload --port 8000
```

### Step 3: Test Health Check

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

### Step 4: Test Video Generation

```bash
curl -X POST http://localhost:8000/api/remotion/videos \
  -H "Content-Type: application/json" \
  -d "{
    \"template\": \"product-modern-v1\",
    \"imageUrl\": \"https://example.com/image.jpg\",
    \"product\": {
      \"title\": \"Test Product\",
      \"price\": \"$99.99\",
      \"rating\": 4.5,
      \"reviewCount\": 123,
      \"currency\": \"USD\"
    },
    \"metadata\": {
      \"short_id\": \"test123\",
      \"scene_id\": \"scene456\",
      \"sceneNumber\": 1
    }
  }"
```

Expected response:
```json
{
  "taskId": "task-uuid-here",
  "status": "pending"
}
```

### Step 5: Check Task Status

```bash
curl "http://localhost:8000/api/remotion/tasks/{taskId}?shortId=test123&sceneNumber=1"
```

Expected response:
```json
{
  "status": "processing",
  "stage": "rendering",
  "progress": 50
}
```

Or when completed:
```json
{
  "status": "completed",
  "videoUrl": "https://..."
}
```

## 🔌 Updating Next.js to Use Middleware

### Before (Direct to Remotion):
```typescript
const response = await fetch('http://localhost:5050/videos', {
  method: 'POST',
  ...
});
```

### After (Through Middleware):
```typescript
const response = await fetch('http://localhost:8000/api/remotion/videos', {
  method: 'POST',
  ...
});
```

### Example Next.js API Route:

```typescript
// app/api/remotion/generate-scene1/route.ts
export async function POST(request: Request) {
  const body = await request.json();
  
  // Forward to Python middleware
  const response = await fetch('http://localhost:8000/api/remotion/videos', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      template: 'product-modern-v1',
      imageUrl: body.imageUrl,
      product: body.product,
      metadata: {
        short_id: body.shortId,
        scene_id: body.sceneId,
        sceneNumber: 1
      }
    })
  });
  
  return Response.json(await response.json());
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const taskId = searchParams.get('taskId');
  const shortId = searchParams.get('shortId');
  
  // Check status via middleware
  const response = await fetch(
    `http://localhost:8000/api/remotion/tasks/${taskId}?shortId=${shortId}&sceneNumber=1`
  );
  
  return Response.json(await response.json());
}
```

## 📊 API Endpoints Summary

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/remotion/videos` | POST | Start video generation |
| `/api/remotion/tasks/{taskId}` | GET | Check task status |
| `/api/remotion/health` | GET | Health check |

## 🔍 Monitoring

### Check Logs

The middleware logs all operations:

```
[REMOTION PROXY] Starting video generation: http://localhost:5050/videos
[REMOTION PROXY] Template: product-modern-v1, Scene: 1
[REMOTION PROXY] Video generation started: taskId=task-123
[REMOTION PROXY] Checking task status: http://localhost:5050/tasks/task-123
[REMOTION PROXY] Task task-123: status=processing, stage=rendering, progress=50%
[REMOTION PROXY] Task completed: videoUrl=https://...
```

## ❗ Troubleshooting

### "Cannot connect to Remotion server"

**Solution**: Make sure Remotion server is running on port 5050

```bash
# Test Remotion server directly
curl http://localhost:5050/health
```

### "503 Service Unavailable"

**Cause**: Remotion server is not reachable

**Solutions**:
1. Start Remotion server
2. Check if port 5050 is in use
3. Verify firewall settings

### Timeout Errors

**Cause**: Video generation takes longer than 5 minutes

**Solution**: Increase timeout in `app/middleware/remotion_proxy.py`:
```python
REQUEST_TIMEOUT = 600  # 10 minutes
```

## ✅ Success Indicators

You'll know everything is working when:

1. ✅ Health check returns `"remotion_server": "connected"`
2. ✅ POST to `/videos` returns a `taskId`
3. ✅ GET to `/tasks/{taskId}` returns status updates
4. ✅ Logs show `[REMOTION PROXY]` messages
5. ✅ Next.js successfully receives video URLs

## 🎯 Next Steps

1. Update all Next.js API routes to call middleware instead of Remotion directly
2. Test the complete flow end-to-end
3. Handle errors gracefully in Next.js
4. Monitor logs for any issues
5. Deploy both services (Python middleware and Remotion server)

## 📚 Full Documentation

See `REMOTION_MIDDLEWARE.md` for complete documentation including:
- Detailed API reference
- Error handling
- Complete Next.js examples
- Deployment guide
