# Shadow Generation API

## Overview

The Shadow Generation API adds realistic shadow effects to product images using OpenAI's AI capabilities. The endpoint accepts a product image URL and description, then generates a new image with a natural-looking shadow that enhances depth and focus.

## Endpoint

```
POST /image/add-shadow
```

## Request Format

### Headers
```
Content-Type: application/json
Authorization: Bearer YOUR_API_KEY (optional)
```

### Request Body

```json
{
  "image_url": "https://example.com/product-image.jpg",
  "product_description": "A sleek modern smartwatch with black metal band and OLED display",
  "user_id": "user_123"
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `image_url` | string | Yes | URL of the product image to add shadow to |
| `product_description` | string | Yes | Product description used to generate appropriate shadow prompt |
| `user_id` | string | Yes | User ID for credit tracking and storage organization |

## Response Format

### Success Response

```json
{
  "success": true,
  "image_url": "https://your-storage.supabase.co/storage/v1/object/public/generated-content/shadow-images/user_123/abc-123-def.png",
  "message": "Shadow effect applied successfully",
  "error": null
}
```

### Error Response

```json
{
  "success": false,
  "image_url": null,
  "message": "Failed to generate shadow image",
  "error": "OpenAI client not initialized"
}
```

## How It Works

The shadow generation process follows these steps:

1. **Prompt Extraction**: Uses OpenAI GPT-4o-mini to analyze the product description and generate a detailed shadow effect prompt
   - The prompt is based on the template: "Using the following product description, generate a prompt to apply a realistic shadow effect to the image. The shadow should enhance the depth and focus on the product, making it stand out as though it is placed on a surface with a soft, natural shadow. The shadow should be subtle yet provide a clear contrast from the background, simulating how a shadow would naturally appear under proper lighting conditions."

2. **Image Download**: Downloads the original product image from the provided URL

3. **Shadow Generation**: Uses OpenAI DALL-E 3 to generate a new image with the shadow effect applied
   - Creates professional product photography with realistic shadows
   - Maintains high quality and commercial-grade appearance

4. **Upload to Storage**: Uploads the generated image to Supabase storage
   - Organized by user ID
   - Returns a public URL for immediate use

5. **Cleanup**: Removes temporary files from local storage

## Example Usage

### cURL

```bash
curl -X POST "http://localhost:8000/image/add-shadow" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "image_url": "https://example.com/product.jpg",
    "product_description": "Premium leather wallet with RFID protection, brown color",
    "user_id": "user_123"
  }'
```

### Python

```python
import requests

url = "http://localhost:8000/image/add-shadow"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer YOUR_API_KEY"
}
data = {
    "image_url": "https://example.com/product.jpg",
    "product_description": "Premium leather wallet with RFID protection, brown color",
    "user_id": "user_123"
}

response = requests.post(url, json=data, headers=headers)
result = response.json()

if result["success"]:
    print(f"Shadow added! New image URL: {result['image_url']}")
else:
    print(f"Error: {result['error']}")
```

### JavaScript/TypeScript

```typescript
const response = await fetch('http://localhost:8000/image/add-shadow', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer YOUR_API_KEY'
  },
  body: JSON.stringify({
    image_url: 'https://example.com/product.jpg',
    product_description: 'Premium leather wallet with RFID protection, brown color',
    user_id: 'user_123'
  })
});

const result = await response.json();

if (result.success) {
  console.log('Shadow added! New image URL:', result.image_url);
} else {
  console.error('Error:', result.error);
}
```

## Configuration

The shadow generation service requires the following environment variables:

```env
OPENAI_API_KEY=your_openai_api_key_here
```

Make sure this is set in your `.env` file.

## Error Handling

The endpoint may return the following errors:

| HTTP Status | Error | Description |
|-------------|-------|-------------|
| 400 | Bad Request | Invalid request parameters |
| 500 | Internal Server Error | OpenAI API error, download failure, or storage error |

Common error scenarios:
- **OpenAI client not initialized**: Check that `OPENAI_API_KEY` is set
- **Failed to download original image**: Check that the image URL is valid and accessible
- **Failed to generate image with shadow**: OpenAI API may be unavailable or rate-limited
- **Failed to upload image to storage**: Supabase connection issue

## Technical Details

### Dependencies
- **OpenAI SDK** (`openai>=1.100.0`): For AI-powered prompt extraction and image generation
- **Requests**: For downloading images
- **Supabase**: For storage of generated images

### Models Used
- **GPT-4o-mini**: For analyzing product descriptions and generating shadow prompts
- **DALL-E 3**: For generating images with shadow effects

### Storage Location
Generated images are stored in Supabase storage at:
```
generated-content/shadow-images/{user_id}/{uuid}.png
```

## Reference Implementation

The shadow generation service is implemented similarly to the scenario generation service (see `app/services/scenario_generation_service_backup.py` for reference), following these patterns:

- OpenAI client initialization
- Prompt engineering with GPT models
- Image generation with DALL-E
- File handling and cleanup
- Supabase storage integration

## Notes

- Image generation typically takes 10-30 seconds depending on OpenAI API response time
- The endpoint is synchronous and returns only when the image is ready
- Temporary files are automatically cleaned up after upload
- The shadow effect is applied based on the product description context
- Generated images are in PNG format at 1024x1024 resolution (DALL-E 3 standard)
