"""
Every actor in the chain shares three state variables:
  quantity_available  How much output good is ready this step.
  unit_price          Current asking price per unit.
  active              Whether this agent is still in the market.

All concrete agent classes inherit from SupplyChainAgent.
There are four concrete classes, each handling multiple roles
via a 'role' attribute set at agent initialisation:

  Farmer    role: "sa" | "eu"
  Trader    role: "wholesaler" | "feed_trader"
  Transport role: "sa_land" | "sea" | "eu_land"
  Process   role: "processor" | "feed_manufacturer"
"""

from Melodie import Agent


class SupplyChainAgent(Agent):
    """
    Shared base for every supply chain actor.

    Melodie injects the following before setup() is called:
      self.id           Unique integer per agent (auto-assigned)
      self.scenario     Active SupplyChainScenario instance
      self.environment  Active SupplyChainEnvironment instance
      self.model        Active SupplyChainModel instance

    The 'role' attribute must be set from the agent data table
    (or by the model) before setup() is called, so that each
    concrete class can branch its initialisation accordingly.
    """

    def setup(self):
        """
        Explicitly assigns all shared instance attributes.

        Class-level annotations (active: bool = True) create class
        attributes, not instance attributes — they won't appear in
        agent.__dict__ and Melodie's data collector can't find them.
        Assigning here with self.x = value puts them on the instance.

        Subclasses must call super().setup() as their first line so
        these are always initialised before subclass-specific logic.
        """
        self.quantity_available: float = 0.0
        self.unit_price: float = 0.0
        self.active: bool = True

    def step(self):
        pass
