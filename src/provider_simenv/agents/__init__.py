"""
agents/__init__.py — Re-exports all agent classes.

Allows model.py to import cleanly:
  from provider_simenv.agents import Farmer, Trader, Transport, Process

Four classes, each parameterised by a 'role' attribute:

  Farmer     role: "bra" | "arg" | "usa" | "eu"
  Trader     role: "wholesaler" | "feed_trader"
  Transport  role: "sa_land" | "sea" | "eu_land"
  Process    role: "processor" | "feed_manufacturer"
"""

from .base import SupplyChainAgent
from .farmer import Farmer, ROLE_PRODUCER, ROLE_CONSUMER
from .trader import Trader, ROLE_WHOLESALER, ROLE_FEED_TRADER
from .transport import Transport, ROLE_SA_SANTOS, ROLE_SA_PARANAGUA, ROLE_SEA_SANTOS, ROLE_SEA_PARANAGUA, ROLE_SEA_ARG, ROLE_SEA_USA, ROLE_EU_RTM, ROLE_EU_HAM
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
    "ROLE_SA_SANTOS",
    "ROLE_SA_PARANAGUA",
    "ROLE_SEA_SANTOS",
    "ROLE_SEA_PARANAGUA",
    "ROLE_SEA_ARG",
    "ROLE_SEA_USA",
    "ROLE_EU_RTM",
    "ROLE_EU_HAM",
    "ROLE_PROCESSOR",
    "ROLE_FEED_MANUFACTURER",
]
