"""Environment variable loader."""

import os
from dotenv import load_dotenv
from typing import List

def load_environment() -> None:
    """Load environment variables from .env file."""
    load_dotenv()

def get_env_var(key: str, default: str = None, required: bool = False) -> str:
    """Get environment variable with validation."""
    value = os.getenv(key, default)
    if required and value is None:
        raise ValueError(f"Required environment variable {key} is not set")
    return value

def get_env_int(key: str, default: int = None, required: bool = False) -> int:
    """Get environment variable as integer."""
    value = get_env_var(key, str(default) if default is not None else None, required)
    try:
        return int(value) if value else None
    except ValueError:
        raise ValueError(f"Environment variable {key} must be an integer")

def get_env_float(key: str, default: float = None, required: bool = False) -> float:
    """Get environment variable as float."""
    value = get_env_var(key, str(default) if default is not None else None, required)
    try:
        return float(value) if value else None
    except ValueError:
        raise ValueError(f"Environment variable {key} must be a float")

def get_env_bool(key: str, default: bool = False) -> bool:
    """Get environment variable as boolean."""
    value = get_env_var(key, str(default).lower())
    return value.lower() in ('true', '1', 'yes', 'on')

def get_env_list(key: str, default: List[str] = None, separator: str = ',') -> List[str]:
    """Get environment variable as list of strings."""
    value = get_env_var(key, separator.join(default) if default else "")
    if not value:
        return default or []
    return [item.strip() for item in value.split(separator) if item.strip()]
