#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Professional Risk Management System
- Stop Loss (hard and trailing)
- Position sizing (Kelly-based)
- Drawdown protection
- Daily loss limits
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from datetime import datetime, date
from collections import deque


@dataclass
class Position:
    """Trading position data"""
    symbol: str
    side: str
    entry_price: float
    amount: float
    entry_time: datetime
    stop_loss_price: float
    take_profit_price: float
    trailing_stop_pct: float = 0.0
    highest_price: float = 0.0
    lowest_price: float = float('inf')
    position_id: str = ""


class RiskManager:
    """Advanced risk management system"""
    
    def __init__(self, initial_balance: float = 10000.0, config: Dict = None):
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.peak_balance = initial_balance
        self.config = config or {}
        
        # Risk parameters
        self.max_position_size = self.config.get('max_position_size', 0.25)
        self.default_stop_loss_pct = self.config.get('default_stop_loss_pct', 2.0)
        self.default_take_profit_pct = self.config.get('default_take_profit_pct', 4.0)
        self.max_daily_loss_pct = self.config.get('max_daily_loss_pct', 5.0)
        self.max_consecutive_losses = self.config.get('max_consecutive_losses', 3)
        
        # Trading state
        self.open_positions: Dict[str, Position] = {}
        self.closed_positions: List[Position] = []
        self.daily_pnl = 0.0
        self.current_day = date.today()
        self.consecutive_losses = 0
        self.total_trades = 0
        self.winning_trades = 0
        
        # Performance tracking
        self.balance_history = deque(maxlen=1000)
        self.balance_history.append(initial_balance)
        self.drawdown_history = deque(maxlen=100)
        
        # Lock flags
        self.is_locked = False
        self.lock_reason = ""
        
    def update_balance(self, pnl: float):
        """Update balance after trade execution"""
        self.current_balance += pnl
        
        if self.current_balance > self.peak_balance:
            self.peak_balance = self.current_balance
        
        today = date.today()
        if today != self.current_day:
            self.daily_pnl = 0.0
            self.current_day = today
        self.daily_pnl += pnl
        
        self.balance_history.append(self.current_balance)
        
        daily_loss_pct = abs(self.daily_pnl / self.initial_balance * 100)
        if daily_loss_pct >= self.max_daily_loss_pct:
            self.is_locked = True
            self.lock_reason = f"Daily loss limit reached: {daily_loss_pct:.2f}%"
    
    def update_trade_result(self, is_win: bool, pnl: float):
        """Update trade statistics"""
        self.total_trades += 1
        if is_win:
            self.winning_trades += 1
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1
            
        if self.consecutive_losses >= self.max_consecutive_losses:
            self.is_locked = True
            self.lock_reason = f"Max consecutive losses: {self.consecutive_losses}"
        
        self.update_balance(pnl)
    
    def calculate_position_size(self, capital: float, risk_per_trade_pct: float = 1.0,
                                stop_loss_pct: float = 2.0) -> float:
        if stop_loss_pct <= 0:
            return capital * self.max_position_size
        
        risk_amount = capital * (risk_per_trade_pct / 100)
        position_size = risk_amount / (stop_loss_pct / 100)
        max_size = capital * self.max_position_size
        return min(position_size, max_size)
    
    def calculate_stop_loss(self, entry_price: float, side: str, 
                            stop_loss_pct: float = None) -> float:
        if stop_loss_pct is None:
            stop_loss_pct = self.default_stop_loss_pct
        
        if side.lower() == 'buy':
            return entry_price * (1 - stop_loss_pct / 100)
        else:
            return entry_price * (1 + stop_loss_pct / 100)
    
    def calculate_take_profit(self, entry_price: float, side: str,
                               take_profit_pct: float = None) -> float:
        if take_profit_pct is None:
            take_profit_pct = self.default_take_profit_pct
        
        if side.lower() == 'buy':
            return entry_price * (1 + take_profit_pct / 100)
        else:
            return entry_price * (1 - take_profit_pct / 100)
    
    def update_trailing_stop(self, position: Position, current_price: float) -> Optional[float]:
        if position.trailing_stop_pct <= 0:
            return None
        
        if position.side == 'buy':
            if current_price > position.highest_price:
                position.highest_price = current_price
                new_stop = position.highest_price * (1 - position.trailing_stop_pct / 100)
                if new_stop > position.stop_loss_price:
                    position.stop_loss_price = new_stop
                    return new_stop
        else:
            if current_price < position.lowest_price:
                position.lowest_price = current_price
                new_stop = position.lowest_price * (1 + position.trailing_stop_pct / 100)
                if new_stop < position.stop_loss_price:
                    position.stop_loss_price = new_stop
                    return new_stop
        return None
    
    def check_stop_loss(self, position: Position, current_price: float) -> Tuple[bool, str]:
        if position.side == 'buy':
            if current_price <= position.stop_loss_price:
                return True, f"Stop loss triggered at {current_price}"
        else:
            if current_price >= position.stop_loss_price:
                return True, f"Stop loss triggered at {current_price}"
        return False, ""
    
    def check_take_profit(self, position: Position, current_price: float) -> Tuple[bool, str]:
        if position.side == 'buy':
            if current_price >= position.take_profit_price:
                return True, f"Take profit triggered at {current_price}"
        else:
            if current_price <= position.take_profit_price:
                return True, f"Take profit triggered at {current_price}"
        return False, ""
    
    @property
    def current_drawdown(self) -> float:
        if self.peak_balance <= 0:
            return 0.0
        return (self.peak_balance - self.current_balance) / self.peak_balance * 100
    
    @property
    def max_drawdown(self) -> float:
        if not self.balance_history:
            return 0.0
        
        peak = self.balance_history[0]
        max_dd = 0.0
        
        for balance in self.balance_history:
            if balance > peak:
                peak = balance
            dd = (peak - balance) / peak * 100
            if dd > max_dd:
                max_dd = dd
        return max_dd
    
    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return self.winning_trades / self.total_trades * 100
    
    @property
    def total_profit(self) -> float:
        return self.current_balance - self.initial_balance
    
    def get_status(self) -> Dict:
        """Get current risk status - MODIFIED for real balance"""
        return {
            'balance': self.current_balance,
            'initial_balance': self.initial_balance,
            'total_profit': self.total_profit,
            'total_profit_pct': (self.total_profit / self.initial_balance * 100) if self.initial_balance > 0 else 0,
            'current_drawdown': self.current_drawdown,
            'max_drawdown': self.max_drawdown,
            'win_rate': self.win_rate,
            'total_trades': self.total_trades,
            'open_positions': len(self.open_positions),
            'is_locked': self.is_locked,
            'lock_reason': self.lock_reason,
            'daily_pnl': self.daily_pnl,
            'daily_pnl_pct': (self.daily_pnl / self.initial_balance * 100) if self.initial_balance > 0 else 0
        }
    
    def reset_lock(self):
        self.is_locked = False
        self.lock_reason = ""
        self.consecutive_losses = 0
