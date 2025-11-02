import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    database_url: str = os.getenv("DATABASE_URL", "")
    db_host: str = os.getenv("DB_HOST", "localhost")
    db_port: int = int(os.getenv("DB_PORT", "5435"))
    db_name: str = os.getenv("DB_NAME", "fintegrate_db")
    db_user: str = os.getenv("DB_USER", "fintegrate_user")
    db_password: str = os.getenv("DB_PASSWORD", "fintegrate_pass")
    
    # API
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8000"))
    api_log_level: str = os.getenv("API_LOG_LEVEL", "INFO")
    
    # Service Identity
    service_name: str = os.getenv("SERVICE_NAME", "customer_service")
    service_version: str = os.getenv("SERVICE_VERSION", "1.0.0")
    
    # Rate Limiting Configuration
    redis_host: str = os.getenv("REDIS_HOST", "redis")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    rate_limit_ip_per_minute: int = int(os.getenv("RATE_LIMIT_IP_PER_MINUTE", "10"))
    rate_limit_ip_burst: int = int(os.getenv("RATE_LIMIT_IP_BURST", "5"))
    rate_limit_api_key_per_minute: int = int(os.getenv("RATE_LIMIT_API_KEY_PER_MINUTE", "50"))
    rate_limit_api_key_burst: int = int(os.getenv("RATE_LIMIT_API_KEY_BURST", "10"))
    
    def get_database_url(self) -> str:
        """Get database URL, preferring environment variable."""
        if self.database_url:
            return self.database_url
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
    
    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
