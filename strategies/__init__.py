"""Strategies package - base class and concrete strategy implementations."""
from strategies.base import AbstractStrategy, Signal, SignalType
from strategies.ema_crossover import EMACrossoverStrategy
from strategies.rsi_mean_reversion import RSIMeanReversionStrategy

__all__ = [
    "AbstractStrategy",
    "Signal",
    "SignalType",
    "EMACrossoverStrategy",
    "RSIMeanReversionStrategy",
]