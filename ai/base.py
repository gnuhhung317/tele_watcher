"""Base AI parser interface."""

from abc import ABC, abstractmethod
from typing import Optional
from .models import ParseResult, TradingSignal

class BaseAIParser(ABC):
    """Abstract base class for AI parsers."""
    
    def __init__(self, api_key: str, model_name: str = None):
        """Initialize parser.
        
        Args:
            api_key: API key for the AI service
            model_name: Model name to use
        """
        self.api_key = api_key
        self.model_name = model_name
    
    @abstractmethod
    async def parse_message(self, message: str, source: str = "") -> ParseResult:
        """Parse a message for trading signals.
        
        Args:
            message: Raw message text to parse
            source: Source of the message (e.g., telegram channel)
            
        Returns:
            ParseResult containing the parsed signal or error
        """
        pass
    
    @abstractmethod
    def is_valid_signal(self, text: str) -> bool:
        """Quick check if text might contain a trading signal.
        
        Args:
            text: Text to check
            
        Returns:
            True if text might contain a signal, False otherwise
        """
        pass
    
    def _validate_signal(self, signal: TradingSignal) -> bool:
        """Validate a parsed trading signal.
        
        Args:
            signal: Signal to validate
            
        Returns:
            True if signal is valid, False otherwise
        """
        if not signal:
            return False
        
        # Basic validation
        if not signal.coin or not signal.coin.strip():
            return False
        
        if signal.entry <= 0:
            return False
        
        if signal.stop_loss <= 0:
            return False
        
        # Logic validation for long positions
        if signal.side.value == "long" and signal.stop_loss >= signal.entry:
            return False
        
        # Logic validation for short positions  
        if signal.side.value == "short" and signal.stop_loss <= signal.entry:
            return False
        
        return True
