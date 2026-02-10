# Bridge Implementation: Python Server as Pass-Through

## Overview
Python server now acts as a simple bridge between Next.js and Node.js (Remotion) servers for scene1 video generation.

**Flow:**
```
Next.js → Python Server → Node.js (Remotion) → Python Server → Next.js
```

## What Was Implemented

### 1. Environment Configuration (`.env`)
Added Node.js server URL configuration:
```env
# Node.js Remotion Server Settings
REMOTION_SERVER_URL=http://localhost:5050
```

### 2. Data Models (`app/models.py`)
Added new Pydantic models for Scene1 requests/responses:

**Scene1ProductInfo:**
- `title` - Product name
- `price` - Product price
- `rating` - Product rating (0-5)
- `reviewCount` - Number of reviews

**GenerateScene1Request:**
- `imageUrl` - Direct image URL (optional)
- `shortId` - UUID of the short (optional)
- `sceneNumber` - Scene number (optional)
- `product` - Product information (required)

**GenerateScene1Response:**
- `success` - Operation success status
- `taskId` - Task ID for polling
- `status` - Current task status
- `message` - Response message
- `videoUrl` - Generated video URL (when completed)
- `stage` - Current processing stage
- `progress` - Progress percentage
- `error` - Error message if failed

### 3. Bridge Endpoints (`app/api/routes.py`)

#### POST `/api/remotion/generate-scene1`
**Purpose:** Start video generation for Scene1

**How it works:**
1. Receives request from Next.js
2. Forwards entire request to Node.js server at `{REMOTION_SERVER_URL}/videos`
3. Waits for Node.js response
4. Returns Node.js response back to Next.js

**Node.js Endpoint:** `POST http://localhost:5050/videos`

**Example Next.js call:**
```typescript
const response = await fetch('http://your-python-server:8000/api/remotion/generate-scene1', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    shortId: 'abc-123',
    sceneNumber: 1,
    product: {
      title: 'Wireless Headphones',
      price: '$99.99',
      rating: 4.5,
      reviewCount: 1234
    }
  })
})

const data = await response.json()
// { success: true, taskId: "...", status: "pending", message: "..." }
```

#### GET `/api/remotion/generate-scene1`
**Purpose:** Check status of video generation task

**How it works:**
1. Receives status check from Next.js with query parameters (taskId, shortId, sceneNumber)
2. Forwards request to Node.js server at `{REMOTION_SERVER_URL}/task/{taskId}` (with optional query params)
3. Waits for Node.js response
4. Returns Node.js response back to Next.js

**Node.js Endpoint:** `GET http://localhost:5050/task/{taskId}?shortId=xxx&sceneNumber=1`

**Example Next.js call:**
```typescript
const response = await fetch(
  `http://your-python-server:8000/api/remotion/generate-scene1?taskId=${taskId}&shortId=${shortId}&sceneNumber=1`
)

const data = await response.json()
// Processing: { success: true, status: "processing", progress: 50, ... }
// Completed: { success: true, status: "completed", videoUrl: "...", ... }
// Failed: { success: true, status: "failed", error: "...", ... }
```

## Key Features

### 1. Simple Pass-Through Design
- No complex proxy logic
- Direct forwarding of requests and responses
- Maintains original request/response structure

### 2. Error Handling
- Catches Node.js server connection errors
- Handles HTTP errors from Node.js
- Returns structured error responses to Next.js

### 3. Logging
- Logs all forwarding operations
- Tracks request/response flow
- Helps with debugging

### 4. Async Implementation
- Uses `httpx.AsyncClient` for non-blocking HTTP calls
- Integrates smoothly with FastAPI's async architecture
- 60-second timeout for long-running operations

## Configuration

### Update Node.js Server URL
Edit `.env` file:
```env
REMOTION_SERVER_URL=http://localhost:5050
```

For production:
```env
REMOTION_SERVER_URL=https://your-node-server.com
```

### Node.js Server Endpoints
The Python bridge forwards to these Node.js endpoints:
- **POST** `/videos` - Start video generation
- **GET** `/task/:taskId` - Check task status (supports query params: `shortId`, `sceneNumber`)

## Testing

### 1. Start all servers:
```bash
# Terminal 1: Python Server
python start_server.py

# Terminal 2: Node.js Server (Remotion)
cd /path/to/node-server
npm run dev
```

### 2. Update Next.js to call Python server:
Change your Next.js API calls from:
```typescript
// OLD - Direct to Node.js
const response = await fetch('http://localhost:3000/api/remotion/generate-scene1', ...)
```

To:
```typescript
// NEW - Through Python bridge
const response = await fetch('http://localhost:8000/api/remotion/generate-scene1', ...)
```

### 3. Test the flow:
1. Make a POST request from Next.js to start video generation
2. Poll the GET endpoint to check status
3. Verify logs in both Python and Node.js servers

## Logs to Monitor

**Python server logs:**
```
INFO: Forwarding scene1 generation request to Node.js: http://localhost:5050/videos
INFO: Request data: shortId=abc-123, sceneNumber=1
INFO: Received response from Node.js: success=True, taskId=task-xyz
INFO: Forwarding scene1 status check to Node.js: http://localhost:5050/task/task-xyz
```

**Node.js server logs:**
```
POST /videos - Starting video generation...
GET /task/task-xyz - Checking task status...
```

## Benefits

1. **Centralized Control**: All Next.js requests go through Python server
2. **Easy to Extend**: Add more bridge endpoints for other Remotion APIs
3. **Monitoring**: Track all API calls in one place
4. **Security**: Can add authentication/rate limiting in Python layer
5. **Flexibility**: Can modify requests/responses if needed in the future

## Next Steps (Optional)

If you want to add more Remotion endpoints:
1. Add models in `app/models.py`
2. Add bridge endpoints in `app/api/routes.py`
3. Follow the same pattern as scene1 endpoints
