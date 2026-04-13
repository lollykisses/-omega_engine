#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Audio telemetry system for Xeon workstation
"""

import threading
from typing import Optional

AUDIO_AVAILABLE = False
try:
    import winsound
    AUDIO_AVAILABLE = True
except ImportError:
    pass


class AudioTelemetry:
    """8-bit sound telemetry system"""
    
    SOUNDS = {
        'gold': 1597,
        'radar': 610,
        'entry': 987,
        'exit': 377,
        'danger': 233,
        'nuclear': 144,
        'heartbeat': 55,
        'victory': 2584,
        'alert': 880,
        'confirm': 523
    }
    
    DURATIONS = {
        'short': 100,
        'medium': 300,
        'long': 500,
        'emergency': 1000
    }
    
    def __init__(self, enabled: bool = True):
        self.enabled = enabled and AUDIO_AVAILABLE
    
    def play(self, sound_type: str, duration: str = 'medium', async_play: bool = True):
        """Play a sound"""
        if not self.enabled:
            return
        
        freq = self.SOUNDS.get(sound_type, 440)
        dur = self.DURATIONS.get(duration, 300)
        
        if async_play:
            threading.Thread(target=self._beep, args=(freq, dur), daemon=True).start()
        else:
            self._beep(freq, dur)
    
    def _beep(self, freq: int, duration: int):
        """Internal beep function"""
        try:
            winsound.Beep(freq, duration)
        except Exception:
            pass
    
    def play_success(self):
        """Play success sound"""
        self.play('gold', 'short')
    
    def play_error(self):
        """Play error sound"""
        self.play('danger', 'short')
    
    def play_entry(self):
        """Play trade entry sound"""
        self.play('entry', 'short')
    
    def play_exit(self):
        """Play trade exit sound"""
        self.play('exit', 'short')
