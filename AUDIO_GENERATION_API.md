# Audio Generation API Documentation

## Overview

The Audio Generation API provides AI-powered audio content creation using ElevenLabs voice synthesis and OpenAI script generation. The service uses a direct REST API pattern for immediate response with generated audio.

## Base URL

```
http://localhost:8000
```

## Authentication

All endpoints support optional API key authentication via Bearer token:

```http
Authorization: Bearer your_api_key_here
```

## API Endpoints

### 1. Generate Audio

**Endpoint:** `POST /generate-audio`

**Description:** Generates audio content for a specific scenario. Returns the generated audio immediately.

**Request Body:**
```json
{
  "voice_id": "string (required)",
  "user_id": "string (required)", 
  "short_id": "string (required)"
}
```

**Request Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `voice_id` | string | Yes | ElevenLabs voice ID for audio generation |
| `user_id` | string | Yes | User ID associated with the request |
| `short_id` | string | Yes | Short ID to generate audio for |

**Response (Success - 200):**
```json
{
  "success": true,
  "audio_url": "string",
  "script": "string",
  "words_per_minute": 150.5,
  "duration": 25.3,
  "voice_id": "string",
  "user_id": "string",
  "short_id": "string",
  "created_at": "2025-01-XX T XX:XX:XX.XXXZ",
  "is_cached": false,
  "message": "Audio generated successfully",
  "subtitle_timing": [
    {
      "text": "Welcome to our amazing product!",
      "start_time": 0.0,
      "end_time": 2.5,
      "duration": 2.5
    },
    {
      "text": "This innovative solution will transform your daily routine.",
      "start_time": 2.5,
      "end_time": 6.8,
      "duration": 4.3
    },
    {
      "text": "Get yours today!",
      "start_time": 6.8,
      "end_time": 8.2,
      "duration": 1.4
    }
  ],
  "credit_info": {
    "deducted": true,
    "new_balance": 95
  }
}
```

**Response (Error - 400):**
```json
{
  "detail": "Missing required fields: voice_id, user_id, short_id"
}
```

**Response (Error - 402):**
```json
{
  "detail": "Insufficient credits for audio generation"
}
```

**Response (Error - 500):**
```json
{
  "detail": "Audio generation failed: [error message]"
}
```

## Complete Workflow Example

### Generate Audio

```bash
curl -X POST "http://localhost:8000/generate-audio" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_api_key_here" \
  -d '{
    "voice_id": "pNInz6obpgDQGcFmaJgB",
    "user_id": "user-uuid-123",
    "short_id": "short-uuid-456"
  }'
```

**Response:**
```json
{
  "success": true,
  "audio_url": "https://your-supabase-url.supabase.co/storage/v1/object/public/audio-files/user-uuid-123/audio-uuid-abc.mp3",
  "script": "Welcome to our amazing product! This innovative solution will transform your daily routine. Get yours today!",
  "words_per_minute": 145.2,
  "duration": 28.5,
  "voice_id": "pNInz6obpgDQGcFmaJgB",
  "user_id": "user-uuid-123",
  "short_id": "short-uuid-456",
  "created_at": "2025-01-XX T XX:XX:XX.XXXZ",
  "is_cached": false,
  "message": "Audio generated successfully",
  "subtitle_timing": [
    {
      "text": "Welcome to our amazing product!",
      "start_time": 0.0,
      "end_time": 2.5,
      "duration": 2.5
    },
    {
      "text": "This innovative solution will transform your daily routine.",
      "start_time": 2.5,
      "end_time": 6.8,
      "duration": 4.3
    },
    {
      "text": "Get yours today!",
      "start_time": 6.8,
      "end_time": 8.2,
      "duration": 1.4
    }
  ],
  "credit_info": {
    "deducted": true,
    "new_balance": 95
  }
}
```

## Python Client Example

```python
import requests
import json

class AudioGenerationClient:
    def __init__(self, base_url="http://localhost:8000", api_key=None):
        self.base_url = base_url
        self.headers = {"Content-Type": "application/json"}
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"
    
    def generate_audio(self, voice_id, user_id, short_id):
        """Generate audio for a short using direct REST API"""
        
        response = requests.post(
            f"{self.base_url}/generate-audio",
            headers=self.headers,
            json={
                "voice_id": voice_id,
                "user_id": user_id,
                "short_id": short_id
            }
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to generate audio: {response.text}")
        
        return response.json()

# Usage example
client = AudioGenerationClient(api_key="your_api_key_here")

try:
    result = client.generate_audio(
        voice_id="pNInz6obpgDQGcFmaJgB",
        user_id="user-uuid-123", 
        short_id="short-uuid-456"
    )
    
    print(f"Success: {result['success']}")
    print(f"Audio URL: {result['audio_url']}")
    print(f"Script: {result['script']}")
    print(f"Duration: {result['duration']} seconds")
    print(f"Words per minute: {result['words_per_minute']}")
    print(f"Credits deducted: {result['credit_info']['deducted']}")
    print(f"New balance: {result['credit_info']['new_balance']}")
    
    # Display subtitle timing
    if result.get('subtitle_timing'):
        print("\nSubtitle Timing:")
        for i, segment in enumerate(result['subtitle_timing'], 1):
            print(f"{i}. [{segment['start_time']:.1f}s - {segment['end_time']:.1f}s] {segment['text']}")
    
except Exception as e:
    print(f"Error: {e}")
```

## JavaScript/Node.js Client Example

```javascript
class AudioGenerationClient {
    constructor(baseUrl = 'http://localhost:8000', apiKey = null) {
        this.baseUrl = baseUrl;
        this.headers = {
            'Content-Type': 'application/json'
        };
        if (apiKey) {
            this.headers['Authorization'] = `Bearer ${apiKey}`;
        }
    }

    async generateAudio(voiceId, userId, shortId) {
        const response = await fetch(`${this.baseUrl}/generate-audio`, {
            method: 'POST',
            headers: this.headers,
            body: JSON.stringify({
                voice_id: voiceId,
                user_id: userId,
                short_id: shortId
            })
        });

        if (!response.ok) {
            throw new Error(`Failed to generate audio: ${await response.text()}`);
        }

        return await response.json();
    }
}

// Usage example
const client = new AudioGenerationClient('http://localhost:8000', 'your_api_key_here');

client.generateAudio(
    'pNInz6obpgDQGcFmaJgB',
    'user-uuid-123',
    'short-uuid-456'
)
.then(result => {
    console.log('Success:', result.success);
    console.log('Audio URL:', result.audio_url);
    console.log('Script:', result.script);
    console.log('Duration:', result.duration, 'seconds');
    console.log('Words per minute:', result.words_per_minute);
    console.log('Credits deducted:', result.credit_info.deducted);
    console.log('New balance:', result.credit_info.new_balance);
    
    // Display subtitle timing
    if (result.subtitle_timing && result.subtitle_timing.length > 0) {
        console.log('\nSubtitle Timing:');
        result.subtitle_timing.forEach((segment, index) => {
            console.log(`${index + 1}. [${segment.start_time.toFixed(1)}s - ${segment.end_time.toFixed(1)}s] ${segment.text}`);
        });
    }
})
.catch(error => {
    console.error('Error:', error.message);
});
```

## Subtitle Timing

The API provides precise subtitle timing information for each generated audio:

### Subtitle Timing Format

Each subtitle segment contains:

| Field | Type | Description |
|-------|------|-------------|
| `text` | string | The text content of the subtitle segment |
| `start_time` | number | Start time in seconds |
| `end_time` | number | End time in seconds |
| `duration` | number | Duration of the segment in seconds |

### Subtitle Processing

The service automatically:
1. **Character-level Analysis**: Uses ElevenLabs' character-level timing data
2. **Word Grouping**: Groups characters into words based on spaces and punctuation
3. **Sentence Segmentation**: Groups words into sentences for better readability
4. **Timing Calculation**: Calculates precise start/end times for each segment

### Example Subtitle Timing

```json
{
  "subtitle_timing": [
    {
      "text": "Welcome to our amazing product!",
      "start_time": 0.0,
      "end_time": 2.5,
      "duration": 2.5
    },
    {
      "text": "This innovative solution will transform your daily routine.",
      "start_time": 2.5,
      "end_time": 6.8,
      "duration": 4.3
    },
    {
      "text": "Get yours today!",
      "start_time": 6.8,
      "end_time": 8.2,
      "duration": 1.4
    }
  ]
}
```

### Use Cases

- **Video Editing**: Sync subtitles with video content
- **Accessibility**: Provide closed captions for hearing-impaired users
- **Language Learning**: Highlight words as they're spoken
- **Interactive Media**: Create clickable transcript segments
- **Analytics**: Track which parts of audio are most engaging

## Audio Generation Process

The audio generation service follows this workflow:

1. **Test Audio Check**: Checks MongoDB for existing test audio for the voice
2. **Test Audio Generation**: If not found, generates test audio using ElevenLabs
3. **Speed Analysis**: Analyzes test audio to determine words per minute (WPM)
4. **Script Generation**: Uses OpenAI to create contextual audio scripts based on:
   - Short information (title, description, duration, style, mood)
   - Detected speaking rate from test audio
   - Product information from the short
5. **Final Audio Generation**: Creates final audio using ElevenLabs `convertWithTimestamps` with the generated script
6. **Subtitle Processing**: Processes character-level timing data into subtitle segments
7. **Storage**: Saves audio to Supabase storage and metadata to Supabase `audio_info` table
8. **Credit Deduction**: Deducts credits for successful audio generation
9. **Response**: Returns immediate response with audio URL, metadata, and subtitle timing

## Error Handling

### Common Error Scenarios

1. **Invalid Voice ID**: Returns 400 with validation error
2. **Insufficient Credits**: Returns 402 with credit information
3. **Short Not Found**: Returns 500 with short error
4. **ElevenLabs API Error**: Returns 500 with API error details
5. **OpenAI API Error**: Returns 500 with API error details
6. **Storage Error**: Returns 500 with storage error details

### Retry Logic

For production applications, implement retry logic for:
- Network timeouts
- Temporary API failures
- Rate limiting (429 responses)

## Rate Limits

| Access Type | Rate Limit | Daily Limit |
|-------------|------------|-------------|
| Anonymous | 10 req/min | None |
| API Key | 200 req/min | 5000 req/day |

## Supported Voice IDs

The service supports all ElevenLabs voice IDs. Common examples:

- `pNInz6obpgDQGcFmaJgB` - Adam (Male, American English)
- `EXAVITQu4vr4xnSDxMaL` - Bella (Female, American English)
- `VR6AewLTigWG4xSOukaG` - Arnold (Male, American English)

## Audio Storage

Generated audio files are stored in Supabase storage with the following structure:

```
audio-files/
├── {user_id}/
│   ├── {uuid1}.mp3
│   ├── {uuid2}.mp3
│   └── ...
```

- **Bucket**: `audio-files`
- **Format**: MP3, 44.1kHz, 128kbps
- **Naming**: UUID-based for uniqueness
- **Access**: Public URLs for immediate playback
- **Metadata**: Stored in Supabase `audio_info` table with detailed information

## Testing

### Test Audio Generation

You can also generate test audio for voice testing:

```bash
curl -X POST "http://localhost:8000/test-audio" \
  -H "Content-Type: application/json" \
  -d '{
    "voice_id": "pNInz6obpgDQGcFmaJgB",
    "language": "en-US",
    "user_id": "user-uuid-123"
  }'
```

This generates a short test audio sample to verify voice quality and speed.

## Best Practices

1. **Timeout Handling**: Implement reasonable timeouts (30-60 seconds) for audio generation
2. **Error Recovery**: Implement retry logic for transient failures
3. **Credit Management**: Monitor credit usage and implement limits
4. **Caching**: Test audio is cached in MongoDB to avoid regeneration
5. **Response Handling**: Handle both success and error responses appropriately
6. **User Experience**: Show loading states during audio generation

## Support

For issues or questions:
- Check the application logs for detailed error information
- Verify API keys and configuration
- Ensure sufficient credits for audio generation
- Contact support for ElevenLabs or OpenAI API issues
