"""Position utilities for Multi-TP trading."""

from typing import List, Dict, Tuple
from dataclasses import dataclass

@dataclass
class TPOrder:
    """Individual take profit order."""
    level: int  # TP level (1, 2, 3, etc.)
    price: float
    percentage: float  # Percentage of total position
    quantity: float  # Actual quantity for this TP
    order_id: str = ""  # Exchange order ID when placed
    filled: bool = False
    filled_quantity: float = 0.0

def calculate_position_splits(
    total_position_size: float,
    take_profits: List[float],
    tp_percentages: List[float] = None
) -> List[TPOrder]:
    """
    Calculate position splits for multiple take profits.
    
    Args:
        total_position_size: Total position size (in base currency)
        take_profits: List of take profit prices
        tp_percentages: Custom percentage splits (optional)
    
    Returns:
        List of TPOrder objects with calculated quantities
    """
    if not take_profits:
        return []
    
    tp_count = len(take_profits)
    
    # Use custom percentages or defaults
    if tp_percentages and len(tp_percentages) == tp_count:
        percentages = tp_percentages
    else:
        percentages = get_default_tp_percentages(tp_count)
    
    # Normalize percentages to ensure they sum to 100%
    total_percentage = sum(percentages)
    if total_percentage > 0:
        percentages = [pct / total_percentage * 100.0 for pct in percentages]
    
    # Calculate quantities
    tp_orders = []
    remaining_size = total_position_size
    
    for i, (price, percentage) in enumerate(zip(take_profits, percentages)):
        if i == len(take_profits) - 1:
            # Last TP gets remaining quantity to avoid rounding errors
            quantity = remaining_size
        else:
            quantity = total_position_size * (percentage / 100.0)
            remaining_size -= quantity
        
        tp_orders.append(TPOrder(
            level=i + 1,
            price=price,
            percentage=percentage,
            quantity=quantity
        ))
    
    return tp_orders

def get_default_tp_percentages(tp_count: int) -> List[float]:
    """
    Get default position split percentages based on TP count.
    
    Args:
        tp_count: Number of take profit levels
    
    Returns:
        List of percentage values that sum to 100
    """
    if tp_count == 1:
        return [100.0]
    elif tp_count == 2:
        return [40.0, 60.0]
    elif tp_count == 3:
        return [25.0, 45.0, 30.0]
    elif tp_count == 4:
        return [20.0, 20.0, 40.0, 20.0]
    else:
        # For 5+ TPs, distribute evenly
        percentage = 100.0 / tp_count
        return [percentage] * tp_count

def calculate_risk_per_tp(
    entry_price: float,
    stop_loss: float,
    take_profits: List[float],
    tp_orders: List[TPOrder],
    side: str = "long"
) -> Dict[int, Dict[str, float]]:
    """
    Calculate risk/reward metrics for each TP level.
    
    Args:
        entry_price: Entry price
        stop_loss: Stop loss price
        take_profits: Take profit prices
        tp_orders: List of TP orders with quantities
        side: Position side ("long" or "short")
    
    Returns:
        Dict with risk metrics per TP level
    """
    metrics = {}
    
    for tp_order in tp_orders:
        tp_price = tp_order.price
        
        if side.lower() == "long":
            risk_per_unit = entry_price - stop_loss
            reward_per_unit = tp_price - entry_price
        else:  # short
            risk_per_unit = stop_loss - entry_price
            reward_per_unit = entry_price - tp_price
        
        risk_reward_ratio = reward_per_unit / risk_per_unit if risk_per_unit > 0 else 0
        
        metrics[tp_order.level] = {
            "price": tp_price,
            "quantity": tp_order.quantity,
            "percentage": tp_order.percentage,
            "risk_per_unit": risk_per_unit,
            "reward_per_unit": reward_per_unit,
            "risk_reward_ratio": risk_reward_ratio,
            "total_risk": risk_per_unit * tp_order.quantity,
            "total_reward": reward_per_unit * tp_order.quantity
        }
    
    return metrics

def validate_tp_prices(
    entry_price: float,
    take_profits: List[float],
    side: str = "long"
) -> Tuple[bool, str]:
    """
    Validate take profit prices are in correct order.
    
    Args:
        entry_price: Entry price
        take_profits: List of take profit prices
        side: Position side ("long" or "short")
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not take_profits:
        return False, "No take profit prices provided"
    
    # Check all TPs are different from entry
    for i, tp in enumerate(take_profits):
        if tp == entry_price:
            return False, f"TP{i+1} cannot equal entry price"
    
    if side.lower() == "long":
        # For long positions, TPs should be above entry and in ascending order
        for i, tp in enumerate(take_profits):
            if tp <= entry_price:
                return False, f"TP{i+1} must be above entry price for long positions"
            
            if i > 0 and tp <= take_profits[i-1]:
                return False, f"TP{i+1} must be higher than TP{i}"
    
    else:  # short
        # For short positions, TPs should be below entry and in descending order
        for i, tp in enumerate(take_profits):
            if tp >= entry_price:
                return False, f"TP{i+1} must be below entry price for short positions"
            
            if i > 0 and tp >= take_profits[i-1]:
                return False, f"TP{i+1} must be lower than TP{i}"
    
    return True, ""

def calculate_breakeven_after_tp(
    entry_price: float,
    stop_loss: float,
    filled_tp_orders: List[TPOrder],
    remaining_quantity: float,
    side: str = "long"
) -> float:
    """
    Calculate new stop loss for breakeven protection after TP fills.
    
    Args:
        entry_price: Original entry price
        stop_loss: Original stop loss
        filled_tp_orders: List of filled TP orders
        remaining_quantity: Remaining position quantity
        side: Position side ("long" or "short")
    
    Returns:
        New stop loss price for breakeven
    """
    if not filled_tp_orders or remaining_quantity <= 0:
        return stop_loss
    
    # Calculate profit from filled TPs
    total_profit = 0.0
    for tp_order in filled_tp_orders:
        if side.lower() == "long":
            profit_per_unit = tp_order.price - entry_price
        else:  # short
            profit_per_unit = entry_price - tp_order.price
        
        total_profit += profit_per_unit * tp_order.quantity
    
    # Calculate breakeven price for remaining position
    if side.lower() == "long":
        # For remaining long position to breakeven: (entry - new_sl) * remaining = total_profit
        breakeven_sl = entry_price - (total_profit / remaining_quantity)
        # Don't move SL below original or below entry
        return max(breakeven_sl, stop_loss, entry_price * 0.999)  # Small buffer below entry
    else:  # short
        # For remaining short position to breakeven: (new_sl - entry) * remaining = total_profit
        breakeven_sl = entry_price + (total_profit / remaining_quantity)
        # Don't move SL above original or above entry
        return min(breakeven_sl, stop_loss, entry_price * 1.001)  # Small buffer above entry