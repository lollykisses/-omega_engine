#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram Bot for Omega Engine
"""

import threading
from datetime import datetime
from telebot import TeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton


class OmegaTelegramBot:
    """Telegram bot for monitoring and controlling Omega Engine"""
    
    def __init__(self, token: str, chat_id: str, engine=None):
        self.token = token
        self.chat_id = chat_id
        self.engine = engine
        self.bot = TeleBot(token)
        self.is_running = False
        
        self._setup_handlers()
        
    def _setup_handlers(self):
        """Setup all command handlers"""
        
        @self.bot.message_handler(commands=['start', 'help'])
        def send_welcome(message):
            text = """
🤖 **Omega Engine Bot** 🤖

**Available Commands:**

📊 `/status` - Show engine status
💰 `/balance` - Show current balance
📈 `/performance` - Show trading performance
🎯 `/risk` - Show risk metrics
🛑 `/stop` - Stop the engine
▶️ `/start_engine` - Start the engine
🆘 `/emergency` - Emergency kill
❓ `/help` - Show this help

**Status:** 🟢 Online
            """
            self.bot.reply_to(message, text, parse_mode=None)
        
        @self.bot.message_handler(commands=['status'])
        def send_status(message):
            if self.engine:
                status = self.engine.risk_manager.get_status()
                text = f"""
📊 **Omega Engine Status**

💰 **Balance:** ${status['balance']:,.2f}
📈 **Total P&L:** ${status['total_profit']:,.2f} ({status['total_profit_pct']:.2f}%)
📉 **Drawdown:** {status['current_drawdown']:.2f}%
🎯 **Win Rate:** {status['win_rate']:.1f}%
📊 **Total Trades:** {status['total_trades']}
🔒 **Risk Lock:** {'🔴 Locked' if status['is_locked'] else '🟢 Normal'}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                """
                self.bot.reply_to(message, text, parse_mode=None)
            else:
                self.bot.reply_to(message, "❌ Engine not connected")
        
        @self.bot.message_handler(commands=['balance'])
        def send_balance(message):
            if self.engine:
                status = self.engine.risk_manager.get_status()
                text = f"""
💰 **Balance Information**

**Current Balance:** ${status['balance']:,.2f}
**Initial Balance:** ${status['initial_balance']:,.2f}
**Total Profit:** ${status['total_profit']:,.2f}
**Profit %:** {status['total_profit_pct']:.2f}%

**Daily P&L:** ${status['daily_pnl']:,.2f}
**Daily P&L %:** {status['daily_pnl_pct']:.2f}%
                """
                self.bot.reply_to(message, text, parse_mode=None)
        
        @self.bot.message_handler(commands=['performance'])
        def send_performance(message):
            if self.engine:
                status = self.engine.risk_manager.get_status()
                text = f"""
📈 **Performance Metrics**

**Win Rate:** {status['win_rate']:.1f}%
**Total Trades:** {status['total_trades']}
**Current Drawdown:** {status['current_drawdown']:.2f}%
**Max Drawdown:** {status['max_drawdown']:.2f}%

**Open Positions:** {status['open_positions']}
**Risk Lock:** {status['lock_reason'] if status['is_locked'] else 'None'}
                """
                self.bot.reply_to(message, text, parse_mode=None)
        
        @self.bot.message_handler(commands=['risk'])
        def send_risk(message):
            if self.engine:
                status = self.engine.risk_manager.get_status()
                text = f"""
🎯 **Risk Management**

**Stop Loss:** {self.engine.risk_manager.default_stop_loss_pct}%
**Take Profit:** {self.engine.risk_manager.default_take_profit_pct}%
**Max Position Size:** {self.engine.risk_manager.max_position_size * 100}%
**Max Daily Loss:** {self.engine.risk_manager.max_daily_loss_pct}%

**Consecutive Losses:** {self.engine.risk_manager.consecutive_losses}
**Is Locked:** {'🔴 YES' if status['is_locked'] else '🟢 NO'}
                """
                self.bot.reply_to(message, text, parse_mode=None)
        
        @self.bot.message_handler(commands=['emergency'])
        def emergency_kill(message):
            # Create confirmation keyboard
            keyboard = InlineKeyboardMarkup()
            yes_btn = InlineKeyboardButton("✅ YES - Emergency Kill", callback_data="emergency_yes")
            no_btn = InlineKeyboardButton("❌ NO - Cancel", callback_data="emergency_no")
            keyboard.add(yes_btn, no_btn)
            
            self.bot.reply_to(message, "⚠️ **EMERGENCY KILL CONFIRMATION** ⚠️\n\nThis will close ALL positions!\nAre you sure?", 
                            reply_markup=keyboard, parse_mode=None)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('emergency_'))
        def handle_emergency_callback(call):
            if call.data == "emergency_yes":
                if self.engine:
                    self.engine.emergency_kill()
                    self.bot.send_message(call.message.chat.id, "💀 **EMERGENCY KILL ACTIVATED**\nAll positions closed!", parse_mode=None)
                else:
                    self.bot.send_message(call.message.chat.id, "❌ Engine not connected")
            else:
                self.bot.send_message(call.message.chat.id, "✅ Emergency kill cancelled")
            
            self.bot.answer_callback_query(call.id)
        
        @self.bot.message_handler(commands=['stop'])
        def stop_engine(message):
            if self.engine:
                self.engine.active = False
                self.bot.reply_to(message, "🛑 **Engine stopped**\nUse /start_engine to restart", parse_mode=None)
            else:
                self.bot.reply_to(message, "❌ Engine not connected")
        
        @self.bot.message_handler(commands=['start_engine'])
        def start_engine(message):
            if self.engine:
                self.engine.active = True
                self.bot.reply_to(message, "▶️ **Engine started**", parse_mode=None)
            else:
                self.bot.reply_to(message, "❌ Engine not connected")
    
    def start(self):
        """Start the bot in a separate thread"""
        self.is_running = True
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()
        print("✅ Telegram Bot started")
    
    def _run(self):
        """Run bot polling"""
        try:
            self.bot.infinity_polling(timeout=30,long_polling_timeout=30)
        except Exception as e:
            print(f"Telegram bot error: {e}")
    
    def send_message(self, text: str):
        """Send message to Telegram"""
        if self.chat_id:
            try:
                self.bot.send_message(self.chat_id, text, parse_mode=None)
            except Exception as e:
                print(f"Failed to send message: {e}")
    
    def send_trade_notification(self, symbol: str, side: str, amount: float, price: float, pnl: float = None):
        """Send trade notification"""
        if pnl is not None:
            emoji = "🟢" if pnl >= 0 else "🔴"
            text = f"""
{emoji} **TRADE EXECUTED**

📊 **Symbol:** {symbol}
🔄 **Side:** {side.upper()}
💰 **Amount:** ${amount:,.2f}
💵 **Price:** ${price:,.2f}
📈 **P&L:** ${pnl:,.2f}
⏰ **Time:** {datetime.now().strftime('%H:%M:%S')}
            """
        else:
            text = f"""
🎯 **ORDER EXECUTED**

📊 **Symbol:** {symbol}
🔄 **Side:** {side.upper()}
💰 **Amount:** ${amount:,.2f}
💵 **Price:** ${price:,.2f}
⏰ **Time:** {datetime.now().strftime('%H:%M:%S')}
            """
        self.send_message(text)
    
    def send_alert(self, title: str, message: str, level: str = "info"):
        """Send alert message"""
        emoji = {"info": "ℹ️", "warning": "⚠️", "error": "❌", "success": "✅"}.get(level, "📢")
        text = f"""
{emoji} **{title}**

{message}
⏰ {datetime.now().strftime('%H:%M:%S')}
        """
        self.send_message(text)
    
    def stop(self):
        """Stop the bot"""
        self.is_running = False
        try:
            self.bot.stop_polling()
        except:
            pass
