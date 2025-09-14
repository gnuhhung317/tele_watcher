"""Base exchange implementation."""

from abc import ABC
from typing import Dict, List, Optional

# Import with absolute path
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from trading.interfaces import IExchange, ExchangeOrder, Position, Balance, OrderType, OrderSide, OrderStatus
from ai.models import TradingSignal
from utils import get_logger

logger = get_logger(__name__)

class BaseExchange(IExchange):
    """Base implementation for exchanges."""
    
    def __init__(self, 
                 api_key: str, 
                 api_secret: str, 
                 passphrase: str = "", 
                 sandbox: bool = True):
        """Initialize exchange.
        
        Args:
            api_key: API key
            api_secret: API secret
            passphrase: API passphrase (if required)
            sandbox: Use sandbox environment
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.sandbox = sandbox
        self.client = None
        self.connected = False
    
    async def connect(self) -> bool:
        """Connect to exchange."""
        try:
            await self._initialize_client()
            self.connected = True
            logger.info(f"Connected to {self.__class__.__name__}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to {self.__class__.__name__}: {e}")
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from exchange."""
        if self.client:
            try:
                await self.client.close()
            except Exception as e:
                logger.error(f"Error disconnecting from exchange: {e}")
        
        self.connected = False
        logger.info(f"Disconnected from {self.__class__.__name__}")
    
    async def _initialize_client(self):
        """Initialize exchange client. Must be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement _initialize_client")
    
    def _ensure_connected(self):
        """Ensure exchange is connected."""
        if not self.connected:
            raise RuntimeError("Exchange not connected. Call connect() first.")
    
    async def execute_signal(self, signal: TradingSignal, position_size: float, leverage: int = 1) -> List[ExchangeOrder]:
        """Execute a trading signal with proper order management.
        
        Args:
            signal: Trading signal to execute
            position_size: Position size in quote currency
            leverage: Leverage to use for the position
            
        Returns:
            List of created orders
        """
        self._ensure_connected()
        
        orders = []
        
        try:
            # Format symbol for this exchange
            symbol = self.format_symbol(signal.coin)
            
            # Set leverage if exchange supports it
            if hasattr(self, 'set_leverage'):
                self.set_leverage(symbol, leverage)
            
            # Get ticker to validate symbol and get current price
            ticker = await self.get_ticker(symbol)
            current_price = float(ticker['last'])
            
            # Calculate position size in base currency
            base_amount = position_size / signal.entry
            
            # Create entry order - use MARKET order to avoid position mode issues
            entry_side = OrderSide.BUY if signal.side.value == "long" else OrderSide.SELL
            
            entry_order = ExchangeOrder(
                price=signal.entry,
                symbol=symbol,
                side=entry_side,
                amount=base_amount,
                order_type=OrderType.MARKET if signal.order_type == 'market' else OrderType.LIMIT
            )
            
            created_entry = await self.create_order(entry_order)
            orders.append(created_entry)
            
            logger.info(f"Created entry order: {created_entry.order_id} for {symbol}")
            
            # Create stop loss order (if entry order is filled or pending)
            if created_entry.status != OrderStatus.REJECTED:
                stop_side = OrderSide.SELL if signal.side.value == "long" else OrderSide.BUY
                
                stop_order = ExchangeOrder(
                    symbol=symbol,
                    side=stop_side,
                    amount=base_amount,
                    order_type=OrderType.STOP_LOSS,
                    stop_price=signal.stop_loss
                )
                
                try:
                    created_stop = await self.create_order(stop_order)
                    orders.append(created_stop)
                    logger.info(f"Created stop loss order: {created_stop.order_id}")
                except Exception as e:
                    logger.error(f"Failed to create stop loss order: {e}")
            
            # Create take profit order (if specified)
            if signal.take_profit and created_entry.status != OrderStatus.REJECTED:
                tp_side = OrderSide.SELL if signal.side.value == "long" else OrderSide.BUY
                
                tp_order = ExchangeOrder(
                    symbol=symbol,
                    side=tp_side,
                    amount=base_amount,
                    order_type=OrderType.TAKE_PROFIT,
                    price=signal.take_profit
                )
                
                try:
                    created_tp = await self.create_order(tp_order)
                    orders.append(created_tp)
                    logger.info(f"Created take profit order: {created_tp.order_id}")
                except Exception as e:
                    logger.error(f"Failed to create take profit order: {e}")
            
            return orders
            
        except Exception as e:
            logger.error(f"Error executing signal for {signal.coin}: {e}")
            
            # Cancel any created orders on error
            for order in orders:
                if order.order_id:
                    try:
                        await self.cancel_order(order.order_id, order.symbol)
                        logger.info(f"Cancelled order {order.order_id} due to error")
                    except Exception as cancel_error:
                        logger.error(f"Failed to cancel order {order.order_id}: {cancel_error}")
            
            raise e
    
    def format_symbol(self, base: str, quote: str = "USDT") -> str:
        """Default symbol formatting. Override in subclasses if needed.
        
        Args:
            base: Base currency
            quote: Quote currency
            
        Returns:
            Formatted symbol
        """
        return f"{base.upper()}{quote.upper()}"
