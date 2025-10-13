#!/usr/bin/env python3
"""
Simple test script for generating images using Google Vertex AI Gemini 2.5 Flash Image model.
Direct implementation without dependencies on utils functions.
"""

import os
import base64
from pathlib import Path
from google import genai
from google.genai import types
from google.oauth2 import service_account
from dotenv import load_dotenv
load_dotenv()

def create_vertex_client():
    """Create and return a Vertex AI client."""
    # Set up credentials
    project_root = Path(__file__).parent
    key_file_path = project_root / "promo-nex-ai-vertex-ai-key.json"
    
    if not os.path.exists(key_file_path):
        raise FileNotFoundError(f"Service account key file not found: {key_file_path}")
    
    # Set environment variables
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(key_file_path)
    os.environ['GOOGLE_CLOUD_PROJECT'] = 'promo-nex-ai-466218'
    
    # Create client
    client = genai.Client(
        vertexai=True,
        http_options=types.HttpOptions(api_version='v1'),
        credentials=service_account.Credentials.from_service_account_file(
            str(key_file_path),
            scopes=['https://www.googleapis.com/auth/cloud-platform']
        )
    )
    
    return client

def generate_image(client, prompt, output_path="generated_image.png"):
    """Generate an image using Gemini 2.5 Flash Image model."""
    print(f"Generating image with prompt: {prompt}")
    
    try:
        # Generate content
        response = client.models.generate_content(
            model="gemini-2.5-flash-image",
            contents=[prompt],
            config=types.GenerateContentConfig(
                response_modalities=["Image"]
            ),
        )
        
        # Extract image data
        generated_image = None
        for part in response.candidates[0].content.parts:
            if part.inline_data is not None:
                generated_image = part.inline_data.data
                break
        
        if generated_image is None:
            raise ValueError("No image was generated")
        
        # Save image
        with open(output_path, "wb") as f:
            f.write(generated_image)
        
        print(f"✅ Image saved to: {output_path}")
        print(f"Image size: {len(generated_image)} bytes")
        
        return True
        
    except Exception as e:
        print(f"❌ Error generating image: {e}")
        return False

def main():
    """Main function to test image generation."""
    print("🚀 Simple Vertex AI Image Generation Test")
    print("=" * 50)
    
    try:
        # Create client
        print("Creating Vertex AI client...")
        client = create_vertex_client()
        print("✅ Client created successfully!")
        
        # Test prompts
        test_prompts = [
            {
                "prompt": "A modern, tech-inspired thumbnail showing an automated workflow creating a storytelling video — featuring icons or visuals of Discord, AI script generation, video editing, voice narration, and YouTube upload connected by flowing lines or circuit-like paths. Include visuals of a computer screen, automation gears, and digital storytelling scenes. Bright, futuristic color palette (blue, purple, orange). Clean and minimal composition, suitable as a YouTube or portfolio thumbnail.",
                "output": "sunset_mountain.png"
            }
        ]
        
        # Generate images
        success_count = 0
        for i, test in enumerate(test_prompts, 1):
            print(f"\n--- Test {i}/3 ---")
            if generate_image(client, test["prompt"], test["output"]):
                success_count += 1
        
        # Summary
        print(f"\n{'='*50}")
        print(f"SUMMARY: {success_count}/{len(test_prompts)} images generated successfully")
        
        if success_count > 0:
            print("\nGenerated images:")
            for test in test_prompts:
                if Path(test["output"]).exists():
                    print(f"- {test['output']}")
        
    except Exception as e:
        print(f"❌ Setup failed: {e}")
        print("\nMake sure:")
        print("1. Service account key file exists: promo-nex-ai-vertex-ai-key.json")
        print("2. Google GenAI package is installed: pip install google-genai")

if __name__ == "__main__":
    main()
