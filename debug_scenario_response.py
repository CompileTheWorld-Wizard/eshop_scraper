"""
Debug script to inspect scenario generation responses
Run this to see exactly what the backend is returning
"""
import requests
import json
import time

API_BASE = "http://localhost:8000/api/v1"

def check_scenario_response(task_id):
    """Check the scenario generation task response"""
    print(f"\n{'='*80}")
    print(f"Checking scenario generation task: {task_id}")
    print(f"{'='*80}\n")
    
    response = requests.get(f"{API_BASE}/scenario/generate/tasks/{task_id}")
    
    if response.status_code != 200:
        print(f"❌ Error: {response.status_code}")
        print(response.text)
        return
    
    data = response.json()
    
    print(f"Task Status: {data.get('status')}")
    print(f"Progress: {data.get('progress')}%")
    print(f"Current Step: {data.get('current_step')}")
    print(f"Message: {data.get('message')}\n")
    
    # Check scenario data
    scenario = data.get('scenario')
    if not scenario:
        print("⚠️  No scenario data in response yet")
        return
    
    print(f"📋 Scenario Details:")
    print(f"   Title: {scenario.get('title')}")
    print(f"   Description: {scenario.get('description')}")
    print(f"   Total Duration: {scenario.get('total_duration')} seconds")
    print(f"   Style: {scenario.get('style')}")
    print(f"   Mood: {scenario.get('mood')}")
    print(f"   Resolution: {scenario.get('resolution')}\n")
    
    # Check scenes
    scenes = scenario.get('scenes', [])
    print(f"🎬 SCENES COUNT: {len(scenes)}")
    print(f"{'='*80}\n")
    
    if len(scenes) == 0:
        print("❌ WARNING: No scenes in the scenario!")
    else:
        for i, scene in enumerate(scenes, 1):
            print(f"Scene {i}:")
            print(f"   ID: {scene.get('scene_id')}")
            print(f"   Number: {scene.get('scene_number')}")
            print(f"   Duration: {scene.get('duration')} seconds")
            print(f"   Description: {scene.get('description', '')[:80]}...")
            print(f"   Image Prompt: {scene.get('image_prompt', '')[:80]}...")
            print(f"   Visual Prompt: {scene.get('visual_prompt', '')[:80]}...")
            print(f"   Generated Image URL: {scene.get('generated_image_url')}")
            print()
    
    # Save full response to file for inspection
    with open('scenario_response_debug.json', 'w') as f:
        json.dump(data, f, indent=2, default=str)
    print(f"✅ Full response saved to: scenario_response_debug.json\n")

def generate_and_monitor_scenario(product_id, user_id):
    """Generate a scenario and monitor it"""
    print(f"\n{'='*80}")
    print(f"Starting scenario generation for product: {product_id}")
    print(f"{'='*80}\n")
    
    # Start scenario generation
    payload = {
        "product_id": product_id,
        "user_id": user_id,
        "style": "product-showcase",
        "mood": "professional",
        "video_length": 24,
        "resolution": "720:1280",
        "target_language": "en-US"
    }
    
    response = requests.post(f"{API_BASE}/scenario/generate", json=payload)
    
    if response.status_code != 200:
        print(f"❌ Failed to start scenario generation: {response.status_code}")
        print(response.text)
        return
    
    data = response.json()
    task_id = data['task_id']
    print(f"✅ Task started: {task_id}\n")
    
    # Poll until complete
    max_attempts = 60
    for attempt in range(max_attempts):
        time.sleep(3)
        check_scenario_response(task_id)
        
        response = requests.get(f"{API_BASE}/scenario/generate/tasks/{task_id}")
        if response.status_code == 200:
            status = response.json().get('status')
            if status in ['completed', 'failed']:
                break
    
    return task_id

if __name__ == "__main__":
    print("\n🔍 Scenario Response Debugger")
    print("="*80)
    
    # Option 1: Check existing task
    print("\nOption 1: Check existing task")
    print("Enter task ID to check (or press Enter to generate new scenario):")
    task_id = input("> ").strip()
    
    if task_id:
        check_scenario_response(task_id)
    else:
        # Option 2: Generate new scenario
        print("\nOption 2: Generate new scenario")
        product_id = input("Enter product ID: ").strip()
        user_id = input("Enter user ID: ").strip()
        
        if product_id and user_id:
            task_id = generate_and_monitor_scenario(product_id, user_id)
            if task_id:
                print(f"\n✅ Final check of task {task_id}")
                check_scenario_response(task_id)
        else:
            print("❌ Product ID and User ID are required")
