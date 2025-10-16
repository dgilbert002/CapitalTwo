"""
Log Manager - Session-based log rotation with 7-day retention
"""
import os
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

class SessionLogManager:
    """Manages session-based logging with rotation and cleanup"""
    
    def __init__(self, log_dir: str = "logs", retention_days: int = 7):
        self.log_dir = Path(log_dir)
        self.retention_days = retention_days
        self.current_log_file: Optional[Path] = None
        self.session_id = None
        
        # Create logs directory if it doesn't exist
        self.log_dir.mkdir(exist_ok=True)
        
        # Clean up old logs on initialization
        self.cleanup_old_logs()
    
    def start_new_session(self) -> Path:
        """Start a new logging session with timestamp-based filename"""
        # Generate session ID with timestamp
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create new log file in logs directory
        self.current_log_file = self.log_dir / f"session_{self.session_id}.log"
        
        # Clean up old logs
        self.cleanup_old_logs()
        
        return self.current_log_file
    
    def cleanup_old_logs(self):
        """Remove logs older than retention_days"""
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        
        # Check all log files in the logs directory
        for log_file in self.log_dir.glob("session_*.log*"):
            try:
                # Extract date from filename (session_YYYYMMDD_HHMMSS.log)
                filename = log_file.stem  # Gets 'session_YYYYMMDD_HHMMSS' from 'session_YYYYMMDD_HHMMSS.log'
                parts = filename.split('_')
                if len(parts) >= 3:
                    date_str = parts[1]  # Get YYYYMMDD
                    
                    # Parse the date
                    file_date = datetime.strptime(date_str, "%Y%m%d")
                    
                    # Remove if older than retention period
                    if file_date < cutoff_date:
                        log_file.unlink()
                        print(f"Removed old log: {log_file}")
                    
            except (ValueError, IndexError) as e:
                # Skip files that don't match expected format
                continue
    
    def get_session_logs(self, days: int = 7) -> list:
        """Get list of session logs from the last N days"""
        cutoff_date = datetime.now() - timedelta(days=days)
        session_logs = []
        
        for log_file in sorted(self.log_dir.glob("session_*.log*"), reverse=True):
            try:
                # Extract date from filename
                filename = log_file.stem.split('.')[0]
                date_str = filename.split('_')[1] + filename.split('_')[2]
                file_date = datetime.strptime(date_str[:8], "%Y%m%d")
                
                if file_date >= cutoff_date:
                    size = log_file.stat().st_size
                    session_logs.append({
                        'filename': log_file.name,
                        'path': str(log_file),
                        'date': file_date.strftime("%Y-%m-%d"),
                        'size': f"{size / 1024 / 1024:.2f} MB" if size > 1024*1024 else f"{size / 1024:.2f} KB",
                        'compressed': log_file.suffix == '.gz'
                    })
            except:
                continue
        
        return session_logs

# Global instance
log_manager = SessionLogManager()

def setup_logging(log_level: str = "WARNING") -> logging.Logger:
    """Setup logging with the session manager - defaults to production mode (WARNING)"""
    # Start new session
    log_file = log_manager.start_new_session()
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),   # Session log file in logs/ folder
            logging.StreamHandler()           # Console output
        ]
    )
    
    print(f"Logging to: {log_file}")
    
    return logging.getLogger(__name__)

def set_log_level(debug_mode: bool):
    """Change log level based on debug mode toggle"""
    level = logging.DEBUG if debug_mode else logging.WARNING
    
    # Update root logger first
    logging.root.setLevel(level)
    
    # Update all handlers
    for handler in logging.root.handlers:
        handler.setLevel(level)
    
    # Update all existing loggers
    for logger_name in logging.root.manager.loggerDict:
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)
    
    # Log the change (this will only appear if level allows it)
    if debug_mode:
        logging.info(f"Log level changed to: DEBUG/INFO")
    else:
        logging.warning(f"Log level changed to: ERROR/WARNING only")
