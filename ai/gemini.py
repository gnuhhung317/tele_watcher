"""Gemini AI parser implementation."""

import json
import re
import time
from typing import Optional, Dict, Any
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# Import with absolute path
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .base import BaseAIParser
from .models import ParseResult, TradingSignal, ParseStatus, SignalType
from utils import get_logger, safe_float, parse_hashtag

logger = get_logger(__name__)

class GeminiParser(BaseAIParser):
    """Gemini AI implementation for parsing trading signals."""
    
    def __init__(self, api_key: str, model_name: str = "gemini-1.5-flash"):
        """Initialize Gemini parser.
        
        Args:
            api_key: Gemini API key
            model_name: Model name to use
        """
        super().__init__(api_key, model_name)
        
        # Configure Gemini
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            safety_settings={
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }
        )
        
        # System prompt for trading signal parsing
        self.system_prompt = """
You are a professional trading signal parser. Your task is to extract trading signals from messages.

IMPORTANT RULES:
1. Only parse messages that contain clear trading signals with entry price and stop loss
2. If the message doesn't contain a trading signal, return {"is_signal": false}
3. Always extract exact numerical values - don't make assumptions
4. For coin symbols, look for hashtags (#SYMBOL) or clear mentions, the symbol must be like XUSDT, not X/USDT or X, modify to XUSDT
5. Return confidence score (0.0 to 1.0) based on signal clarity
6. For multiple take profits (TP1, TP2, etc.), include all in take_profits array. If more than 4 TP, convert to 4 TP by average
7. If only one take profit is mentioned, use the take_profit field
8. Determine order_type based on message content:
   - "market": if message suggests immediate execution (words like "now")
   - "limit": if message suggests SAY EXACT PRICE LIKE 1.0, 0.5
   - Default to "market" if unclear

Expected JSON format for valid signals:
{
    "is_signal": true,
    "coin": "SYMBOL",
    "entry": 0.0000,
    "stop_loss": 0.0000,
    "take_profit": 0.0000,  // optional (for single TP)
    "take_profits": [0.0000, 0.0000],  // optional (for multiple TPs)
    "tp_percentages": [40.0, 60.0],  // optional custom split percentages
    "side": "long",  // "long" or "short", default "long"
    "order_type": "market",  // "market" or "limit"
    "confidence": 0.95
}

For non-signals:
{
    "is_signal": false,
    "reason": "No clear trading signal found"
}

Examples of valid signals:
- "#PUMPBTC Entry: now Stop Loss: 0.02911" -> order_type: "market"
- "LONG BTCUSDT at 45000, SL: 44000" -> order_type: "limit"
- "Wait for ETH limit at 3200, SL: 3100" -> order_type: "limit"
- "BTC Entry: 45000 SL: 44000 TP1: 46000 TP2: 47000 TP3: 48000" -> order_type: "limit"
- "ETH entry 3200 STOP 3100 TP1 3300" -> order_type: "limit"
- "Buy ONDO now " -> order_type: "market"

Parse this message:
"""
    
    async def parse_message(self, message: str, source: str = "") -> ParseResult:
        """Parse message using Gemini AI.
        
        Args:
            message: Message text to parse
            source: Source of the message
            
        Returns:
            ParseResult with parsed signal or error
        """
        start_time = time.time()
        
        try:
            # Prepare prompt
            prompt = f"{self.system_prompt}\n\nMessage: {message}"
            
            # Call Gemini
            response = self.model.generate_content(prompt)
            processing_time = time.time() - start_time
            
            if not response.text:
                return ParseResult(
                    status=ParseStatus.FAILED,
                    error_message="Empty response from AI",
                    processing_time=processing_time
                )
            
            # Parse JSON response
            try:
                parsed_data = json.loads(response.text.strip())
            except json.JSONDecodeError:
                # Try to extract JSON from response
                json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
                if json_match:
                    try:
                        parsed_data = json.loads(json_match.group())
                    except json.JSONDecodeError:
                        return ParseResult(
                            status=ParseStatus.FAILED,
                            error_message="Failed to parse AI response as JSON",
                            raw_response=response.text,
                            processing_time=processing_time
                        )
                else:
                    return ParseResult(
                        status=ParseStatus.FAILED,
                        error_message="No JSON found in AI response",
                        raw_response=response.text,
                        processing_time=processing_time
                    )
            
            # Check if it's a valid signal
            if not parsed_data.get('is_signal', False):
                return ParseResult(
                    status=ParseStatus.NO_SIGNAL,
                    error_message=parsed_data.get('reason', 'No trading signal detected'),
                    confidence=parsed_data.get('confidence', 0.0),
                    raw_response=response.text,
                    processing_time=processing_time
                )
            
            # Create trading signal
            signal = self._create_signal_from_data(parsed_data, message, source)
            
            if not signal or not self._validate_signal(signal):
                return ParseResult(
                    status=ParseStatus.FAILED,
                    error_message="Invalid signal data parsed",
                    raw_response=response.text,
                    processing_time=processing_time
                )
            
            confidence = parsed_data.get('confidence', 0.0)
            
            return ParseResult(
                status=ParseStatus.SUCCESS,
                signal=signal,
                confidence=confidence,
                raw_response=response.text,
                processing_time=processing_time
            )
            
        except Exception as e:
            logger.error(f"Error parsing message with Gemini: {e}")
            return ParseResult(
                status=ParseStatus.FAILED,
                error_message=f"AI parsing error: {str(e)}",
                processing_time=time.time() - start_time
            )
    
    def is_valid_signal(self, text: str) -> bool:
        """Quick check for potential trading signals.
        
        Args:
            text: Text to check
            
        Returns:
            True if might contain signal, False otherwise
        """
        pass
        
    
    def _create_signal_from_data(
        self, 
        data: Dict[str, Any], 
        raw_message: str, 
        source: str
    ) -> Optional[TradingSignal]:
        """Create TradingSignal from parsed data.
        
        Args:
            data: Parsed data from AI
            raw_message: Original message
            source: Message source
            
        Returns:
            TradingSignal instance or None if invalid
        """
        try:
            coin = data.get('coin', '').upper().strip()
            entry = safe_float(data.get('entry'))
            stop_loss = safe_float(data.get('stop_loss'))
            take_profit = safe_float(data.get('take_profit')) if data.get('take_profit') else None
            
            # Handle multiple take profits
            take_profits = None
            tp_data = data.get('take_profits')
            if tp_data:
                if isinstance(tp_data, list):
                    take_profits = [safe_float(tp) for tp in tp_data if safe_float(tp) > 0]
                    if not take_profits:
                        take_profits = None
            
            # Handle custom TP percentages
            tp_percentages = None
            tp_pct_data = data.get('tp_percentages')
            if tp_pct_data:
                if isinstance(tp_pct_data, list):
                    tp_percentages = [safe_float(pct) for pct in tp_pct_data if safe_float(pct) > 0]
                    # Validate percentages sum to 100
                    if tp_percentages and abs(sum(tp_percentages) - 100.0) > 1.0:
                        tp_percentages = None  # Invalid percentages, use defaults
            
            # Determine side
            side_str = data.get('side', 'long').lower()
            if side_str == 'short':
                side = SignalType.SHORT
            elif side_str == 'long':
                side = SignalType.LONG
            else:
                side = SignalType.LONG  # Default
            
            # Get order type from AI response
            order_type = data.get('order_type', 'market').lower()
            if order_type not in ['market', 'limit']:
                order_type = 'market'  # Default fallback
            
            confidence = safe_float(data.get('confidence'), 0.0)
            
            # Validate required fields
            if not coin or entry <= 0 or stop_loss <= 0:
                return None
            
            return TradingSignal(
                coin=coin,
                entry=entry,
                stop_loss=stop_loss,
                take_profit=take_profit,
                take_profits=take_profits,
                tp_percentages=tp_percentages,
                side=side,
                confidence=confidence,
                order_type=order_type,  # Set from AI response
                source=source,
                raw_message=raw_message,
                metadata={
                    'parser': 'gemini',
                    'model': self.model_name,
                    'parsed_data': data
                }
            )
            
        except Exception as e:
            logger.error(f"Error creating signal from data: {e}")
            return None
