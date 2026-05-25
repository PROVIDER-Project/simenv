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

from Melodie import Environment


# maps scenario param name -> (onset_field, end_field) on SupplyChainScenario
_PARAM_TIMING_FIELDS: list[tuple[str, str, str]] = [
    ("farm_capacity_bra", "shock_onset_farm_bra", "shock_end_farm_bra"),
    ("farm_capacity_arg", "shock_onset_farm_arg", "shock_end_farm_arg"),
    ("port_capacity_santos", "shock_onset_port_santos", "shock_end_port_santos"),
    ("port_capacity_paranagua", "shock_onset_port_paranagua", "shock_end_port_paranagua"),
    ("port_capacity_rotterdam", "shock_onset_port_rotterdam", "shock_end_port_rotterdam"),
    ("port_capacity_hamburg", "shock_onset_port_hamburg", "shock_end_port_hamburg"),
    ("fertilizer_price_factor", "shock_onset_fertilizer", "shock_end_fertilizer"),
    ("energy_price_factor", "shock_onset_energy", "shock_end_energy"),
    ("oil_mill_capacity", "shock_onset_oil_mill", "shock_end_oil_mill"),
    ("feed_mill_capacity", "shock_onset_feed_mill", "shock_end_feed_mill"),
]


class SupplyChainEnvironment(Environment):
    """
    Updated once per simulation step after all agents acted.
    """

    # current price of raw soja
    soja_price: float = 0.0

    # current price of precessed animal feed
    feed_price: float = 0.0

    # global shock intensity
    # Agents should call get_shock_scale(param) instead of reading this directly.
    shock_scale: float = 0.0

    # drought severity this step
    drought_severity: float = 0.0

    # total soja quantity available in the chain this step
    total_soja_supply: float = 0.0

    # average transport capacity utilisation across all transport agents (0.0 ~ 1.0)
    transport_utilisation: float = 0.0

    # step
    current_step: int = 0

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

        # per-parameter shock activation scale
        self.shock_scales: dict[str, float] = {
            param: 0.0 for param, _, _ in _PARAM_TIMING_FIELDS
        }

    def update_shock_scales(self, period: int):
        """
        update per-parameter shock activation scales for the given day.

        Each parameter has its own onset and end day read from the scenario.
        A parameter's scale is 1.0 (fully active) when onset <= period < end,
        and 0.0 (inactive) otherwise. With shock_ramp_steps = 0 (PDL default)
        the transition is instantaneous.
        """
        for param, onset_field, end_field in _PARAM_TIMING_FIELDS:
            onset = getattr(self.scenario, onset_field)
            end = getattr(self.scenario, end_field)
            value = getattr(self.scenario, param)
            has_shock = value != 1.0
            self.shock_scales[param] = (1.0 if has_shock and onset <= period < end else 0.0)

        self.shock_scale = max(self.shock_scales.values(), default=0.0)
        self.drought_severity = (
            self.shock_scales["farm_capacity_bra"] * (1.0 - self.scenario.farm_capacity_bra)
        )


    def get_shock_scale(self, param: str) -> float:
        """
        Return the current shock actibation scale for a scenario parameter.
        """
        return self.shock_scales.get(param, 0.0)

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

