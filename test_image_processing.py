"""
Test script for Image Processing Service

This script tests the background removal and image compositing functionality.
Run this script to verify the service is working correctly.

Usage:
    python test_image_processing.py
"""

import asyncio
import os
from pathlib import Path
import sys

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent))

from app.services.image_processing_service import image_processing_service
from app.utils.supabase_utils import supabase_manager
from app.logging_config import get_logger

logger = get_logger(__name__)

# Test configuration
TEST_USER_ID = "test-user-123"
TEST_SCENE_ID = "test-scene-456"

# Sample image URLs (replace with your own test images)
SAMPLE_PRODUCT_IMAGE = "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=400"  # Sample product image
SAMPLE_BACKGROUND_IMAGE = "https://images.unsplash.com/photo-1557683316-973673baf926?w=800"  # Sample background


def print_section(title: str):
    """Print a section header."""
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60 + "\n")


def test_supabase_connection():
    """Test Supabase connection."""
    print_section("Test 1: Supabase Connection")
    
    if supabase_manager.is_connected():
        print("✅ Supabase connection successful")
        return True
    else:
        print("❌ Supabase connection failed")
        print("   Please check your .env file and Supabase credentials")
        return False


def test_remove_background():
    """Test background removal functionality."""
    print_section("Test 2: Background Removal")
    
    print(f"Testing with sample product image: {SAMPLE_PRODUCT_IMAGE}")
    print("Removing background using Remove.bg API...")
    
    try:
        result = image_processing_service.remove_background(
            image_url=SAMPLE_PRODUCT_IMAGE,
            scene_id=TEST_SCENE_ID
        )
        
        if result['success']:
            print("✅ Background removal successful")
            print(f"   Background-removed image URL: {result['image_url']}")
            return result['image_url']
        else:
            print(f"❌ Background removal failed: {result['error']}")
            return None
            
    except Exception as e:
        print(f"❌ Exception during background removal: {e}")
        return None


def test_composite_images(overlay_url: str):
    """Test image compositing functionality."""
    print_section("Test 3: Image Compositing")
    
    if not overlay_url:
        print("⚠️  Skipping composite test - no overlay image available")
        return None
    
    print(f"Background image: {SAMPLE_BACKGROUND_IMAGE}")
    print(f"Overlay image: {overlay_url}")
    print("Compositing images...")
    
    try:
        result = image_processing_service.composite_images(
            background_url=SAMPLE_BACKGROUND_IMAGE,
            overlay_url=overlay_url,
            scene_id=TEST_SCENE_ID,
            user_id=TEST_USER_ID
        )
        
        if result['success']:
            print("✅ Image compositing successful")
            print(f"   Composited image URL: {result['image_url']}")
            return result['image_url']
        else:
            print(f"❌ Image compositing failed: {result['error']}")
            return None
            
    except Exception as e:
        print(f"❌ Exception during image compositing: {e}")
        return None


def test_replace_background():
    """Test complete background replacement workflow."""
    print_section("Test 4: Complete Background Replacement")
    
    print(f"Product image: {SAMPLE_PRODUCT_IMAGE}")
    print(f"New background: {SAMPLE_BACKGROUND_IMAGE}")
    print("Performing complete background replacement workflow...")
    
    try:
        result = image_processing_service.replace_background(
            product_image_url=SAMPLE_PRODUCT_IMAGE,
            background_image_url=SAMPLE_BACKGROUND_IMAGE,
            scene_id=TEST_SCENE_ID,
            user_id=TEST_USER_ID
        )
        
        if result['success']:
            print("✅ Background replacement successful")
            print(f"   Final image URL: {result['image_url']}")
            return result['image_url']
        else:
            print(f"❌ Background replacement failed: {result['error']}")
            return None
            
    except Exception as e:
        print(f"❌ Exception during background replacement: {e}")
        return None


def test_api_key():
    """Test Remove.bg API key configuration."""
    print_section("Test 0: Configuration Check")
    
    api_key = os.getenv("REMOVEBG_API_KEY", "")
    
    if api_key:
        print(f"✅ Remove.bg API key found: {api_key[:10]}...")
        return True
    else:
        print("❌ Remove.bg API key not found in .env file")
        print("   Please add REMOVEBG_API_KEY to your .env file")
        return False


def main():
    """Run all tests."""
    print("\n" + "╔" + "="*58 + "╗")
    print("║" + " "*10 + "Image Processing Service Test Suite" + " "*12 + "║")
    print("╚" + "="*58 + "╝")
    
    # Test 0: Check API key
    if not test_api_key():
        print("\n⚠️  Please configure Remove.bg API key before running tests")
        return
    
    # Test 1: Check Supabase connection
    if not test_supabase_connection():
        print("\n⚠️  Cannot proceed without Supabase connection")
        return
    
    # Test 2: Remove background
    print("\n⚠️  Note: This test will use 1 Remove.bg API call")
    input("Press Enter to continue or Ctrl+C to cancel...")
    
    overlay_url = test_remove_background()
    
    # Test 3: Composite images
    if overlay_url:
        input("\nPress Enter to test image compositing...")
        test_composite_images(overlay_url)
    
    # Test 4: Complete workflow
    print("\n⚠️  Note: This test will use 1 additional Remove.bg API call")
    input("Press Enter to test complete workflow or Ctrl+C to cancel...")
    
    test_replace_background()
    
    # Summary
    print_section("Test Summary")
    print("All tests completed!")
    print("\nNext steps:")
    print("1. Check the Supabase storage to verify images were uploaded")
    print("2. Integrate the API endpoints into your frontend")
    print("3. Test with real product images from your video_scenes table")
    print("\nFor detailed documentation, see:")
    print("  - app/services/IMAGE_PROCESSING_README.md")
    print("  - IMPLEMENTATION_SUMMARY.md")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests cancelled by user")
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        logger.error(f"Test script error: {e}", exc_info=True)
