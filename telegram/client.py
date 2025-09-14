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
            
            # Verify channels and get entities
            channel_entities = await self._verify_channels()
            
            # Setup message handler with entity objects
            @self.client.on(events.NewMessage(chats=channel_entities))
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
        """Verify that all channels are accessible.
        
        Returns:
            List of channel entities that can be monitored
        """
        # Get all dialogs first
        logger.info("Getting accessible dialogs...")
        dialogs = await self.client.get_dialogs(limit=100)
        
        # Create mapping of channel ID to entity
        available_channels = {}
        for dialog in dialogs:
            # Store both ID and title/username for lookup
            available_channels[str(dialog.entity.id)] = dialog.entity
            if hasattr(dialog.entity, 'username') and dialog.entity.username:
                available_channels[dialog.entity.username] = dialog.entity
            if hasattr(dialog.entity, 'title') and dialog.entity.title:
                available_channels[dialog.entity.title] = dialog.entity
        
        logger.info(f"Found {len(dialogs)} accessible dialogs")
        
        channel_entities = []
        for channel in self.config.channels:
            channel_str = str(channel)
            if channel_str in available_channels:
                entity = available_channels[channel_str]
                channel_entities.append(entity)
                channel_name = getattr(entity, 'title', getattr(entity, 'username', channel))
                logger.info(f"✅ Watching channel: {channel_name} (ID: {channel})")
            else:
                logger.error(f"❌ Cannot access channel {channel}")
                logger.error("Available channels:")
                for dialog in dialogs[:10]:  # Show first 10 for debugging
                    name = getattr(dialog.entity, 'title', getattr(dialog.entity, 'username', 'Unknown'))
                    logger.error(f"  - {name} (ID: {dialog.entity.id})")
                raise ValueError(f"Channel {channel} is not accessible")
        
        return channel_entities
    
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
