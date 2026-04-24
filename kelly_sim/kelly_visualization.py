#!/usr/bin/env python3
"""
Kelly Criterion Visualization
==============================
Creates visual charts comparing different betting strategies over time.

Requires: matplotlib
Install: pip install matplotlib
"""

import sys

try:
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker
except ImportError:
    print("Error: matplotlib is required for visualization.")
    print("Install with: pip install matplotlib")
    sys.exit(1)

from kelly_criterion_game import KellyCriterionGame, BettingStrategy
import random


def create_performance_chart(results: dict, num_flips: int, win_prob: float):
    """
    Create a line chart showing bankroll growth over time for each strategy.

    Args:
        results: Dictionary of BettingStrategy objects
        num_flips: Number of flips simulated
        win_prob: Win probability used
    """
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))
    fig.suptitle(f'Kelly Criterion Demonstration: {num_flips} Flips at {win_prob*100:.0f}% Win Rate',
                 fontsize=16, fontweight='bold')

    # Color scheme
    colors = {
        'Kelly Criterion': '#2E86AB',      # Blue
        'Half Kelly': '#06A77D',            # Green
        'Quarter Kelly': '#A23B72',         # Purple
        'Fixed 10%': '#F18F01',             # Orange
        'Fixed 25%': '#C73E1D',             # Red
        'All-In (100%)': '#6C757D'          # Gray
    }

    # Plot 1: Linear scale
    ax1.set_title('Bankroll Growth Over Time (Linear Scale)', fontsize=12, pad=10)
    ax1.set_xlabel('Flip Number', fontsize=10)
    ax1.set_ylabel('Bankroll ($)', fontsize=10)
    ax1.grid(True, alpha=0.3, linestyle='--')

    # Plot 2: Logarithmic scale
    ax2.set_title('Bankroll Growth Over Time (Logarithmic Scale)', fontsize=12, pad=10)
    ax2.set_xlabel('Flip Number', fontsize=10)
    ax2.set_ylabel('Bankroll ($, log scale)', fontsize=10)
    ax2.set_yscale('log')
    ax2.grid(True, alpha=0.3, linestyle='--')

    # Plot each strategy
    for strategy_name, strategy in results.items():
        color = colors.get(strategy.name, '#000000')
        flips = range(len(strategy.history))

        # Linear plot
        line1, = ax1.plot(flips, strategy.history, label=strategy.name,
                          color=color, linewidth=2, alpha=0.8)

        # Add final value annotation
        if len(strategy.history) > 0:
            final_value = strategy.history[-1]
            if final_value > 0:
                ax1.annotate(f'${final_value:.2f}',
                            xy=(len(strategy.history)-1, final_value),
                            xytext=(5, 0), textcoords='offset points',
                            fontsize=8, color=color, fontweight='bold')

        # Log plot
        # Replace zeros with small value for log scale
        history_log = [max(h, 0.01) for h in strategy.history]
        line2, = ax2.plot(flips, history_log, label=strategy.name,
                          color=color, linewidth=2, alpha=0.8)

        # Mark bust point
        if strategy.is_bust():
            bust_flip = next((i for i, v in enumerate(strategy.history) if v <= 0.01), len(strategy.history))
            ax1.scatter([bust_flip], [0], color=color, s=100, marker='X',
                       zorder=5, edgecolors='black', linewidths=1.5)
            ax2.scatter([bust_flip], [0.01], color=color, s=100, marker='X',
                       zorder=5, edgecolors='black', linewidths=1.5)

    # Add starting bankroll reference line
    ax1.axhline(y=100, color='black', linestyle=':', linewidth=1, alpha=0.5, label='Starting Bankroll')
    ax2.axhline(y=100, color='black', linestyle=':', linewidth=1, alpha=0.5, label='Starting Bankroll')

    # Format y-axis for linear plot
    ax1.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f'${x:,.0f}'))

    # Format y-axis for log plot
    ax2.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f'${x:,.0f}'))

    # Legends
    ax1.legend(loc='upper left', fontsize=9, framealpha=0.9)
    ax2.legend(loc='upper left', fontsize=9, framealpha=0.9)

    plt.tight_layout()
    return fig


def create_comparison_bar_chart(results: dict):
    """
    Create a bar chart comparing final bankrolls.

    Args:
        results: Dictionary of BettingStrategy objects
    """
    fig, ax = plt.subplots(figsize=(12, 6))
    fig.suptitle('Final Bankroll Comparison', fontsize=14, fontweight='bold')

    # Prepare data
    strategies = []
    bankrolls = []
    colors_list = []

    colors = {
        'Kelly Criterion': '#2E86AB',
        'Half Kelly': '#06A77D',
        'Quarter Kelly': '#A23B72',
        'Fixed 10%': '#F18F01',
        'Fixed 25%': '#C73E1D',
        'All-In (100%)': '#6C757D'
    }

    # Sort by final bankroll
    sorted_results = sorted(results.items(), key=lambda x: x[1].bankroll, reverse=True)

    for _, strategy in sorted_results:
        strategies.append(strategy.name)
        bankrolls.append(max(strategy.bankroll, 0))
        colors_list.append(colors.get(strategy.name, '#000000'))

    # Create bars
    bars = ax.bar(strategies, bankrolls, color=colors_list, alpha=0.8, edgecolor='black', linewidth=1.5)

    # Add value labels on bars
    for i, (bar, value) in enumerate(zip(bars, bankrolls)):
        height = bar.get_height()
        if value > 0:
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'${value:,.2f}',
                   ha='center', va='bottom', fontsize=10, fontweight='bold')
        else:
            ax.text(bar.get_x() + bar.get_width()/2., 10,
                   'BUST',
                   ha='center', va='bottom', fontsize=10, fontweight='bold', color='red')

    # Formatting
    ax.set_ylabel('Final Bankroll ($)', fontsize=11)
    ax.set_xlabel('Strategy', fontsize=11)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f'${x:,.0f}'))
    ax.axhline(y=100, color='black', linestyle='--', linewidth=1, alpha=0.5, label='Starting Bankroll ($100)')
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    ax.legend()

    plt.xticks(rotation=15, ha='right')
    plt.tight_layout()
    return fig


def create_roi_chart(results: dict):
    """
    Create a bar chart showing ROI for each strategy.

    Args:
        results: Dictionary of BettingStrategy objects
    """
    fig, ax = plt.subplots(figsize=(12, 6))
    fig.suptitle('Return on Investment (ROI) Comparison', fontsize=14, fontweight='bold')

    # Prepare data
    strategies = []
    rois = []
    colors_list = []

    colors = {
        'Kelly Criterion': '#2E86AB',
        'Half Kelly': '#06A77D',
        'Quarter Kelly': '#A23B72',
        'Fixed 10%': '#F18F01',
        'Fixed 25%': '#C73E1D',
        'All-In (100%)': '#6C757D'
    }

    # Sort by ROI
    sorted_results = sorted(results.items(), key=lambda x: x[1].get_stats()['roi'], reverse=True)

    for _, strategy in sorted_results:
        strategies.append(strategy.name)
        roi = strategy.get_stats()['roi']
        rois.append(roi)
        colors_list.append(colors.get(strategy.name, '#000000'))

    # Create bars
    bars = ax.bar(strategies, rois, color=colors_list, alpha=0.8, edgecolor='black', linewidth=1.5)

    # Add value labels on bars
    for bar, value in zip(bars, rois):
        height = bar.get_height()
        label_y = height if height > 0 else height - 50
        va = 'bottom' if height > 0 else 'top'
        ax.text(bar.get_x() + bar.get_width()/2., label_y,
               f'{value:+.1f}%',
               ha='center', va=va, fontsize=10, fontweight='bold')

    # Formatting
    ax.set_ylabel('ROI (%)', fontsize=11)
    ax.set_xlabel('Strategy', fontsize=11)
    ax.axhline(y=0, color='black', linestyle='-', linewidth=1.5, alpha=0.7)
    ax.grid(axis='y', alpha=0.3, linestyle='--')

    plt.xticks(rotation=15, ha='right')
    plt.tight_layout()
    return fig


def run_visualization(num_flips: int = 500, win_prob: float = 0.6):
    """
    Run simulation and create all visualizations.

    Args:
        num_flips: Number of flips to simulate
        win_prob: Probability of winning each flip
    """
    print(f"\nRunning simulation: {num_flips} flips at {win_prob*100:.0f}% win rate...")

    # Create game and run simulation
    game = KellyCriterionGame(win_probability=win_prob)
    game.print_game_info()

    strategies = ["kelly", "half_kelly", "quarter_kelly", "fixed_10", "fixed_25", "all_in"]
    results = game.run_simulation(num_flips, strategies)

    # Print results
    game.print_simulation_results(results)

    print("\nGenerating visualizations...")

    # Create charts
    fig1 = create_performance_chart(results, num_flips, win_prob)
    fig2 = create_comparison_bar_chart(results)
    fig3 = create_roi_chart(results)

    # Save figures
    fig1.savefig('kelly_performance_over_time.png', dpi=300, bbox_inches='tight')
    print("  ✓ Saved: kelly_performance_over_time.png")

    fig2.savefig('kelly_final_bankroll.png', dpi=300, bbox_inches='tight')
    print("  ✓ Saved: kelly_final_bankroll.png")

    fig3.savefig('kelly_roi_comparison.png', dpi=300, bbox_inches='tight')
    print("  ✓ Saved: kelly_roi_comparison.png")

    print("\nDisplaying charts... (close windows to exit)")
    plt.show()


def main():
    """Main entry point."""
    print("="*70)
    print("KELLY CRITERION VISUALIZATION")
    print("="*70)

    if len(sys.argv) > 1:
        try:
            num_flips = int(sys.argv[1])
        except ValueError:
            print("Invalid number of flips. Using default (500).")
            num_flips = 500
    else:
        num_flips = 500

    if len(sys.argv) > 2:
        try:
            win_prob = float(sys.argv[2])
            if not 0.5 <= win_prob <= 1.0:
                print("Win probability must be between 0.5 and 1.0. Using default (0.6).")
                win_prob = 0.6
        except ValueError:
            print("Invalid win probability. Using default (0.6).")
            win_prob = 0.6
    else:
        win_prob = 0.6

    # Optional: Set random seed for reproducibility
    # random.seed(42)

    run_visualization(num_flips, win_prob)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nVisualization interrupted.")
        sys.exit(0)
