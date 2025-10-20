"""
Session Management Service for tracking task sessions in MongoDB.
Handles session creation, updates, and cleanup for different task types.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict

try:
    from pymongo import MongoClient, ASCENDING, DESCENDING, IndexModel
    from pymongo.errors import PyMongoError, ConnectionFailure, ServerSelectionTimeoutError
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False
    MongoClient = None

from app.config import settings
from app.models import SessionInfo
from app.utils.mongodb_manager import MongoDBManager, mongodb_manager

logger = logging.getLogger(__name__)


@dataclass
class Session:
    """Session data structure for MongoDB storage"""
    short_id: str
    task_type: str
    task_id: str
    created_at: datetime
    updated_at: datetime
    user_id: Optional[str] = None
    status: str = "active"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for MongoDB storage"""
        data = asdict(self)
        # Convert datetime objects to ISO format for JSON serialization
        for key, value in data.items():
            if isinstance(value, datetime):
                data[key] = value.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Session':
        """Create Session from dictionary"""
        # Filter out MongoDB-specific fields
        filtered_data = {k: v for k, v in data.items() if not k.startswith('_')}
        
        # Convert ISO format strings back to datetime objects
        for key, value in filtered_data.items():
            if key in ['created_at', 'updated_at'] and value:
                if isinstance(value, str):
                    filtered_data[key] = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return cls(**filtered_data)


class SessionService:
    """Service for managing task sessions"""
    
    def __init__(self):
        from app.utils.mongodb_manager import mongodb_manager
        self.session_manager = mongodb_manager
        self.mongodb_available = False
        
    def connect(self) -> bool:
        """Connect to MongoDB"""
        try:
            self.mongodb_available = self.session_manager.connect()
            if self.mongodb_available:
                logger.info("MongoDB connection established successfully for sessions")
            else:
                logger.warning("MongoDB connection failed for sessions - sessions will not be tracked")
            return self.mongodb_available
        except Exception as e:
            logger.error(f"Error connecting to MongoDB for sessions: {e}")
            self.mongodb_available = False
            return False
    
    def disconnect(self):
        """Disconnect from MongoDB"""
        self.session_manager.disconnect()
    
    def create_session(
        self,
        short_id: str,
        task_type: str,
        task_id: str,
        user_id: Optional[str] = None
    ) -> bool:
        """
        Create a new session for a task
        
        Args:
            short_id: Short ID associated with the session
            task_type: Type of task (e.g., 'scraping', 'scenario_generation')
            task_id: Task ID associated with the session
            user_id: Optional user ID for the session
            
        Returns:
            bool: True if session was created successfully
        """
        try:
            if not self.mongodb_available:
                logger.warning("MongoDB not available, skipping session creation")
                return False
                
            logger.info(f"Creating session for task {task_id} (type: {task_type}, short_id: {short_id})")
            
            # Ensure connection
            if not self.session_manager.ensure_connection():
                logger.error(f"Failed to ensure MongoDB connection for session creation")
                return False
            
            # Check if session already exists for this task_id
            existing_session = self.session_manager.sessions_collection.find_one({"task_id": task_id})
            if existing_session:
                logger.warning(f"Session with task_id {task_id} already exists")
                return False
            
            # Create session
            session = Session(
                short_id=short_id,
                task_type=task_type,
                task_id=task_id,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                user_id=user_id,
                status="active"
            )
            
            # Insert the session
            result = self.session_manager.sessions_collection.insert_one(session.to_dict())
            if result.inserted_id:
                logger.info(f"Session created successfully for task {task_id} with MongoDB ID: {result.inserted_id}")
                return True
            else:
                logger.error(f"Failed to insert session for task {task_id} - no inserted_id returned")
                return False
                
        except Exception as e:
            logger.error(f"Failed to create session for task {task_id}: {e}")
            return False
    
    def update_session_status(
        self,
        task_id: str,
        status: str
    ) -> bool:
        """
        Update session status
        
        Args:
            task_id: Task ID to update
            status: New status (active, completed, failed)
            
        Returns:
            bool: True if session was updated successfully
        """
        try:
            if not self.mongodb_available:
                logger.warning("MongoDB not available, skipping session update")
                return False
                
            logger.info(f"Updating session status for task {task_id} to {status}")
            
            # Ensure connection
            if not self.session_manager.ensure_connection():
                logger.error(f"Failed to ensure MongoDB connection for session update")
                return False
            
            # Update session status
            result = self.session_manager.sessions_collection.update_one(
                {"task_id": task_id},
                {
                    "$set": {
                        "status": status,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            
            if result.modified_count > 0:
                logger.info(f"Session status updated successfully for task {task_id}")
                return True
            else:
                logger.warning(f"Session not found or not modified for task {task_id}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to update session status for task {task_id}: {e}")
            return False
    
    def remove_session(self, task_id: str) -> bool:
        """
        Remove a session
        
        Args:
            task_id: Task ID to remove session for
            
        Returns:
            bool: True if session was removed successfully
        """
        try:
            if not self.mongodb_available:
                logger.warning("MongoDB not available, skipping session removal")
                return False
                
            logger.info(f"Removing session for task {task_id}")
            
            # Ensure connection
            if not self.session_manager.ensure_connection():
                logger.error(f"Failed to ensure MongoDB connection for session removal")
                return False
            
            # Remove session
            result = self.session_manager.sessions_collection.delete_one({"task_id": task_id})
            if result.deleted_count > 0:
                logger.info(f"Session removed successfully for task {task_id}")
                return True
            else:
                logger.warning(f"Session not found for task {task_id}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to remove session for task {task_id}: {e}")
            return False
    
    def get_session(self, task_id: str) -> Optional[Session]:
        """
        Get session by task ID
        
        Args:
            task_id: Task ID to get session for
            
        Returns:
            Session object or None if not found
        """
        try:
            if not self.mongodb_available:
                logger.warning("MongoDB not available, cannot get session")
                return None
                
            # Ensure connection
            if not self.session_manager.ensure_connection():
                logger.error(f"Failed to ensure MongoDB connection for session retrieval")
                return None
            
            # Get session
            session_doc = self.session_manager.sessions_collection.find_one({"task_id": task_id})
            if session_doc:
                return Session.from_dict(session_doc)
            return None
                
        except Exception as e:
            logger.error(f"Failed to get session for task {task_id}: {e}")
            return None
    
    def get_sessions_by_short_id(self, short_id: str) -> List[Session]:
        """
        Get all sessions for a short_id
        
        Args:
            short_id: Short ID to get sessions for
            
        Returns:
            List of Session objects
        """
        try:
            if not self.mongodb_available:
                logger.warning("MongoDB not available, cannot get sessions")
                return []
                
            # Ensure connection
            if not self.session_manager.ensure_connection():
                logger.error(f"Failed to ensure MongoDB connection for session retrieval")
                return []
            
            # Get sessions
            sessions_docs = self.session_manager.sessions_collection.find({"short_id": short_id})
            sessions = []
            for doc in sessions_docs:
                sessions.append(Session.from_dict(doc))
            return sessions
                
        except Exception as e:
            logger.error(f"Failed to get sessions for short_id {short_id}: {e}")
            return []
    
    def get_sessions_by_user_id(self, user_id: str) -> List[Session]:
        """
        Get all sessions for a user_id
        
        Args:
            user_id: User ID to get sessions for
            
        Returns:
            List of Session objects
        """
        try:
            if not self.mongodb_available:
                logger.warning("MongoDB not available, cannot get sessions")
                return []
                
            # Ensure connection
            if not self.session_manager.ensure_connection():
                logger.error(f"Failed to ensure MongoDB connection for session retrieval")
                return []
            
            # Get sessions
            sessions_docs = self.session_manager.sessions_collection.find({"user_id": user_id})
            sessions = []
            for doc in sessions_docs:
                sessions.append(Session.from_dict(doc))
            return sessions
                
        except Exception as e:
            logger.error(f"Failed to get sessions for user_id {user_id}: {e}")
            return []
    
    def cleanup_old_sessions(self, days_old: int = 7) -> int:
        """
        Clean up old completed/failed sessions
        
        Args:
            days_old: Number of days old to clean up
            
        Returns:
            Number of sessions cleaned up
        """
        try:
            if not self.mongodb_available:
                logger.warning("MongoDB not available, cannot cleanup sessions")
                return 0
                
            # Ensure connection
            if not self.session_manager.ensure_connection():
                logger.error(f"Failed to ensure MongoDB connection for session cleanup")
                return 0
            
            from datetime import timedelta
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)
            cutoff_date_iso = cutoff_date.isoformat()
            
            result = self.session_manager.sessions_collection.delete_many({
                "created_at": {"$lt": cutoff_date_iso},
                "status": {"$in": ["completed", "failed"]}
            })
            
            deleted_count = result.deleted_count
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old sessions")
            else:
                logger.info("No old sessions found to clean up")
            
            return deleted_count
                
        except Exception as e:
            logger.error(f"Failed to cleanup old sessions: {e}")
            return 0


# Global instance
session_service = SessionService()


def initialize_session_service():
    """Initialize session service and MongoDB connection"""
    return session_service.connect()


def cleanup_session_service():
    """Cleanup session service and MongoDB connection"""
    session_service.disconnect()
