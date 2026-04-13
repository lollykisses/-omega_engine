#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Async Database Manager with retry logic for MySQL and Redis
"""

import asyncio
import json
from typing import Dict, Optional, Any
from datetime import datetime

import aiomysql
from aiomysql import Pool
import redis.asyncio as aioredis


class MySQLManager:
    """
    Async MySQL manager with automatic reconnection and retry logic.
    """
    
    def __init__(self, config: Dict):
        self.config = config
        self.host = config.get('host', 'localhost')
        self.port = config.get('port', 3306)
        self.user = config.get('user', 'root')
        self.password = config.get('password', '')
        self.database = config.get('database', 'omega_engine')
        self.pool_size = config.get('pool_size', 10)
        self.retry_attempts = config.get('retry_attempts', 5)
        self.retry_delay = config.get('retry_delay_seconds', 3)
        
        self.pool: Optional[Pool] = None
        self.connected = False
        self._reconnect_task: Optional[asyncio.Task] = None
        
    async def connect(self) -> bool:
        """Create connection pool with retry logic"""
        for attempt in range(1, self.retry_attempts + 1):
            try:
                self.pool = await aiomysql.create_pool(
                    host=self.host,
                    port=self.port,
                    user=self.user,
                    password=self.password,
                    db=self.database,
                    minsize=1,
                    maxsize=self.pool_size,
                    autocommit=True,
                    charset='utf8mb4',
                    connect_timeout=5
                )
                
                await self._create_tables()
                self.connected = True
                print(f"✅ MySQL connected (attempt {attempt})")
                return True
                
            except Exception as e:
                print(f"⚠️ MySQL connection attempt {attempt}/{self.retry_attempts} failed: {e}")
                if attempt < self.retry_attempts:
                    await asyncio.sleep(self.retry_delay)
                else:
                    print(f"❌ MySQL connection failed after {self.retry_attempts} attempts")
                    self.connected = False
                    return False
        
        return False
    
    async def _create_tables(self):
        """Create necessary tables if they don't exist"""
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                # Trades history table
                await cursor.execute("""
                    CREATE TABLE IF NOT EXISTS trades_history (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        trade_id VARCHAR(100) UNIQUE,
                        symbol VARCHAR(20),
                        side VARCHAR(10),
                        entry_price DECIMAL(20, 8),
                        exit_price DECIMAL(20, 8),
                        amount DECIMAL(20, 8),
                        profit_loss DECIMAL(20, 8),
                        profit_loss_pct DECIMAL(10, 4),
                        entry_time DATETIME,
                        exit_time DATETIME,
                        venue VARCHAR(50),
                        latency_us INT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_symbol (symbol),
                        INDEX idx_entry_time (entry_time)
                    )
                """)
                
                # AI Logs table
                await cursor.execute("""
                    CREATE TABLE IF NOT EXISTS ai_logs (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        decision_id VARCHAR(100),
                        symbol VARCHAR(20),
                        action VARCHAR(10),
                        confidence DECIMAL(5, 2),
                        market_state VARCHAR(20),
                        predicted_price DECIMAL(20, 8),
                        target_price DECIMAL(20, 8),
                        stop_price DECIMAL(20, 8),
                        position_size DECIMAL(20, 8),
                        spoofing_score DECIMAL(5, 4),
                        orderflow_imbalance DECIMAL(10, 4),
                        features_snapshot TEXT,
                        execution_result TEXT,
                        timestamp DATETIME,
                        INDEX idx_symbol (symbol),
                        INDEX idx_timestamp (timestamp)
                    )
                """)
                
                # Orderflow metrics table
                await cursor.execute("""
                    CREATE TABLE IF NOT EXISTS orderflow_metrics (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        symbol VARCHAR(20),
                        imbalance_ratio DECIMAL(10, 4),
                        spoofing_score DECIMAL(5, 4),
                        bid_pressure DECIMAL(20, 8),
                        ask_pressure DECIMAL(20, 8),
                        whale_detected BOOLEAN,
                        whale_size DECIMAL(20, 8),
                        timestamp DATETIME,
                        INDEX idx_symbol_timestamp (symbol, timestamp)
                    )
                """)
    
    async def execute_with_retry(self, query: str, params: tuple = None) -> Optional[Any]:
        """Execute query with automatic retry on failure"""
        if not self.connected:
            return None
        
        for attempt in range(3):
            try:
                async with self.pool.acquire() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute(query, params)
                        if query.strip().upper().startswith('SELECT'):
                            return await cursor.fetchall()
                        return cursor.lastrowid
            except Exception as e:
                if attempt < 2:
                    await asyncio.sleep(0.5)
                else:
                    print(f"Query failed after retries: {e}")
                    return None
    
    async def save_trade(self, trade_data: Dict) -> bool:
        """Save executed trade to database"""
        result = await self.execute_with_retry("""
            INSERT INTO trades_history 
            (trade_id, symbol, side, entry_price, exit_price, amount, 
            profit_loss, profit_loss_pct, entry_time, exit_time, venue, latency_us)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
            exit_price = VALUES(exit_price),
            profit_loss = VALUES(profit_loss),
            profit_loss_pct = VALUES(profit_loss_pct),
            exit_time = VALUES(exit_time)
        """, (
            trade_data.get('trade_id'),
            trade_data.get('symbol'),
            trade_data.get('side'),
            trade_data.get('entry_price'),
            trade_data.get('exit_price'),
            trade_data.get('amount'),
            trade_data.get('profit_loss'),
            trade_data.get('profit_loss_pct'),
            trade_data.get('entry_time'),
            trade_data.get('exit_time'),
            trade_data.get('venue'),
            trade_data.get('latency_us', 0)
        ))
        return result is not None
    
    async def close(self):
        """Close database connections"""
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()
            self.connected = False


class RedisManager:
    """Async Redis manager with automatic reconnection"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.host = config.get('host', 'localhost')
        self.port = config.get('port', 6379)
        self.db = config.get('db', 0)
        self.retry_attempts = config.get('retry_attempts', 5)
        self.retry_delay = config.get('retry_delay_seconds', 2)
        
        self.redis = None
        self.connected = False
        
    async def connect(self) -> bool:
        """Connect to Redis with retry logic"""
        for attempt in range(1, self.retry_attempts + 1):
            try:
                self.redis = await aioredis.from_url(
                    f"redis://{self.host}:{self.port}/{self.db}",
                    encoding="utf-8",
                    decode_responses=True,
                    max_connections=20,
                    socket_timeout=5,
                    socket_connect_timeout=5
                )
                
                await self.redis.ping()
                self.connected = True
                print(f"✅ Redis connected (attempt {attempt})")
                return True
                
            except Exception as e:
                print(f"⚠️ Redis connection attempt {attempt}/{self.retry_attempts} failed: {e}")
                if attempt < self.retry_attempts:
                    await asyncio.sleep(self.retry_delay)
                else:
                    print(f"❌ Redis connection failed after {self.retry_attempts} attempts")
                    self.connected = False
                    return False
        
        return False
    
    async def setex(self, key: str, ttl: int, value: Any) -> bool:
        """Set value with TTL and retry"""
        if not self.connected or not self.redis:
            return False
        
        try:
            await self.redis.setex(key, ttl, value)
            return True
        except Exception:
            return False
    
    async def get(self, key: str) -> Optional[str]:
        """Get value with retry"""
        if not self.connected or not self.redis:
            return None
        
        try:
            return await self.redis.get(key)
        except Exception:
            return None
    
    async def close(self):
        """Close Redis connection"""
        if self.redis:
            await self.redis.close()
            self.connected = False
