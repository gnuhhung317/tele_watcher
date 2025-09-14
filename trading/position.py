"""Position management module."""

from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta

# Import with absolute path
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.models import TradingSignal
from .interfaces import IExchange, Position, ExchangeOrder
from config import TradingConfig
from utils import get_logger, TPOrder, calculate_position_splits

logger = get_logger(__name__)

@dataclass
class ManagedPosition:
    """A managed trading position with metadata."""
    position: Position
    signal: TradingSignal
    entry_orders: List[ExchangeOrder]
    stop_loss_orders: List[ExchangeOrder]
    take_profit_orders: List[ExchangeOrder]
    created_at: datetime
    updated_at: datetime
    is_active: bool = True
    
    # Multi-TP support
    tp_orders: List[TPOrder] = field(default_factory=list)  # Planned TP orders
    tp_filled_status: Dict[int, bool] = field(default_factory=dict)  # TP level -> filled status
    remaining_quantity: float = 0.0  # Remaining position size
    breakeven_adjusted: bool = False  # Whether SL was moved to breakeven
    last_tp_filled: Optional[int] = None  # Last TP level that was filled
    
    def __post_init__(self):
        """Initialize Multi-TP tracking after creation."""
        if self.signal.is_multi_tp():
            # Initialize TP tracking
            for tp_order in self.tp_orders:
                self.tp_filled_status[tp_order.level] = False
            self.remaining_quantity = self.position.size
    
    def update_timestamp(self):
        """Update the last updated timestamp."""
        self.updated_at = datetime.now()
    
    def mark_tp_filled(self, tp_level: int, filled_quantity: float = None):
        """Mark a TP level as filled."""
        if tp_level in self.tp_filled_status:
            self.tp_filled_status[tp_level] = True
            self.last_tp_filled = tp_level
            
            # Update TP order
            for tp_order in self.tp_orders:
                if tp_order.level == tp_level:
                    tp_order.filled = True
                    if filled_quantity is not None:
                        tp_order.filled_quantity = filled_quantity
                        self.remaining_quantity -= filled_quantity
                    else:
                        tp_order.filled_quantity = tp_order.quantity
                        self.remaining_quantity -= tp_order.quantity
                    break
            
            self.update_timestamp()
    
    def get_filled_tp_count(self) -> int:
        """Get number of filled TP levels."""
        return sum(1 for filled in self.tp_filled_status.values() if filled)
    
    def get_next_unfilled_tp(self) -> Optional[TPOrder]:
        """Get the next unfilled TP order."""
        for tp_order in self.tp_orders:
            if not tp_order.filled:
                return tp_order
        return None
    
    def should_adjust_to_breakeven(self) -> bool:
        """Check if stop loss should be adjusted to breakeven."""
        return (
            self.signal.is_multi_tp() and 
            not self.breakeven_adjusted and
            self.get_filled_tp_count() > 0 and
            self.remaining_quantity > 0
        )
    
    def is_fully_closed(self) -> bool:
        """Check if position is fully closed (all TPs filled or stopped out)."""
        if not self.signal.is_multi_tp():
            return not self.is_active
        
        return (
            not self.is_active or 
            self.remaining_quantity <= 0 or
            all(self.tp_filled_status.values())
        )

class PositionManager:
    """Manages trading positions across exchanges."""
    
    def __init__(self, exchange: IExchange, trading_config: TradingConfig, max_positions: int = 5):
        """Initialize position manager.
        
        Args:
            exchange: Exchange instance
            trading_config: Trading configuration
            max_positions: Maximum number of open positions
        """
        self.exchange = exchange
        self.trading_config = trading_config
        self.max_positions = max_positions
        self.managed_positions: Dict[str, ManagedPosition] = {}
    
    async def can_open_position(self, signal: TradingSignal) -> bool:
        """Check if a new position can be opened.
        
        Args:
            signal: Trading signal
            
        Returns:
            True if position can be opened
        """
        # Check maximum position limit
        active_positions = await self.get_active_positions()
        if len(active_positions) >= self.max_positions:
            logger.warning(f"Maximum positions ({self.max_positions}) reached")
            return False
        
        # Check if already have position for this symbol
        symbol = self.exchange.format_symbol(signal.coin)
        for managed_pos in active_positions:
            if managed_pos.position.symbol == symbol:
                logger.warning(f"Already have position for {symbol}")
                return False
        
        # Check account balance
        try:
            balance = await self.exchange.get_balance("USDT")
            if balance.free < 10:  # Minimum balance check
                logger.warning("Insufficient balance for new position")
                return False
        except Exception as e:
            logger.error(f"Error checking balance: {e}")
            return False
        
        return True
    
    async def open_position(self, signal: TradingSignal, position_size: float) -> Optional[ManagedPosition]:
        """Open a new position based on trading signal.
        
        Args:
            signal: Trading signal
            position_size: Position size in quote currency
            
        Returns:
            ManagedPosition if successful, None otherwise
        """
        if not await self.can_open_position(signal):
            return None
        
        try:
            # Get leverage for this coin
            leverage = self.trading_config.get_leverage_for_coin(signal.coin)
            logger.info(f"Using leverage {leverage}x for {signal.coin}")
            
            # Execute signal to create orders
            orders = await self.exchange.execute_signal(signal, position_size, leverage)
            
            if not orders:
                logger.error("No orders created for signal")
                return None
            
            # Categorize orders
            entry_orders = []
            stop_loss_orders = []
            take_profit_orders = []
            
            for order in orders:
                if order.order_type.value in ['market', 'limit']:
                    entry_orders.append(order)
                elif order.order_type.value == 'stop_loss':
                    stop_loss_orders.append(order)
                elif order.order_type.value == 'take_profit':
                    take_profit_orders.append(order)
            
            # Create managed position
            symbol = self.exchange.format_symbol(signal.coin)
            
            # Get leverage for this coin
            leverage = self.trading_config.get_leverage_for_coin(signal.coin)
            logger.info(f"Using leverage {leverage}x for {signal.coin}")
            
            position = Position(
                symbol=symbol,
                side=signal.side.value,
                size=position_size / signal.entry,
                entry_price=signal.entry,
                current_price=signal.entry,
                unrealized_pnl=0.0,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                leverage=leverage,
                timestamp=datetime.now().isoformat()
            )
            
            managed_position = ManagedPosition(
                position=position,
                signal=signal,
                entry_orders=entry_orders,
                stop_loss_orders=stop_loss_orders,
                take_profit_orders=take_profit_orders,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            
            # Setup Multi-TP tracking if needed
            if signal.is_multi_tp():
                tp_orders = calculate_position_splits(
                    position.size,  # Total position size in base currency
                    signal.get_all_take_profits(),
                    signal.tp_percentages
                )
                managed_position.tp_orders = tp_orders
                
                # Initialize TP tracking
                for tp_order in tp_orders:
                    managed_position.tp_filled_status[tp_order.level] = False
                managed_position.remaining_quantity = position.size
                
                logger.info(f"Setup Multi-TP for {symbol}: {len(tp_orders)} levels")
            
            self.managed_positions[symbol] = managed_position
            
            logger.info(f"Opened managed position for {symbol}")
            return managed_position
            
        except Exception as e:
            logger.error(f"Error opening position for {signal.coin}: {e}")
            return None
    
    async def close_position(self, symbol: str, reason: str = "manual") -> bool:
        """Close a managed position.
        
        Args:
            symbol: Symbol to close
            reason: Reason for closing
            
        Returns:
            True if closed successfully
        """
        if symbol not in self.managed_positions:
            logger.warning(f"No managed position found for {symbol}")
            return False
        
        managed_pos = self.managed_positions[symbol]
        
        try:
            # Cancel all pending orders
            all_orders = (managed_pos.entry_orders + 
                         managed_pos.stop_loss_orders + 
                         managed_pos.take_profit_orders)
            
            for order in all_orders:
                if order.order_id and order.status.value in ['open', 'pending']:
                    await self.exchange.cancel_order(order.order_id, symbol)
            
            # Create market order to close position if needed
            positions = await self.exchange.get_positions(symbol)
            for pos in positions:
                if pos.size > 0:
                    # Create closing order
                    # Implementation depends on exchange specifics
                    pass
            
            # Mark position as inactive
            managed_pos.is_active = False
            managed_pos.update_timestamp()
            
            logger.info(f"Closed position for {symbol}, reason: {reason}")
            return True
            
        except Exception as e:
            logger.error(f"Error closing position for {symbol}: {e}")
            return False
    
    async def update_positions(self):
        """Update all managed positions with current data."""
        for symbol, managed_pos in self.managed_positions.items():
            if not managed_pos.is_active:
                continue
            
            try:
                # Update order statuses
                for order_list in [managed_pos.entry_orders, 
                                  managed_pos.stop_loss_orders, 
                                  managed_pos.take_profit_orders]:
                    for order in order_list:
                        if order.order_id:
                            updated_order = await self.exchange.get_order_status(
                                order.order_id, symbol
                            )
                            # Check if order was found before updating
                            if updated_order is not None:
                                order.status = updated_order.status
                                order.filled_amount = updated_order.filled_amount
                                order.average_price = updated_order.average_price
                            else:
                                # Order not found - likely filled/cancelled, mark as cancelled
                                from trading.interfaces import OrderStatus
                                order.status = OrderStatus.CANCELLED
                                logger.debug(f"Order {order.order_id} not found, marked as cancelled")
                
                # Update position from exchange
                exchange_positions = await self.exchange.get_positions(symbol)
                if exchange_positions:
                    exchange_pos = exchange_positions[0]
                    managed_pos.position.current_price = exchange_pos.current_price
                    managed_pos.position.unrealized_pnl = exchange_pos.unrealized_pnl
                    managed_pos.position.size = exchange_pos.size
                
                managed_pos.update_timestamp()
                
            except Exception as e:
                logger.error(f"Error updating position for {symbol}: {e}")
    
    async def get_active_positions(self) -> List[ManagedPosition]:
        """Get all active managed positions.
        
        Returns:
            List of active managed positions
        """
        return [pos for pos in self.managed_positions.values() if pos.is_active]
    
    async def get_position_summary(self) -> Dict:
        """Get summary of all positions.
        
        Returns:
            Position summary dictionary
        """
        active_positions = await self.get_active_positions()
        
        total_unrealized_pnl = sum(pos.position.unrealized_pnl for pos in active_positions)
        total_positions = len(active_positions)
        
        return {
            'total_positions': total_positions,
            'max_positions': self.max_positions,
            'available_slots': self.max_positions - total_positions,
            'total_unrealized_pnl': total_unrealized_pnl,
            'positions': [
                {
                    'symbol': pos.position.symbol,
                    'side': pos.position.side,
                    'size': pos.position.size,
                    'entry_price': pos.position.entry_price,
                    'current_price': pos.position.current_price,
                    'unrealized_pnl': pos.position.unrealized_pnl,
                    'pnl_percentage': pos.position.pnl_percentage,
                    'created_at': pos.created_at.isoformat()
                } for pos in active_positions
            ]
        }
    
    async def cleanup_inactive_positions(self, max_age_hours: int = 24):
        """Clean up inactive positions older than specified hours.
        
        Args:
            max_age_hours: Maximum age in hours for inactive positions
        """
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        
        to_remove = []
        for symbol, managed_pos in self.managed_positions.items():
            if (not managed_pos.is_active and 
                managed_pos.updated_at < cutoff_time):
                to_remove.append(symbol)
        
        for symbol in to_remove:
            del self.managed_positions[symbol]
            logger.info(f"Cleaned up inactive position for {symbol}")
        
        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} inactive positions")
    
    async def check_tp_fills(self) -> Dict[str, List[int]]:
        """Check for filled take profit orders and update tracking.
        
        Returns:
            Dict mapping symbol to list of newly filled TP levels
        """
        newly_filled = {}
        
        for symbol, managed_pos in self.managed_positions.items():
            if not managed_pos.is_active or not managed_pos.signal.is_multi_tp():
                continue
            
            try:
                filled_levels = []
                
                # Check each TP order
                for tp_order in managed_pos.tp_orders:
                    if tp_order.filled or not tp_order.order_id:
                        continue
                    
                    # Get order status from exchange
                    order_status = await self.exchange.get_order_status(
                        tp_order.order_id, symbol
                    )
                    
                    # Check if order was found before checking status
                    if order_status is not None and order_status.status == "filled":
                        managed_pos.mark_tp_filled(
                            tp_order.level,
                            order_status.filled_amount
                        )
                        filled_levels.append(tp_order.level)
                        logger.info(f"TP{tp_order.level} filled for {symbol}")
                    elif order_status is None:
                        # Order not found - might be cancelled or expired
                        logger.debug(f"TP order {tp_order.order_id} not found for {symbol}")
                
                if filled_levels:
                    newly_filled[symbol] = filled_levels
                    
                    # Check if position should move to breakeven
                    if managed_pos.should_adjust_to_breakeven():
                        await self._adjust_stop_loss_to_breakeven(managed_pos)
                        
            except Exception as e:
                logger.error(f"Error checking TP fills for {symbol}: {e}")
        
        return newly_filled
    
    async def _adjust_stop_loss_to_breakeven(self, managed_pos: ManagedPosition):
        """Adjust stop loss to breakeven after TP fills."""
        from utils import calculate_breakeven_after_tp
        
        filled_tp_orders = [tp for tp in managed_pos.tp_orders if tp.filled]
        
        if not filled_tp_orders:
            return
        
        try:
            new_sl = calculate_breakeven_after_tp(
                managed_pos.signal.entry,
                managed_pos.signal.stop_loss,
                filled_tp_orders,
                managed_pos.remaining_quantity,
                managed_pos.signal.side.value
            )
            
            if new_sl != managed_pos.signal.stop_loss:
                # Update stop loss on exchange
                symbol = managed_pos.position.symbol
                await self.exchange.modify_stop_loss(symbol, new_sl)
                
                # Update position tracking
                managed_pos.position.stop_loss = new_sl
                managed_pos.breakeven_adjusted = True
                managed_pos.update_timestamp()
                
                logger.info(f"Adjusted SL to breakeven for {symbol}: {new_sl}")
                
        except Exception as e:
            logger.error(f"Error adjusting stop loss to breakeven: {e}")
    
    async def get_multi_tp_status(self, symbol: str) -> Optional[Dict]:
        """Get Multi-TP status for a specific position.
        
        Args:
            symbol: Position symbol
            
        Returns:
            Dict with Multi-TP status or None if not found
        """
        if symbol not in self.managed_positions:
            return None
        
        managed_pos = self.managed_positions[symbol]
        
        if not managed_pos.signal.is_multi_tp():
            return {"is_multi_tp": False}
        
        return {
            "is_multi_tp": True,
            "total_tp_levels": len(managed_pos.tp_orders),
            "filled_tp_count": managed_pos.get_filled_tp_count(),
            "remaining_quantity": managed_pos.remaining_quantity,
            "breakeven_adjusted": managed_pos.breakeven_adjusted,
            "last_tp_filled": managed_pos.last_tp_filled,
            "tp_status": [
                {
                    "level": tp.level,
                    "price": tp.price,
                    "percentage": tp.percentage,
                    "quantity": tp.quantity,
                    "filled": tp.filled,
                    "filled_quantity": tp.filled_quantity,
                    "order_id": tp.order_id
                }
                for tp in managed_pos.tp_orders
            ]
        }
