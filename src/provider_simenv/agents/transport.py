"""Melodie graph/state adapter for standalone transport decisions."""

from typing import Any

from provider_agents.offis_agents import (
    ROLE_LAND_TRANSPORT,
    ROLE_SEA_TRANSPORT,
    TransportProviderAgent,
)

from .base import SupplyChainAgent

__all__ = ["ROLE_LAND_TRANSPORT", "ROLE_SEA_TRANSPORT", "Transport"]


class Transport(SupplyChainAgent):
    agent_type = TransportProviderAgent

    def _state(self):
        state = super()._state()
        if hasattr(self, "scenario"):
            state["margin_transport"] = self.scenario.margin_transport
        return state

    def step(self):
        upstream, sources = self._sources(self.model.upstream(self.list_name))
        peers = getattr(self.model, self.list_name).filter(lambda a: a.active)
        routes: list[dict[str, Any]] = [
            {"name": entry.archetype.name, "role": entry.archetype.role,
             "is_transport": entry.archetype.agent_class is Transport,
             "entity_ids": list(entry.entity_ids)}
            for entry in self.model._roster
        ]
        weights = {
            entity: getattr(self.scenario, f"share_{entity}")
            for route in routes for entity in route["entity_ids"]
            if hasattr(self.scenario, f"share_{entity}")
        }
        data = {**self._step_input(), "upstream": upstream,
                "peer_count": len(peers), "list_name": self.list_name,
                "routes": routes, "route_weights": weights,
                "adjacency": {name: list(values) for name, values
                              in self.model._flow_adjacency.items()}}
        self._apply_result(self._implementation.step(data), sources)
