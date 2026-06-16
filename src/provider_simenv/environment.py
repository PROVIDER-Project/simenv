"""
Global supply chain market state.
It tracks the global soja market: current prices, transport availability,
and the active disruption level (drought).

Agents do not modify the environment directely.
The env updates itself each step based on aggregate agent behavior.

Tracked prices mirror the computed unit_price at key chain nodes:
    soja_price: weighted average price from active wholesalers
    feed_price: weighted average price from active feed traders
    total_soja_supply: sum of quantity_available across BRA + USA farmers
    transport_utilisation: average utilisation of all transport agents
"""
from __future__ import annotations
from typing import TYPE_CHECKING
from Melodie import Environment


from .shock_registry import DROUGHT_KEY
from .event_tracker import EventTracker


class SupplyChainEnvironment(Environment):
    """
    Updated once per simulation step after all agents acted.
    """

    # current price of raw soja
    soja_price: float = 0.0

    # current price of precessed animal feed
    feed_price: float = 0.0

    # global shock intensity
    # Agents should call get_shock_scale(entity, field) instead of reading this directly.
    shock_scale: float = 0.0

    # drought severity this step
    drought_severity: float = 0.0

    # total soja quantity available in the chain this step
    total_soja_supply: float = 0.0

    # average transport capacity utilisation across all transport agents (0.0 ~ 1.0)
    transport_utilisation: float = 0.0

    # step
    current_step: int = 0

    # conditional-event tracker
    # set in Model.run()/run_stepwise() for PDL runs
    _tracker: EventTracker | None = None

    def setup(self):
        """
        Initialise environment state form the scenario parameters.
        """
        self.soja_price = 0.0
        self.feed_price = 0.0
        self.shock_scale = 0.0
        self.drought_severity = 0.0
        self.total_soja_supply = 0.0
        self.transport_utilisation = 0.0
        self.current_step = 0

        # per (entity, field) shock activation scale.
        self.shock_scales: dict[tuple[str, str], float] = {}


    def update_shock_scales(self, period: int):
        """
        update per-parameter shock activation scales for the given day.

        Two modes:
            - Tracker mode (PDL with conditions): EventTracker evaluate conditions and durations at runtime.
            - Static mode (no PDL, fallback): onset/end read from scenario fields
        """
        if self._tracker is not None:
            self._tracker.step(period)
            # seed the key once
            if not self.shock_scales:
                self.shock_scales = {key: 0.0 for key in self._tracker.known_keys()}
            for key in self.shock_scales:
                self.shock_scales[key] = self._tracker.get_shock_scale(*key)
        else:
            for key in self.shock_scales:
                self.shock_scales[key] = 0.0

        self.shock_scale = max(self.shock_scales.values(), default=0.0)

        # Drought severity is defined as brazil_farms supply degradation (DROUGHT_KEY)
        bra_scale = self.shock_scales.get(DROUGHT_KEY, 0.0)
        bra_value = self.get_effective_value(*DROUGHT_KEY)
        self.drought_severity = (bra_scale * (1.0 - bra_value))




    def get_shock_scale(self, entity: str, field: str) -> float:
        """
        Return the current shock actibation scale for a scenario parameter.
        """
        return self.shock_scales.get((entity, field), 0.0)


    def get_effective_value(self, entity: str, field: str) -> float:
        """
        Return the effective value for this step.

        Tracker mode: aggregated from currently active events only.
        No tracker (baseline / non-PDL): unshocked, always 1.0
        """
        if self._tracker is not None:
            return self._tracker.get_param_value(entity, field)
        return 1.0


    def step(self):
        """
        Aggregate agent outputs into macro indicators
        after all agents have acted in the current step.

        soja_price: quantity-weighted average price across active wholesalers
        feed_price: quantity-weighted average price across active feed traders
        total_soja_supply: total tons produced by active BRA + USA farmers
        transport_utilisation: mean utilisation of all transport agents
        """
        self.current_step += 1

        # Soja supply (BRA + USA farmer output)
        active_bra = self.model.bra_farmers.filter(lambda f: f.active)
        active_arg = self.model.arg_farmers.filter(lambda f: f.active)
        active_usa = self.model.usa_farmers.filter(lambda f: f.active)
        self.total_soja_supply = (
            sum(f.quantity_available for f in active_bra)
            + sum(f.quantity_available for f in active_arg)
            + sum(f.quantity_available for f in active_usa)
        )


        # Soja price (wholesaler lvl)
        active_wholesalers = self.model.wholesalers.filter(lambda w: w.active)
        total_w_vol = sum(w.quantity_available for w in active_wholesalers)
        if total_w_vol > 0:
            self.soja_price = (
                sum(w.unit_price * w.quantity_available for w in active_wholesalers)
                / total_w_vol
            )
        else:
            self.soja_price = 0.0

        # Feed price (feed trader lvl)
        active_traders = self.model.feed_traders.filter(lambda t: t.active)
        total_t_vol = sum(t.quantity_available for t in active_traders)
        if total_t_vol > 0:
            self.feed_price = (
                sum(t.unit_price * t.quantity_available for t in active_traders)
                / total_t_vol
            )
        else:
            self.feed_price = 0.0

        # Transport util
        all_transport = (
            self.model.transport_sa_santos.filter(lambda a: a.active)
            + self.model.transport_sa_paranagua.filter(lambda a: a.active)
            + self.model.sea_lane_santos.filter(lambda a: a.active)
            + self.model.sea_lane_paranagua.filter(lambda a: a.active)
            + self.model.sea_lane_arg.filter(lambda a: a.active)
            + self.model.sea_lane_usa.filter(lambda a: a.active)
            + self.model.transport_eu_rtm.filter(lambda a: a.active)
            + self.model.transport_eu_ham.filter(lambda a: a.active)
        )

        if all_transport:
            self.transport_utilisation = sum(
                a.utilisation for a in all_transport
            ) / len(all_transport)
        else:
            self.transport_utilisation = 0.0

