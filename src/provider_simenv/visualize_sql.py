"""
Price and volume flow visualization for PROVIDER simenv.

Reads form the Melodie SQLiet output database and generates matplotlib PNGs in data/output/.

Output files:
    data/output/price_curves.png - soja + feed price per scenario
    data/output/volume_flow.png - BRA vs USA sourcing volumes per scenario

"""

import os
import sqlite3

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import pandas as pd

matplotlib.use('Agg')

# --------------------
# Config
# --------------------

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "data", "output")
DB_PATH = os.path.join(OUTPUT_DIR, "provider-simenv.sqlite")

# LAbels for each id_scenario
SCENARIO_LABELS = {
    0: "Baseline (no disruption)",
    1: "Mild drought (BRA -15%, costs + 20%)",
    2: "Severe - Brazil drought (KG values)",
}

COLORS = {0: "#2196F3", 1: "#FF9800", 2: "#F44336"} # blue, orange, red

# --------------------
# Load data from SQLite
# --------------------

def _load_table(conn, table):
    """Read a full simulation result table from the SQLite database."""
    return pd.read_sql("SELECT * FROM [" + table + "]", conn)

def load_data():
    """
    Open the SQLite database and return the two tables needed for plotting.
    """
    conn = sqlite3.connect(DB_PATH)
    df_env = _load_table(conn, "Result_Simulator_Environment")
    df_wholesalers = _load_table(conn, "Result_Simulator_Wholesalers")
    conn.close()
    return df_env, df_wholesalers

# --------------------
# Plots
# --------------------

def plot_price_curves(df_env, save_path):
    """
    Two subplots: soja_price and feed_price.
    One line per scenario, colored by drought severity.
    """

    scenarios = sorted(df_env["id_scenario"].unique())

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    fig.suptitle(
        "PROVIDER Simulation -- Price Development under Drought Scenarios",
        fontsize = 13, fontweight="bold",
    )

    for sid in scenarios:
        sub = df_env[df_env["id_scenario"] == sid].sort_values("period")
        label = SCENARIO_LABELS.get(sid, "Scenario " + str(sid))
        color = COLORS.get(sid, "#999999")

        ax1.plot(sub["period"], sub["soja_price"], label=label, color=color, linewidth=2)
        ax2.plot(sub["period"], sub["feed_price"], label=label, color=color, linewidth=2)

    ax1.set_ylabel("Soja Price (EUR/t)", fontsize=10)
    ax1.set_title("Soja Price -- Wholesaler level", fontsize=10)
    ax1.legend(fontsize=9, loc="upper left")
    ax1.yaxis.set_major_formatter(ticker.FormatStrFormatter("%0f EUR"))
    ax1.grid(True, alpha=0.3)

    ax2.set_ylabel("Feed Price (EUR/t)", fontsize=10)
    ax2.set_title("Feed Price -- Feed Trader level", fontsize=10)
    ax2.set_xlabel("Simulation Step (weeks)", fontsize=10)
    ax2.legend(fontsize=9, loc="upper left")
    ax2.yaxis.set_major_formatter(ticker.FormatStrFormatter("%0f EUR"))
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    print("[visualize_sql] price_curves -> " + save_path)
    plt.close()

def plot_volume_flow(df_wholesalers, save_path):
        """
        Stacked area chart showing how much soja wholesalers source from
        BRA vs USA each step. One panel per scenario.

        Data: bra_volume + usa_volume summed across all wholesaler agents per step.
        """
        agg = (
            df_wholesalers
            .groupby(["id_scenario", "period"])[["bra_volume", "usa_volume"]]
            .sum()
            .reset_index()
        )

        scenarios = sorted(agg["id_scenario"].unique())
        n = len(scenarios)

        fig, axes = plt.subplots(n, 1, figsize=(12, 4 * n), sharex=True)
        if n == 1:
            axes = [axes]

        fig.suptitle(
            "PROVIDER Simulation -- Sourcing Volume Flow (BRA vs USA)",
            fontsize=13, fontweight="bold",
        )

        for ax, sid in zip(axes, scenarios):
            sub = agg[agg["id_scenario"] == sid].sort_values("period")
            label = SCENARIO_LABELS.get(sid, "Scenario " + str(sid))

            ax.stackplot(
                sub["period"],
                sub["bra_volume"],
                sub["usa_volume"],
                labels=["BRA (Brazil)", "USA"],
                colors=["#4CAF50", "#2196F3"],
                alpha=0.75,
            )

            ax.set_title(label, fontsize=10)
            ax.set_ylabel("Volume (tonnes)", fontsize=9)
            ax.legend(fontsize=9, loc="upper right")
            ax.yaxis.set_major_formatter(
                ticker.FuncFormatter(lambda x, _: "{:,.0f} t".format(x))
            )
            ax.grid(True, alpha=0.3)

        axes[-1].set_xlabel("Simulation Step (weeks)", fontsize=10)

        plt.tight_layout()
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        print("[visualize_db] volume_flow   -> " + save_path)
        plt.close()


if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        print("[visualize_db] ERROR: database not found at:")
        print("               " + DB_PATH)
        print("  -> Run main.py first to generate simulation output.")
        raise SystemExit(1)

    print("[visualize_db] Loading simulation output from SQLite...")
    df_env, df_wholesalers = load_data()

    n_scenarios = df_env["id_scenario"].nunique()
    print("[visualize_db] " + str(n_scenarios) + " scenario(s): " + str(sorted(df_env["id_scenario"].unique())))

    plot_price_curves(df_env, os.path.join(OUTPUT_DIR, "price_curves.png"))
    plot_volume_flow(df_wholesalers, os.path.join(OUTPUT_DIR, "volume_flow.png"))

    print("[visualize_db] Done.")