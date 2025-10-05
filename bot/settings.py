import configparser
import logging
import os

logger = logging.getLogger(__name__)

class TradingBotSettings:
    """Manages bot settings from settings.txt file"""
    
    def __init__(self, settings_file: str = "settings.txt"):
        self.settings_file = settings_file
        self.config = configparser.ConfigParser()
        self.last_modified = 0
        self.load_settings()
    
    def load_settings(self):
        """Load settings from file"""
        try:
            if os.path.exists(self.settings_file):
                current_modified = os.path.getmtime(self.settings_file)
                if current_modified > self.last_modified:
                    self.config.read(self.settings_file)
                    self.last_modified = current_modified
                    logger.info("Settings reloaded from file")
            else:
                logger.warning(f"Settings file {self.settings_file} not found")
        except Exception as e:
            logger.error(f"Error loading settings: {e}")
    
    def has_section(self, section: str) -> bool:
        """Check if a section exists in the config"""
        self.load_settings()  # Reload if file changed
        return self.config.has_section(section)
    
    def get(self, section: str, key: str, fallback: str = "") -> str:
        """Get setting value"""
        self.load_settings()  # Check for updates
        return self.config.get(section, key, fallback=fallback)
    
    def getfloat(self, section: str, key: str, fallback: float = 0.0) -> float:
        """Get float setting value"""
        self.load_settings()
        return self.config.getfloat(section, key, fallback=fallback)
    
    def getint(self, section: str, key: str, fallback: int = 0) -> int:
        """Get integer setting value"""
        self.load_settings()
        return self.config.getint(section, key, fallback=fallback)
    
    def getboolean(self, section: str, key: str, fallback: bool = False) -> bool:
        """Get boolean setting value"""
        self.load_settings()
        return self.config.getboolean(section, key, fallback=fallback)

    def set_value(self, section: str, key: str, value) -> None:
        """Set a setting value and persist to file."""
        try:
            logger.info(f"TradingBotSettings.set_value(section={section}, key={key}, value={value})")
            if not self.config.has_section(section):
                self.config.add_section(section)
            self.config.set(section, key, str(value))
            self.save()
        except Exception as e:
            logger.error(f"Error setting value: {e}")

    def set_env_account(self, environment: str, account_id: str) -> None:
        """Remember selected account per environment."""
        try:
            if not self.config.has_section("ENV_ACCOUNTS"):
                self.config.add_section("ENV_ACCOUNTS")
            self.config.set("ENV_ACCOUNTS", environment.lower(), account_id)
            self.save()
            logger.info(f"Saved environment account map: {environment} -> {account_id}")
        except Exception as e:
            logger.error(f"Error saving env account: {e}")

    def get_env_account(self, environment: str) -> str:
        """Get account ID for environment"""
        self.load_settings()
        try:
            return self.config.get("ENV_ACCOUNTS", environment.lower())
        except (configparser.NoSectionError, configparser.NoOptionError):
            return ""

    def save(self) -> None:
        """Persist current config to settings file."""
        try:
            with open(self.settings_file, 'w') as f:
                self.config.write(f)
            # Update last modified timestamp so subsequent reads don't reload unnecessarily
            self.last_modified = os.path.getmtime(self.settings_file)
            logger.info("Settings saved to file")
        except Exception as e:
            logger.error(f"Error saving settings: {e}")

