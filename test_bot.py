"""Simple test for bot configuration."""

import asyncio
import sys
import os

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import AppConfig
from telegram import TelegramBot
from utils import setup_logging, get_logger

async def test_bot_config():
    """Test bot configuration and provide setup guidance."""
    
    setup_logging(level="INFO")
    logger = get_logger(__name__)
    
    logger.info("🤖 Bot Configuration Test")
    
    try:
        config = AppConfig()
        
        # Check configuration
        logger.info(f"Bot Token: {'✅ Set' if config.telegram.bot_token else '❌ Missing'}")
        logger.info(f"Chat ID: {'✅ Set' if config.telegram.bot_chat_id else '❌ Missing'}")
        
        if not config.telegram.bot_token:
            logger.error("❌ TELEGRAM_BOT_TOKEN missing in .env")
            logger.info("Please add: TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather")
            return
        
        if not config.telegram.bot_chat_id:
            logger.warning("⚠️ TELEGRAM_BOT_CHAT_ID missing in .env")
            logger.info("Please add: TELEGRAM_BOT_CHAT_ID=your_user_id_or_channel")
            logger.info("You can get your chat ID by messaging @userinfobot")
            return
        
        # Test connection
        bot = TelegramBot(config.telegram)
        
        if await bot.connect():
            logger.info("✅ Bot connected successfully!")
            
            # Try to send message
            test_msg = "🤖 Bot test - connection successful!"
            success = await bot.send_message(test_msg)
            
            if success:
                logger.info("✅ Test message sent!")
            else:
                logger.error("❌ Failed to send message")
                logger.info("Check if your TELEGRAM_BOT_CHAT_ID is correct")
                logger.info("Make sure it's your user ID, not another bot's ID")
            
            await bot.disconnect()
        else:
            logger.error("❌ Failed to connect bot")
            
    except Exception as e:
        logger.error(f"❌ Error: {e}")

if __name__ == "__main__":
    print("🔧 Bot Configuration Test")
    print("-" * 30)
    asyncio.run(test_bot_config())