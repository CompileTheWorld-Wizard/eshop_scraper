"""
Remove cached test audio documents from MongoDB.
Run from project root: python scripts/clear_test_audio_cache.py
"""
import sys
from pathlib import Path

# Add project root so app is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.utils.mongodb_manager import MongoDBManager


def main():
    m = MongoDBManager()
    if not m.ensure_connection():
        print("Failed to connect to MongoDB")
        sys.exit(1)
    result = m.database.test_audio.delete_many({"type": "test_audio"})
    print(f"Deleted {result.deleted_count} test audio document(s)")


if __name__ == "__main__":
    main()
