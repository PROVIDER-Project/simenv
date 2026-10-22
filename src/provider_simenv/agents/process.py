"""Melodie adapter for standalone input-transformation actors."""

from provider_agents.offis_agents import (
    ROLE_FEED_MANUFACTURER,
    ROLE_PROCESSOR,
    ProcessProviderAgent,
)

from .base import SupplyChainAgent

__all__ = ["ROLE_FEED_MANUFACTURER", "ROLE_PROCESSOR", "Process"]


class Process(SupplyChainAgent):
    agent_type = ProcessProviderAgent

    def _step_input(self):
        upstream, _ = self._sources(self.model.upstream(self.list_name))
        peers = getattr(self.model, self.list_name).filter(lambda a: a.active)
        return {**super()._step_input(), "upstream": upstream,
                "peer_count": len(peers)}
