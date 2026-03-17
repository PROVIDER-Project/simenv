"""
Global supply chain market state.
It tracks the global soja market: current prices, transport availability,
and the active disruption level (drought).

Agents do not modify the environment directely.
The env updates itself each step based on aggregate agent behavior.

Tracked prices mirror the computed unit_price at key chain nodes:
    soja_price: weighted average price from active wholesalers
    feed_price: weighted average price from active feed traders
    total_soja_supply: sum of quantity_available across SA farmers
    transport_utilisation: averae utilisation of all transport agents
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

    # drought severity this step
    # currently, copied from scenario
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
        self.soja_price = self.scenario.initial_soja_price
        self.feed_price = self.scenario.initial_feed_price
        self.drought_severity = self.scenario.drought_severity
        self.total_soja_supply = 0.0
        self.transport_utilisation = 0.0
        self.current_step = 0


    def step(self):
        """
        Aggregate agent outputs into macro indicators
        after all agents have acted in the current step.

        soja_price: quantity-weighted average price across active wholesalers
        feed_price: quantity-weighted average price across active feed traders
        total_soja_supply: total tons produced by active SA farmers
        transport_utilisation: mean utilisation of all transport agents
        """
        self.current_step += 1

        # Soja supply (SA farmer output)
        active_sa = self.model.sa_farmers.filter(lambda f: f.active)
        self.total_soja_supply = sum(f.quantity_available for f in active_sa)

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

