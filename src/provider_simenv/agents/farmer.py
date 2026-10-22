"""Melodie adapter for standalone agricultural actors."""

from provider_agents.offis_agents import (
    ROLE_CONSUMER,
    ROLE_PRODUCER,
    FarmerProviderAgent,
)

from .base import SupplyChainAgent

__all__ = ["ROLE_CONSUMER", "ROLE_PRODUCER", "Farmer"]


class Farmer(SupplyChainAgent):
    agent_type = FarmerProviderAgent

    def _setup_input(self):
        return {**super()._setup_input(),
                "farm_size_seed": self.scenario.farm_size_seed,
                "agent_id": self.id}

    def _step_input(self):
        sources = list(self.model.upstream(self.list_name) or ())
        upstream, _ = self._sources(sources)
        for record, source in zip(upstream, sources):
            record["recipient_count"] = self.model.active_recipients(source.list_name)
        return {**super()._step_input(), "upstream": upstream}

    def step(self, drought_severity: float = 0.0):
        super().step()
