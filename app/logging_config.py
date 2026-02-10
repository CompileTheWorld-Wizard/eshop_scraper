import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path
from app.config import settings

# Enable ANSI colors on Windows 10+
if sys.platform == 'win32':
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)  # Enable ANSI escape sequences
    except:
        pass  # If it fails, colors just won't work (not critical)

# Global flag to track if logging has been initialized
_logging_initialized = False

# ANSI color codes for console output (Windows compatible)
class Colors:
    """ANSI color codes for terminal output"""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    
    # Log levels
    DEBUG = '\033[36m'      # Cyan
    INFO = '\033[32m'       # Green
    WARNING = '\033[33m'    # Yellow
    ERROR = '\033[31m'      # Red
    CRITICAL = '\033[35m'   # Magenta
    
    # Components
    TIMESTAMP = '\033[90m'  # Dark gray
    MODULE = '\033[94m'     # Blue
    SEPARATOR = '\033[90m'  # Dark gray


class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds colors to console output"""
    
    COLORS = {
        'DEBUG': Colors.DEBUG,
        'INFO': Colors.INFO,
        'WARNING': Colors.WARNING,
        'ERROR': Colors.ERROR,
        'CRITICAL': Colors.CRITICAL,
    }
    
    def format(self, record):
        # Get base formatted message
        log_message = super().format(record)
        
        # Only add colors if outputting to terminal
        if hasattr(sys.stdout, 'isatty') and sys.stdout.isatty():
            level_color = self.COLORS.get(record.levelname, Colors.RESET)
            
            # Color the log level
            log_message = log_message.replace(
                record.levelname,
                f"{level_color}{Colors.BOLD}{record.levelname}{Colors.RESET}"
            )
        
        return log_message


class DetailedFormatter(logging.Formatter):
    """Enhanced formatter for file logs with clear separation"""
    
    def format(self, record):
        # Create base formatted message
        formatted = super().format(record)
        
        # Add separator line for errors and critical messages
        if record.levelno >= logging.ERROR:
            separator = "=" * 100
            formatted = f"\n{separator}\n{formatted}\n{separator}\n"
        
        # Add separator for warnings
        elif record.levelno == logging.WARNING:
            separator = "-" * 100
            formatted = f"\n{separator}\n{formatted}\n{separator}\n"
        
        return formatted


def get_service_name(name: str) -> str:
    """Extract service name from logger name for better organization"""
    parts = name.split('.')
    if len(parts) > 1:
        if parts[0] == 'app':
            if parts[1] == 'services':
                return parts[2] if len(parts) > 2 else 'service'
            elif parts[1] == 'utils':
                return f"utils.{parts[2]}" if len(parts) > 2 else 'utils'
            elif parts[1] == 'extractors':
                return f"extractors.{parts[2]}" if len(parts) > 2 else 'extractors'
    return name


def setup_logging():
    """Setup comprehensive logging configuration with file and console handlers"""
    global _logging_initialized
    
    # Prevent multiple initializations
    if _logging_initialized:
        return
    
    # Create logs directory if it doesn't exist
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    
    # Create subdirectories for organized logs
    (logs_dir / "services").mkdir(exist_ok=True)
    (logs_dir / "api").mkdir(exist_ok=True)
    (logs_dir / "credits").mkdir(exist_ok=True)
    
    # Get the root logger
    root_logger = logging.getLogger()
    
    # Only set up logging if it hasn't been configured yet
    if not root_logger.handlers:
        root_logger.setLevel(getattr(logging, settings.LOG_LEVEL))
        
        # Create formatters
        # Detailed formatter for files with clear structure
        detailed_formatter = DetailedFormatter(
            fmt='%(asctime)s | %(levelname)-8s | %(name)-30s | %(filename)s:%(lineno)-4d | %(funcName)-20s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Colored formatter for console
        console_formatter = ColoredFormatter(
            fmt='%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s',
            datefmt='%H:%M:%S'
        )
        
        # Simple formatter for console (fallback if colors not supported)
        simple_formatter = logging.Formatter(
            fmt='%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s',
            datefmt='%H:%M:%S'
        )
        
        # Console handler with colors
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, settings.LOG_LEVEL))
        
        # Use colored formatter if terminal supports it
        try:
            console_handler.setFormatter(console_formatter)
        except:
            console_handler.setFormatter(simple_formatter)
        
        # Main application log file (all logs)
        file_handler = logging.handlers.RotatingFileHandler(
            logs_dir / "app.log",
            maxBytes=settings.LOG_FILE_MAX_SIZE,
            backupCount=settings.LOG_FILE_BACKUP_COUNT,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(detailed_formatter)
        
        # Errors-only log file
        error_handler = logging.handlers.RotatingFileHandler(
            logs_dir / "errors.log",
            maxBytes=settings.LOG_FILE_MAX_SIZE // 2,  # 5MB
            backupCount=3,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(detailed_formatter)
        
        # Security events log file
        security_handler = logging.handlers.RotatingFileHandler(
            logs_dir / "security.log",
            maxBytes=settings.LOG_FILE_MAX_SIZE // 2,  # 5MB
            backupCount=3,
            encoding='utf-8'
        )
        security_handler.setLevel(logging.WARNING)
        security_handler.setFormatter(detailed_formatter)
        
        # Service-specific log handlers
        service_handler = logging.handlers.RotatingFileHandler(
            logs_dir / "services" / "all_services.log",
            maxBytes=settings.LOG_FILE_MAX_SIZE,
            backupCount=5,
            encoding='utf-8'
        )
        service_handler.setLevel(logging.DEBUG)
        service_handler.setFormatter(detailed_formatter)
        service_handler.addFilter(lambda record: 'app.services' in record.name)
        
        # Credit operations log
        credit_handler = logging.handlers.RotatingFileHandler(
            logs_dir / "credits" / "credit_operations.log",
            maxBytes=settings.LOG_FILE_MAX_SIZE // 2,
            backupCount=5,
            encoding='utf-8'
        )
        credit_handler.setLevel(logging.DEBUG)
        credit_handler.setFormatter(detailed_formatter)
        credit_handler.addFilter(lambda record: 'credit' in record.name.lower())
        
        # API requests log
        api_handler = logging.handlers.RotatingFileHandler(
            logs_dir / "api" / "api_requests.log",
            maxBytes=settings.LOG_FILE_MAX_SIZE,
            backupCount=5,
            encoding='utf-8'
        )
        api_handler.setLevel(logging.INFO)
        api_handler.setFormatter(detailed_formatter)
        api_handler.addFilter(lambda record: 'app.api' in record.name or 'routes' in record.name)
        
        # Add handlers to root logger
        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)
        root_logger.addHandler(error_handler)
        root_logger.addHandler(service_handler)
        root_logger.addHandler(credit_handler)
        root_logger.addHandler(api_handler)
        
        # Create security logger (separate from root)
        security_logger = logging.getLogger('security')
        security_logger.addHandler(security_handler)
        security_logger.setLevel(logging.WARNING)
        security_logger.propagate = False  # Don't propagate to root logger
        
        # Set specific loggers to appropriate levels
        logging.getLogger('uvicorn').setLevel(logging.INFO)
        logging.getLogger('uvicorn.access').setLevel(logging.INFO)
        logging.getLogger('fastapi').setLevel(logging.INFO)
        logging.getLogger('playwright').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)
        logging.getLogger('requests').setLevel(logging.WARNING)
        logging.getLogger('httpx').setLevel(logging.WARNING)
        
        # Mark logging as initialized
        _logging_initialized = True
        
        # Log startup message with clear separation
        logger = logging.getLogger(__name__)
        logger.info("=" * 100)
        logger.info("LOGGING SYSTEM INITIALIZED")
        logger.info("=" * 100)
        logger.info(f"📁 Log files directory: {logs_dir.absolute()}")
        logger.info(f"📊 Log level: {settings.LOG_LEVEL}")
        logger.info(f"📝 Main log: {logs_dir / 'app.log'}")
        logger.info(f"❌ Error log: {logs_dir / 'errors.log'}")
        logger.info(f"🔒 Security log: {logs_dir / 'security.log'}")
        logger.info(f"⚙️  Services log: {logs_dir / 'services' / 'all_services.log'}")
        logger.info(f"💳 Credits log: {logs_dir / 'credits' / 'credit_operations.log'}")
        logger.info(f"🌐 API log: {logs_dir / 'api' / 'api_requests.log'}")
        logger.info("=" * 100)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the specified name that writes to appropriate log files based on level"""
    # Ensure logging is set up if it hasn't been yet
    if not _logging_initialized:
        setup_logging()
    
    logger = logging.getLogger(name)
    
    return logger

def reset_logging():
    """Reset the logging initialization flag (useful for testing)"""
    global _logging_initialized
    _logging_initialized = False 