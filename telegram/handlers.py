"""Message handlers for processing Telegram messages."""

import asyncio
from datetime import datetime
from typing import Optional, Callable, List

# Import with absolute path
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai import BaseAIParser, ParseResult, ParseStatus
from trading import PositionManager
from config import TradingConfig
from utils import get_logger, validate_trading_signal

logger = get_logger(__name__)

class MessageHandler:
    """Handles incoming Telegram messages and processes trading signals."""
    
    def __init__(self, 
                 ai_parser: BaseAIParser,
                 position_manager: PositionManager,
                 trading_config: TradingConfig):
        """Initialize message handler.
        
        Args:
            ai_parser: AI parser for signal extraction
            position_manager: Position manager for trade execution
            trading_config: Trading configuration
        """
        self.ai_parser = ai_parser
        self.position_manager = position_manager
        self.trading_config = trading_config
        self.signal_callbacks: List[Callable] = []
        self.error_callbacks: List[Callable] = []
    
    def add_signal_callback(self, callback: Callable):
        """Add callback for successful signal processing.
        
        Args:
            callback: Function to call with signal data
        """
        self.signal_callbacks.append(callback)
    
    def add_error_callback(self, callback: Callable):
        """Add callback for error handling.
        
        Args:
            callback: Function to call with error data
        """
        self.error_callbacks.append(callback)
    
    async def handle_message(self, 
                           text: str, 
                           source: str, 
                           message_id: int, 
                           timestamp: datetime) -> Optional[ParseResult]:
        """Handle incoming message.
        
        Args:
            text: Message text
            source: Source channel
            message_id: Message ID
            timestamp: Message timestamp
            
        Returns:
            ParseResult if signal was processed, None otherwise
        """
        logger.info(f"Processing message from {source}: {text}...")
        
        try:
            # # Quick pre-filter
            # if not self.ai_parser.is_valid_signal(text):
            #     logger.debug("Message doesn't appear to contain trading signal")
            #     return None
            
            # Parse with AI
            parse_result = await self.ai_parser.parse_message(text, source)
            logger.info(parse_result)
            if parse_result.status == ParseStatus.NO_SIGNAL:
                logger.debug(f"No trading signal found in message: {parse_result.error_message}")
                return parse_result
            
            if parse_result.status == ParseStatus.FAILED:
                logger.error(f"Failed to parse message: {parse_result.error_message}")
                await self._notify_error("parse_failed", parse_result.error_message, {
                    'source': source,
                    'message_id': message_id,
                    'text': text[:200]
                })
                return parse_result
            
            # Validate confidence
            if parse_result.confidence < self.trading_config.min_confidence:
                logger.warning(f"Signal confidence {parse_result.confidence} below threshold {self.trading_config.min_confidence}")
                return parse_result
            
            # Validate signal data
            signal = parse_result.signal
            if not signal:
                logger.error("Parse result has no signal data")
                return parse_result
            
            validation_errors = validate_trading_signal(signal.to_dict())
            if validation_errors:
                logger.error(f"Signal validation failed: {validation_errors}")
                await self._notify_error("validation_failed", str(validation_errors), {
                    'signal': signal.to_dict(),
                    'source': source
                })
                return parse_result
            
            # Validate Multi-TP configuration
            is_valid, error_msg = self.trading_config.validate_multi_tp_signal(signal)
            if not is_valid:
                logger.error(f"Multi-TP validation failed: {error_msg}")
                await self._notify_error("multi_tp_validation_failed", error_msg, {
                    'signal': signal.to_dict(),
                    'source': source
                })
                return parse_result
            
            logger.info(f"Valid trading signal found: {signal.coin} at {signal.entry}")
            
            # Log Multi-TP details if applicable
            if signal.is_multi_tp():
                logger.info(f"Multi-TP signal: {signal.tp_count} levels, percentages: {signal.effective_tp_percentages}")
            
            # Notify signal callbacks
            await self._notify_signal(signal, source, message_id)
            
            # Execute trade if trading is enabled
            if self.trading_config.enabled:
                await self._execute_signal(signal)
            else:
                logger.info("Trading disabled, signal logged only")
            
            return parse_result
            
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            await self._notify_error("handler_error", str(e), {
                'source': source,
                'message_id': message_id
            })
            return None
    
    async def _execute_signal(self, signal) -> bool:
        """Execute trading signal.
        
        Args:
            signal: Trading signal to execute
            
        Returns:
            True if executed successfully
        """
        try:
            # Check if can open position
            if not await self.position_manager.can_open_position(signal):
                logger.warning(f"Cannot open position for {signal.coin}")
                return False
            leverage = self.trading_config.get_leverage_for_coin(signal.coin)
            # Calculate position size
            position_size = min(
                self.trading_config.default_position_size/20*leverage,
                self.trading_config.max_position_size/20*leverage
            )

            # Open position
            managed_position = await self.position_manager.open_position(
                signal, 
                position_size
            )
            
            if managed_position:
                logger.info(f"Successfully opened position for {signal.coin}")
                return True
            else:
                logger.error(f"Failed to open position for {signal.coin}")
                return False
                
        except Exception as e:
            logger.error(f"Error executing signal: {e}")
            await self._notify_error("execution_error", str(e), {
                'signal': signal.to_dict()
            })
            return False
    
    async def _notify_signal(self, signal, source: str, message_id: int):
        """Notify signal callbacks.
        
        Args:
            signal: Trading signal
            source: Message source
            message_id: Message ID
        """
        for callback in self.signal_callbacks:
            try:
                await callback({
                    'type': 'signal_found',
                    'signal': signal.to_dict(),
                    'source': source,
                    'message_id': message_id,
                    'timestamp': datetime.now().isoformat()
                })
            except Exception as e:
                logger.error(f"Error in signal callback: {e}")
    
    async def _notify_error(self, error_type: str, message: str, context: dict = None):
        """Notify error callbacks.
        
        Args:
            error_type: Type of error
            message: Error message
            context: Additional context
        """
        for callback in self.error_callbacks:
            try:
                await callback({
                    'type': error_type,
                    'message': message,
                    'context': context or {},
                    'timestamp': datetime.now().isoformat()
                })
            except Exception as e:
                logger.error(f"Error in error callback: {e}")
    
    async def get_stats(self) -> dict:
        """Get handler statistics.
        
        Returns:
            Statistics dictionary
        """
        # This could be enhanced with actual metrics tracking
        return {
            'signal_callbacks': len(self.signal_callbacks),
            'error_callbacks': len(self.error_callbacks),
            'trading_enabled': self.trading_config.enabled,
            'min_confidence': self.trading_config.min_confidence,
            'position_manager_stats': await self.position_manager.get_position_summary()
        }
