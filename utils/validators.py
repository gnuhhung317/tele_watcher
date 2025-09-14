"""Data validation utilities."""

import re
from typing import Optional, Dict, Any
from decimal import Decimal, InvalidOperation

def validate_trading_signal(data: Dict[str, Any]) -> Dict[str, str]:
    """Validate trading signal data.
    
    Args:
        data: Trading signal data to validate
        
    Returns:
        Dictionary of validation errors (empty if valid)
    """
    errors = {}
    
    # Required fields
    required_fields = ['coin', 'entry', 'stop_loss']
    for field in required_fields:
        if field not in data or data[field] is None:
            errors[field] = f"{field} is required"
    
    # Coin validation
    if 'coin' in data and data['coin']:
        coin = str(data['coin']).upper().strip()
        if not re.match(r'^[A-Z0-9]+$', coin):
            errors['coin'] = "Coin symbol must contain only letters and numbers"
        elif len(coin) < 2 or len(coin) > 20:
            errors['coin'] = "Coin symbol must be between 2 and 20 characters"
    
    # Price validation
    price_fields = ['entry', 'stop_loss', 'take_profit']
    for field in price_fields:
        if field in data and data[field] is not None:
            try:
                price = float(data[field])
                if price <= 0:
                    errors[field] = f"{field} must be greater than 0"
            except (ValueError, TypeError):
                errors[field] = f"{field} must be a valid number"
    
    # Logic validation
    if ('entry' in data and 'stop_loss' in data and 
        data['entry'] is not None and data['stop_loss'] is not None):
        try:
            entry = float(data['entry'])
            stop_loss = float(data['stop_loss'])
            
            # For long positions, stop loss should be below entry
            # For short positions, stop loss should be above entry
            # We'll assume long position by default
            if stop_loss >= entry:
                errors['stop_loss'] = "Stop loss should be below entry price for long positions"
        except (ValueError, TypeError):
            pass  # Already handled above
    
    return errors

def is_valid_symbol(symbol: str) -> bool:
    """Check if a trading symbol is valid format.
    
    Args:
        symbol: Trading symbol to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not symbol:
        return False
    
    # Remove common separators
    clean_symbol = symbol.replace('/', '').replace('-', '').replace('_', '')
    return re.match(r'^[A-Z0-9]{4,20}$', clean_symbol.upper()) is not None

def validate_price(price: Any) -> Optional[float]:
    """Validate and convert price to float.
    
    Args:
        price: Price value to validate
        
    Returns:
        Valid price as float or None if invalid
    """
    if price is None:
        return None
    
    try:
        price_float = float(price)
        if price_float <= 0:
            return None
        return price_float
    except (ValueError, TypeError):
        return None

def validate_percentage(percentage: Any) -> Optional[float]:
    """Validate percentage value (0-100).
    
    Args:
        percentage: Percentage value to validate
        
    Returns:
        Valid percentage as float or None if invalid
    """
    if percentage is None:
        return None
    
    try:
        pct = float(percentage)
        if 0 <= pct <= 100:
            return pct
        return None
    except (ValueError, TypeError):
        return None
