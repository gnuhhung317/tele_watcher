"""Application settings and configuration classes."""

from dataclasses import dataclass
from typing import List, Optional
from .env import (
    get_env_var, get_env_int, get_env_float, 
    get_env_bool, get_env_list, load_environment
)

# Load environment variables
load_environment()

@dataclass
class TelegramConfig:
    """Telegram client configuration."""
    api_id: int = get_env_int("TELEGRAM_API_ID", required=True)
    api_hash: str = get_env_var("TELEGRAM_API_HASH", required=True)
    session_name: str = get_env_var("TELEGRAM_SESSION_NAME", "watcher")
    channels: List[str] = None
    download_media: bool = get_env_bool("TELEGRAM_DOWNLOAD_MEDIA", False)
    download_path: str = get_env_var("TELEGRAM_DOWNLOAD_PATH", "downloads")
    
    # Bot configuration for sending messages
    bot_token: Optional[str] = get_env_var("TELEGRAM_BOT_TOKEN", required=False)
    bot_chat_id: Optional[str] = get_env_var("TELEGRAM_BOT_CHAT_ID", required=False)
    bot_session_name: str = get_env_var("TELEGRAM_BOT_SESSION_NAME", "bot")
    
    def __post_init__(self):
        if self.channels is None:
            self.channels = get_env_list("TELEGRAM_CHANNELS", ["MegaLodonFutures"])

@dataclass
class AIConfig:
    """AI service configuration."""
    gemini_api_key: str = get_env_var("GEMINI_API_KEY", required=True)
    model_name: str = get_env_var("GEMINI_MODEL_NAME", "gemini-1.5-flash")
    max_retries: int = get_env_int("AI_MAX_RETRIES", 3)
    timeout: int = get_env_int("AI_TIMEOUT", 30)
    min_confidence: float = get_env_float("AI_MIN_CONFIDENCE", 0.7)

@dataclass
class ExchangeConfig:
    """Exchange configuration."""
    # Bitget
    bitget_api_key: str = get_env_var("BITGET_API_KEY", required=True)
    bitget_api_secret: str = get_env_var("BITGET_API_SECRET", required=True)
    bitget_passphrase: str = get_env_var("BITGET_PASSPHRASE", required=False)
    bitget_sandbox: bool = get_env_bool("BITGET_SANDBOX", True)
    
    # Future exchanges can be added here
    # binance_api_key: str = get_env_var("BINANCE_API_KEY", "")
    # binance_api_secret: str = get_env_var("BINANCE_API_SECRET", "")

@dataclass
class TradingConfig:
    """Trading configuration."""
    max_positions: int = get_env_int("TRADING_MAX_POSITIONS", 5)
    risk_per_trade: float = get_env_float("TRADING_RISK_PER_TRADE", 0.02)
    default_leverage: int = get_env_int("TRADING_DEFAULT_LEVERAGE", 20)
    high_leverage: int = get_env_int("TRADING_HIGH_LEVERAGE", 75)
    high_leverage_coins: List[str] = None
    min_confidence: float = get_env_float("TRADING_MIN_CONFIDENCE", 0.7)
    default_position_size: float = get_env_float("TRADING_DEFAULT_POSITION_SIZE", 20)
    max_position_size: float = get_env_float("TRADING_MAX_POSITION_SIZE", 1000)
    stop_loss_buffer: float = get_env_float("TRADING_STOP_LOSS_BUFFER", 0.01)
    position_mode: str = get_env_var("TRADING_POSITION_MODE", "cross")  # "cross" or "isolated"
    enabled: bool = get_env_bool("TRADING_ENABLED", False)
    
    # Multi-TP Configuration
    multi_tp_enabled: bool = get_env_bool("TRADING_MULTI_TP_ENABLED", True)
    auto_breakeven: bool = get_env_bool("TRADING_AUTO_BREAKEVEN", True)
    tp_monitor_interval: int = get_env_int("TRADING_TP_MONITOR_INTERVAL", 15)  # seconds
    max_tp_levels: int = get_env_int("TRADING_MAX_TP_LEVELS", 4)
    min_tp_percentage: float = get_env_float("TRADING_MIN_TP_PERCENTAGE", 10.0)  # minimum % per TP
    
    def __post_init__(self):
        if self.high_leverage_coins is None:
            self.high_leverage_coins = get_env_list("TRADING_HIGH_LEVERAGE_COINS", ["BTC", "ETH"])
    
    def get_leverage_for_coin(self, coin: str) -> int:
        """Get leverage for specific coin.
        
        Args:
            coin: Coin symbol (e.g., "BTC", "ETH", "PUMP")
            
        Returns:
            Leverage value
        """
        coin_upper = coin.upper().replace("USDT", "").replace("USD", "")
        
        if coin_upper in self.high_leverage_coins:
            return self.high_leverage
        else:
            return self.default_leverage
    
    def validate_multi_tp_signal(self, signal) -> tuple[bool, str]:
        """Validate Multi-TP signal against configuration.
        
        Args:
            signal: TradingSignal instance
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not self.multi_tp_enabled:
            return True, ""  # If Multi-TP disabled, skip validation
        
        if not signal.is_multi_tp():
            return True, ""  # Not a Multi-TP signal
        
        # Check max TP levels
        if signal.tp_count > self.max_tp_levels:
            return False, f"Too many TP levels: {signal.tp_count} > {self.max_tp_levels}"
        
        # Check minimum TP percentage
        percentages = signal.effective_tp_percentages
        for i, pct in enumerate(percentages):
            if pct < self.min_tp_percentage:
                return False, f"TP{i+1} percentage too small: {pct}% < {self.min_tp_percentage}%"
        
        return True, ""
    
@dataclass
class AppConfig:
    """Main application configuration."""
    debug: bool = get_env_bool("DEBUG", False)
    log_level: str = get_env_var("LOG_LEVEL", "INFO")
    log_file: str = get_env_var("LOG_FILE", "watch_caller.log")
    
    telegram: TelegramConfig = None
    ai: AIConfig = None
    exchange: ExchangeConfig = None
    trading: TradingConfig = None
    
    def __post_init__(self):
        """Initialize nested config objects and validate configuration after initialization."""
        if self.telegram is None:
            self.telegram = TelegramConfig()
        if self.ai is None:
            self.ai = AIConfig()
        if self.exchange is None:
            self.exchange = ExchangeConfig()
        if self.trading is None:
            self.trading = TradingConfig()
        
        self._validate_config()
    
    def _validate_config(self):
        """Validate configuration values."""
        if self.trading.risk_per_trade <= 0 or self.trading.risk_per_trade > 1:
            raise ValueError("Risk per trade must be between 0 and 1")
        
        if self.trading.max_positions <= 0:
            raise ValueError("Max positions must be greater than 0")
        
        if self.ai.min_confidence < 0 or self.ai.min_confidence > 1:
            raise ValueError("Min confidence must be between 0 and 1")
