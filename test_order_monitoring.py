"""
Test script for enhanced order monitoring functionality.

This script tests:
1. Enhanced get_order_status method with graceful error handling
2. check_order_filled_status method for limit vs market orders
3. monitor_order_status method with notifications
"""

import asyncio
import sys
import os

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import AppConfig
from utils import setup_logging, get_logger
from trading.exchanges import BitgetExchange
from trading.interfaces import OrderType, OrderSide, ExchangeOrder
from telegram import TelegramBot, TelegramNotifier

logger = get_logger(__name__)

async def test_order_monitoring():
    """Test order monitoring functionality."""
    
    # Setup logging
    setup_logging()
    
    # Load config
    config = AppConfig()
    
    # Initialize exchange
    exchange = BitgetExchange(
        api_key=config.exchange.bitget_api_key,
        api_secret=config.exchange.bitget_api_secret,
        passphrase=config.exchange.bitget_passphrase,
        sandbox=config.exchange.bitget_sandbox
    )
    
    try:
        # Connect to exchange
        logger.info("Connecting to exchange...")
        connected = await exchange.connect()
        if not connected:
            logger.error("Failed to connect to exchange")
            return
        
        logger.info("✅ Exchange connected successfully")
        
        # Test 1: Test get_order_status with non-existent order (should handle gracefully)
        logger.info("\n🧪 Test 1: Testing get_order_status with non-existent order")
        fake_order_id = "1234567890000000000"
        symbol = "BTCUSDT"
        
        order_status = await exchange.get_order_status(fake_order_id, symbol)
        if order_status is None:
            logger.info("✅ get_order_status correctly returned None for non-existent order")
        else:
            logger.warning("❌ get_order_status should have returned None")
        
        # Test 2: Test check_order_filled_status with different order types
        logger.info("\n🧪 Test 2: Testing check_order_filled_status")
        
        # Test with limit order (should handle gracefully)
        is_filled, order_details = await exchange.check_order_filled_status(
            fake_order_id, symbol, OrderType.LIMIT
        )
        
        if not is_filled and order_details is None:
            logger.info("✅ check_order_filled_status correctly handled non-existent limit order")
        else:
            logger.warning("❌ check_order_filled_status should return (False, None) for non-existent order")
        
        # Test 3: Test monitor_order_status
        logger.info("\n🧪 Test 3: Testing monitor_order_status")
        
        monitored_order = await exchange.monitor_order_status(
            fake_order_id, symbol, OrderType.LIMIT
        )
        
        if monitored_order is None:
            logger.info("✅ monitor_order_status correctly returned None for non-existent order")
        else:
            logger.warning("❌ monitor_order_status should have returned None")
        
        # Test 4: Test with actual market data (get current positions)
        logger.info("\n🧪 Test 4: Testing with real market data")
        
        try:
            positions = await exchange.get_positions()
            logger.info(f"✅ Successfully fetched {len(positions)} positions")
            
            if positions:
                for pos in positions:
                    logger.info(f"Position: {pos.symbol} - Side: {pos.side} - Size: {pos.size}")
            else:
                logger.info("No open positions found")
                
        except Exception as e:
            logger.warning(f"Could not fetch positions: {e}")
        
        # Test 5: Test Telegram bot integration (if configured)
        logger.info("\n🧪 Test 5: Testing Telegram bot integration")
        
        try:
            if config.telegram.bot_token and config.telegram.bot_chat_id:
                telegram_bot = TelegramBot(config.telegram)
                bot_connected = await telegram_bot.connect()
                
                if bot_connected:
                    logger.info("✅ Telegram bot connected successfully")
                    
                    # Test notification
                    notifier = TelegramNotifier(telegram_bot)
                    test_message = "🧪 Order monitoring test completed successfully!"
                    
                    success = await telegram_bot.send_message(test_message)
                    if success:
                        logger.info("✅ Test notification sent successfully")
                    else:
                        logger.warning("❌ Failed to send test notification")
                    
                    await telegram_bot.disconnect()
                else:
                    logger.warning("❌ Telegram bot failed to connect")
            else:
                logger.info("⏭️ Telegram bot not configured, skipping test")
                
        except Exception as e:
            logger.warning(f"Telegram bot test failed: {e}")
        
        logger.info("\n✅ All order monitoring tests completed!")
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        
    finally:
        # Cleanup
        await exchange.disconnect()
        logger.info("🧹 Exchange disconnected")

async def test_error_scenarios():
    """Test various error scenarios."""
    
    logger.info("\n🧪 Testing error scenarios...")
    
    config = AppConfig()
    exchange = BitgetExchange(
        api_key=config.exchange.bitget_api_key,
        api_secret=config.exchange.bitget_api_secret,
        passphrase=config.exchange.bitget_passphrase,
        sandbox=config.exchange.bitget_sandbox
    )
    
    try:
        await exchange.connect()
        
        # Test with invalid symbol
        logger.info("Testing with invalid symbol...")
        order_status = await exchange.get_order_status("123", "INVALIDSYMBOL")
        if order_status is None:
            logger.info("✅ Correctly handled invalid symbol")
        
        # Test with empty order ID
        logger.info("Testing with empty order ID...")
        order_status = await exchange.get_order_status("", "BTCUSDT")
        if order_status is None:
            logger.info("✅ Correctly handled empty order ID")
        
        logger.info("✅ Error scenario tests completed!")
        
    except Exception as e:
        logger.error(f"Error scenario test failed: {e}")
        
    finally:
        await exchange.disconnect()

if __name__ == "__main__":
    print("🚀 Starting order monitoring tests...")
    print("=" * 50)
    
    async def run_all_tests():
        await test_order_monitoring()
        await test_error_scenarios()
        
        print("\n" + "=" * 50)
        print("🎉 All tests completed!")
    
    asyncio.run(run_all_tests())