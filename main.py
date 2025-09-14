"""
Watch Caller - Telegram Signal Trading Bot

A modular trading bot that:
1. Watches Telegram channels for trading signals
2. Parses signals using Gemini AI
3. Executes trades on supported exchanges (Bitget)
4. Manages positions with risk management
"""

import asyncio
import signal
import sys
import os
from typing import Optional

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import AppConfig
from utils import setup_logging, get_logger
from telegram import TelegramWatcher, MessageHandler, TelegramBot, TelegramNotifier
from ai import GeminiParser
from trading import ExchangeFactory, PositionManager
from trading.exchanges import BitgetExchange

logger = get_logger(__name__)

class WatchCaller:
    """Main application class."""
    
    def __init__(self):
        """Initialize the application."""
        self.config = AppConfig()
        self.telegram_watcher: Optional[TelegramWatcher] = None
        self.message_handler: Optional[MessageHandler] = None
        self.position_manager: Optional[PositionManager] = None
        self.telegram_bot: Optional[TelegramBot] = None
        self.notifier: Optional[TelegramNotifier] = None
        self.exchange = None
        self.running = False
    
    async def initialize(self):
        """Initialize all components."""
        logger.info("Initializing Watch Caller...")
        
        # Setup logging
        setup_logging(
            level=self.config.log_level,
            log_file=self.config.log_file
        )
        
        # Initialize exchange
        logger.info("Initializing exchange...")
        ExchangeFactory.register_exchange("bitget", BitgetExchange)
        
        self.exchange = ExchangeFactory.create_exchange(
            "bitget",
            api_key=self.config.exchange.bitget_api_key,
            api_secret=self.config.exchange.bitget_api_secret,
            passphrase=self.config.exchange.bitget_passphrase,
            sandbox=self.config.exchange.bitget_sandbox,
            position_mode=self.config.trading.position_mode
        )
        
        # Connect to exchange
        connected = await self.exchange.connect()
        if not connected:
            raise RuntimeError("Failed to connect to exchange")
        
        # Initialize position manager
        logger.info("Initializing position manager...")
        self.position_manager = PositionManager(
            exchange=self.exchange,
            trading_config=self.config.trading,
            max_positions=self.config.trading.max_positions
        )
        
        # Initialize AI parser
        logger.info("Initializing AI parser...")
        ai_parser = GeminiParser(
            api_key=self.config.ai.gemini_api_key,
            model_name=self.config.ai.model_name
        )
        
        # Initialize message handler
        logger.info("Initializing message handler...")
        self.message_handler = MessageHandler(
            ai_parser=ai_parser,
            position_manager=self.position_manager,
            trading_config=self.config.trading
        )
        
        # Add callbacks
        self.message_handler.add_signal_callback(self._on_signal_found)
        self.message_handler.add_error_callback(self._on_error)
        
        # Initialize Telegram bot for notifications
        logger.info("Initializing Telegram bot...")
        try:
            self.telegram_bot = TelegramBot(self.config.telegram)
            bot_connected = await self.telegram_bot.connect()
            
            if bot_connected:
                self.notifier = TelegramNotifier(self.telegram_bot)
                logger.info("Telegram bot connected and ready for notifications")
                
                # Test bot connection if chat ID is configured
                if self.config.telegram.bot_chat_id:
                    await self.telegram_bot.test_connection()
            else:
                logger.warning("Telegram bot failed to connect - notifications disabled")
                
        except Exception as e:
            logger.warning(f"Failed to initialize Telegram bot: {e}")
            logger.warning("Continuing without bot notifications")
        
        # Initialize Telegram watcher
        logger.info("Initializing Telegram watcher...")
        self.telegram_watcher = TelegramWatcher(self.config.telegram)
        self.telegram_watcher.add_message_handler(self.message_handler.handle_message)
        
        logger.info("Initialization complete!")
    
    async def start(self):
        """Start the application."""
        if not self.telegram_watcher:
            await self.initialize()
        
        logger.info("Starting Watch Caller...")
        
        # Setup signal handlers for graceful shutdown
        for sig in [signal.SIGINT, signal.SIGTERM]:
            signal.signal(sig, self._signal_handler)
        
        self.running = True
        
        # Start background tasks
        tasks = [
            asyncio.create_task(self._run_telegram_watcher()),
            asyncio.create_task(self._run_position_updater()),
            asyncio.create_task(self._run_cleanup_task()),
            asyncio.create_task(self._run_tp_monitor())  # Multi-TP monitoring
        ]
        
        try:
            # Wait for all tasks
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("Application cancelled")
        except Exception as e:
            logger.error(f"Application error: {e}")
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """Shutdown the application gracefully."""
        logger.info("Shutting down Watch Caller...")
        
        self.running = False
        
        # Stop Telegram watcher
        if self.telegram_watcher:
            await self.telegram_watcher.stop()
        
        # Disconnect Telegram bot
        if self.telegram_bot:
            await self.telegram_bot.disconnect()
        
        # Disconnect exchange
        if self.exchange:
            await self.exchange.disconnect()
        
        logger.info("Shutdown complete")
    
    async def _run_telegram_watcher(self):
        """Run Telegram message watcher."""
        try:
            await self.telegram_watcher.run()
        except Exception as e:
            logger.error(f"Telegram watcher error: {e}")
            self.running = False
    
    async def _run_position_updater(self):
        """Run position updater task with order monitoring."""
        while self.running:
            try:
                # Update positions
                await self.position_manager.update_positions()
                
                # Monitor active orders if exchange supports it
                if hasattr(self.exchange, 'monitor_order_status'):
                    await self._monitor_active_orders()
                
                await asyncio.sleep(30)  # Update every 30 seconds
            except Exception as e:
                logger.error(f"Position updater error: {e}")
                # Send error notification for critical position updates
                if self.notifier:
                    await self.notifier.error_occurred(f"Position update failed: {e}", "Position Updater")
                await asyncio.sleep(60)  # Wait longer on error
    
    async def _monitor_active_orders(self):
        """Monitor active orders for fills and updates."""
        try:
            # Get all managed positions
            if hasattr(self.position_manager, 'get_active_positions'):
                active_positions = await self.position_manager.get_active_positions()
                
                for position in active_positions:
                    # Check entry orders
                    if hasattr(position, 'entry_orders'):
                        for entry_order in position.entry_orders:
                            if (entry_order.order_id and 
                                entry_order.status.value not in ['filled', 'cancelled']):
                                
                                updated_order = await self.exchange.monitor_order_status(
                                    entry_order.order_id, 
                                    position.position.symbol, 
                                    entry_order.order_type
                                )
                                
                                if updated_order and updated_order.status.value == 'filled':
                                    if self.notifier:
                                        await self.notifier.signal_filled({
                                            'symbol': position.position.symbol,
                                            'order_id': entry_order.order_id,
                                            'fill_price': updated_order.average_price,
                                            'order_type': 'ENTRY'
                                        })
                    
                    # Check TP orders
                    if hasattr(position, 'take_profit_orders'):
                        for tp_order in position.take_profit_orders:
                            if (tp_order.order_id and 
                                tp_order.status.value not in ['filled', 'cancelled']):
                                
                                updated_order = await self.exchange.monitor_order_status(
                                    tp_order.order_id, 
                                    position.position.symbol, 
                                    tp_order.order_type
                                )
                                
                                if updated_order and updated_order.status.value == 'filled':
                                    if self.notifier:
                                        await self.notifier.tp_hit({
                                            'symbol': position.position.symbol,
                                            'order_id': tp_order.order_id,
                                            'fill_price': updated_order.average_price
                                        }, 1)  # TP level
                    
                    # Check SL orders
                    if hasattr(position, 'stop_loss_orders'):
                        for sl_order in position.stop_loss_orders:
                            if (sl_order.order_id and 
                                sl_order.status.value not in ['filled', 'cancelled']):
                                
                                updated_order = await self.exchange.monitor_order_status(
                                    sl_order.order_id, 
                                    position.position.symbol, 
                                    sl_order.order_type
                                )
                                
                                if updated_order and updated_order.status.value == 'filled':
                                    if self.notifier:
                                        await self.notifier.sl_hit({
                                            'symbol': position.position.symbol,
                                            'order_id': sl_order.order_id,
                                            'fill_price': updated_order.average_price
                                        })
        
        except Exception as e:
            logger.warning(f"Order monitoring error: {e}")
    
    async def _run_cleanup_task(self):
        """Run cleanup task."""
        while self.running:
            try:
                await self.position_manager.cleanup_inactive_positions()
                await asyncio.sleep(3600)  # Run every hour
            except Exception as e:
                logger.error(f"Cleanup task error: {e}")
                await asyncio.sleep(3600)
    
    async def _run_tp_monitor(self):
        """Run Multi-TP monitoring task with enhanced notifications."""
        while self.running:
            try:
                # Check for filled take profit orders
                filled_tps = await self.position_manager.check_tp_fills()
                
                if filled_tps:
                    for symbol, tp_levels in filled_tps.items():
                        logger.info(f"TP filled for {symbol}: levels {tp_levels}")
                        
                        # Get Multi-TP status
                        tp_status = await self.position_manager.get_multi_tp_status(symbol)
                        if tp_status and tp_status.get('is_multi_tp'):
                            filled_count = tp_status['filled_tp_count']
                            total_count = tp_status['total_tp_levels']
                            remaining = tp_status['remaining_quantity']
                            
                            logger.info(
                                f"{symbol} Multi-TP progress: {filled_count}/{total_count} filled, "
                                f"remaining: {remaining:.6f}, breakeven: {tp_status['breakeven_adjusted']}"
                            )
                            
                            # Send enhanced notification
                            if self.notifier:
                                notification_data = {
                                    'symbol': symbol,
                                    'filled_levels': tp_levels,
                                    'status': tp_status,
                                    'progress': f"{filled_count}/{total_count}",
                                    'remaining_quantity': remaining,
                                    'breakeven_adjusted': tp_status['breakeven_adjusted']
                                }
                                await self.notifier.tp_hit(notification_data, tp_levels[0] if tp_levels else 0)
                            
                            # Trigger callback for TP fills
                            await self._on_tp_filled({
                                'symbol': symbol,
                                'filled_levels': tp_levels,
                                'status': tp_status
                            })
                
                await asyncio.sleep(self.config.trading.tp_monitor_interval)  # Use config interval
                
            except Exception as e:
                logger.error(f"TP monitor error: {e}")
                # Send notification for TP monitoring errors
                if self.notifier:
                    await self.notifier.error_occurred(f"TP monitoring failed: {e}", "TP Monitor")
                await asyncio.sleep(30)  # Wait longer on error
    
    async def _on_signal_found(self, data: dict):
        """Handle signal found event.
        
        Args:
            data: Signal data
        """
        logger.info(f"Signal found: {data['signal']['coin']} from {data['source']}")
        
        # Log signal details
        signal_data = data['signal']
        logger.info(f"Entry: {signal_data['entry']}, Stop Loss: {signal_data['stop_loss']}, Confidence: {signal_data['confidence']}")
        
        # Send notification for new signal
        if self.notifier:
            try:
                await self.notifier.signal_opened(signal_data)
            except Exception as e:
                logger.warning(f"Failed to send signal notification: {e}")
    
    async def _on_error(self, data: dict):
        """Handle error event.
        
        Args:
            data: Error data
        """
        logger.error(f"Error {data['type']}: {data['message']}")
        
        # Send notification for critical errors
        if self.notifier and data.get('critical', False):
            try:
                await self.notifier.error_occurred(data['message'], data['type'])
            except Exception as e:
                logger.warning(f"Failed to send error notification: {e}")
    
    async def _monitor_order_status(self, order_id: str, symbol: str, order_type: str = "LIMIT"):
        """Monitor individual order status and send notifications.
        
        Args:
            order_id: Order ID to monitor
            symbol: Trading symbol
            order_type: Type of order (LIMIT/MARKET)
        """
        try:
            from trading.interfaces import OrderType
            
            # Convert string to OrderType enum
            order_type_enum = OrderType.LIMIT if order_type == "LIMIT" else OrderType.MARKET
            
            # Monitor order using enhanced method
            order_status = await self.exchange.monitor_order_status(order_id, symbol, order_type_enum)
            
            if order_status:
                # Send notification for order fills
                if order_status.status.value in ["filled", "partially_filled"]:
                    if self.notifier:
                        message = (
                            f"✅ Order Filled\n"
                            f"Symbol: {symbol}\n"
                            f"Order ID: {order_id[:8]}...\n"
                            f"Type: {order_type}\n"
                            f"Status: {order_status.status.value}\n"
                            f"Fill Price: {order_status.average_price or 'N/A'}\n"
                            f"Filled: {order_status.filled_amount}/{order_status.amount}"
                        )
                        await self.telegram_bot.send_message(message)
                        
            return order_status
            
        except Exception as e:
            logger.error(f"Error monitoring order {order_id}: {e}")
            if self.notifier:
                await self.notifier.error_occurred(
                    f"Order monitoring failed: {e}", 
                    f"Order {order_id[:8]}..."
                )
            return None
    
    async def _on_tp_filled(self, data: dict):
        """Handle take profit filled event.
        
        Args:
            data: TP fill data
        """
        symbol = data['symbol']
        filled_levels = data['filled_levels']
        status = data['status']
        
        logger.info(f"TP filled callback for {symbol}: levels {filled_levels}")
        
        # Log detailed Multi-TP status
        if status.get('is_multi_tp'):
            filled_count = status['filled_tp_count']
            total_count = status['total_tp_levels']
            remaining = status['remaining_quantity']
            breakeven = status['breakeven_adjusted']
            
            # Send notification via Telegram bot
            message = (
                f"🎯 Multi-TP Update for {symbol}\n"
                f"✅ TP{filled_levels} filled\n"
                f"📊 Progress: {filled_count}/{total_count} TPs\n"
                f"💰 Remaining: {remaining:.6f}\n"
                f"🛡️ Breakeven: {'Yes' if breakeven else 'No'}"
            )
            
            logger.info(message)
            
            # Send notification if bot is available
            if self.notifier:
                await self.notifier.tp_hit(data, filled_levels[0] if filled_levels else 0)
            
            # Check if all TPs are filled
            if filled_count == total_count:
                logger.info(f"🎉 All TPs filled for {symbol} - Position fully closed!")
                if self.notifier:
                    await self.notifier.position_closed(data)
        
        # Could trigger additional actions like:
        # - Update external tracking systems
        # - Trigger other trading strategies
    
    def _signal_handler(self, signum, frame):
        """Handle system signals for graceful shutdown."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False
    
    # Convenience methods for sending notifications
    async def send_notification(self, message: str, chat_id: Optional[str] = None) -> bool:
        """Send a notification message via Telegram bot.
        
        Args:
            message: Message to send
            chat_id: Optional chat ID (uses default if None)
            
        Returns:
            True if sent successfully
        """
        if self.telegram_bot and self.telegram_bot.is_connected:
            return await self.telegram_bot.send_message(message, chat_id)
        return False
    
    async def send_signal_notification(self, signal_data: dict, status: str = "NEW") -> bool:
        """Send a signal notification.
        
        Args:
            signal_data: Signal data dictionary
            status: Signal status
            
        Returns:
            True if sent successfully
        """
        if self.notifier:
            return await self.notifier.signal_opened(signal_data) if status == "NEW" else \
                   await self.notifier.signal_filled(signal_data) if status == "FILLED" else \
                   await self.telegram_bot.send_signal_notification(signal_data, status)
        return False
    
    async def send_error_notification(self, error_message: str, context: str = None) -> bool:
        """Send an error notification.
        
        Args:
            error_message: Error message
            context: Additional context
            
        Returns:
            True if sent successfully
        """
        if self.notifier:
            return await self.notifier.error_occurred(error_message, context)
        return False

    async def get_status(self) -> dict:
        """Get application status.
        
        Returns:
            Status dictionary
        """
        status = {
            'running': self.running,
            'telegram_connected': self.telegram_watcher.is_running if self.telegram_watcher else False,
            'exchange_connected': self.exchange.connected if self.exchange else False,
            'trading_enabled': self.config.trading.enabled
        }
        
        if self.position_manager:
            status['positions'] = await self.position_manager.get_position_summary()
        
        if self.message_handler:
            status['handler_stats'] = await self.message_handler.get_stats()
        
        return status

async def main():
    """Main entry point."""
    app = WatchCaller()
    
    try:
        await app.start()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Check if running in debug mode
    if len(sys.argv) > 1 and sys.argv[1] == "--debug":
        import logging
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Run the application
    asyncio.run(main())
