#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Numba-accelerated mathematical functions for HFT
Optimized for sub-500µs latency
"""

import numpy as np
from numba import njit, prange, float64, int64, boolean
from typing import Tuple


@njit(float64[:](float64[:], float64[:]), parallel=True, cache=True, fastmath=True)
def kelly_criterion_parallel(win_rates: np.ndarray, win_loss_ratios: np.ndarray) -> np.ndarray:
    """
    Vectorized Kelly Criterion calculation with Numba JIT.
    
    ⚠️ IMPORTANT: Inputs MUST be numpy arrays, not Python lists!
    
    Formula: f* = (p * b - q) / b
    where p = win rate, q = 1-p, b = win/loss ratio
    
    Args:
        win_rates: np.ndarray of win rates (0-1)
        win_loss_ratios: np.ndarray of win/loss ratios
    
    Returns:
        np.ndarray of optimal position sizes (0-0.25)
    """
    n = len(win_rates)
    results = np.zeros(n, dtype=np.float64)
    
    for i in prange(n):
        p = win_rates[i]
        b = win_loss_ratios[i]
        q = 1.0 - p
        
        if b > 0 and p > 0:
            kelly = (p * b - q) / b
            # Quarter-Kelly for safety (max 25%)
            results[i] = max(0.0, min(0.25, kelly * 0.25))
        else:
            results[i] = 0.02  # Default 2%
            
    return results


@njit(float64[:](float64, float64[:], int64), parallel=True, fastmath=True, cache=True)
def monte_carlo_simulation(initial_capital: float, returns: np.ndarray, 
                        num_simulations: int = 10000) -> np.ndarray:
    """
    Monte Carlo simulation for risk assessment.
    
    Args:
        initial_capital: Starting capital
        returns: np.ndarray of historical returns
        num_simulations: Number of Monte Carlo runs
    
    Returns:
        np.ndarray of final capital values
    """
    n = len(returns)
    results = np.zeros(num_simulations, dtype=np.float64)
    
    for i in prange(num_simulations):
        capital = initial_capital
        # Randomly sample returns with replacement
        for _ in range(n):
            idx = np.random.randint(0, n)
            capital *= (1.0 + returns[idx])
        results[i] = capital
        
    return results


@njit(float64(float64[:], float64), fastmath=True, cache=True)
def calculate_var(returns: np.ndarray, confidence_level: float = 0.95) -> float:
    """
    Value at Risk (VaR) calculation using historical method.
    
    Args:
        returns: np.ndarray of historical returns
        confidence_level: Confidence level (default 0.95)
    
    Returns:
        VaR as percentage
    """
    sorted_returns = np.sort(returns)
    idx = int((1 - confidence_level) * len(sorted_returns))
    idx = max(0, min(idx, len(sorted_returns) - 1))
    return -sorted_returns[idx] * 100


@njit(float64(float64[:], float64), fastmath=True, cache=True)
def calculate_cvar(returns: np.ndarray, confidence_level: float = 0.95) -> float:
    """
    Conditional Value at Risk (CVaR) - Expected shortfall.
    
    Args:
        returns: np.ndarray of historical returns
        confidence_level: Confidence level (default 0.95)
    
    Returns:
        CVaR as percentage
    """
    var = calculate_var(returns, confidence_level)
    threshold = -var / 100
    tail_returns = returns[returns < threshold]
    if len(tail_returns) > 0:
        return -np.mean(tail_returns) * 100
    return var


@njit(float64(float64[:], float64), fastmath=True, cache=True)
def calculate_sharpe_ratio(returns: np.ndarray, risk_free_rate: float = 0.02) -> float:
    """
    Calculate Sharpe Ratio.
    
    Formula: SR = (E[R] - Rf) / σ(R)
    
    Args:
        returns: np.ndarray of returns
        risk_free_rate: Annual risk-free rate (default 2%)
    
    Returns:
        Sharpe Ratio
    """
    if len(returns) < 2:
        return 0.0
    
    mean_return = np.mean(returns)
    std_return = np.std(returns)
    
    if std_return == 0:
        return 0.0
        
    return (mean_return - risk_free_rate / 252) / std_return * np.sqrt(252)


@njit(float64[:](float64[:], int64), fastmath=True, cache=True)
def calculate_returns(prices: np.ndarray, window: int = 1) -> np.ndarray:
    """
    Calculate returns from price array.
    
    Args:
        prices: np.ndarray of prices
        window: Return window (1 for simple returns)
    
    Returns:
        np.ndarray of returns
    """
    n = len(prices)
    if n <= window:
        return np.zeros(0, dtype=np.float64)
    
    returns = np.zeros(n - window, dtype=np.float64)
    for i in range(n - window):
        returns[i] = (prices[i + window] - prices[i]) / prices[i]
    
    return returns


@njit(float64[:](float64[:], int64), fastmath=True, cache=True)
def calculate_sma(prices: np.ndarray, period: int) -> np.ndarray:
    """
    Calculate Simple Moving Average.
    
    Args:
        prices: np.ndarray of prices
        period: SMA period
    
    Returns:
        np.ndarray of SMA values
    """
    n = len(prices)
    if n < period:
        return np.zeros(0, dtype=np.float64)
    
    sma = np.zeros(n - period + 1, dtype=np.float64)
    window_sum = 0.0
    
    # Initial window
    for i in range(period):
        window_sum += prices[i]
    sma[0] = window_sum / period
    
    # Sliding window
    for i in range(1, n - period + 1):
        window_sum = window_sum - prices[i - 1] + prices[i + period - 1]
        sma[i] = window_sum / period
    
    return sma


@njit(float64[:](float64[:], int64), fastmath=True, cache=True)
def calculate_rsi(prices: np.ndarray, period: int = 14) -> np.ndarray:
    """
    Calculate RSI indicator.
    
    Args:
        prices: np.ndarray of prices
        period: RSI period (default 14)
    
    Returns:
        np.ndarray of RSI values (0-100)
    """
    n = len(prices)
    if n <= period:
        return np.zeros(0, dtype=np.float64)
    
    # Calculate price changes
    deltas = np.zeros(n - 1, dtype=np.float64)
    for i in range(n - 1):
        deltas[i] = prices[i + 1] - prices[i]
    
    # Calculate gains and losses
    gains = np.zeros(len(deltas), dtype=np.float64)
    losses = np.zeros(len(deltas), dtype=np.float64)
    
    for i in range(len(deltas)):
        if deltas[i] > 0:
            gains[i] = deltas[i]
        else:
            losses[i] = -deltas[i]
    
    # Calculate average gains and losses
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    
    if avg_loss == 0:
        return np.full(n - period, 100.0, dtype=np.float64)
    
    rs = avg_gain / avg_loss
    rsi = np.zeros(n - period, dtype=np.float64)
    rsi[0] = 100.0 - (100.0 / (1.0 + rs))
    
    # Wilder's smoothing
    for i in range(1, n - period):
        avg_gain = (avg_gain * (period - 1) + gains[period + i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[period + i - 1]) / period
        
        if avg_loss == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i] = 100.0 - (100.0 / (1.0 + rs))
    
    return rsi
