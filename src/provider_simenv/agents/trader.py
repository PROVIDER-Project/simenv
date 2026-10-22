"""Melodie adapter for standalone regional and feed traders."""

from provider_agents.offis_agents import (
    ROLE_FEED_TRADER,
    ROLE_WHOLESALER,
    TraderProviderAgent,
)

from .base import SupplyChainAgent

__all__ = ["ROLE_FEED_TRADER", "ROLE_WHOLESALER", "Trader"]


class Trader(SupplyChainAgent):
    agent_type = TraderProviderAgent

    def _step_input(self):
        name = getattr(self, "list_name", "") or self.origin
        if not name:
            name = next(
                entry.archetype.name for entry in self.model._roster
                if any(agent is self for agent in getattr(
                    self.model, entry.archetype.name,
                ).agents)
            )
        upstream, _ = self._sources(self.model.upstream(name))
        peers = getattr(self.model, name).filter(lambda a: a.active)
        return {**super()._step_input(), "upstream": upstream,
                "peer_count": len(peers)}
