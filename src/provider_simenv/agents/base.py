"""Translate Melodie lifecycle and state into standalone agent contracts."""

from typing import TYPE_CHECKING, Any, ClassVar, cast

from Melodie import Agent

if TYPE_CHECKING:
    from ..environment import SupplyChainEnvironment
    from ..model import SupplyChainModel
    from ..scenario import SupplyChainScenario


class SupplyChainAgent(Agent):
    """Framework adapter; concrete wrappers select a standalone agent type."""

    agent_type: ClassVar[Any]
    model: "SupplyChainModel"
    scenario: "SupplyChainScenario"
    list_name: str

    def setup(self):
        self._implementation = self.agent_type()
        self._apply_result(self._implementation.setup({}))
        self.origin = ""
        self.binding = {}

    def _setup_input(self):
        return self._state()

    def post_setup(self):
        self._apply_result(self._implementation.setup(self._setup_input()))

    def _state(self):
        return {name: getattr(self, name) for name in self._implementation.defaults}

    def _effects(self):
        return {slot: self.effective(slot) for slot in self.binding}

    def _step_input(self):
        return {"state": self._state(), "effects": self._effects()}

    def step(self):
        self._apply_result(self._implementation.step(self._step_input()))

    def _apply_result(self, result, sources=None):
        for name, value in result.items():
            if name != "upstream_updates":
                setattr(self, name, value)
        for update in result.get("upstream_updates", []):
            source = (sources or {})[update["key"]]
            for name, value in update.items():
                if name != "key":
                    setattr(source, name, value)

    def _sources(self, upstream):
        """Return plain source records and a step-local key/object lookup."""
        from .transport import Transport

        records = []
        sources = {}
        for index, source in enumerate(upstream or []):
            key = str(index)
            sources[key] = source
            record = {
                "key": key, "quantity_available": source.quantity_available,
                "unit_price": source.unit_price,
            }
            if hasattr(source, "base_yield"):
                record["base_yield"] = source.base_yield
            if isinstance(source, Transport):
                record.update(is_transport=True, capacity=source.capacity,
                              effects=source._effects())
            records.append(record)
        return records, sources

    def effective(self, slot: str) -> float:
        """Resolve framework-owned PDL binding; absent bindings are neutral."""
        key = self.binding.get(slot)
        if key is None:
            return 1.0
        environment = cast("SupplyChainEnvironment", self.model.environment)
        return environment.get_effective_value(*key)
