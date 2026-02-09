# Image Processing Service Implementation Summary

## Overview

A new image processing service has been successfully created to handle background removal and image compositing for the video scenes workflow. The implementation follows the existing project structure and patterns.

## Files Created/Modified

### 1. New Service File
**Location**: `app/services/image_processing_service.py`

This is the main service file containing three primary functions:

#### Functions:
- **`remove_background(image_url, scene_id)`** - Removes background from an image using Remove.bg API
- **`composite_images(background_url, overlay_url, scene_id, user_id)`** - Merges two images together
- **`replace_background(product_image_url, background_image_url, scene_id, user_id)`** - Complete workflow combining both operations

#### Features:
- Automatic retry logic (3 attempts)
- Temporary file cleanup
- Supabase storage integration
- Automatic database updates for video_scenes table
- Comprehensive error handling and logging

### 2. Models Updated
**Location**: `app/models.py`

Added six new Pydantic models for request/response handling:
- `RemoveBackgroundRequest`
- `RemoveBackgroundResponse`
- `CompositeImagesRequest`
- `CompositeImagesResponse`
- `ReplaceBackgroundRequest`
- `ReplaceBackgroundResponse`

### 3. API Routes Updated
**Location**: `app/api/routes.py`

Added three new endpoints:
- `POST /api/v1/image/remove-background`
- `POST /api/v1/image/composite`
- `POST /api/v1/image/replace-background`

### 4. Documentation
**Location**: `app/services/IMAGE_PROCESSING_README.md`

Complete documentation including:
- API endpoint specifications
- Python usage examples
- Frontend integration examples
- Configuration guide
- Troubleshooting tips

## API Endpoints

### 1. Remove Background
```
POST /api/v1/image/remove-background
```
Removes background from a single image using Remove.bg API.

### 2. Composite Images
```
POST /api/v1/image/composite
```
Merges two images (background + overlay) and updates the scene's image_url in the database.

### 3. Replace Background (Recommended)
```
POST /api/v1/image/replace-background
```
Complete workflow: removes background from product image and composites it with a new background.

## Environment Configuration

The following environment variable is already configured in `.env`:
```
REMOVEBG_API_KEY=jQBQDQS18iNM6YtmLWwRFexh
```

## Database Integration

When using `composite_images` or `replace_background`, the service automatically:
1. Processes the images
2. Uploads the result to Supabase storage (`generated-content` bucket)
3. Updates the `image_url` column in the `video_scenes` table

## Storage Structure

Processed images are stored in Supabase storage with the following structure:

```
generated-content/
├── background-removed/
│   └── [scene_id]/
│       └── [uuid].png
└── composited-images/
    └── [user_id]/
        └── [scene_id]/
            └── [uuid].png
```

## Frontend Integration

When the user clicks the "replace background" button in the frontend:

```javascript
// Example frontend code
const response = await fetch('/api/v1/image/replace-background', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    product_image_url: productImageUrl,
    background_image_url: backgroundImageUrl,
    scene_id: sceneId,
    user_id: userId
  })
});

const result = await response.json();
if (result.success) {
  // result.image_url contains the new composited image URL
  // The database has been automatically updated
  console.log('New image URL:', result.image_url);
}
```

## Technology Stack

- **Image Processing**: Pillow (PIL) for compositing
- **Background Removal**: Remove.bg API
- **HTTP Client**: httpx for async operations, requests for Remove.bg
- **Storage**: Supabase storage
- **Database**: Supabase PostgreSQL

## Dependencies

All required dependencies are already in `requirements.txt`:
- ✅ Pillow>=10.0.0
- ✅ requests>=2.31.0
- ✅ httpx>=0.25.0

## Testing

To test the new functionality:

1. **Start the FastAPI server**:
   ```bash
   python -m uvicorn app.main:app --reload
   ```

2. **Test with curl**:
   ```bash
   curl -X POST "http://localhost:8000/api/v1/image/replace-background" \
     -H "Content-Type: application/json" \
     -d '{
       "product_image_url": "https://example.com/product.jpg",
       "background_image_url": "https://example.com/background.jpg",
       "scene_id": "your-scene-uuid",
       "user_id": "your-user-uuid"
     }'
   ```

3. **Check the result**:
   - The response will contain the new image URL
   - Check the `video_scenes` table to verify the `image_url` was updated
   - Verify the image was uploaded to Supabase storage

## Workflow Example

For a typical background replacement workflow:

```
1. User has a product image with original background
   └─> product_image_url

2. User selects a new background image
   └─> background_image_url

3. Frontend calls POST /api/v1/image/replace-background
   └─> Service removes background from product
   └─> Service downloads new background
   └─> Service composites the images
   └─> Service uploads to Supabase
   └─> Service updates video_scenes.image_url

4. Frontend receives the new image URL
   └─> Updates the UI with the new image
   └─> Scene is ready for video generation
```

## Error Handling

All functions return a consistent response format:

```python
{
    'success': bool,          # Operation status
    'image_url': str | None,  # Result URL (if successful)
    'error': str | None       # Error message (if failed)
}
```

## Key Features

✅ **Background Removal**: Uses industry-standard Remove.bg API  
✅ **Image Compositing**: High-quality PIL-based image merging  
✅ **Auto-scaling**: Automatically resizes overlay to fit background  
✅ **Centering**: Automatically centers product on new background  
✅ **Database Updates**: Automatically updates video_scenes table  
✅ **Storage Integration**: Seamless Supabase storage upload  
✅ **Error Handling**: Comprehensive error handling with retries  
✅ **Cleanup**: Automatic temporary file cleanup  
✅ **Logging**: Detailed logging for debugging  

## Next Steps

1. **Test the API endpoints** with sample images
2. **Integrate the replace background button** in the frontend
3. **Monitor Remove.bg API usage** (50 calls/month on free plan)
4. **Consider caching** background-removed images to reduce API calls

## Maintenance Notes

- The Remove.bg API key is stored in `.env` file
- Free plan allows 50 API calls per month
- Consider upgrading to paid plan for production use
- Monitor Supabase storage usage
- Temporary files are automatically cleaned up

## Support & Troubleshooting

For detailed troubleshooting, see `IMAGE_PROCESSING_README.md` in the `app/services/` directory.

Common issues:
- **API Key Error**: Verify `REMOVEBG_API_KEY` in `.env`
- **Supabase Error**: Check Supabase credentials
- **Image Quality**: Adjust resize parameters in `_composite_images_locally()`
- **Storage Error**: Verify bucket permissions
