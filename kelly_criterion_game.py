#!/usr/bin/env python3
"""
Kelly Criterion Coin Flip Game
================================
An interactive simulation demonstrating the Kelly Criterion betting strategy.

The Kelly Criterion is a formula that determines the optimal bet size to maximize
long-term wealth growth. This game shows it in action with a biased coin.

Formula: f* = (bp - q) / b
where:
    f* = fraction of bankroll to bet
    b = net odds received on the bet
    p = probability of winning
    q = probability of losing (1 - p)
"""

import random
import sys
from typing import List, Tuple, Dict
from dataclasses import dataclass, field


@dataclass
class BettingStrategy:
    """Represents a betting strategy with its performance metrics."""
    name: str
    bankroll: float = 100.0
    history: List[float] = field(default_factory=list)
    wins: int = 0
    losses: int = 0

    def record_result(self, new_bankroll: float, won: bool):
        """Record the result of a bet."""
        self.bankroll = new_bankroll
        self.history.append(new_bankroll)
        if won:
            self.wins += 1
        else:
            self.losses += 1

    def is_bust(self) -> bool:
        """Check if the strategy has gone bust."""
        return self.bankroll <= 0.01

    def get_stats(self) -> Dict[str, float]:
        """Get performance statistics."""
        total_bets = self.wins + self.losses
        win_rate = (self.wins / total_bets * 100) if total_bets > 0 else 0

        return {
            'final_bankroll': self.bankroll,
            'total_bets': total_bets,
            'wins': self.wins,
            'losses': self.losses,
            'win_rate': win_rate,
            'roi': ((self.bankroll - 100) / 100 * 100) if self.bankroll > 0 else -100
        }


class KellyCriterionGame:
    """Main game class for Kelly Criterion demonstration."""

    def __init__(self, win_probability: float = 0.6, payout_ratio: float = 1.0):
        """
        Initialize the game.

        Args:
            win_probability: Probability of winning each flip (default 0.6 = 60%)
            payout_ratio: Payout ratio (default 1.0 = even money, win $1 for every $1 bet)
        """
        self.win_prob = win_probability
        self.payout_ratio = payout_ratio
        self.kelly_fraction = self.calculate_kelly_fraction()

    def calculate_kelly_fraction(self) -> float:
        """
        Calculate the optimal Kelly Criterion bet fraction.

        Formula: f* = (bp - q) / b
        """
        b = self.payout_ratio  # Net odds
        p = self.win_prob      # Probability of winning
        q = 1 - p              # Probability of losing

        kelly = (b * p - q) / b
        return max(0, kelly)  # Can't bet negative amounts

    def flip_coin(self) -> bool:
        """Simulate a biased coin flip."""
        return random.random() < self.win_prob

    def calculate_bet_size(self, strategy_type: str, bankroll: float) -> float:
        """
        Calculate bet size based on strategy type.

        Args:
            strategy_type: Type of betting strategy
            bankroll: Current bankroll

        Returns:
            Bet size in dollars
        """
        if bankroll <= 0:
            return 0

        if strategy_type == "kelly":
            return bankroll * self.kelly_fraction
        elif strategy_type == "half_kelly":
            return bankroll * (self.kelly_fraction / 2)
        elif strategy_type == "quarter_kelly":
            return bankroll * (self.kelly_fraction / 4)
        elif strategy_type == "fixed_10":
            return min(bankroll * 0.10, bankroll)
        elif strategy_type == "fixed_25":
            return min(bankroll * 0.25, bankroll)
        elif strategy_type == "all_in":
            return bankroll
        else:
            return 0

    def play_round(self, strategy: BettingStrategy, strategy_type: str) -> Tuple[bool, float, float]:
        """
        Play a single round for a strategy.

        Returns:
            (won, bet_size, new_bankroll)
        """
        if strategy.is_bust():
            return False, 0, 0

        bet_size = self.calculate_bet_size(strategy_type, strategy.bankroll)
        won = self.flip_coin()

        if won:
            new_bankroll = strategy.bankroll + (bet_size * self.payout_ratio)
        else:
            new_bankroll = strategy.bankroll - bet_size

        strategy.record_result(new_bankroll, won)
        return won, bet_size, new_bankroll

    def run_simulation(self, num_flips: int = 100, strategies: List[str] = None) -> Dict[str, BettingStrategy]:
        """
        Run a simulation comparing different betting strategies.

        Args:
            num_flips: Number of coin flips to simulate
            strategies: List of strategy types to compare

        Returns:
            Dictionary of strategy results
        """
        if strategies is None:
            strategies = ["kelly", "half_kelly", "fixed_25", "all_in"]

        # Initialize strategies
        strategy_objects = {
            name: BettingStrategy(name=self._format_strategy_name(name))
            for name in strategies
        }

        # Run simulation
        for flip_num in range(num_flips):
            for strategy_type, strategy_obj in strategy_objects.items():
                if not strategy_obj.is_bust():
                    self.play_round(strategy_obj, strategy_type)

        return strategy_objects

    def _format_strategy_name(self, strategy_type: str) -> str:
        """Format strategy type for display."""
        names = {
            "kelly": "Kelly Criterion",
            "half_kelly": "Half Kelly",
            "quarter_kelly": "Quarter Kelly",
            "fixed_10": "Fixed 10%",
            "fixed_25": "Fixed 25%",
            "all_in": "All-In (100%)"
        }
        return names.get(strategy_type, strategy_type)

    def print_game_info(self):
        """Print game information and Kelly calculation."""
        print("\n" + "="*70)
        print("KELLY CRITERION COIN FLIP GAME")
        print("="*70)
        print(f"\nGame Parameters:")
        print(f"  Win Probability: {self.win_prob * 100:.1f}%")
        print(f"  Loss Probability: {(1 - self.win_prob) * 100:.1f}%")
        print(f"  Payout Ratio: {self.payout_ratio}:1 (even money)")
        print(f"\nKelly Criterion Calculation:")
        print(f"  Formula: f* = (bp - q) / b")
        print(f"  f* = ({self.payout_ratio} × {self.win_prob} - {1-self.win_prob}) / {self.payout_ratio}")
        print(f"  f* = {self.kelly_fraction:.3f} or {self.kelly_fraction * 100:.1f}%")
        print(f"\n  → Optimal bet size: {self.kelly_fraction * 100:.1f}% of your bankroll")
        print("="*70)

    def print_simulation_results(self, results: Dict[str, BettingStrategy]):
        """Print detailed simulation results."""
        print("\n" + "="*70)
        print("SIMULATION RESULTS")
        print("="*70)

        # Sort by final bankroll
        sorted_results = sorted(
            results.items(),
            key=lambda x: x[1].bankroll,
            reverse=True
        )

        for rank, (strategy_type, strategy) in enumerate(sorted_results, 1):
            stats = strategy.get_stats()
            print(f"\n#{rank} - {strategy.name}")
            print(f"  Final Bankroll: ${stats['final_bankroll']:.2f}")
            print(f"  ROI: {stats['roi']:+.1f}%")
            print(f"  Win Rate: {stats['win_rate']:.1f}% ({stats['wins']}/{stats['total_bets']} wins)")

            if strategy.is_bust():
                print(f"  Status: BUSTED! 💀")

            # Show growth trajectory
            if len(strategy.history) > 0:
                max_bankroll = max(strategy.history)
                min_bankroll = min(strategy.history)
                print(f"  Peak: ${max_bankroll:.2f} | Low: ${min_bankroll:.2f}")

        print("\n" + "="*70)


def print_menu():
    """Print the main menu."""
    print("\n" + "="*70)
    print("MAIN MENU")
    print("="*70)
    print("1. Run Quick Simulation (100 flips)")
    print("2. Run Long Simulation (1000 flips)")
    print("3. Interactive Mode (play yourself)")
    print("4. Compare All Strategies")
    print("5. Custom Simulation")
    print("6. Explain Kelly Criterion")
    print("7. Quit")
    print("="*70)


def explain_kelly_criterion():
    """Print detailed explanation of Kelly Criterion."""
    print("\n" + "="*70)
    print("UNDERSTANDING THE KELLY CRITERION")
    print("="*70)
    print("""
The Kelly Criterion is a mathematical formula that tells you the optimal
fraction of your bankroll to bet to maximize long-term wealth growth.

FORMULA: f* = (bp - q) / b

Where:
  f* = optimal fraction of bankroll to bet
  b  = net odds received (payout ratio)
  p  = probability of winning
  q  = probability of losing (1 - p)

EXAMPLE (this game):
  - You have a 60% chance of winning (p = 0.6)
  - You have a 40% chance of losing (q = 0.4)
  - Even money payout (b = 1.0)

  f* = (1.0 × 0.6 - 0.4) / 1.0
  f* = (0.6 - 0.4) / 1.0
  f* = 0.2 or 20%

  → You should bet 20% of your bankroll each time!

WHY IT WORKS:
  ✓ Betting too much: You risk going bust even with an advantage
  ✓ Betting too little: You don't capitalize on your edge
  ✓ Kelly betting: Optimal growth without excessive risk

PRACTICAL CONSIDERATIONS:
  - Many professionals use "fractional Kelly" (e.g., Half Kelly = f*/2)
  - This reduces volatility at the cost of slower growth
  - Full Kelly can be psychologically difficult due to swings

Try the simulation to see it in action!
""")
    print("="*70)


def interactive_mode(game: KellyCriterionGame):
    """Run interactive mode where user makes betting decisions."""
    print("\n" + "="*70)
    print("INTERACTIVE MODE")
    print("="*70)
    print(f"\nOptimal Kelly bet: {game.kelly_fraction * 100:.1f}% of bankroll")
    print("Starting bankroll: $100.00\n")

    bankroll = 100.0
    flip_count = 0

    while bankroll > 0:
        print(f"\nFlip #{flip_count + 1} | Bankroll: ${bankroll:.2f}")
        print("How much do you want to bet?")
        print(f"  [k] Kelly optimal ({game.kelly_fraction * 100:.1f}% = ${bankroll * game.kelly_fraction:.2f})")
        print(f"  [h] Half Kelly ({game.kelly_fraction * 50:.1f}% = ${bankroll * game.kelly_fraction / 2:.2f})")
        print(f"  [c] Custom amount")
        print(f"  [q] Quit interactive mode")

        choice = input("\nYour choice: ").strip().lower()

        if choice == 'q':
            break
        elif choice == 'k':
            bet = bankroll * game.kelly_fraction
        elif choice == 'h':
            bet = bankroll * game.kelly_fraction / 2
        elif choice == 'c':
            try:
                bet = float(input(f"Enter bet amount ($0-${bankroll:.2f}): $"))
                if bet < 0 or bet > bankroll:
                    print("Invalid bet amount!")
                    continue
            except ValueError:
                print("Invalid input!")
                continue
        else:
            print("Invalid choice!")
            continue

        # Flip the coin
        won = game.flip_coin()
        flip_count += 1

        if won:
            profit = bet * game.payout_ratio
            bankroll += profit
            print(f"\n✓ WIN! You won ${profit:.2f}")
        else:
            bankroll -= bet
            print(f"\n✗ LOSS! You lost ${bet:.2f}")

        print(f"New bankroll: ${bankroll:.2f}")

        if bankroll <= 0:
            print("\n💀 You went bust!")
            break

    roi = ((bankroll - 100) / 100 * 100)
    print(f"\n{'='*70}")
    print(f"Game Over! Final Results:")
    print(f"  Flips: {flip_count}")
    print(f"  Final Bankroll: ${bankroll:.2f}")
    print(f"  ROI: {roi:+.1f}%")
    print(f"{'='*70}")


def custom_simulation():
    """Run a custom simulation with user-defined parameters."""
    print("\n" + "="*70)
    print("CUSTOM SIMULATION")
    print("="*70)

    try:
        win_prob = float(input("\nWin probability (0.5-1.0, default 0.6): ") or "0.6")
        if not 0.5 <= win_prob <= 1.0:
            print("Using default 0.6")
            win_prob = 0.6

        num_flips = int(input("Number of flips (default 100): ") or "100")
        if num_flips < 1:
            num_flips = 100

        game = KellyCriterionGame(win_probability=win_prob)
        game.print_game_info()

        print(f"\nRunning simulation with {num_flips} flips...")
        results = game.run_simulation(num_flips)
        game.print_simulation_results(results)

    except ValueError:
        print("Invalid input! Using defaults.")
        custom_simulation()


def main():
    """Main game loop."""
    # Seed for reproducibility (comment out for true randomness)
    # random.seed(42)

    game = KellyCriterionGame(win_probability=0.6, payout_ratio=1.0)

    print("\n🪙  Welcome to the Kelly Criterion Coin Flip Game! 🪙")
    game.print_game_info()

    while True:
        print_menu()
        choice = input("\nEnter your choice (1-7): ").strip()

        if choice == '1':
            print("\nRunning quick simulation (100 flips)...")
            results = game.run_simulation(100)
            game.print_simulation_results(results)

        elif choice == '2':
            print("\nRunning long simulation (1000 flips)...")
            results = game.run_simulation(1000)
            game.print_simulation_results(results)

        elif choice == '3':
            interactive_mode(game)

        elif choice == '4':
            print("\nComparing ALL strategies (500 flips)...")
            strategies = ["kelly", "half_kelly", "quarter_kelly", "fixed_10", "fixed_25", "all_in"]
            results = game.run_simulation(500, strategies)
            game.print_simulation_results(results)

        elif choice == '5':
            custom_simulation()

        elif choice == '6':
            explain_kelly_criterion()

        elif choice == '7':
            print("\nThanks for playing! Remember: bet the Kelly fraction! 📈")
            sys.exit(0)

        else:
            print("\n❌ Invalid choice! Please enter 1-7.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nGame interrupted. Goodbye!")
        sys.exit(0)
