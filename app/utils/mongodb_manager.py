"""
MongoDB Manager for centralized database operations.
Handles connections, collections, and common database operations.
"""

from typing import Optional, Dict, Any
from datetime import datetime, timezone
import logging

try:
    from pymongo import MongoClient, ASCENDING, DESCENDING, IndexModel
    from pymongo.errors import PyMongoError, ConnectionFailure, ServerSelectionTimeoutError
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False
    MongoClient = None

from ..config import settings

logger = logging.getLogger(__name__)


class MongoDBManager:
    """MongoDB connection and operation manager with singleton pattern"""
    
    _instance = None
    _connected = False
    
    def __new__(cls, connection_string: str = None, database_name: str = None):
        if cls._instance is None:
            cls._instance = super(MongoDBManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, connection_string: str = None, database_name: str = None):
        # Only initialize once
        if hasattr(self, '_initialized'):
            return
            
        self.connection_string = connection_string or getattr(settings, 'MONGODB_URI', 'mongodb://localhost:27017')
        self.database_name = database_name or getattr(settings, 'MONGODB_DATABASE', 'eshop_scraper')
        self.client: Optional[MongoClient] = None
        self.database = None
        self.tasks_collection = None
        self.sessions_collection = None
        self.test_audio_collection = None
        self._connection_pool_size = getattr(settings, 'MONGODB_POOL_SIZE', 10)
        self._max_pool_size = getattr(settings, 'MONGODB_MAX_POOL_SIZE', 100)
        self._server_selection_timeout = getattr(settings, 'MONGODB_SERVER_SELECTION_TIMEOUT', 5000)
        self._connect_timeout = getattr(settings, 'MONGODB_CONNECT_TIMEOUT', 20000)
        self._socket_timeout = getattr(settings, 'MONGODB_SOCKET_TIMEOUT', 30000)
        self._initialized = True
        
    def connect(self) -> bool:
        """Establish connection to MongoDB"""
        # Check if already connected
        if MongoDBManager._connected and self.health_check():
            logger.debug("MongoDB already connected, skipping connection")
            return True
            
        if not MONGODB_AVAILABLE:
            logger.error("MongoDB dependencies not available. Install pymongo.")
            return False
            
        try:
            logger.info(f"Attempting to connect to MongoDB at: {self.connection_string}")
            self.client = MongoClient(
                self.connection_string,
                maxPoolSize=self._max_pool_size,
                serverSelectionTimeoutMS=self._server_selection_timeout,
                connectTimeoutMS=self._connect_timeout,
                socketTimeoutMS=self._socket_timeout,
                retryWrites=True,
                retryReads=True,
                # Connection pool settings for persistence
                minPoolSize=5,
                maxIdleTimeMS=30000,
                waitQueueTimeoutMS=5000
            )
            
            # Test connection
            logger.info("Testing MongoDB connection...")
            self.client.admin.command('ping')
            logger.info("MongoDB ping successful")
            
            self.database = self.client[self.database_name]
            
            # Initialize collections
            self.tasks_collection = self.database.tasks
            self.sessions_collection = self.database.sessions
            self.test_audio_collection = self.database.test_audio
            
            # Create indexes for better performance
            logger.info("Creating MongoDB indexes...")
            self._create_indexes()
            
            logger.info(f"Successfully connected to MongoDB: {self.database_name}")
            MongoDBManager._connected = True
            return True
                
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            MongoDBManager._connected = False
            return False
        except Exception as e:
            logger.error(f"Unexpected error connecting to MongoDB: {e}")
            MongoDBManager._connected = False
            return False
    
    def disconnect(self):
        """Close MongoDB connection"""
        if self.client:
            self.client.close()
            self.client = None
            self.database = None
            self.tasks_collection = None
            self.sessions_collection = None
            self.test_audio_collection = None
            MongoDBManager._connected = False
            logger.info("MongoDB connection closed")
    
    def _create_indexes(self):
        """Create database indexes for better performance"""
        try:
            # Tasks collection indexes
            if self.tasks_collection is not None:
                self.tasks_collection.create_index(
                    IndexModel([("task_id", ASCENDING)], unique=True)
                )
                self.tasks_collection.create_index(
                    IndexModel([("task_type", ASCENDING)])
                )
                self.tasks_collection.create_index(
                    IndexModel([("task_status", ASCENDING)])
                )
                self.tasks_collection.create_index(
                    IndexModel([("created_at", DESCENDING)])
                )
                self.tasks_collection.create_index(
                    IndexModel([("user_id", ASCENDING)])
                )
            
            # Sessions collection indexes
            if self.sessions_collection is not None:
                self.sessions_collection.create_index(
                    IndexModel([("short_id", ASCENDING)])
                )
                self.sessions_collection.create_index(
                    IndexModel([("task_id", ASCENDING)], unique=True)
                )
                self.sessions_collection.create_index(
                    IndexModel([("task_type", ASCENDING)])
                )
                self.sessions_collection.create_index(
                    IndexModel([("status", ASCENDING)])
                )
                self.sessions_collection.create_index(
                    IndexModel([("created_at", DESCENDING)])
                )
                self.sessions_collection.create_index(
                    IndexModel([("user_id", ASCENDING)])
                )
            
            # Test audio collection indexes
            if self.test_audio_collection is not None:
                self.test_audio_collection.create_index(
                    IndexModel([("voice_id", ASCENDING)])
                )
                self.test_audio_collection.create_index(
                    IndexModel([("type", ASCENDING)])
                )
                self.test_audio_collection.create_index(
                    IndexModel([("created_at", DESCENDING)])
                )
            
            logger.info("MongoDB indexes created successfully")
            
        except Exception as e:
            logger.warning(f"Failed to create some indexes: {e}")
    
    def health_check(self) -> bool:
        """Check if MongoDB connection is healthy"""
        try:
            if not self.client:
                return False
            self.client.admin.command('ping')
            return True
        except Exception:
            return False
    
    def ensure_connection(self) -> bool:
        """Ensure MongoDB connection is active, reconnect if needed"""
        if MongoDBManager._connected and self.health_check():
            return True
        
        logger.info("MongoDB connection lost, attempting to reconnect...")
        return self.connect()
    
    def monitor_connection(self):
        """Monitor connection health and reconnect if needed"""
        try:
            if not self.health_check():
                logger.warning("MongoDB connection unhealthy, reconnecting...")
                self.connect()
        except Exception as e:
            logger.error(f"Error monitoring MongoDB connection: {e}")
            self.connect()


# Global instance for shared use
mongodb_manager = MongoDBManager()
