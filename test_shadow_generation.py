"""
Test script for Shadow Generation API endpoint
"""

import requests
import json
from pprint import pprint

# Configuration
API_BASE_URL = "http://localhost:8000"
ENDPOINT = f"{API_BASE_URL}/image/add-shadow"

# Test data
test_request = {
    "image_url": "https://example.com/product-image.jpg",
    "product_description": "A sleek modern smartwatch with black metal band and OLED display, featuring fitness tracking and heart rate monitoring",
    "user_id": "test_user_123"
}

def test_shadow_generation():
    """Test the shadow generation endpoint"""
    print("=" * 60)
    print("Testing Shadow Generation API")
    print("=" * 60)
    
    print("\n1. Request Details:")
    print(f"   URL: {ENDPOINT}")
    print(f"   Image URL: {test_request['image_url']}")
    print(f"   Description: {test_request['product_description']}")
    print(f"   User ID: {test_request['user_id']}")
    
    print("\n2. Sending request to API...")
    
    try:
        response = requests.post(
            ENDPOINT,
            json=test_request,
            headers={"Content-Type": "application/json"},
            timeout=60  # Shadow generation may take some time
        )
        
        print(f"\n3. Response Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("\n4. Response Body:")
            pprint(result, indent=2)
            
            if result.get("success"):
                print("\n✅ SUCCESS!")
                print(f"   New image URL: {result.get('image_url')}")
                print(f"   Message: {result.get('message')}")
            else:
                print("\n❌ FAILED!")
                print(f"   Error: {result.get('error')}")
                
        else:
            print("\n❌ API ERROR!")
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.text}")
            
    except requests.exceptions.Timeout:
        print("\n❌ REQUEST TIMEOUT!")
        print("   The request took too long. Shadow generation may still be processing.")
        
    except requests.exceptions.ConnectionError:
        print("\n❌ CONNECTION ERROR!")
        print("   Could not connect to the API. Make sure the server is running.")
        
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR!")
        print(f"   Error: {str(e)}")
    
    print("\n" + "=" * 60)


def test_with_custom_data(image_url: str, description: str, user_id: str):
    """Test with custom data"""
    custom_request = {
        "image_url": image_url,
        "product_description": description,
        "user_id": user_id
    }
    
    print("=" * 60)
    print("Testing Shadow Generation API (Custom Data)")
    print("=" * 60)
    
    print("\nRequest:")
    pprint(custom_request, indent=2)
    
    try:
        response = requests.post(
            ENDPOINT,
            json=custom_request,
            headers={"Content-Type": "application/json"},
            timeout=60
        )
        
        print(f"\nStatus Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("\nResponse:")
            pprint(result, indent=2)
            
            if result.get("success"):
                print(f"\n✅ Shadow added successfully!")
                print(f"New image: {result.get('image_url')}")
            else:
                print(f"\n❌ Failed: {result.get('error')}")
        else:
            print(f"\n❌ API Error: {response.text}")
            
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    print("\n🧪 Shadow Generation API Test Script\n")
    
    # Run basic test
    test_shadow_generation()
    
    # Uncomment to test with your own data:
    # test_with_custom_data(
    #     image_url="https://your-image-url.com/image.jpg",
    #     description="Your product description here",
    #     user_id="your_user_id"
    # )
