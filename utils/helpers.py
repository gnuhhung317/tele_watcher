"""Helper utility functions."""

import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Any, Union

def format_price(price: Union[float, Decimal], decimals: int = 8) -> str:
    """Format price with appropriate decimal places.
    
    Args:
        price: Price to format
        decimals: Number of decimal places
        
    Returns:
        Formatted price string
    """
    if price is None:
        return "0.00000000"
    
    try:
        decimal_price = Decimal(str(price))
        # Remove trailing zeros
        formatted = f"{decimal_price:.{decimals}f}".rstrip('0').rstrip('.')
        
        # Ensure at least 2 decimal places for readability
        if '.' not in formatted:
            formatted += '.00'
        elif len(formatted.split('.')[1]) == 1:
            formatted += '0'
        
        return formatted
    except (ValueError, TypeError):
        return "0.00"

def safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert value to float.
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
        
    Returns:
        Float value or default
    """
    if value is None:
        return default
    
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def safe_int(value: Any, default: int = 0) -> int:
    """Safely convert value to int.
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
        
    Returns:
        Integer value or default
    """
    if value is None:
        return default
    
    try:
        return int(float(value))  # Handle string floats like "1.0"
    except (ValueError, TypeError):
        return default

def extract_number(text: str) -> Optional[float]:
    """Extract first number from text.
    
    Args:
        text: Text to search for numbers
        
    Returns:
        First number found or None
    """
    if not text:
        return None
    
    # Look for number patterns (including decimals)
    pattern = r'[\d]+\.?[\d]*'
    matches = re.findall(pattern, text)
    
    if matches:
        try:
            return float(matches[0])
        except ValueError:
            pass
    
    return None

def clean_symbol(symbol: str) -> str:
    """Clean trading symbol by removing common separators and converting to uppercase.
    
    Args:
        symbol: Raw symbol string
        
    Returns:
        Cleaned symbol
    """
    if not symbol:
        return ""
    
    # Remove common separators and whitespace
    cleaned = re.sub(r'[/\-_\s]', '', symbol.upper())
    
    # Remove non-alphanumeric characters except common ones
    cleaned = re.sub(r'[^A-Z0-9]', '', cleaned)
    
    return cleaned

def parse_hashtag(text: str) -> Optional[str]:
    """Extract coin symbol from hashtag format.
    
    Args:
        text: Text containing hashtag (e.g., "#PUMPBTC")
        
    Returns:
        Coin symbol without hashtag or None if not found
    """
    if not text:
        return None
    
    # Look for hashtag pattern
    hashtag_pattern = r'#([A-Z0-9]+)'
    matches = re.findall(hashtag_pattern, text.upper())
    
    if matches:
        return matches[0]
    
    return None

def calculate_percentage_change(old_value: float, new_value: float) -> float:
    """Calculate percentage change between two values.
    
    Args:
        old_value: Original value
        new_value: New value
        
    Returns:
        Percentage change
    """
    if old_value == 0:
        return 0.0
    
    return ((new_value - old_value) / old_value) * 100
