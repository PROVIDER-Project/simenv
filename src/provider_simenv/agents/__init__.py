"""
agents/__init__.py — Re-exports all agent classes.

Allows model.py to import cleanly:
  from provider_simenv.agents import Farmer, Trader, Transport, Process

Four classes, each parameterised by a 'role' attribute:

  Farmer     role: "bra" | "arg" | "usa" | "eu"
  Trader     role: "wholesaler" | "feed_trader"
  Transport  role: "land_transport" | "sea_lane"
  Process    role: "processor" | "feed_manufacturer"
"""

from .base import SupplyChainAgent
from .farmer import Farmer, ROLE_PRODUCER, ROLE_CONSUMER
from .trader import Trader, ROLE_WHOLESALER, ROLE_FEED_TRADER
from .transport import (
    Transport,
    ROLE_LAND_TRANSPORT,
    ROLE_SEA_LANE,
)
from .process import Process, ROLE_PROCESSOR, ROLE_FEED_MANUFACTURER

__all__ = [
    # Base
    "SupplyChainAgent",
    # Concrete agent classes
    "Farmer",
    "Trader",
    "Transport",
    "Process",
    # Role constants — import these to avoid magic strings in model.py
    "ROLE_PRODUCER",
    "ROLE_CONSUMER",
    "ROLE_WHOLESALER",
    "ROLE_FEED_TRADER",
    "ROLE_LAND_TRANSPORT",
    "ROLE_SEA_LANE",
    "ROLE_PROCESSOR",
    "ROLE_FEED_MANUFACTURER",
]
