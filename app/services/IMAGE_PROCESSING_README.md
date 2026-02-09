# Image Processing Service

This service provides image processing capabilities including background removal and image compositing.

## Features

1. **Background Removal**: Remove backgrounds from images using Remove.bg API
2. **Image Compositing**: Merge two images together (overlay on background)
3. **Complete Background Replacement**: Full workflow combining background removal and compositing

## API Endpoints

### 1. Remove Background

**Endpoint**: `POST /api/v1/image/remove-background`

Remove background from an image using Remove.bg API.

**Request Body**:
```json
{
  "image_url": "https://example.com/product.jpg",
  "scene_id": "optional-scene-uuid",
  "user_id": "user-uuid"
}
```

**Response**:
```json
{
  "success": true,
  "image_url": "https://supabase-storage-url/background-removed/image.png",
  "message": "Background removed successfully",
  "error": null
}
```

**Example using curl**:
```bash
curl -X POST "http://localhost:8000/api/v1/image/remove-background" \
  -H "Content-Type: application/json" \
  -d '{
    "image_url": "https://example.com/product.jpg",
    "user_id": "user-123"
  }'
```

### 2. Composite Images

**Endpoint**: `POST /api/v1/image/composite`

Merge two images together (overlay on top of background).

**Request Body**:
```json
{
  "background_url": "https://example.com/background.jpg",
  "overlay_url": "https://example.com/product-no-bg.png",
  "scene_id": "scene-uuid",
  "user_id": "user-uuid"
}
```

**Response**:
```json
{
  "success": true,
  "image_url": "https://supabase-storage-url/composited-images/final.png",
  "message": "Images composited successfully",
  "error": null
}
```

**Example using curl**:
```bash
curl -X POST "http://localhost:8000/api/v1/image/composite" \
  -H "Content-Type: application/json" \
  -d '{
    "background_url": "https://example.com/background.jpg",
    "overlay_url": "https://example.com/product-no-bg.png",
    "scene_id": "scene-123",
    "user_id": "user-123"
  }'
```

### 3. Replace Background (Complete Workflow)

**Endpoint**: `POST /api/v1/image/replace-background`

Complete workflow: Remove background from product image and composite with new background.

**Request Body**:
```json
{
  "product_image_url": "https://example.com/product.jpg",
  "background_image_url": "https://example.com/new-background.jpg",
  "scene_id": "scene-uuid",
  "user_id": "user-uuid"
}
```

**Response**:
```json
{
  "success": true,
  "image_url": "https://supabase-storage-url/composited-images/final.png",
  "message": "Background replaced successfully",
  "error": null
}
```

**Example using curl**:
```bash
curl -X POST "http://localhost:8000/api/v1/image/replace-background" \
  -H "Content-Type: application/json" \
  -d '{
    "product_image_url": "https://example.com/product.jpg",
    "background_image_url": "https://example.com/new-background.jpg",
    "scene_id": "scene-123",
    "user_id": "user-123"
  }'
```

## Python Usage Examples

### Example 1: Direct Service Usage

```python
from app.services.image_processing_service import image_processing_service

# Remove background only
result = image_processing_service.remove_background(
    image_url="https://example.com/product.jpg",
    scene_id="optional-scene-id"
)

if result['success']:
    print(f"Background removed image URL: {result['image_url']}")
else:
    print(f"Error: {result['error']}")
```

### Example 2: Composite Images

```python
from app.services.image_processing_service import image_processing_service

# Composite two images
result = image_processing_service.composite_images(
    background_url="https://example.com/background.jpg",
    overlay_url="https://example.com/product-no-bg.png",
    scene_id="scene-123",
    user_id="user-123"
)

if result['success']:
    print(f"Composited image URL: {result['image_url']}")
    print("Scene image_url updated in database")
else:
    print(f"Error: {result['error']}")
```

### Example 3: Complete Background Replacement Workflow

```python
from app.services.image_processing_service import image_processing_service

# Complete workflow: remove background and composite
result = image_processing_service.replace_background(
    product_image_url="https://example.com/product.jpg",
    background_image_url="https://example.com/new-background.jpg",
    scene_id="scene-123",
    user_id="user-123"
)

if result['success']:
    print(f"Final composited image URL: {result['image_url']}")
    print("Scene image_url updated in database")
else:
    print(f"Error: {result['error']}")
```

## Frontend Integration Example

Here's how to integrate the background replacement feature in your frontend:

```javascript
// Replace background button handler
async function handleReplaceBackground(productImageUrl, backgroundImageUrl, sceneId, userId) {
  try {
    const response = await fetch('http://localhost:8000/api/v1/image/replace-background', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        product_image_url: productImageUrl,
        background_image_url: backgroundImageUrl,
        scene_id: sceneId,
        user_id: userId
      })
    });

    const result = await response.json();

    if (result.success) {
      console.log('Background replaced successfully!');
      console.log('New image URL:', result.image_url);
      
      // Update the UI with the new image
      document.getElementById('scene-image').src = result.image_url;
      
      // The scene's image_url in the database is automatically updated
      alert('Background replaced successfully!');
    } else {
      console.error('Background replacement failed:', result.error);
      alert('Failed to replace background: ' + result.error);
    }
  } catch (error) {
    console.error('Error:', error);
    alert('An error occurred while replacing the background');
  }
}

// Example usage
const productImageUrl = 'https://supabase-storage-url/products/product-123.jpg';
const backgroundImageUrl = 'https://supabase-storage-url/backgrounds/beach.jpg';
const sceneId = 'scene-uuid-123';
const userId = 'user-uuid-456';

handleReplaceBackground(productImageUrl, backgroundImageUrl, sceneId, userId);
```

## Configuration

### Environment Variables

Make sure the following environment variable is set in your `.env` file:

```env
REMOVEBG_API_KEY=your_remove_bg_api_key_here
```

You can get your Remove.bg API key from: https://remove.bg/api

### Supabase Storage

The service automatically uploads processed images to the `generated-content` bucket in Supabase:

- **Background-removed images**: `background-removed/[scene_id]/[uuid].png`
- **Composited images**: `composited-images/[user_id]/[scene_id]/[uuid].png`

## Database Updates

When using the `composite_images` or `replace_background` methods, the service automatically updates the `image_url` column in the `video_scenes` table with the new composited image URL.

## Error Handling

All service methods return a dictionary with the following structure:

```python
{
    'success': bool,          # Whether the operation succeeded
    'image_url': str | None,  # URL of the processed image (if successful)
    'error': str | None       # Error message (if failed)
}
```

## Image Processing Details

### Background Removal
- Uses Remove.bg API with `size: 'auto'` parameter
- Outputs PNG files with transparency
- Retries up to 3 times on failure

### Image Compositing
- Uses Pillow (PIL) for image processing
- Automatically resizes overlay to fit background (80% of background size)
- Centers the overlay on the background
- Maintains aspect ratio of the overlay image
- Outputs high-quality PNG files

## Dependencies

The service requires the following Python packages (already in requirements.txt):

- `Pillow>=10.0.0` - For image processing
- `requests>=2.31.0` - For Remove.bg API calls
- `httpx>=0.25.0` - For async HTTP requests

## Limitations

1. **Remove.bg API**:
   - Requires valid API key
   - Has rate limits based on your subscription plan
   - Free plan: 50 API calls per month

2. **Image Size**:
   - Large images may take longer to process
   - Maximum file size depends on Remove.bg plan

3. **File Format**:
   - Output is always PNG for transparency support
   - Input can be any image format supported by Pillow

## Troubleshooting

### "Remove.bg API key not configured"
- Make sure `REMOVEBG_API_KEY` is set in your `.env` file
- Restart the application after adding the key

### "Supabase connection not available"
- Check your Supabase credentials in `.env`
- Verify Supabase service is running

### "Bucket not found"
- The service will automatically create the `generated-content` bucket if it doesn't exist
- Make sure your Supabase service role key has storage permissions

### "Background removal failed"
- Check your Remove.bg API quota
- Verify the image URL is accessible
- Check the image format is supported

## Support

For issues or questions, please check:
1. Environment variables are correctly set
2. API keys are valid
3. Image URLs are accessible
4. Supabase connection is working
