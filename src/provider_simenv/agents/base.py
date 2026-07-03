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

        # PDL entity id this agent represents. Set by model.setup() from the roster's entity_ids.
        # "" for synthetic hubs (wholesaler/feed_traders)
        self.origin: str = ""

        # PDL bindings: semantic slot -> (entity, impact_field).
        # Applied by model.setup() from Archetype.params["bindings"] in
        # topology.py (cross-entity slots), plus the entity-driven "capacity" slot.
        self.binding: dict[str, tuple[str, str]] = {}

    def step(self):
        pass

    def effective(self, slot: str) -> float:
        """
        Effective shock multiplier for a semantic binding slot.

        Resolves the slot to its PDL (entity, impact_field) via self.binding and
        reads the current value from the environment. Returns 1.0 (unshocked)
        when the slot is not bound for this role — so agents that don't read a
        given shock, or PDLs that omit the entity, run unaffected rather than
        raising. This is the single home of the absent-key -> 1.0 default.
        """
        key = self.binding.get(slot)
        if key is None:
            return 1.0
        return self.model.environment.get_effective_value(*key)
