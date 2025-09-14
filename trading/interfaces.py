"""Trading interfaces and factory."""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Union
from dataclasses import dataclass
from enum import Enum

# Import with absolute path
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.models import TradingSignal

class OrderType(Enum):
    """Order types."""
    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"

class OrderSide(Enum):
    """Order sides."""
    BUY = "buy"
    SELL = "sell"

class OrderStatus(Enum):
    """Order status."""
    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"

@dataclass
class ExchangeOrder:
    """Exchange order representation."""
    symbol: str
    side: OrderSide
    amount: float
    order_type: OrderType = OrderType.MARKET
    price: Optional[float] = None
    stop_price: Optional[float] = None
    order_id: Optional[str] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_amount: float = 0.0
    average_price: Optional[float] = None
    fees: Optional[Dict] = None
    timestamp: Optional[str] = None
    stoploss_price: Optional[float] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'symbol': self.symbol,
            'side': self.side.value,
            'amount': self.amount,
            'type': self.order_type.value,
            'price': self.price,
            'stopPrice': self.stop_price,
            'id': self.order_id,
            'status': self.status.value,
            'filled': self.filled_amount,
            'average': self.average_price,
            'fee': self.fees,
            'timestamp': self.timestamp
        }

@dataclass
class Position:
    """Trading position."""
    symbol: str
    side: str  # "long" or "short"
    size: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float = 0.0
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    leverage: int = 1
    margin: float = 0.0
    timestamp: Optional[str] = None
    
    @property
    def pnl_percentage(self) -> float:
        """Calculate PnL percentage."""
        if self.entry_price == 0:
            return 0.0
        
        if self.side == "long":
            return ((self.current_price - self.entry_price) / self.entry_price) * 100
        else:  # short
            return ((self.entry_price - self.current_price) / self.entry_price) * 100

@dataclass
class Balance:
    """Account balance."""
    currency: str
    free: float
    used: float
    total: float

class IExchange(ABC):
    """Interface for exchange implementations."""
    
    @abstractmethod
    async def connect(self) -> bool:
        """Connect to exchange.
        
        Returns:
            True if connected successfully, False otherwise
        """
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from exchange."""
        pass
    
    @abstractmethod
    async def get_balance(self, currency: str = None) -> Union[Balance, Dict[str, Balance]]:
        """Get account balance.
        
        Args:
            currency: Specific currency or None for all
            
        Returns:
            Balance or dictionary of balances
        """
        pass
    
    @abstractmethod
    async def create_order(self, order: ExchangeOrder) -> ExchangeOrder:
        """Create a new order.
        
        Args:
            order: Order to create
            
        Returns:
            Created order with ID and status
        """
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an order.
        
        Args:
            order_id: Order ID to cancel
            symbol: Trading symbol
            
        Returns:
            True if cancelled successfully
        """
        pass
    
    @abstractmethod
    async def get_order_status(self, order_id: str, symbol: str) -> Optional[ExchangeOrder]:
        """Get order status.
        
        Args:
            order_id: Order ID
            symbol: Trading symbol
            
        Returns:
            Order with current status or None if not found
        """
        pass
    
    @abstractmethod
    async def get_positions(self, symbol: str = None) -> List[Position]:
        """Get open positions.
        
        Args:
            symbol: Specific symbol or None for all
            
        Returns:
            List of positions
        """
        pass
    
    @abstractmethod
    async def get_ticker(self, symbol: str) -> Dict:
        """Get ticker data.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Ticker data
        """
        pass
    
    @abstractmethod
    def format_symbol(self, base: str, quote: str = "USDT") -> str:
        """Format symbol for this exchange.
        
        Args:
            base: Base currency
            quote: Quote currency
            
        Returns:
            Formatted symbol
        """
        pass
    
    @abstractmethod
    async def execute_signal(self, signal: TradingSignal, position_size: float, leverage: int = 1) -> List[ExchangeOrder]:
        """Execute a trading signal.
        
        Args:
            signal: Trading signal to execute
            position_size: Position size in quote currency
            leverage: Leverage to use
            
        Returns:
            List of created orders
        """
        pass
    
    async def create_multi_tp_orders(
        self, 
        symbol: str, 
        side: OrderSide, 
        tp_orders: List, 
        reduce_only: bool = True
    ) -> List[ExchangeOrder]:
        """Create multiple take profit orders.
        
        Args:
            symbol: Trading symbol
            side: Order side (opposite of position side)
            tp_orders: List of TPOrder objects
            reduce_only: Whether orders should be reduce-only
            
        Returns:
            List of created take profit orders
        """
        created_orders = []
        
        for tp_order in tp_orders:
            try:
                order = ExchangeOrder(
                    symbol=symbol,
                    side=side,
                    amount=tp_order.quantity,
                    order_type=OrderType.LIMIT,  # TP as limit order
                    price=tp_order.price
                )
                
                created_order = await self.create_order(order)
                
                # Update TPOrder with exchange order ID
                tp_order.order_id = created_order.order_id
                created_orders.append(created_order)
                
            except Exception as e:
                # Log error but continue with other TPs
                print(f"Error creating TP{tp_order.level} order: {e}")
        
        return created_orders
    
    async def modify_stop_loss(self, symbol: str, new_stop_price: float) -> bool:
        """Modify stop loss for a position.
        
        Args:
            symbol: Trading symbol
            new_stop_price: New stop loss price
            
        Returns:
            True if modified successfully
        """
        # Default implementation - exchanges should override if they support direct modification
        return False

class ExchangeFactory:
    """Factory for creating exchange instances."""
    
    _exchanges = {}
    
    @classmethod
    def register_exchange(cls, name: str, exchange_class):
        """Register an exchange class.
        
        Args:
            name: Exchange name
            exchange_class: Exchange class
        """
        cls._exchanges[name.lower()] = exchange_class
    
    @classmethod
    def create_exchange(cls, name: str, **kwargs) -> IExchange:
        """Create exchange instance.
        
        Args:
            name: Exchange name
            **kwargs: Exchange-specific parameters
            
        Returns:
            Exchange instance
        """
        exchange_class = cls._exchanges.get(name.lower())
        if not exchange_class:
            raise ValueError(f"Exchange '{name}' not registered")
        
        return exchange_class(**kwargs)
    
    @classmethod
    def get_available_exchanges(cls) -> List[str]:
        """Get list of available exchanges.
        
        Returns:
            List of exchange names
        """
        return list(cls._exchanges.keys())
