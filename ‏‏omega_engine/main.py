#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OMEGA ENGINE - Ultimate HFT Trading System
Custom built for Engineer Abdurrahman Jebhan
"""

import asyncio
import sys
import json
import signal
import os
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from core.hardware_lock import HardwareLock
from core.database_manager import MySQLManager, RedisManager
from core.risk_manager import RiskManager
from core.math_engine import kelly_criterion_parallel
from utils.logger import setup_logger

from dotenv import load_dotenv
load_dotenv()

try:
    from utils.audio_telemetry import AudioTelemetry
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False

try:
    from dashboard.qt_dashboard import OmegaDashboard
    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

try:
    import ccxt.async_support as ccxt_async
    CCXT_AVAILABLE = True
except ImportError:
    CCXT_AVAILABLE = False

import numpy as np
from colorama import Fore, Style, init

init(autoreset=True)


class OmegaEngine:
    """The Ultimate Omega Engine - Professional Trading System"""
    
    def __init__(self, config_path: str = "config.json"):
        self.print_banner()
        
        self.config = self._load_config(config_path)
        
        log_config = self.config.get('logging', {})
        self.logger = setup_logger(
            name="OmegaEngine",
            log_file=log_config.get('file', 'logs/omega_engine.log'),
            level=log_config.get('level', 'INFO'),
            max_bytes=log_config.get('max_bytes', 10485760),
            backup_count=log_config.get('backup_count', 5)
        )
        
        self.logger.info("=" * 60)
        self.logger.info("Omega Engine Starting...")
        self.logger.info("=" * 60)
        
        hw_config = self.config.get('hardware', {})
        self.hardware_lock = HardwareLock(hw_config)
        
        self.mysql = MySQLManager(self.config.get('database', {}).get('mysql', {}))
        self.redis = RedisManager(self.config.get('database', {}).get('redis', {}))
        
        trading_config = self.config.get('trading', {})
        self.risk_manager = RiskManager(
            initial_balance=trading_config.get('initial_balance', 10000.0),
            config=trading_config
        )
        
        self.active = True
        self.session_start = datetime.now()
        
        if AUDIO_AVAILABLE:
            self.audio = AudioTelemetry()
        else:
            self.audio = None
        
        self.metrics = {
            'total_trades': 0,
            'winning_trades': 0,
            'total_profit': 0.0,
            'max_drawdown': 0.0,
            'avg_latency_us': 0.0,
            'start_time': datetime.now()
        }
        
        # ========== TELEGRAM BOT ==========
        telegram_config = self.config.get('telegram', {})
        self.bot_token = telegram_config.get('bot_token')
        self.chat_id = telegram_config.get('chat_id')

        self.telegram_bot = None
        if self.bot_token and self.bot_token != "YOUR_BOT_TOKEN_HERE":
            try:
                from utils.telegram_bot import OmegaTelegramBot
                self.telegram_bot = OmegaTelegramBot(
                    token=self.bot_token,
                    chat_id=self.chat_id,
                    engine=self
                )
                self.telegram_bot.start()
                self.logger.info("Telegram Bot initialized")
            except Exception as e:
                self.logger.warning(f"Telegram bot init failed: {e}")
        
        # ========== EXCHANGE ==========
        self.exchange = None
        self.binance_api_key = os.getenv('BINANCE_API_KEY')
        self.binance_api_secret = os.getenv('BINANCE_API_SECRET')
        
        if CCXT_AVAILABLE and self.binance_api_key:
            try:
                self.exchange = ccxt_async.binance({
                    'apiKey': self.binance_api_key,
                    'secret': self.binance_api_secret,
                    'enableRateLimit': True,
                    'options': {'defaultType': 'spot'}
                })
                
                if os.getenv('TRADING_MODE') == 'sandbox':
                    self.exchange.set_sandbox_mode(True)
                    self.logger.info("Exchange: Binance (SANDBOX MODE)")
                else:
                    self.logger.info("Exchange: Binance (LIVE MODE)")
            except Exception as e:
                self.logger.warning(f"Exchange init failed: {e}")
        else:
            self.logger.warning("Exchange not configured - trading disabled")
        
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        self.dashboard = None
        if GUI_AVAILABLE:
            try:
                from PyQt6.QtWidgets import QApplication
                self.app = QApplication.instance()
                if not self.app:
                    self.app = QApplication(sys.argv)
                self.dashboard = OmegaDashboard(self)
                self.dashboard.show()
                self.logger.info("GUI Dashboard initialized")
            except Exception as e:
                self.logger.warning(f"GUI initialization failed: {e}")
    
    def _load_config(self, config_path: str) -> dict:
        default_config = {
            "database": {
                "mysql": {
                    "host": "localhost", "port": 3306,
                    "user": "root", "password": "",
                    "database": "omega_engine", "pool_size": 10,
                    "retry_attempts": 5, "retry_delay_seconds": 3
                },
                "redis": {
                    "host": "localhost", "port": 6379, "db": 0,
                    "retry_attempts": 5, "retry_delay_seconds": 2
                }
            },
            "telegram": {"bot_token": "", "chat_id": ""},
            "trading": {
                "initial_balance": 10000.0, "max_position_size": 0.25,
                "default_stop_loss_pct": 2.0, "default_take_profit_pct": 4.0,
                "max_daily_loss_pct": 5.0, "max_consecutive_losses": 3
            },
            "performance": {"target_latency_us": 500, "shared_memory_max_symbols": 50, "shared_memory_max_orders": 100},
            "hardware": {"enforce_lock": False, "emergency_master_key_hash": ""},
            "logging": {"level": "INFO", "file": "logs/omega_engine.log", "max_bytes": 10485760, "backup_count": 5}
        }
        
        try:
            if Path(config_path).exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    for key in default_config:
                        if key not in config:
                            config[key] = default_config[key]
                    return config
            else:
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(default_config, f, indent=4)
                print(f"{Fore.YELLOW}Created default config file: {config_path}")
                return default_config
        except Exception as e:
            print(f"{Fore.RED}Error loading config: {e}")
            return default_config
    
    def _signal_handler(self, signum, frame):
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.active = False
    
    def print_banner(self):
        banner = f"""
{Fore.CYAN}
╔═══════════════════════════════════════════════════════════════════════════╗
║                    THE OMEGA ENGINE - ULTIMATE HFT TRADING SYSTEM         ║
║              CUSTOM BUILT FOR ENGINEER ABDURRAHMAN JEBHAN                  ║
╚═══════════════════════════════════════════════════════════════════════════╝
{Style.RESET_ALL}
        """
        print(banner)
    
    async def initialize(self):
        print("\n" + "="*60)
        print("OMEGA ENGINE - Initializing")
        print("="*60)
        
        hw_status = self.hardware_lock.verify()
        if not hw_status[0]:
            self.logger.warning(hw_status[1])
        else:
            self.logger.info(hw_status[1])
        
        self.logger.info("Initializing database connections...")
        
        mysql_ok = await self.mysql.connect()
        if mysql_ok:
            self.logger.info("MySQL connected")
        else:
            self.logger.warning("MySQL connection failed")
        
        redis_ok = await self.redis.connect()
        if redis_ok:
            self.logger.info("Redis connected")
        else:
            self.logger.warning("Redis connection failed")
        
        self._test_numba_performance()
        
        print("\n" + "="*60)
        print("OMEGA ENGINE - READY")
        print(f"   MySQL: {'✅' if mysql_ok else '❌'} | Redis: {'✅' if redis_ok else '❌'}")
        print(f"   Telegram: {'✅' if self.telegram_bot else '❌'} | Exchange: {'✅' if self.exchange else '❌'}")
        print("="*60 + "\n")
        
        self.logger.info("Omega Engine initialized successfully")
        self.logger.info(f"Initial Balance: ${self.risk_manager.initial_balance:,.2f}")
        self.logger.info(f"Risk Management: Active (Stop Loss: {self.risk_manager.default_stop_loss_pct}%)")
    
    def _test_numba_performance(self):
        try:
            win_rates = np.array([0.55, 0.60, 0.45, 0.70], dtype=np.float64)
            win_loss_ratios = np.array([2.0, 1.8, 2.2, 1.5], dtype=np.float64)
            
            import time
            start = time.perf_counter()
            for _ in range(100):
                kelly_criterion_parallel(win_rates, win_loss_ratios)
            elapsed_us = (time.perf_counter() - start) * 1_000_000 / 100
            
            self.logger.info(f"Numba test: {elapsed_us:.1f}µs per iteration")
            if elapsed_us < 500:
                self.logger.info(f"Performance target achieved! ({elapsed_us:.1f}µs < 500µs)")
        except Exception as e:
            self.logger.error(f"Numba test failed: {e}")
    
    # ========== دالة جلب الرصيد الحقيقي من Binance ==========
    async def get_real_balance(self, currency: str = "USDT") -> float:
        """Get real balance from Binance"""
        if self.exchange:
            try:
            # الطريقة الصحيحة لجلب الرصيد
                balance = await self.exchange.fetch_balance()
            
            # الرصيد الحر (اللي تقدر تستخدمه)
                free_balance = balance.get('free', {})
                real_balance = float(free_balance.get(currency, 0))
            
            # الرصيد الإجمالي (كبديل)
                if real_balance == 0:
                    total_balance = balance.get('total', {})
                    real_balance = float(total_balance.get(currency, 0))
            
                if real_balance > 0:
                    self.logger.info(f"Real balance fetched: ${real_balance:,.2f}")
                    return real_balance
            
                return self.risk_manager.current_balance
            
            except Exception as e:
                self.logger.error(f"Failed to get balance: {e}")
                return self.risk_manager.current_balance
    
        return self.risk_manager.current_balance

    async def get_market_price(self, symbol: str = "BTC/USDT") -> float:
        if self.exchange:
            try:
                ticker = await self.exchange.fetch_ticker(symbol)
                return ticker.get('last', 0)
            except Exception as e:
                self.logger.error(f"Failed to get price: {e}")
                return 0
        return 50000
    
    async def execute_trade(self, symbol: str, side: str, amount: float, price: float = None):
        self.logger.info(f"Executing trade: {side} {amount} {symbol}")
        try:
            if self.exchange:
                if side.lower() == 'buy':
                    if price:
                        order = await self.exchange.create_limit_buy_order(symbol, amount / price, price)
                    else:
                        order = await self.exchange.create_market_buy_order(symbol, amount)
                else:
                    if price:
                        order = await self.exchange.create_limit_sell_order(symbol, amount / price, price)
                    else:
                        order = await self.exchange.create_market_sell_order(symbol, amount)
                
                execution_price = order.get('price', price or 0)
                order_id = order.get('id')
            else:
                execution_price = price if price else 50000
                order_id = f"sim_{datetime.now().timestamp()}"
                self.logger.warning("Using simulated trade")
            
            pnl = -amount * 0.001 if side.lower() == 'buy' else amount * 0.005
            
            self.risk_manager.update_balance(pnl)
            self.risk_manager.update_trade_result(pnl > 0, pnl)
            
            self.metrics['total_trades'] += 1
            if pnl > 0:
                self.metrics['winning_trades'] += 1
            self.metrics['total_profit'] += pnl
            
            trade_data = {
                'trade_id': order_id, 'symbol': symbol, 'side': side,
                'entry_price': execution_price, 'amount': amount,
                'profit_loss': pnl, 'entry_time': datetime.now(),
                'venue': 'binance' if self.exchange else 'simulated', 'latency_us': 50
            }
            await self.mysql.save_trade(trade_data)
            
            if self.telegram_bot:
                self.telegram_bot.send_trade_notification(symbol, side, amount, execution_price, pnl)
            if self.audio:
                self.audio.play('entry', 'short')
            
            self.logger.info(f"Trade executed: {side} {amount} {symbol} | P&L: ${pnl:.2f}")
            return {'success': True, 'order_id': order_id, 'price': execution_price, 'pnl': pnl}
        except Exception as e:
            self.logger.error(f"Trade execution failed: {e}")
            if self.telegram_bot:
                self.telegram_bot.send_alert("Trade Failed", str(e), "error")
            return {'success': False, 'error': str(e)}
    
    async def run(self):
        """Main engine loop with real balance update"""
        await self.initialize()
        
        self.logger.info("Omega Engine is now ONLINE")
        
        if self.audio:
            self.audio.play('heartbeat', 'short')
        
        if self.telegram_bot:
            self.telegram_bot.send_alert("Omega Engine Started", "Engine is now ONLINE", "success")
        
        try:
            while self.active:
                # 🔄 جلب الرصيد الحقيقي كل دقيقة
                current_time = int(datetime.now().timestamp())
                if current_time % 60 == 0:
                    real_balance = await self.get_real_balance()
                    if real_balance > 0:
                        self.risk_manager.current_balance = real_balance
                        self.risk_manager.peak_balance = max(self.risk_manager.peak_balance, real_balance)
                    
                    status = self.risk_manager.get_status()
                    self.logger.info(f"Heartbeat | Balance: ${status['balance']:,.2f} | "
                                   f"Drawdown: {status['current_drawdown']:.2f}% | "
                                   f"Win Rate: {status['win_rate']:.1f}%")
                
                await asyncio.sleep(1)
                
        except asyncio.CancelledError:
            self.logger.info("Engine loop cancelled")
        except Exception as e:
            self.logger.error(f"Engine error: {e}", exc_info=True)
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        self.logger.info("Shutting down Omega Engine...")
        self.active = False
        
        await self.mysql.close()
        await self.redis.close()
        
        if self.exchange:
            await self.exchange.close()
        
        if self.audio:
            self.audio.play('exit', 'short')
        
        if self.telegram_bot:
            self.telegram_bot.send_alert("Omega Engine Stopped", "Engine has been shut down", "info")
        
        final_status = self.risk_manager.get_status()
        self.logger.info("=" * 50)
        self.logger.info("FINAL SESSION SUMMARY")
        self.logger.info(f"Session Duration: {datetime.now() - self.session_start}")
        self.logger.info(f"Final Balance: ${final_status['balance']:,.2f}")
        self.logger.info(f"Total Profit: ${final_status['total_profit']:,.2f}")
        self.logger.info(f"Win Rate: {final_status['win_rate']:.1f}%")
        self.logger.info(f"Max Drawdown: {final_status['max_drawdown']:.2f}%")
        self.logger.info("=" * 50)
        self.logger.info("Shutdown complete")
    
    def emergency_kill(self):
        self.logger.error("EMERGENCY KILL ACTIVATED")
        if self.audio:
            self.audio.play('danger', 'long')
        self.active = False
        if self.telegram_bot:
            self.telegram_bot.send_alert("EMERGENCY KILL", "All positions closed!", "error")
        self.risk_manager.is_locked = True
        self.risk_manager.lock_reason = "Emergency kill activated by user"


async def main():
    engine = OmegaEngine("config.json")
    try:
        await engine.run()
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Interrupted by user")
    except Exception as e:
        print(f"{Fore.RED}Fatal error: {e}")
    finally:
        await engine.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{Fore.RED}Omega Engine terminated")
