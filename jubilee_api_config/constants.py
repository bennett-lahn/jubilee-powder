"""
Constants for Jubilee automation system.

This module contains enumerations and constants used across the Jubilee automation system.
"""
from enum import Enum


class FeedRate(Enum):
    """Enumeration for feedrate settings (values in mm/min)."""
    FAST = 5000
    MEDIUM = 2800
    SLOW = 700

