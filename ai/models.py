"""Data models for AI parsing."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum

class SignalType(Enum):
    """Trading signal types."""
    LONG = "long"
    SHORT = "short"
    UNKNOWN = "unknown"

class ParseStatus(Enum):
    """Parse result status."""
    SUCCESS = "success"
    FAILED = "failed"
    NO_SIGNAL = "no_signal"
    LOW_CONFIDENCE = "low_confidence"

@dataclass
class TradingSignal:
    """Parsed trading signal data."""
    coin: str
    entry: float
    stop_loss: float
    take_profit: Optional[float] = None  # Single TP (backward compatibility)
    take_profits: Optional[List[float]] = None  # Multiple TP levels
    tp_percentages: Optional[List[float]] = None  # Custom split percentages
    position_size: Optional[float] = None
    leverage: Optional[int] = 1
    side: SignalType = SignalType.LONG
    confidence: float = 0.0
    timestamp: datetime = None
    source: str = ""
    raw_message: str = ""
    metadata: Optional[Dict[str, Any]] = None
    order_type: Optional[str] = None  # "market" or "limit" - AI decides from signal content
    
    def __post_init__(self):
        """Set default timestamp and metadata if not provided."""
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.metadata is None:
            self.metadata = {}
        
        # Set default order type if not specified
        if self.order_type is None:
            self.order_type = "market"  # Default to market order
    
    @property
    def tp_count(self) -> int:
        """Get number of take profit levels."""
        if self.take_profits:
            return len(self.take_profits)
        elif self.take_profit:
            return 1
        return 0
    
    @property
    def default_tp_percentages(self) -> List[float]:
        """Get default position split percentages based on TP count."""
        tp_count = self.tp_count
        if tp_count == 1:
            return [100.0]
        elif tp_count == 2:
            return [40.0, 60.0]
        elif tp_count == 3:
            return [30.0, 40.0, 30.0]
        elif tp_count == 4:
            return [20.0, 20.0, 40.0, 20.0]
        else:
            # For 5+ TPs, distribute evenly
            percentage = 100.0 / tp_count
            return [percentage] * tp_count
    
    @property
    def effective_tp_percentages(self) -> List[float]:
        """Get effective split percentages (custom or default)."""
        if self.tp_percentages and len(self.tp_percentages) == self.tp_count:
            return self.tp_percentages
        return self.default_tp_percentages
    
    def get_all_take_profits(self) -> List[float]:
        """Get all take profit levels as a list."""
        if self.take_profits:
            return self.take_profits
        elif self.take_profit:
            return [self.take_profit]
        return []
    
    def is_multi_tp(self) -> bool:
        """Check if this is a multi-TP signal."""
        return self.tp_count > 1
    
    @property
    def symbol(self) -> str:
        """Get trading symbol (coin name)."""
        return self.coin.upper()
    
    @property
    def risk_reward_ratio(self) -> Optional[float]:
        """Calculate risk-reward ratio using weighted average TP or single TP."""
        all_tps = self.get_all_take_profits()
        if not all_tps:
            return None
        
        # Use weighted average TP for multi-TP signals
        if len(all_tps) > 1:
            percentages = self.effective_tp_percentages
            weighted_tp = sum(tp * (pct / 100.0) for tp, pct in zip(all_tps, percentages))
        else:
            weighted_tp = all_tps[0]
        
        if self.side == SignalType.LONG:
            risk = abs(self.entry - self.stop_loss)
            reward = abs(weighted_tp - self.entry)
        else:  # SHORT
            risk = abs(self.stop_loss - self.entry)
            reward = abs(self.entry - weighted_tp)
        
        return reward / risk if risk > 0 else None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "coin": self.coin,
            "entry": self.entry,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "take_profits": self.take_profits,
            "tp_percentages": self.tp_percentages,
            "position_size": self.position_size,
            "leverage": self.leverage,
            "side": self.side.value,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "source": self.source,
            "raw_message": self.raw_message,
            "metadata": self.metadata,
            "tp_count": self.tp_count,
            "is_multi_tp": self.is_multi_tp(),
            "risk_reward_ratio": self.risk_reward_ratio
        }

@dataclass
class ParseResult:
    """Result of AI parsing operation."""
    status: ParseStatus
    signal: Optional[TradingSignal] = None
    error_message: str = ""
    confidence: float = 0.0
    processing_time: float = 0.0
    raw_response: str = ""
    
    @property
    def is_success(self) -> bool:
        """Check if parsing was successful."""
        return self.status == ParseStatus.SUCCESS
    
    @property
    def has_signal(self) -> bool:
        """Check if result contains a valid signal."""
        return self.is_success and self.signal is not None
