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
        upstream, _ = self._sources(self.model.upstream(self.list_name))
        count = sum(
            len(getattr(self.model, entry.archetype.name).filter(
                lambda consumer: consumer.active,
            ))
            for entry in self.model._roster
            if entry.archetype.role == ROLE_CONSUMER
        )
        return {**super()._step_input(), "upstream": upstream,
                "consumer_count": count}

    def step(self, drought_severity: float = 0.0):
        super().step()
