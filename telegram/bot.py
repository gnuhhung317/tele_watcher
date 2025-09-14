"""Telegram Bot for sending messages."""

import asyncio
from typing import Optional, Union, List
from telethon import TelegramClient
from telethon.tl.types import User, Chat, Channel

# Import with absolute path
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import TelegramConfig
from utils import get_logger

logger = get_logger(__name__)

class TelegramBot:
    """Telegram bot for sending messages and notifications."""
    
    def __init__(self, config: TelegramConfig):
        """Initialize Telegram bot.
        
        Args:
            config: Telegram configuration
        """
        self.config = config
        self.client = None
        self.is_connected = False
        
        # Validate bot configuration
        if not config.bot_token:
            logger.warning("Bot token not provided - bot functionality disabled")
        if not config.bot_chat_id:
            logger.warning("Bot chat ID not provided - using default chat")
    
    async def connect(self):
        """Connect to Telegram as bot."""
        try:
            if not self.config.bot_token:
                logger.error("Cannot connect bot - no bot token provided")
                return False
            
            # Create bot client
            self.client = TelegramClient(
                self.config.bot_session_name,
                self.config.api_id,
                self.config.api_hash
            )
            
            # Start as bot
            await self.client.start(bot_token=self.config.bot_token)
            self.is_connected = True
            
            # Get bot info
            me = await self.client.get_me()
            logger.info(f"Bot connected: @{me.username} ({me.first_name})")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect bot: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect the bot."""
        try:
            if self.client and self.is_connected:
                await self.client.disconnect()
                self.is_connected = False
                logger.info("Bot disconnected")
        except Exception as e:
            logger.error(f"Error disconnecting bot: {e}")
    
    async def send_message(
        self, 
        message: str, 
        chat_id: Optional[Union[str, int]] = None,
        parse_mode: str = "md",
        disable_web_page_preview: bool = True
    ) -> bool:
        """Send a message to specified chat.
        
        Args:
            message: Message text to send
            chat_id: Chat ID (username, phone, or ID). Uses default if None
            parse_mode: Parse mode ("md" for Markdown, "html" for HTML, None for plain)
            disable_web_page_preview: Disable link previews
            
        Returns:
            True if sent successfully
        """
        if not self.is_connected:
            logger.error("Bot not connected - cannot send message")
            return False
        
        try:
            # Use provided chat_id or default from config
            target_chat = chat_id or self.config.bot_chat_id
            
            if not target_chat:
                logger.error("No chat ID specified and no default chat configured")
                return False
            
            # Send message
            sent_message = await self.client.send_message(
                entity=target_chat,
                message=message,
                parse_mode=parse_mode,
                link_preview=not disable_web_page_preview
            )
            
            logger.info(f"Message sent to {target_chat}: {message[:50]}...")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return False
    
    async def send_signal_notification(
        self, 
        signal_data: dict, 
        status: str = "NEW",
        chat_id: Optional[Union[str, int]] = None
    ) -> bool:
        """Send a formatted trading signal notification.
        
        Args:
            signal_data: Signal data dictionary
            status: Signal status (NEW, FILLED, TP_HIT, etc.)
            chat_id: Chat ID to send to
            
        Returns:
            True if sent successfully
        """
        try:
            # Format signal message
            message = self._format_signal_message(signal_data, status)
            return await self.send_message(message, chat_id)
            
        except Exception as e:
            logger.error(f"Failed to send signal notification: {e}")
            return False
    
    async def send_position_update(
        self, 
        position_data: dict, 
        update_type: str = "UPDATE",
        chat_id: Optional[Union[str, int]] = None
    ) -> bool:
        """Send position update notification.
        
        Args:
            position_data: Position data dictionary
            update_type: Update type (UPDATE, CLOSED, SL_HIT, etc.)
            chat_id: Chat ID to send to
            
        Returns:
            True if sent successfully
        """
        try:
            # Format position message
            message = self._format_position_message(position_data, update_type)
            return await self.send_message(message, chat_id)
            
        except Exception as e:
            logger.error(f"Failed to send position update: {e}")
            return False
    
    async def send_error_notification(
        self, 
        error_message: str, 
        context: Optional[str] = None,
        chat_id: Optional[Union[str, int]] = None
    ) -> bool:
        """Send error notification.
        
        Args:
            error_message: Error message
            context: Additional context
            chat_id: Chat ID to send to
            
        Returns:
            True if sent successfully
        """
        try:
            message = f"🚨 **ERROR** 🚨\n\n"
            message += f"**Error:** {error_message}\n"
            
            if context:
                message += f"**Context:** {context}\n"
            
            message += f"\n⏰ Time: {self._get_timestamp()}"
            
            return await self.send_message(message, chat_id)
            
        except Exception as e:
            logger.error(f"Failed to send error notification: {e}")
            return False
    
    def _format_signal_message(self, signal_data: dict, status: str) -> str:
        """Format trading signal message.
        
        Args:
            signal_data: Signal data
            status: Signal status
            
        Returns:
            Formatted message string
        """
        status_emoji = {
            "NEW": "🆕",
            "FILLED": "✅", 
            "TP_HIT": "🎯",
            "SL_HIT": "🛑",
            "CANCELLED": "❌"
        }
        
        emoji = status_emoji.get(status, "📊")
        
        message = f"{emoji} **{status} SIGNAL** {emoji}\n\n"
        message += f"**Coin:** {signal_data.get('coin', 'N/A')}\n"
        message += f"**Side:** {signal_data.get('side', 'N/A').upper()}\n"
        message += f"**Entry:** {signal_data.get('entry', 'N/A')}\n"
        message += f"**Stop Loss:** {signal_data.get('stop_loss', 'N/A')}\n"
        
        # Handle multiple TPs
        take_profits = signal_data.get('take_profits')
        if take_profits:
            message += f"**Take Profits:**\n"
            for i, tp in enumerate(take_profits, 1):
                message += f"  TP{i}: {tp}\n"
        elif signal_data.get('take_profit'):
            message += f"**Take Profit:** {signal_data.get('take_profit')}\n"
        
        message += f"**Confidence:** {signal_data.get('confidence', 0):.1%}\n"
        message += f"**Order Type:** {signal_data.get('order_type', 'market').upper()}\n"
        
        message += f"\n⏰ {self._get_timestamp()}"
        
        return message
    
    def _format_position_message(self, position_data: dict, update_type: str) -> str:
        """Format position update message.
        
        Args:
            position_data: Position data
            update_type: Update type
            
        Returns:
            Formatted message string
        """
        update_emoji = {
            "UPDATE": "📈",
            "CLOSED": "🏁",
            "SL_HIT": "🛑",
            "TP_HIT": "🎯",
            "BREAKEVEN": "⚖️"
        }
        
        emoji = update_emoji.get(update_type, "📊")
        
        message = f"{emoji} **POSITION {update_type}** {emoji}\n\n"
        message += f"**Symbol:** {position_data.get('symbol', 'N/A')}\n"
        message += f"**Side:** {position_data.get('side', 'N/A').upper()}\n"
        message += f"**Size:** {position_data.get('size', 'N/A')}\n"
        message += f"**Entry Price:** {position_data.get('entry_price', 'N/A')}\n"
        message += f"**Current Price:** {position_data.get('current_price', 'N/A')}\n"
        
        pnl = position_data.get('unrealized_pnl', 0)
        pnl_emoji = "🟢" if pnl >= 0 else "🔴"
        message += f"**PnL:** {pnl_emoji} {pnl:.4f} USDT\n"
        
        if position_data.get('leverage'):
            message += f"**Leverage:** {position_data.get('leverage')}x\n"
        
        message += f"\n⏰ {self._get_timestamp()}"
        
        return message
    
    def _get_timestamp(self) -> str:
        """Get formatted timestamp."""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    async def get_chat_info(self, chat_id: Union[str, int]) -> Optional[dict]:
        """Get information about a chat.
        
        Args:
            chat_id: Chat ID or username
            
        Returns:
            Chat information dictionary or None
        """
        if not self.is_connected:
            return None
        
        try:
            entity = await self.client.get_entity(chat_id)
            
            if isinstance(entity, User):
                return {
                    "type": "user",
                    "id": entity.id,
                    "username": entity.username,
                    "first_name": entity.first_name,
                    "last_name": entity.last_name
                }
            elif isinstance(entity, (Chat, Channel)):
                return {
                    "type": "channel" if isinstance(entity, Channel) else "group",
                    "id": entity.id,
                    "title": entity.title,
                    "username": getattr(entity, 'username', None)
                }
            
        except Exception as e:
            logger.error(f"Failed to get chat info for {chat_id}: {e}")
            return None
    
    async def test_connection(self, chat_id: Optional[Union[str, int]] = None) -> bool:
        """Test bot connection by sending a test message.
        
        Args:
            chat_id: Chat ID to test with
            
        Returns:
            True if test successful
        """
        test_message = "🤖 Bot connection test - Watch Caller is online!"
        return await self.send_message(test_message, chat_id)

# Convenience functions for easy usage
class TelegramNotifier:
    """Convenience wrapper for common notification patterns."""
    
    def __init__(self, bot: TelegramBot):
        """Initialize notifier with bot instance."""
        self.bot = bot
    
    async def signal_opened(self, signal_data: dict):
        """Notify that a new signal was opened."""
        await self.bot.send_signal_notification(signal_data, "NEW")
    
    async def signal_filled(self, signal_data: dict):
        """Notify that a signal was filled."""
        await self.bot.send_signal_notification(signal_data, "FILLED")
    
    async def tp_hit(self, position_data: dict, tp_level: int):
        """Notify that a take profit was hit."""
        position_data["tp_level"] = tp_level
        await self.bot.send_position_update(position_data, "TP_HIT")
    
    async def sl_hit(self, position_data: dict):
        """Notify that stop loss was hit."""
        await self.bot.send_position_update(position_data, "SL_HIT")
    
    async def position_closed(self, position_data: dict):
        """Notify that position was closed."""
        await self.bot.send_position_update(position_data, "CLOSED")
    
    async def error_occurred(self, error_message: str, context: str = None):
        """Notify about an error."""
        await self.bot.send_error_notification(error_message, context)