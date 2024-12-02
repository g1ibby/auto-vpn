from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field, validator
from urllib.parse import urlparse

class Settings(BaseSettings):
    USERNAME: str = Field(..., description="Username for authentication")
    PASSWORD: str = Field(..., description="Password for authentication")
    DATABASE_URL: str = Field(
        default="sqlite:///data_layer.db",
        description="Database connection string"
    )
    SELF_URL: Optional[str] = Field(
        default=None,
        description="Optional self URL for the application"
    )
    VULTR_API_KEY: Optional[str] = Field(
        default=None, 
        description="API key for Vultr services"
    )
    LINODE_API_KEY: Optional[str] = Field(
        default=None,
        description="API key for Linode services"
    )

    @validator('DATABASE_URL')
    def validate_database_url(cls, v):
        try:
            result = urlparse(v)
            if not result.scheme:
                raise ValueError("Missing database scheme")
            return v
        except Exception as e:
            raise ValueError(f"Invalid database URL format: {str(e)}")

    @validator('SELF_URL')
    def validate_self_url(cls, v):
        if v is not None:
            try:
                result = urlparse(v)
                if not all([result.scheme, result.netloc]):
                    raise ValueError("Invalid URL format")
                return v
            except Exception as e:
                raise ValueError(f"Invalid SELF_URL format: {str(e)}")
        return v

    def validate_api_keys(self):
        """Validate that at least one provider API key is configured"""
        if not any([self.VULTR_API_KEY, self.LINODE_API_KEY]):
            raise ValueError("At least one provider API key must be configured")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True