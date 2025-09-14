"""Bitget exchange implementation."""

import asyncio
import ccxt
from typing import Dict, List, Optional, Union

# Import with absolute path
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from .base import BaseExchange
from trading.interfaces import ExchangeOrder, Position, Balance, OrderType, OrderSide, OrderStatus
from ai.models import TradingSignal
from utils import get_logger

logger = get_logger(__name__)

class BitgetExchange(BaseExchange):
    """Bitget exchange implementation using CCXT."""
    
    def __init__(self, 
                 api_key: str, 
                 api_secret: str, 
                 passphrase: str, 
                 sandbox: bool = True,
                 position_mode: str = "cross"):
        """Initialize Bitget exchange.
        
        Args:
            api_key: Bitget API key
            api_secret: Bitget API secret
            passphrase: Bitget API passphrase
            sandbox: Use sandbox environment
            position_mode: Position mode - "cross" or "isolated"
        """
        super().__init__(api_key, api_secret, passphrase, sandbox)
        self.exchange_id = "bitget"
        self.position_mode = position_mode
    
    async def _initialize_client(self):
        """Initialize CCXT Bitget client."""
        print(self.api_key,self.api_secret)
        
        # Map position mode to CCXT options
        margin_mode = "cross" if self.position_mode == "cross" else "isolated"
        
        self.client = ccxt.bitget({
            'apiKey': self.api_key,
            'secret': self.api_secret,
            'password': self.passphrase,
            'sandbox': self.sandbox,
            'options': {
                'defaultType': 'future',  # Use futures trading instead of spot
                'marginMode': margin_mode,  # Use configured margin mode
            }
        })
        
        # Test connection - load_markets is synchronous for most exchanges
        try:
            await asyncio.sleep(0)  # Ensure we're in async context
            self.client.load_markets()  # This is usually synchronous
            
            # Set position mode for futures trading
            # await self._set_position_mode()
            
        except Exception as e:
            logger.error(f"Failed to load markets: {e}")
            raise
    
    async def _set_position_mode(self):
        """Set position mode for Bitget futures."""
        try:
            # For Bitget, we need to set position mode to 'one_way_mode' for unilateral positions
            # or 'hedge_mode' for hedge positions
            mode = 'one_way_mode' if self.position_mode == 'cross' else 'hedge_mode'
            
            # Try to set position mode via CCXT private API
            if hasattr(self.client, 'set_position_mode'):
                # Call the private API to set position mode
                result = self.client.set_position_mode(mode, None, {'productType': 'USDT-FUTURES'})
                logger.info(f"Set position mode to {mode}: {result}")
            else:
                logger.warning("Position mode setting not supported by CCXT version")
                
        except Exception as e:
            logger.warning(f"Could not set position mode: {e}")
            # Continue anyway, let the exchange use default mode
    
    def set_leverage(self, symbol: str, leverage: int):
        """Set leverage for a specific symbol.
        
        Args:
            symbol: Trading symbol
            leverage: Leverage value
        """
        try:
            if hasattr(self.client, 'set_leverage'):
                self.client.set_leverage(leverage, symbol)
                logger.info(f"Set leverage to {leverage}x for {symbol}")
            else:
                logger.warning("Leverage setting not supported by CCXT version")
        except Exception as e:
            logger.warning(f"Could not set leverage for {symbol}: {e}")
    
    async def get_balance(self, currency: str = None) -> Union[Balance, Dict[str, Balance]]:
        """Get account balance.
        
        Args:
            currency: Specific currency or None for all
            
        Returns:
            Balance or dictionary of balances
        """
        self._ensure_connected()
        
        try:
            # For futures trading, fetch balance - CCXT methods are usually synchronous
            balance_data = self.client.fetch_balance()
            
            if currency:
                currency = currency.upper()
                if currency in balance_data:
                    return Balance(
                        currency=currency,
                        free=balance_data[currency]['free'],
                        used=balance_data[currency]['used'],
                        total=balance_data[currency]['total']
                    )
                else:
                    return Balance(currency=currency, free=0.0, used=0.0, total=0.0)
            
            # Return all balances
            balances = {}
            for curr, data in balance_data.items():
                if isinstance(data, dict) and 'free' in data:
                    balances[curr] = Balance(
                        currency=curr,
                        free=data['free'],
                        used=data['used'],
                        total=data['total']
                    )
            
            return balances
            
        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            raise
    
    async def create_order(self, order: ExchangeOrder) -> ExchangeOrder:
        """Create a new order.
        
        Args:
            order: Order to create
            
        Returns:
            Created order with ID and status
        """
        self._ensure_connected()
        
        try:
            # Handle stop loss orders with special method
            # if order.order_type == OrderType.STOP_LOSS:
            #     return await self._create_stop_loss_order(order)
            
            # Convert to CCXT format for regular orders
            ccxt_params = {
                'symbol': order.symbol,
                'type': order.order_type.value,
                'side': order.side.value,
                'amount': order.amount,
            }
            
            # Add Bitget-specific parameters for futures trading
            params = {}
            
            # Only add productType for futures
            if 'USDT' in order.symbol:
                params['productType'] = 'USDT-FUTURES'
                params['stopLoss'] = {'triggerPrice': order.stoploss_price}
                params['triggerPrice'] = order.price
            
            if order.price:
                ccxt_params['price'] = order.price
            
            # Add params to ccxt_params
            ccxt_params['params'] = params
            
            # Add Bitget specific parameters for futures
            ccxt_params['params'].update({
                'marginMode': 'cross',  # Use cross margin
                'positionSide': 'both',  # For unilateral position mode
            })
            
            # Create order - CCXT create_order is synchronous
            result = self.client.create_order(**ccxt_params)
            
            # Update order with result
            order.order_id = result.get('id') if result else None
            order.status = self._map_order_status(result.get('status', 'pending') if result else None)
            order.timestamp = result.get('timestamp') if result else None
            order.filled_amount = result.get('filled', 0.0) if result else 0.0
            order.average_price = result.get('average') if result else None
            order.fees = result.get('fee') if result else None
            
            logger.info(f"Created order {order.order_id} for {order.symbol}")
            return order
            
        except Exception as e:
            logger.error(f"Error creating order: {e}")
            order.status = OrderStatus.REJECTED
            raise
    
    async def _create_stop_loss_order(self, order: ExchangeOrder) -> ExchangeOrder:
        """Create a stop loss order using Bitget TPSL plan with market execution.
        
        Args:
            order: Stop loss order to create
            
        Returns:
            Created order with ID and status
        """
        try:
            # Use CCXT's createOrder with stopLoss type and proper params
            try:
                # Method 1: Try CCXT's stopLoss order type
                ccxt_params = {
                    'symbol': order.symbol,
                    'type': 'market',  # Market execution when triggered
                    'side': order.side.value,
                    'amount': order.amount,
                    'params': {
                        'stopPrice': order.stop_price,  # Trigger price
                        'triggerPrice': order.stop_price,
                        'stopLossPrice': order.stop_price,
                        'productType': 'USDT-FUTURES',
                        'marginMode': 'cross',
                        'positionSide': 'both',
                        'triggerType': 'mark_price',  # Use mark price
                        'planType': 'loss_plan'
                    }
                }
                
                result = self.client.create_order(**ccxt_params)
                
                order.order_id = result.get('id') if result else None
                order.status = self._map_order_status(result.get('status', 'pending') if result else None)
                order.timestamp = result.get('timestamp') if result else None
                
                logger.info(f"Created TPSL stop loss order {order.order_id} for {order.symbol}")
                return order
                
            except Exception as ccxt_error:
                logger.warning(f"CCXT stopLoss failed: {ccxt_error}")
                
                # Method 2: Try manual API call with proper endpoint
                try:
                    # Get the correct symbol format for Bitget
                    symbol_for_api = order.symbol.replace('/USDT:USDT', 'USDT')
                    
                    # Use the correct private API method name
                    api_params = {
                        'symbol': symbol_for_api,
                        'marginCoin': 'USDT',
                        'size': str(order.amount),
                        'side': order.side.value,
                        'triggerPrice': str(order.stop_price),
                        'triggerType': 'mark_price',
                        'planType': 'loss_plan'
                    }
                    
                    # Try different API method names that might exist
                    api_methods = [
                        'private_mix_post_v2_mix_order_plan_place_order',
                        'private_mix_post_mix_plan_place_order',
                        'privateMixPostV2MixOrderPlanPlaceOrder'
                    ]
                    
                    result = None
                    for method_name in api_methods:
                        if hasattr(self.client, method_name):
                            method = getattr(self.client, method_name)
                            result = method(api_params)
                            logger.info(f"Used API method: {method_name}")
                            break
                    
                    if result and result.get('code') == '00000':
                        order_data = result.get('data', {})
                        order.order_id = order_data.get('orderId')
                        order.status = OrderStatus.OPEN if order.order_id else OrderStatus.REJECTED
                        order.timestamp = str(result.get('requestTime'))
                        
                        logger.info(f"Created TPSL plan (SL) {order.order_id} for {order.symbol}")
                        return order
                    else:
                        raise Exception(f"API call failed: {result}")
                        
                except Exception as api_error:
                    logger.warning(f"Direct API call failed: {api_error}")
                    
                    # Method 3: Fallback to stop limit order with reasonable price
                    logger.info("Final fallback: Creating stop limit order with safe price")
                    
                    # Get current price to set a safer stop loss
                    ticker = await self.get_ticker(order.symbol)
                    current_price = ticker.get('last', order.stop_price)
                    
                    # Adjust stop loss to be within reasonable range
                    if order.side.value == 'sell':  # Long position stop loss
                        # Make sure SL is not too far below current price (max 20%)
                        min_sl = current_price * 0.8
                        safe_sl = max(order.stop_price, min_sl)
                    else:  # Short position stop loss
                        # Make sure SL is not too far above current price (max 20%)
                        max_sl = current_price * 1.2
                        safe_sl = min(order.stop_price, max_sl)
                    
                    ccxt_params = {
                        'symbol': order.symbol,
                        'type': 'limit',
                        'side': order.side.value,
                        'amount': order.amount,
                        'price': safe_sl,
                        'params': {
                            'productType': 'USDT-FUTURES',
                            'marginMode': 'cross',
                            'positionSide': 'both',
                        }
                    }
                    
                    result = self.client.create_order(**ccxt_params)
                    
                    order.order_id = result.get('id') if result else None
                    order.status = self._map_order_status(result.get('status', 'pending') if result else None)
                    order.timestamp = result.get('timestamp') if result else None
                    
                    logger.info(f"Created safe limit SL order {order.order_id} at {safe_sl} (adjusted from {order.stop_price})")
                    return order
                
        except Exception as e:
            logger.error(f"Error creating stop loss order: {e}")
            order.status = OrderStatus.REJECTED
            raise
    
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an order.
        
        Args:
            order_id: Order ID to cancel
            symbol: Trading symbol
            
        Returns:
            True if cancelled successfully
        """
        self._ensure_connected()
        
        try:
            self.client.cancel_order(order_id, symbol)
            logger.info(f"Cancelled order {order_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            return False
    
    async def get_order_status(self, order_id: str, symbol: str) -> Optional[ExchangeOrder]:
        """Get order status with enhanced error handling.
        
        Args:
            order_id: Order ID
            symbol: Trading symbol
            
        Returns:
            Order with current status or None if not found
        """
        self._ensure_connected()
        
        try:
            result = self.client.fetch_order(order_id, symbol)
            
            return ExchangeOrder(
                symbol=result['symbol'],
                side=OrderSide.BUY if result['side'] == 'buy' else OrderSide.SELL,
                amount=result['amount'],
                order_type=OrderType(result['type']),
                price=result.get('price'),
                stop_price=result.get('stopPrice'),
                order_id=result['id'],
                status=self._map_order_status(result['status']),
                filled_amount=result.get('filled', 0.0),
                average_price=result.get('average'),
                fees=result.get('fee'),
                timestamp=result.get('timestamp')
            )
            
        except Exception as e:
            error_str = str(e).lower()
            
            # Handle "order not found" gracefully
            if any(phrase in error_str for phrase in [
                "cannot be found", 
                "not found", 
                "does not exist",
                "40109"  # Bitget specific error code
            ]):
                logger.debug(f"Order {order_id} not found (possibly filled/cancelled)")
                return None
            
            # Log other errors as warnings
            logger.warning(f"Error fetching order status for {order_id}: {e}")
            return None
    
    async def check_order_filled(self, order_id: str, symbol: str) -> tuple[bool, Optional[ExchangeOrder]]:
        """Check if order is filled and return order details.
        
        Args:
            order_id: Order ID to check
            symbol: Trading symbol
            
        Returns:
            (is_filled, order_details)
        """
        order = await self.get_order_status(order_id, symbol)
        
        if not order:
            return False, None
        
        is_filled = order.status in [OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED]
        return is_filled, order
    
    async def get_positions(self, symbol: str = None) -> List[Position]:
        """Get open positions.
        
        Args:
            symbol: Specific symbol or None for all
            
        Returns:
            List of positions
        """
        self._ensure_connected()
        
        try:
            # Handle symbol parameter safely
            symbols_to_fetch = [symbol] if symbol else None
            positions_data = self.client.fetch_positions(symbols_to_fetch)
            positions = []
            
            for pos_data in positions_data:
                # Check if position data is valid and has actual position
                if (pos_data and 
                    isinstance(pos_data, dict) and 
                    pos_data.get('contracts', 0) > 0):  # Only open positions
                    
                    position = Position(
                        symbol=pos_data.get('symbol', ''),
                        side=pos_data.get('side', ''),
                        size=pos_data.get('contracts', 0),
                        entry_price=pos_data.get('entryPrice', 0),
                        current_price=pos_data.get('markPrice', 0),
                        unrealized_pnl=pos_data.get('unrealizedPnl', 0),
                        realized_pnl=pos_data.get('realizedPnl', 0),
                        leverage=pos_data.get('leverage', 1),
                        margin=pos_data.get('initialMargin', 0),
                        timestamp=pos_data.get('timestamp')
                    )
                    positions.append(position)
            
            return positions
            
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return []
    
    async def get_ticker(self, symbol: str) -> Dict:
        """Get ticker data.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Ticker data
        """
        self._ensure_connected()
        
        try:
            ticker = self.client.fetch_ticker(symbol)
            return ticker
            
        except Exception as e:
            logger.debug(f"Ticker not available for {symbol}: {e}")
            return None
    
    def format_symbol(self, base: str, quote: str = "USDT") -> str:
        """Format symbol for Bitget futures.
        
        Args:
            base: Base currency (can be like 'ONDOUSDT' or 'ONDO')
            quote: Quote currency
            
        Returns:
            Formatted symbol for futures
        """
        # Handle cases where base already contains quote (like 'ONDOUSDT')
        if base.upper().endswith('USDT') and len(base) > 4:
            # Extract the actual base currency (remove 'USDT' suffix)
            actual_base = base.upper()[:-4]  # Remove last 4 characters ('USDT')
            quote = 'USDT'
        elif base.upper().endswith('BTC') and len(base) > 3:
            actual_base = base.upper()[:-3]  # Remove 'BTC'
            quote = 'BTC'
        elif base.upper().endswith('ETH') and len(base) > 3:
            actual_base = base.upper()[:-3]  # Remove 'ETH'
            quote = 'ETH'
        else:
            actual_base = base.upper()
        
        # For Bitget futures, format is typically BASE/QUOTE:SETTLE
        formatted = f"{actual_base}/{quote.upper()}:{quote.upper()}"
        logger.debug(f"Formatted symbol: {base} -> {formatted}")
        return formatted
    
    async def validate_symbol(self, symbol: str) -> str:
        """Validate and correct symbol format for Bitget.
        
        Args:
            symbol: Symbol to validate
            
        Returns:
            Valid symbol or raises exception
        """
        try:
            # Try to get ticker for the symbol to verify it exists
            ticker = await self.get_ticker(symbol)
            if ticker:
                return symbol
        except Exception:
            pass
        
        # If symbol doesn't exist, try alternative formats
        if '/' in symbol and ':' in symbol:
            # Extract base from current format (e.g., "ONDO/USDT:USDT" -> "ONDO")
            base_part = symbol.split('/')[0]
            
            # Try different common formats
            alternative_formats = [
                f"{base_part}/USDT:USDT",
                f"{base_part}/USDT",
                f"{base_part}USDT",
                f"{base_part}/USD:USD",
                f"{base_part}USD"
            ]
            
            for alt_symbol in alternative_formats:
                try:
                    # Re-format through our format_symbol method
                    if '/' not in alt_symbol:
                        formatted_alt = self.format_symbol(alt_symbol)
                    else:
                        formatted_alt = alt_symbol
                    
                    ticker = await self.get_ticker(formatted_alt)
                    if ticker:
                        logger.info(f"Symbol corrected: {symbol} -> {formatted_alt}")
                        return formatted_alt
                except Exception:
                    continue
        
        # If no valid format found, raise error with available symbols info
        logger.error(f"Symbol {symbol} not found on Bitget")
        raise ValueError(f"Symbol {symbol} not available on Bitget. Please check symbol format.")

    def _map_order_status(self, ccxt_status: str) -> OrderStatus:
        """Map CCXT order status to internal status.
        
        Args:
            ccxt_status: CCXT status string
            
        Returns:
            Internal OrderStatus
        """
        if not ccxt_status:
            return OrderStatus.PENDING
            
        status_mapping = {
            'open': OrderStatus.OPEN,
            'closed': OrderStatus.FILLED,
            'canceled': OrderStatus.CANCELLED,
            'cancelled': OrderStatus.CANCELLED,
            'rejected': OrderStatus.REJECTED,
            'pending': OrderStatus.PENDING
        }
        
        return status_mapping.get(ccxt_status.lower(), OrderStatus.PENDING)
    
    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Set leverage for a symbol.
        
        Args:
            symbol: Trading symbol
            leverage: Leverage value
            
        Returns:
            True if successful
        """
        try:
            # Set leverage for the symbol
            self.client.set_leverage(leverage, symbol)
            logger.info(f"Set leverage {leverage}x for {symbol}")
            return True
        except Exception as e:
            logger.error(f"Error setting leverage for {symbol}: {e}")
            return False
    
    async def execute_signal(self, signal: TradingSignal, position_size: float, leverage: int = 1) -> List[ExchangeOrder]:
        """Execute a trading signal with Multi-TP support.
        
        Args:
            signal: Trading signal to execute
            position_size: Position size in quote currency
            leverage: Leverage to use
            
        Returns:
            List of created orders
        """
        from utils import calculate_position_splits
        
        self._ensure_connected()
        
        try:
            symbol = self.format_symbol(signal.coin)
            
            # Validate and correct symbol if needed
            try:
                symbol = await self.validate_symbol(symbol)
            except ValueError as ve:
                logger.error(f"Symbol validation failed: {ve}")
                raise
            
            # Set leverage first
            await self.set_leverage(symbol, leverage)
            
            # Calculate position size in base currency
            base_quantity = position_size / signal.entry
            
            # Determine order side
            order_side = OrderSide.BUY if signal.side.value == "long" else OrderSide.SELL
            
            created_orders = []
            
            # 1. Create entry order - use order_type from signal
            entry_order_type = OrderType.MARKET if signal.order_type == "market" else OrderType.LIMIT
            
            entry_order = ExchangeOrder(
                symbol=symbol,
                side=order_side,
                amount=base_quantity,
                order_type=entry_order_type,
                price=signal.entry if entry_order_type == OrderType.LIMIT else None,
                stoploss_price=signal.stop_loss
            )
            
            logger.info(f"Creating {signal.order_type.upper()} entry order for {symbol} at {signal.entry}")
            entry_result = await self.create_order(entry_order)
            created_orders.append(entry_result)
            
            # 2. Create stop loss order (with error handling)
            sl_side = OrderSide.SELL if order_side == OrderSide.BUY else OrderSide.BUY
            
            try:
                # No price validation - use stop loss exactly as specified in signal
                # TPSL plan with market execution will handle price limits automatically
                adjusted_sl = signal.stop_loss
                
                sl_order = ExchangeOrder(
                    symbol=symbol,
                    side=sl_side,
                    amount=base_quantity,
                    order_type=OrderType.STOP_LOSS,
                    stop_price=adjusted_sl
                )
                
                sl_result = await self.create_order(sl_order)
                created_orders.append(sl_result)
                logger.info(f"Created stop loss order for {symbol} at {adjusted_sl}")
                
            except Exception as sl_error:
                logger.error(f"Failed to create stop loss order for {symbol}: {sl_error}")
                logger.warning("Continuing without stop loss - MANAGE RISK MANUALLY!")
                # Continue without stop loss to not block the entire trade
            
            # 3. Create take profit orders
            if signal.is_multi_tp():
                # Multiple take profits
                tp_orders = calculate_position_splits(
                    base_quantity,
                    signal.get_all_take_profits(),
                    signal.tp_percentages
                )
                
                tp_side = OrderSide.SELL if order_side == OrderSide.BUY else OrderSide.BUY
                tp_results = await self.create_multi_tp_orders(symbol, tp_side, tp_orders)
                created_orders.extend(tp_results)
                
                logger.info(f"Created Multi-TP signal with {len(tp_orders)} TP levels for {symbol}")
                
            elif signal.take_profit:
                # Single take profit
                tp_side = OrderSide.SELL if order_side == OrderSide.BUY else OrderSide.BUY
                
                tp_order = ExchangeOrder(
                    symbol=symbol,
                    side=tp_side,
                    amount=base_quantity,
                    order_type=OrderType.LIMIT,
                    price=signal.take_profit
                )
                
                tp_result = await self.create_order(tp_order)
                created_orders.append(tp_result)
            
            logger.info(f"Executed signal for {symbol}: {len(created_orders)} orders created")
            return created_orders
            
        except Exception as e:
            logger.error(f"Error executing signal for {signal.coin}: {e}")
            raise
    
    async def create_multi_tp_orders(self, symbol: str, side: OrderSide, tp_orders: List) -> List[ExchangeOrder]:
        """Create multiple take profit orders using TPSL plans.
        
        Args:
            symbol: Trading symbol
            side: Order side for TP
            tp_orders: List of TPOrder objects from position_utils
            
        Returns:
            List of created TP orders
        """
        created_orders = []
        
        for i, tp_order in enumerate(tp_orders):
            try:
                # Extract price and amount from TPOrder object
                tp_price = tp_order.price
                tp_amount = tp_order.quantity
                
                # Create TPSL plan for take profit with market execution
                try:
                    # Method 1: Try CCXT's takeProfit order type
                    ccxt_params = {
                        'symbol': symbol,
                        'type': 'market',  # Market execution when triggered
                        'side': side.value,
                        'amount': tp_amount,
                        'params': {
                            'stopPrice': tp_price,  # Trigger price
                            'triggerPrice': tp_price,
                            'takeProfitPrice': tp_price,
                            'productType': 'USDT-FUTURES',
                            'marginMode': 'cross',
                            'positionSide': 'both',
                            'triggerType': 'mark_price',  # Use mark price
                            'planType': 'profit_plan'
                        }
                    }
                    
                    result = self.client.create_order(**ccxt_params)
                    
                    exchange_order = ExchangeOrder(
                        symbol=symbol,
                        side=side,
                        amount=tp_amount,
                        order_type=OrderType.TAKE_PROFIT,
                        price=tp_price,
                        order_id=result.get('id') if result else None,
                        status=self._map_order_status(result.get('status', 'pending') if result else None),
                        timestamp=result.get('timestamp') if result else None
                    )
                    created_orders.append(exchange_order)
                    logger.info(f"Created CCXT TP{i+1} order {exchange_order.order_id} at {tp_price}")
                    
                except Exception as ccxt_error:
                    logger.warning(f"CCXT takeProfit failed for TP{i+1}: {ccxt_error}")
                    
                    # Method 2: Fallback to regular limit order
                    logger.info(f"Fallback: Creating TP{i+1} as limit order")
                    
                    exchange_order = ExchangeOrder(
                        symbol=symbol,
                        side=side,
                        amount=tp_amount,
                        order_type=OrderType.LIMIT,
                        price=tp_price  # No price validation - full freedom
                    )
                    
                    result = await self.create_order(exchange_order)
                    created_orders.append(result)
                    
            except Exception as e:
                logger.error(f"Error creating TP order {i+1}: {e}")
                continue
        
        return created_orders

    async def modify_stop_loss(self, symbol: str, new_stop_price: float) -> bool:
        """Modify stop loss for a position.
        
        Args:
            symbol: Trading symbol
            new_stop_price: New stop loss price
            
        Returns:
            True if modified successfully
        """
        self._ensure_connected()
        
        try:
            # For Bitget, we need to cancel existing SL and create new one
            # First, get existing SL orders
            orders = self.client.fetch_open_orders(symbol)
            sl_orders = [o for o in orders if o.get('type') == 'stop_loss']
            
            # Cancel existing SL orders
            for order in sl_orders:
                await self.cancel_order(order['id'], symbol)
            
            # Get current position to determine new SL order
            positions = await self.get_positions(symbol)
            if not positions:
                return False
            
            position = positions[0]
            side = OrderSide.SELL if position.side == "long" else OrderSide.BUY
            
            # Create new SL order
            new_sl_order = ExchangeOrder(
                symbol=symbol,
                side=side,
                amount=abs(position.size),
                order_type=OrderType.STOP_LOSS,
                stop_price=new_stop_price
            )
            
            await self.create_order(new_sl_order)
            logger.info(f"Modified stop loss for {symbol} to {new_stop_price}")
            return True
            
        except Exception as e:
            logger.error(f"Error modifying stop loss for {symbol}: {e}")
            return False

    async def check_order_filled_status(self, order_id: str, symbol: str, order_type: OrderType = None) -> tuple[bool, Optional[ExchangeOrder]]:
        """Check if order is filled with proper handling for different order types.
        
        Args:
            order_id: Order ID to check
            symbol: Trading symbol
            order_type: Type of order (for better error handling)
            
        Returns:
            (is_filled, order_details)
        """
        order = await self.get_order_status(order_id, symbol)
        
        if not order:
            # For limit orders, this might be normal (order expired/cancelled)
            if order_type == OrderType.LIMIT:
                logger.debug(f"Limit order {order_id} not found (possibly expired/cancelled)")
            else:
                logger.warning(f"Order {order_id} not found")
            return False, None
        
        is_filled = order.status in [OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED]
        return is_filled, order
    
    async def monitor_order_status(self, order_id: str, symbol: str, order_type: OrderType = None) -> Optional[ExchangeOrder]:
        """Monitor single order status with appropriate handling for order type.
        
        Args:
            order_id: Order ID to monitor
            symbol: Trading symbol
            order_type: Type of order for better handling
            
        Returns:
            Updated order details or None if not found
        """
        try:
            is_filled, order = await self.check_order_filled_status(order_id, symbol, order_type)
            
            if order:
                if is_filled:
                    logger.info(f"Order {order_id} filled at {order.average_price}")
                return order
            else:
                # Order not found - handle based on type
                if order_type == OrderType.LIMIT:
                    logger.debug(f"Limit order {order_id} no longer exists (filled/cancelled/expired)")
                else:
                    logger.warning(f"Market order {order_id} not found - unusual situation")
                return None
                
        except Exception as e:
            logger.error(f"Error monitoring order {order_id}: {e}")
            return None
