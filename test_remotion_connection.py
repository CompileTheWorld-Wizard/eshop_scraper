"""
Test script to check if the Remotion server is running and accessible.
"""

import httpx
import sys

REMOTION_URL = "http://localhost:5050"

def test_remotion_connection():
    """Test connection to Remotion server."""
    print("=" * 60)
    print("Testing Remotion Server Connection")
    print("=" * 60)
    print(f"\nRemot ion Server URL: {REMOTION_URL}")
    print("\nChecking connection...")
    
    try:
        # Try to connect to Remotion server
        with httpx.Client(timeout=5) as client:
            # Test health endpoint
            print(f"\n1. Testing {REMOTION_URL}/health...")
            try:
                response = client.get(f"{REMOTION_URL}/health")
                print(f"   Status: {response.status_code}")
                print(f"   Response: {response.text[:200]}")
            except Exception as e:
                print(f"   ❌ Health endpoint failed: {e}")
            
            # Test root endpoint
            print(f"\n2. Testing {REMOTION_URL}/...")
            try:
                response = client.get(REMOTION_URL)
                print(f"   Status: {response.status_code}")
                print(f"   Response: {response.text[:200]}")
            except Exception as e:
                print(f"   ❌ Root endpoint failed: {e}")
            
            # Test videos endpoint (should return 405 Method Not Allowed for GET)
            print(f"\n3. Testing {REMOTION_URL}/videos (GET)...")
            try:
                response = client.get(f"{REMOTION_URL}/videos")
                print(f"   Status: {response.status_code}")
                print(f"   Response: {response.text[:200]}")
            except Exception as e:
                print(f"   ❌ Videos endpoint failed: {e}")
        
        print("\n" + "=" * 60)
        print("✅ Connection test completed!")
        print("=" * 60)
        print("\nIf you see 404 errors above, your Remotion server might not")
        print("be running on localhost:5050, or the endpoints are different.")
        print("\nPlease check:")
        print("1. Is Remotion server running?")
        print("2. Is it on localhost:5050?")
        print("3. What are the actual endpoint paths?")
        return True
        
    except httpx.ConnectError as e:
        print("\n" + "=" * 60)
        print("❌ CANNOT CONNECT TO REMOTION SERVER")
        print("=" * 60)
        print(f"\nError: {e}")
        print("\nReasons:")
        print("1. Remotion server is not running")
        print("2. Remotion server is not on localhost:5050")
        print("3. Firewall is blocking the connection")
        print("\nSolution:")
        print("1. Start your Remotion server")
        print("2. Make sure it's running on http://localhost:5050")
        print("3. Check firewall settings")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    success = test_remotion_connection()
    sys.exit(0 if success else 1)
