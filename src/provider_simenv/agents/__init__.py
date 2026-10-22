"""
agents/__init__.py — Re-exports all agent classes.

Allows model.py to import cleanly:
  from provider_simenv.agents import Farmer, Trader, Transport, Process

Four classes, each parameterised by a 'role' attribute:

  Farmer     role: "producer" | "consumer"
  Trader     role: "wholesaler" | "feed_trader"
  Transport  role: "land_transport" | "sea_transport"
  Process    role: "processor" | "feed_manufacturer"
"""

from .base import SupplyChainAgent
from .farmer import ROLE_CONSUMER, ROLE_PRODUCER, Farmer
from .process import ROLE_FEED_MANUFACTURER, ROLE_PROCESSOR, Process
from .trader import ROLE_FEED_TRADER, ROLE_WHOLESALER, Trader
from .transport import (
    ROLE_LAND_TRANSPORT,
    ROLE_SEA_TRANSPORT,
    Transport,
)

__all__ = [
    "ROLE_CONSUMER",
    "ROLE_FEED_MANUFACTURER",
    "ROLE_FEED_TRADER",
    "ROLE_LAND_TRANSPORT",
    "ROLE_PROCESSOR",
    "ROLE_PRODUCER",
    "ROLE_SEA_TRANSPORT",
    "ROLE_WHOLESALER",
    "Farmer",
    "Process",
    "SupplyChainAgent",
    "Trader",
    "Transport",
]
