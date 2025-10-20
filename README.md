# E-commerce Scraper API

A comprehensive, high-performance API for scraping product information from e-commerce websites with intelligent platform detection, AI-powered content generation, and video processing capabilities.

## 📋 Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Installation](#installation)
- [Configuration](#configuration)
- [API Endpoints](#api-endpoints)
- [Core Features](#core-features)
- [AI Generation](#ai-generation)
- [Video Processing](#video-processing)
- [Security](#security)
- [Database Schema](#database-schema)
- [Usage Examples](#usage-examples)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [License](#license)

## 🚀 Overview

The E-commerce Scraper API is a sophisticated system that provides:

- **Intelligent Web Scraping**: Automatic platform detection and extraction
- **AI-Powered Content Generation**: Image, video, and audio generation using Vertex AI, Flux API, and ElevenLabs
- **Video Processing Pipeline**: Complete video creation and editing workflow
- **Audio Generation**: AI-powered audio script generation and voice synthesis
- **Comprehensive Security**: Rate limiting, IP blocking, and API key authentication
- **Real-time Task Management**: Asynchronous processing with progress tracking
- **Multi-platform Support**: Amazon, eBay, Shopify, WooCommerce, and more

## 🏗️ Architecture

### Core Components

#### 1. Browser Manager (`app/browser_manager.py`)
- Handles Chrome browser setup and page fetching
- Manages image/video blocking for faster scraping
- Configures proxy and user agent rotation
- Implements stealth browsing techniques

#### 2. Extractors (`app/extractors/`)
- **BaseExtractor**: Abstract base class for all extractors
- **GenericExtractor**: Handles unsupported platforms using common selectors
- **Platform-specific Extractors**: Amazon, eBay, Shopify, WooCommerce, etc.
- **Factory Pattern**: Automatic extractor selection based on platform detection

#### 3. Services (`app/services/`)
- **ScrapingService**: Orchestrates the scraping process
- **ImageAnalysisService**: AI-powered image analysis using OpenAI Vision
- **VideoGenerationService**: AI video generation with Vertex AI
- **ScenarioGenerationService**: AI scenario creation for videos
- **SaveScenarioService**: Scenario persistence and image generation
- **AudioGenerationService**: AI-powered audio script generation and voice synthesis
- **TestAudioService**: Test audio generation for voice testing
- **SessionService**: Task session management
- **SchedulerService**: Background task cleanup and maintenance

#### 4. AI Generation Utilities (`app/utils/`)
- **Vertex AI Integration**: Image-to-video and text-to-image generation
- **Vertex AI Integration**: Advanced AI model access
- **Supabase Utils**: Database and storage operations
- **Task Management**: Background processing and status tracking

### Data Flow

```
URL Input → Platform Detection → Extractor Selection → Data Extraction → AI Processing → Storage → Response
```

## 📦 Installation

### Prerequisites

- Python 3.8+
- Chrome browser
- FFmpeg (for video processing)
- MongoDB (for task management)
- Supabase account (for database and storage)

### Quick Start

1. **Clone the repository:**
```bash
git clone <repository-url>
cd eshop-scraper
```

2. **Install dependencies:**
```bash
pip install -r requirements.txt
```

3. **Set up environment variables:**
```bash
cp env_example.txt .env
# Edit .env with your configuration
```

4. **Start the server:**
```bash
python -m app.main
```

Or use the provided scripts:
```bash
# Windows
start_server.bat

# Linux
./start_server_linux.sh
```

## ⚙️ Configuration

### Environment Variables

Create a `.env` file with these essential settings:

```bash
# Server Configuration
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=INFO

# Browser Settings
ROTATE_PROXIES=True
ROTATE_USER_AGENTS=True
PLAYWRIGHT_HEADLESS=True

# Timeout Settings
BROWSER_NETWORK_IDLE_TIMEOUT=5000
BROWSER_DOM_LOAD_TIMEOUT=10000
BROWSER_ADDITIONAL_WAIT=2000
BROWSER_MAX_RETRIES=2

# Database Configuration
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=eshop_scraper

# Supabase Configuration
SUPABASE_URL=your_supabase_url
SUPABASE_ANON_KEY=your_supabase_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key

# AI Services
OPENAI_API_KEY=your_openai_api_key
ELEVENLABS_API_KEY=your_elevenlabs_api_key
ELEVENLABS_DEFAULT_OUTPUT_FORMAT=mp3_44100_128
ELEVENLABS_DEFAULT_MODEL=eleven_multilingual_v2

# Security (Optional)
API_KEY_1=your_secure_api_key_here
API_KEY_1_NAME=Premium User
API_KEY_1_RATE_LIMIT=200
API_KEY_1_DAILY_LIMIT=5000
```

### Logging System

The application uses comprehensive logging:

- **Console Output**: INFO level and above
- **File Logs**: 
  - `logs/app.log` - All logs with detailed formatting
  - `logs/errors.log` - Error-level logs only
  - `logs/security.log` - Security-related events

Log files are automatically rotated when they reach the configured size limit.

## 🔌 API Endpoints

### Core Scraping Endpoints

#### Start Scraping Task
```http
POST /api/v1/scrape
Content-Type: application/json

{
  "url": "https://www.amazon.com/dp/B08N5WRWNW",
  "force_refresh": false,
  "block_images": true,
  "target_language": "en"
}
```

#### Get Task Status
```http
GET /api/v1/tasks/{task_id}
```

#### Get Task Result
```http
GET /api/v1/tasks/{task_id}/result
```

### AI Generation Endpoints

#### Image Analysis
```http
POST /api/v1/image/analyze
Content-Type: application/json

{
  "product_id": "uuid-of-the-product",
  "user_id": "uuid-of-the-user"
}
```

#### Video Generation
```http
POST /api/video/generate
Content-Type: application/json

{
  "scene_id": "uuid-of-scene",
  "user_id": "uuid-of-user"
}
```

#### Scenario Generation
```http
POST /scenario/generate
Content-Type: application/json

{
  "product_id": "required-product-id",
  "user_id": "required-user-id",
  "style": "trendy-influencer-vlog",
  "mood": "energetic",
  "video_length": 30,
  "resolution": "720:1280",
  "target_language": "en-US"
}
```

#### Test Audio Generation
```http
POST /test-audio
Content-Type: application/json

{
  "voice_id": "elevenlabs-voice-id",
  "language": "en-US",
  "user_id": "uuid-of-the-user"
}
```

#### Audio Generation
```http
POST /generate-audio
Content-Type: application/json

{
  "voice_id": "elevenlabs-voice-id",
  "user_id": "uuid-of-the-user",
  "scenario_id": "uuid-of-the-scenario"
}
```

### Video Processing Endpoints

#### Process Video
```http
POST /video/process
Content-Type: application/json

{
  "video_urls": ["https://example.com/video1.mp4"],
  "audio_data": "base64_encoded_audio_data",
  "subtitle_text": "Your subtitle text here",
  "output_resolution": "1920x1080"
}
```

#### Short Finalization
```http
POST /shorts/finalize
Content-Type: application/json

{
  "user_id": "uuid-string",
  "short_id": "uuid-string",
  "upscale": false
}
```

### Session Management

#### Get Sessions
```http
GET /api/v1/sessions/{short_id}
```

#### Get Session by Task
```http
GET /api/v1/sessions/task/{task_id}
```

### Security Endpoints

#### Get Security Statistics
```http
GET /api/v1/security/stats
```

#### Get Security Status
```http
GET /api/v1/security/status
```

## ✨ Core Features

### Intelligent Platform Detection

The system automatically detects e-commerce platforms and applies appropriate extraction strategies:

- **Amazon**: Full support with ASIN extraction, ratings, reviews
- **eBay**: Comprehensive product data extraction
- **Shopify**: Generic Shopify store support
- **WooCommerce**: WordPress e-commerce support
- **Generic**: Common selectors for unsupported platforms

### Asynchronous Processing

All operations use a polling pattern for better scalability:

1. **Start Task**: API returns immediately with task ID
2. **Poll Status**: Check progress with detailed updates
3. **Get Results**: Retrieve final results when completed

### Task Management

- **Real-time Progress**: Detailed step-by-step progress updates
- **Error Handling**: Comprehensive error reporting and retry logic
- **Session Tracking**: Task lifecycle management
- **Automatic Cleanup**: Old tasks are automatically removed

## 🤖 AI Generation

### Vertex AI Integration

The system includes powerful AI generation capabilities:

#### Image-to-Video Generation
   ```python
   from app.utils.vertex_utils import generate_video_with_prompt_and_image
   
   result = await generate_video_with_prompt_and_image(
       prompt_image="product.jpg",
       prompt_text="Show the product rotating with elegant lighting",
    duration=5,
    ratio="1280:720"
)
```

#### Text-to-Image Generation
```python
from app.utils.vertex_utils import generate_image_with_recontext_and_upscale

result = await generate_image_with_recontext_and_upscale(
    prompt_text="A beautiful sunset over a mountain landscape",
    ratio="1920:1080"
)
```

#### Styled Image Generation
```python
from app.utils.flux_utils import flux_manager

result = flux_manager.generate_image_with_prompt_and_image(
    prompt_text="@reference in the style of @style",
    reference_image="path/to/reference.jpg",
    style_image="path/to/style.jpg",
    ratio="1024:1024"
)
```

### Supported Models and Formats

#### Video Generation
- **Model**: gen4_turbo
- **Durations**: 3, 4, 5, 6, 7, 8, 9, 10 seconds
- **Ratios**: 1280:720, 1920:1080, 1080:1920, 720:1280, 1024:1024, 1920:1920

#### Image Generation
- **Model**: gen4_image
- **Ratios**: 1280:720, 1920:1080, 1080:1920, 720:1280, 1024:1024, 1920:1920

### Resolution Mapping System

The video generation service automatically maps video resolutions to optimal image generation ratios:

| Video Resolution | Video Ratio | Image Ratio | Description |
|------------------|-------------|-------------|-------------|
| `1280:720` | `1280:720` | `1920:1080` | 16:9 Landscape → Full HD |
| `720:1280` | `720:1280` | `1080:1920` | 9:16 Portrait → Full HD Portrait |
| `960:960` | `960:960` | `1024:1024` | 1:1 Square → Full HD Square |

## 🎵 Audio Generation

### Audio Generation Pipeline

The audio generation service provides AI-powered audio content creation with the following workflow:

1. **Test Audio Check**: Checks MongoDB for existing test audio for the voice
2. **Test Audio Generation**: If not found, generates test audio using ElevenLabs
3. **Speed Analysis**: Analyzes test audio to determine words per minute (WPM)
4. **Script Generation**: Uses OpenAI to create contextual audio scripts based on:
   - Scenario information (title, description, duration, style, mood)
   - Detected speaking rate from test audio
   - Product information from the scenario
5. **Final Audio Generation**: Creates final audio using ElevenLabs with the generated script

### Audio Generation Features

- **Intelligent Script Generation**: AI creates contextually appropriate scripts based on scenario details
- **Voice Speed Analysis**: Automatically detects optimal speaking rate for each voice
- **Multi-language Support**: Supports multiple languages for test audio generation
- **Caching System**: Reuses existing test audio to optimize performance
- **Credit Integration**: Integrates with the credit system for usage tracking
- **Asynchronous Processing**: Background task processing with progress updates

### Supported Languages

The test audio service supports the following languages:

- **English**: en-US, en-CA, en-GB
- **Spanish**: es, es-MX
- **Portuguese**: pt-BR
- **French**: fr
- **German**: de
- **Dutch**: nl
- **Chinese**: zh
- **Japanese**: ja
- **Arabic**: ar

### Audio Storage Structure

- **Test Audio**: `test-audios/{voice_id}_{language}_{uuid}.mp3`
- **Generated Audio**: `generated-content/generated-audio/{voice_id}_{uuid}.mp3`

## 🎬 Video Processing

### Video Generation Pipeline

1. **Scene Configuration**: Fetch scene data and prompts
2. **Image Generation**: Generate AI images using Vertex AI and Flux API
3. **Video Creation**: Create videos from generated images
4. **Storage**: Secure storage with signed URLs for videos
5. **Database Update**: Update scene records with generated URLs

### Video Processing Features

- **Merge Videos**: Combine multiple videos in sequence
- **Audio Integration**: Add audio from base64 encoded data
- **Subtitle Support**: Embed subtitles directly into videos
- **Resolution Handling**: Support for various video resolutions
- **Watermarking**: Automatic watermarking for free plan users
- **Upscaling**: Optional video quality enhancement

### Storage Structure

- **Images**: `generated-content/{user_id}/{uuid}.png` (Public URLs)
- **Videos**: `video-files/{user_id}/{uuid}.mp4` (Signed URLs, 1-hour expiration)
- **Thumbnails**: `thumbnail_images/{user_id}/{uuid}.png`
- **Final Videos**: `final_videos/{short_id}/{uuid}.mp4`

## 🔒 Security

### Authentication & Authorization

#### API Key Authentication (Optional)
- **Bearer Token**: Use API keys for enhanced rate limits
- **Multiple Keys**: Support for up to 10 different API keys
- **Custom Limits**: Individual rate limits per API key
- **Demo Mode**: Includes demo key for testing

#### Rate Limiting
- **Anonymous Users**: 10 requests per minute
- **API Key Users**: Customizable limits (default: 100 requests/minute)
- **Daily Limits**: Configurable daily request limits
- **Concurrent Limits**: Maximum 5 concurrent requests per IP

### Security Features

#### IP Blocking & Monitoring
- **Automatic Blocking**: Suspicious IPs blocked for 1 hour
- **Activity Detection**: Suspicious patterns marked for 30 minutes
- **Real-time Monitoring**: All security events logged

#### Request Validation
- **URL Validation**: Only allowed domains can be scraped
- **User Agent Validation**: Blocks suspicious user agents
- **Length Limits**: Maximum URL length of 2048 characters
- **Domain Whitelist**: Only supported e-commerce domains

### Supported Domains

- Amazon (amazon.com, amazon.co.uk, amazon.de, amazon.fr, amazon.it, amazon.es)
- eBay (ebay.com, ebay.co.uk, ebay.de, ebay.fr, ebay.it, ebay.es)
- Bol.com, Cdiscount, Otto.de, JD.com
- Shopify stores, WooCommerce sites

### Rate Limits

| Access Type | Rate Limit | Daily Limit | Notes |
|-------------|------------|-------------|-------|
| Anonymous | 10 req/min | None | Basic access |
| Demo Key | 100 req/min | 1000 req/day | For testing |
| API Key 1 | 200 req/min | 5000 req/day | Premium user |
## 🗄️ Database Schema

### Core Tables

#### Products Table
```sql
CREATE TABLE products (
    id UUID PRIMARY KEY,
    product_id TEXT UNIQUE,
    title TEXT,
    price DECIMAL,
    currency TEXT,
    description TEXT,
    images JSONB,
    availability TEXT,
    rating DECIMAL,
    review_count INTEGER,
    seller TEXT,
    brand TEXT,
    sku TEXT,
    category TEXT,
    specifications JSONB,
    raw_data JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

#### Video Scenarios Table
```sql
CREATE TABLE video_scenarios (
    id UUID PRIMARY KEY,
    short_id UUID,
    title TEXT,
    description TEXT,
    script TEXT,
    scene_count INTEGER,
    estimated_duration INTEGER,
    metadata JSONB,
    resolution TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### Video Scenes Table
```sql
CREATE TABLE video_scenes (
    id UUID PRIMARY KEY,
    scenario_id UUID REFERENCES video_scenarios(id),
    scene_number INTEGER,
    image_prompt TEXT,
    visual_prompt TEXT,
    product_reference_image_url TEXT,
    image_url TEXT,
    generated_video_url TEXT,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

#### Shorts Table
```sql
CREATE TABLE shorts (
    id UUID PRIMARY KEY,
    user_id UUID,
    title TEXT,
    thumbnail_url TEXT,
    video_url TEXT,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### MongoDB Collections

#### Tasks Collection
```json
{
  "_id": "ObjectId",
  "task_id": "string",
  "task_type": "string",
  "status": "string",
  "progress": "number",
  "user_id": "string",
  "metadata": "object",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

#### Sessions Collection
```json
{
  "_id": "ObjectId",
  "short_id": "string",
  "task_type": "string",
  "task_id": "string",
  "user_id": "string",
  "status": "string",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

## 📱 Usage Examples

### Python Client - Complete Workflow

```python
import requests
import time

class EShopScraperClient:
    def __init__(self, base_url="http://localhost:8000", api_key=None):
        self.base_url = base_url
        self.headers = {"Content-Type": "application/json"}
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"
    
    def scrape_product(self, url):
        """Scrape a product and return results"""
        response = requests.post(
            f"{self.base_url}/api/v1/scrape",
            headers=self.headers,
            json={"url": url, "target_language": "en"}
        )
        
        task_data = response.json()
        task_id = task_data["task_id"]
        
        # Poll for completion
        while True:
            status_response = requests.get(
                f"{self.base_url}/api/v1/tasks/{task_id}/result"
            )
            result = status_response.json()
            
            if result["status"] in ["completed", "failed"]:
                return result
            
            time.sleep(2)
    
    def generate_audio(self, voice_id, user_id, scenario_id):
        """Generate audio for a scenario"""
        response = requests.post(
            f"{self.base_url}/generate-audio",
            headers=self.headers,
            json={
                "voice_id": voice_id,
                "user_id": user_id,
                "scenario_id": scenario_id
            }
        )
        
        task_data = response.json()
        task_id = task_data["task_id"]
        
        # Poll for completion
        while True:
            status_response = requests.get(
                f"{self.base_url}/api/v1/tasks/{task_id}/result"
            )
            result = status_response.json()
            
            if result["status"] in ["completed", "failed"]:
                return result
            
            time.sleep(2)

# Usage example
client = EShopScraperClient(api_key="your_api_key_here")

# Scrape a product
product_result = client.scrape_product("https://www.amazon.com/dp/B08N5WRWNW")
print(f"Product: {product_result['product_info']['title']}")
print(f"Price: {product_result['product_info']['price']}")

# Generate audio for a scenario
audio_result = client.generate_audio(
    voice_id="elevenlabs-voice-id",
    user_id="user-uuid",
    scenario_id="scenario-uuid"
)
print(f"Audio URL: {audio_result['audio_url']}")
print(f"Script: {audio_result['script']}")
```

### cURL Examples

#### Basic Scraping
```bash
# Start scraping
curl -X POST "http://localhost:8000/api/v1/scrape" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.amazon.com/dp/B08N5WRWNW",
    "target_language": "en"
  }'

# Check status
curl "http://localhost:8000/api/v1/tasks/{task_id}/result"
```

#### Audio Generation
```bash
# Generate audio for a scenario
curl -X POST "http://localhost:8000/generate-audio" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_secure_api_key_here" \
  -d '{
    "voice_id": "elevenlabs-voice-id",
    "user_id": "user-uuid",
    "scenario_id": "scenario-uuid"
  }'

# Check audio generation status
curl "http://localhost:8000/api/v1/tasks/{task_id}/result"
```

#### With API Key
```bash
# Using Bearer token authentication
curl -X POST "http://localhost:8000/api/v1/scrape" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_secure_api_key_here" \
  -d '{
    "url": "https://www.amazon.com/dp/B08N5WRWNW",
    "target_language": "en"
  }'
```

## 🔧 Troubleshooting

### Common Issues

#### 1. Browser Not Starting
- **Cause**: Chrome not installed or not accessible
- **Solution**: Install Chrome and ensure it's in PATH
- **Check**: Verify Chrome installation with `chrome --version`

#### 2. Platform Not Detected
- **Cause**: Platform patterns not configured correctly
- **Solution**: Check platform detection patterns in `ScrapingService`
- **Debug**: Enable debug logging to see detection process

#### 3. Extraction Failures
- **Cause**: CSS selectors outdated or incorrect
- **Solution**: Update selectors in platform extractor
- **Check**: Verify page structure hasn't changed

#### 4. Timeout Errors
- **Cause**: Slow-loading sites or network issues
- **Solutions**:
  - Increase `BROWSER_NETWORK_IDLE_TIMEOUT` for slow sites
   - Increase `BROWSER_DOM_LOAD_TIMEOUT` for complex pages
   - Increase `BROWSER_MAX_RETRIES` for unreliable connections
   - Check network connectivity and proxy settings

#### 5. AI Generation Failures
- **Cause**: API key issues or service unavailability
- **Solutions**:
  - Verify API keys are correct and active
  - Check service status (Vertex AI, OpenAI, ElevenLabs)
  - Monitor API quotas and billing status
  - Implement proper retry logic

### Debug Logging

Enable detailed logging for troubleshooting:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Log Analysis

```bash
# View all logs
tail -f logs/app.log

# View only errors
tail -f logs/errors.log

# View security events
tail -f logs/security.log

# Monitor specific operations
grep "Video generation" logs/app.log
grep "ERROR" logs/app.log | grep "video_generation"
```

## 🛠️ Development

### Adding a New Platform

1. **Create Extractor Class:**
```python
from app.extractors.base import BaseExtractor

class NewPlatformExtractor(BaseExtractor):
    def extract_title(self):
        # Platform-specific title extraction
        return self._extract_text('h1.product-title')
    
    def extract_price(self):
        # Platform-specific price extraction
        return self._extract_price('.price-current')
    
    def extract_description(self):
        # Platform-specific description extraction
        return self._extract_text('.product-description')
    
    # ... implement other required methods
```

2. **Add to Factory:**
```python
# In app/extractors/factory.py
_platform_extractors = {
    'amazon': AmazonExtractor,
    'ebay': EbayExtractor,
    'newplatform': NewPlatformExtractor,  # Add your extractor
}
```

3. **Add Platform Detection:**
```python
# In app/services/scraping_service.py
def _detect_platform(self, url, html_content):
    # Add detection patterns for your platform
    if 'newplatform.com' in url:
        return 'newplatform'
    # ... existing detection logic
```

### Testing

#### Run Tests
```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test files
python -m pytest tests/test_scraping.py -v
python -m pytest tests/test_video_generation.py -v

# Run with coverage
python -m pytest tests/ --cov=app --cov-report=html
```

#### Manual Testing
```bash
# Test GUI
python gui_test.py

# Test specific endpoints
python test.py

# Test session feature
python test_session_feature.py
```

### Code Structure

```
app/
├── __init__.py
├── main.py                 # Application entry point
├── config.py              # Configuration management
├── models.py              # Pydantic models
├── browser_manager.py      # Browser automation
├── stealth_browser.py     # Stealth browsing techniques
├── security.py            # Security middleware
├── logging_config.py      # Logging configuration
├── api/
│   ├── __init__.py
│   └── routes.py          # API route definitions
├── extractors/
│   ├── __init__.py
│   ├── base.py            # Base extractor class
│   ├── factory.py         # Extractor factory
│   ├── amazon.py          # Amazon-specific extractor
│   ├── ebay.py            # eBay-specific extractor
│   ├── shopify.py         # Shopify extractor
│   ├── woocommerce.py     # WooCommerce extractor
│   └── generic.py         # Generic extractor
├── services/
│   ├── __init__.py
│   ├── scraping_service.py           # Main scraping service
│   ├── image_analysis_service.py     # AI image analysis
│   ├── video_generation_service.py  # AI video generation
│   ├── scenario_generation_service.py # AI scenario creation
│   ├── save_scenario_service.py      # Scenario persistence
│   ├── session_service.py           # Session management
│   ├── scheduler_service.py         # Background tasks
│   ├── cache_service.py             # Caching service
│   ├── merging_service.py           # Video merging
│   ├── test_audio_service.py        # Audio testing
│   └── audio_generation_service.py  # AI audio generation
└── utils/
    ├── __init__.py
    ├── task_management.py      # Task management utilities
    ├── supabase_utils.py       # Supabase integration
    ├── flux_utils.py           # Flux API integration
    ├── vertex_utils.py         # Vertex AI integration
    ├── proxy_management.py     # Proxy handling
    ├── user_agent_management.py # User agent rotation
    ├── currency_utils.py       # Currency conversion
    ├── credit_utils.py         # Credit management
    ├── flux_utils.py           # Flux API utilities
    ├── structured_data.py      # Data structuring
    ├── text_processing.py      # Text processing
    └── url_utils.py            # URL utilities
```

### Contributing

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/new-feature`
3. **Make your changes**: Follow the existing code style
4. **Add tests**: Ensure your changes are tested
5. **Update documentation**: Update relevant documentation
6. **Submit a pull request**: Provide a clear description of changes

### Code Style

- **Python**: Follow PEP 8 guidelines
- **Type Hints**: Use type hints for better code clarity
- **Documentation**: Add docstrings for all public methods
- **Error Handling**: Implement comprehensive error handling
- **Logging**: Use appropriate logging levels

## 📄 License

This project is licensed under the MIT License. See the LICENSE file for details.

## 🤝 Support

### Getting Help

1. **Check Documentation**: Review this README and specific feature documentation
2. **Check Logs**: Detailed error information in application logs
3. **Verify Configuration**: Environment variables and database setup
4. **Test Components**: Use provided test scripts
5. **Monitor Progress**: Real-time status updates via API

### Community Resources

- **Issues**: GitHub issue tracking for bug reports and feature requests
- **Discussions**: Community forums and Q&A
- **Contributions**: Pull request guidelines and development setup

### Additional Resources

- **API Documentation**: Swagger/OpenAPI specifications
- **Code Examples**: GitHub repository with working samples
- **Troubleshooting Guide**: Common issues and solutions
- **Performance Tips**: Optimization recommendations

---

**Last Updated**: January 2025  
**Version**: 2.1.0  
**Status**: Production Ready ✅ 