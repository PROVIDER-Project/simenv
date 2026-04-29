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

class SupplyChainEnvironment(Environment):
    """
    Updated once per simulation step after all agents acted.
    """

    # current price of raw soja
    soja_price: float = 0.0

    # current price of precessed animal feed
    feed_price: float = 0.0

    # global shock intensity for the current step (0.0 = baseline, 1.0 = full shock)
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

    def update_shock_scale(self, period: int):
        """
        update the current global shock intensity for the given period.
        the model interpolates from baseline factor 1.0 to the target scenario
        factor over shock_ramp_steps after shock_onset_setup
        """
        onset = self.scenario.shock_onset_step
        ramp_steps = self.scenario.shock_ramp_steps

        if period < onset:
            self.shock_scale = 0.0
        elif ramp_steps <= 0:
            self.shock_scale = 1.0
        else:
            self.shock_scale = min(1.0, max(0.0, (period - onset) / ramp_steps))

        self.drought_severity = self.shock_scale * (1.0 - self.scenario.farm_capacity_bra)

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
        active_usa = self.model.usa_farmers.filter(lambda f: f.active)
        self.total_soja_supply = (
            sum(f.quantity_available for f in active_bra)
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
            self.model.transport_sa.filter(lambda a: a.active)
            + self.model.sea_transport.filter(lambda a: a.active)
            + self.model.transport_eu.filter(lambda a: a.active)
        )

        if all_transport:
            self.transport_utilisation = sum(
                a.utilisation for a in all_transport
            ) / len(all_transport)
        else:
            self.transport_utilisation = 0.0

