import os

from Melodie import Config, Simulator
from model import SupplyChainModel
from scenario import SupplyChainScenario

if __name__ == "__main__":
    config = Config(
        project_name="provider-simenv",
        project_root=os.path.dirname(os.path.abspath(__file__)),
        input_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "input"),
        output_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "output"),
    )

    simulator = Simulator(
        config=config,
        scenario_cls=SupplyChainScenario,
        model_cls=SupplyChainModel,
    )
    simulator.run()
    # simulator.run_parallel(core=4)
    # for python >= 3.14+
    # simulator.run_parallel_multithread(core=4)