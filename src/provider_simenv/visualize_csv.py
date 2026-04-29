"""
Price development visualization
"""

import os
import pandas as pd
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker


# --- Config ---

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "data" , "output")
ENV_CSV = os.path.join(OUTPUT_DIR, "Result_Simulator_Environment.csv")

# Labels for each id_scenario - keep in sync with SimulatorScenarios.csv
SCENARIO_LABELS = {
    0: "Baseline (no disruption)",
    1: "Mild drought (BRA -15%, costs +20%)",
    2: "Severe - Brazil drought (KG values)",
}

COLORS = {0: "#2196F3", 1: "#FF9800", 2: "#F44336"} # blue, orange, red

# --- Load data ---
def load_environment() -> pd.DataFrame:
    df = pd.read_csv(ENV_CSV)
    return df

# --- Matplotlib png ---
def plot_price_curves(df: pd.DataFrame, save_path: str):
    """
    Two subplots: soja_price (wholesaler) and feed_price (feed trader)
    One line per scenario, colored by drought severity.
    """

    scenarios = sorted(df["id_scenario"].unique())

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize = (12, 8), sharex = True)
    fig.suptitle("PROVIDER Simulation - Price development under Drought Scenarios", fontsize = 13, fontweight = "bold")

    for sid in scenarios:
        sub = df[df["id_scenario"] == sid].sort_values("period")
        label = SCENARIO_LABELS.get(sid, f"Scenario {sid}")
        color = COLORS.get(sid, "#999999")

        ax1.plot(sub["period"], sub["soja_price"], label = label, color = color, linewidth = 2)
        ax2.plot(sub["period"], sub["feed_price"], label = label, color = color, linewidth = 2)

    ax1.set_ylabel("Soja Price (EUR/ton)", fontsize = 10)
    ax1.set_title("Soja Price - Wholesaler", fontsize = 10)
    ax1.legend(fontsize = 9, loc="upper left")
    ax1.yaxis.set_major_formatter(ticker.FormatStrFormatter('%.0f €'))
    ax1.grid(True, alpha = 0.3)

    ax2.set_ylabel("Feed Price (EUR/ton)", fontsize = 10)
    ax2.set_title("Feed Price - Feed Trader", fontsize = 10)
    ax2.set_xlabel("Simulation Step (weeks)", fontsize = 10)
    ax2.legend(fontsize = 9, loc="upper left")
    ax2.yaxis.set_major_formatter(ticker.FormatStrFormatter('%.0f €'))
    ax2.grid(True, alpha = 0.3)

    plt.tight_layout()
    plt.savefig(save_path, dpi = 150, bbox_inches = "tight")
    print(f"[visuaize] PNG saved: {save_path}")
    plt.close()


# --- main ---
if __name__ == "__main__":
    if not os.path.exists(ENV_CSV):
            print(f"[visualize] ERROR: {ENV_CSV} not found")
            print(" -> Run main.py first to generate simulation output.")
            raise SystemExit(1)

    print("[visualize] Loading simulation ouput...")
    df = load_environment()

    n_scenarios = df["id_scenario"].nunique()
    print(f"[visualize] Found {n_scenarios} scenarios: {sorted(df['id_scenario'].unique())}")

    png_path = os.path.join(OUTPUT_DIR, "price_curves_2.png")
    plot_price_curves(df, png_path)

    print("[visualize] Done.")