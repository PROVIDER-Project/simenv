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

    @property
    def key(self) -> str:
        return f"{self.list_name}:{self.id}"

    def seed_orders(self, links) -> None:
        """Take what was received from each supplier as the baseline and as the last orders."""
        self.baseline_orders = {source.key: quantity for source, quantity in links}
        self.last_orders = dict(self.baseline_orders)

    def _state(self):
        return {name: getattr(self, name) for name in self._implementation.defaults}

    def _effects(self):
        return {slot: self.effective(slot) for slot in self.binding}

    def _step_input(self):
        data = {"state": self._state(), "effects": self._effects()}
        shipped = self.model.shipped_last_tick(self)
        if shipped is not None:
            data["shipped"] = shipped
        orders = self.model.orders_for(self)
        if orders is not None:
            self._step_buyers = {buyer.key: buyer for buyer, _ in orders if buyer.active}
            data["orders"] = [{"key": buyer.key, "quantity": quantity}
                              for buyer, quantity in orders if buyer.active]
        return data

    def step(self):
        data = {"state": self._state()}
        sources = {}
        self._step_sources = {}
        self._step_buyers = {}
        self._spare = 0.0
        if self._implementation.requires_observations(data["state"]):
            data, sources = self._step_context()
        self._apply_result(self._implementation.step(data), sources)

    def _step_context(self):
        data = self._step_input()
        return data, self._step_sources

    def _apply_result(self, result, sources=None):
        for name, value in result.items():
            if name not in ("upstream_updates", "received", "deliveries", "orders"):
                setattr(self, name, value)
        for entry in result.get("received", []):
            self.model.book_delivery((sources or {})[entry["key"]], entry["quantity"], self)
        if "deliveries" in result:
            for entry in result["deliveries"]:
                self.model.book_delivery(self, entry["quantity"], self._step_buyers[entry["key"]])
            self._spare = max(0.0, self.quantity_available - sum(
                entry["quantity"] for entry in result["deliveries"]))
        for entry in result.get("orders", []):
            self.model.place_order(self, (sources or {})[entry["key"]], entry["quantity"])
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
        for source in upstream or []:
            key = source.key
            sources[key] = source
            record = {
                "key": key, "quantity_available": source.quantity_available,
                "unit_price": source.unit_price,
                "delivered": self.model.delivered(source, self),
                "spare": getattr(source, "_spare", 0.0),
            }
            if hasattr(source, "base_yield"):
                record["base_yield"] = source.base_yield
            if isinstance(source, Transport):
                record.update(is_transport=True, capacity=source.capacity,
                              effects=source._effects())
            records.append(record)
        self._step_sources = sources
        return records, sources

    def effective(self, slot: str) -> float:
        """Resolve framework-owned PDL binding; absent bindings are neutral."""
        key = self.binding.get(slot)
        if key is None:
            return 1.0
        environment = cast("SupplyChainEnvironment", self.model.environment)
        return environment.get_effective_value(*key)
