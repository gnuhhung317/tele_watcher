"""Telegram client wrapper."""

import asyncio
from typing import List, Callable, Optional
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto

# Import with absolute path
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import TelegramConfig
from utils import get_logger

logger = get_logger(__name__)

class TelegramWatcher:
    """Telegram client wrapper for watching messages."""
    
    def __init__(self, config: TelegramConfig):
        """Initialize Telegram watcher.
        
        Args:
            config: Telegram configuration
        """
        self.config = config
        self.client = TelegramClient(
            config.session_name, 
            config.api_id, 
            config.api_hash
        )
        self.message_handlers: List[Callable] = []
        self.is_running = False
    
    def add_message_handler(self, handler: Callable):
        """Add message handler.
        
        Args:
            handler: Async function to handle messages
        """
        self.message_handlers.append(handler)
    
    async def start(self):
        """Start the Telegram client."""
        try:
            await self.client.start()
            self.is_running = True
            logger.info("Telegram client started successfully")
            
            # Verify channels
            await self._verify_channels()
            
            # Setup message handler
            @self.client.on(events.NewMessage(chats=self.config.channels))
            async def message_handler(event: events.NewMessage.Event):
                await self._handle_message(event)
            
        except Exception as e:
            logger.error(f"Failed to start Telegram client: {e}")
            raise
    
    async def stop(self):
        """Stop the Telegram client."""
        if self.client.is_connected():
            await self.client.disconnect()
        self.is_running = False
        logger.info("Telegram client stopped")
    
    async def run(self):
        """Run the client until disconnected."""
        if not self.is_running:
            await self.start()
        
        logger.info("Telegram watcher is running...")
        await self.client.run_until_disconnected()
    
    async def _verify_channels(self):
        """Verify that all channels are accessible."""
        for channel in self.config.channels:
            try:
                entity = await self.client.get_entity(channel)
                channel_name = getattr(entity, 'title', getattr(entity, 'username', channel))
                logger.info(f"Watching channel: {channel_name} ({channel})")
            except Exception as e:
                logger.error(f"Cannot access channel {channel}: {e}")
                raise
    
    async def _handle_message(self, event: events.NewMessage.Event):
        """Handle incoming messages.
        
        Args:
            event: Telegram message event
        """
        try:
            message = event.message
            chat = await event.get_chat()
            chat_title = getattr(chat, 'title', getattr(chat, 'username', 'Unknown'))
            
            # Process text messages
            if message.raw_text:
                for handler in self.message_handlers:
                    try:
                        await handler(
                            text=message.raw_text,
                            source=chat_title,
                            message_id=message.id,
                            timestamp=message.date
                        )
                    except Exception as e:
                        logger.error(f"Error in message handler: {e}")
            
            # Handle media if enabled
            if (self.config.download_media and 
                isinstance(message.media, (MessageMediaPhoto, MessageMediaDocument))):
                await self._handle_media(message, chat_title)
        
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    async def _handle_media(self, message, chat_title: str):
        """Handle media messages.
        
        Args:
            message: Telegram message with media
            chat_title: Chat title
        """
        try:
            import os
            os.makedirs(self.config.download_path, exist_ok=True)
            
            filename = f"{chat_title}_{message.id}"
            path = await self.client.download_media(
                message.media, 
                file=f"{self.config.download_path}/{filename}"
            )
            
            if path:
                logger.info(f"Downloaded media: {path}")
        
        except Exception as e:
            logger.error(f"Error downloading media: {e}")
    
    async def send_message(self, channel: str, text: str):
        """Send message to a channel (if bot has permissions).
        
        Args:
            channel: Channel to send to
            text: Message text
        """
        try:
            if not self.is_running:
                raise RuntimeError("Client not running")
            
            await self.client.send_message(channel, text)
            logger.info(f"Sent message to {channel}")
            
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            raise
    
    async def get_channel_info(self, channel: str) -> dict:
        """Get information about a channel.
        
        Args:
            channel: Channel identifier
            
        Returns:
            Channel information dictionary
        """
        try:
            entity = await self.client.get_entity(channel)
            
            return {
                'id': entity.id,
                'title': getattr(entity, 'title', None),
                'username': getattr(entity, 'username', None),
                'type': entity.__class__.__name__,
                'participants_count': getattr(entity, 'participants_count', None)
            }
            
        except Exception as e:
            logger.error(f"Error getting channel info: {e}")
            return {}
