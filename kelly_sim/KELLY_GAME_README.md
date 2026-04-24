# Kelly Criterion Coin Flip Game 🪙

An interactive Python simulation that demonstrates the **Kelly Criterion** betting strategy in action through a biased coin flipping game.

## What is the Kelly Criterion?

The Kelly Criterion is a mathematical formula developed by John L. Kelly Jr. in 1956 that determines the optimal bet size to maximize long-term wealth growth while minimizing the risk of ruin.

### Formula

```
f* = (bp - q) / b
```

Where:
- **f*** = optimal fraction of bankroll to bet
- **b** = net odds received (payout ratio)
- **p** = probability of winning
- **q** = probability of losing (1 - p)

### Example (60% Win Rate, Even Money)

```
p = 0.6 (60% chance of winning)
q = 0.4 (40% chance of losing)
b = 1.0 (even money payout)

f* = (1.0 × 0.6 - 0.4) / 1.0
f* = 0.2 or 20%
```

**Result**: You should bet 20% of your bankroll on each flip!

## Game Features

### 🎮 Interactive Modes

1. **Quick Simulation** (100 flips)
   - Fast demonstration of Kelly vs other strategies
   - Great for quick understanding

2. **Long Simulation** (1000 flips)
   - Shows long-term performance
   - Demonstrates law of large numbers

3. **Interactive Mode**
   - Play manually and make your own betting decisions
   - Compare your strategy against Kelly optimal

4. **Compare All Strategies**
   - Side-by-side comparison of 6 different strategies
   - See which performs best

5. **Custom Simulation**
   - Set your own win probability
   - Choose number of flips
   - Experiment with different scenarios

6. **Educational Mode**
   - Detailed explanation of Kelly Criterion
   - Formula breakdown
   - Practical considerations

### 📊 Betting Strategies Compared

The game compares several strategies:

1. **Kelly Criterion** - Optimal mathematical bet (20% for 60% win rate)
2. **Half Kelly** - Conservative approach (10% for 60% win rate)
3. **Quarter Kelly** - Very conservative (5% for 60% win rate)
4. **Fixed 10%** - Always bet 10% regardless of edge
5. **Fixed 25%** - Always bet 25% regardless of edge
6. **All-In (100%)** - Bet everything every time (guaranteed bust eventually)

### 📈 Performance Tracking

Each simulation tracks:
- Final bankroll
- ROI (Return on Investment)
- Win rate percentage
- Peak and low points
- Number of wins/losses
- Bust status

## Installation & Requirements

### Requirements
- Python 3.6 or higher
- No external dependencies (uses only standard library)

### Running the Game

```bash
# Make the script executable
chmod +x kelly_criterion_game.py

# Run the game
python3 kelly_criterion_game.py
```

## How to Use

### Main Menu Options

```
1. Run Quick Simulation (100 flips)    - Fast demo
2. Run Long Simulation (1000 flips)    - Long-term results
3. Interactive Mode (play yourself)    - Manual betting
4. Compare All Strategies              - Compare 6 strategies
5. Custom Simulation                   - Set your own parameters
6. Explain Kelly Criterion             - Educational content
7. Quit                                - Exit the game
```

### Interactive Mode Commands

When playing interactively:
- `k` - Bet the Kelly optimal amount
- `h` - Bet half Kelly (conservative)
- `c` - Enter a custom bet amount
- `q` - Quit interactive mode

## Understanding the Results

### Why Kelly Wins

**Example 100-flip simulation results:**

```
#1 - Kelly Criterion
  Final Bankroll: $12,797.14
  ROI: +12,697.1%

#2 - Half Kelly
  Final Bankroll: $1,004.30
  ROI: +904.3%

#3 - Fixed 25%
  Final Bankroll: $236.24
  ROI: +136.2%

#4 - All-In (100%)
  Final Bankroll: $0.00
  Status: BUSTED! 💀
```

**Key Insights:**
- Kelly maximizes growth rate (highest final bankroll)
- Half Kelly reduces volatility but grows slower
- Fixed percentages don't account for edge
- All-in always busts eventually (even with 60% win rate!)

### Volatility vs Growth Trade-off

- **Full Kelly**: Maximum growth, high volatility
- **Half Kelly**: 75% of growth rate, 50% of volatility
- **Quarter Kelly**: More stable, much slower growth

Many professional gamblers use **Half Kelly** or **Quarter Kelly** for psychological reasons and to account for estimation errors.

## Educational Value

This simulation teaches:

1. **Optimal Bet Sizing** - Why betting too much OR too little hurts returns
2. **Risk Management** - How to avoid ruin while maximizing growth
3. **Law of Large Numbers** - Long-term convergence to expected value
4. **Volatility Management** - Trade-offs between growth and stability
5. **Mathematical Proof** - See the formula in action with real results

## Code Structure

```python
KellyCriterionGame        # Main game engine
├── calculate_kelly_fraction()   # Calculates optimal bet
├── flip_coin()                  # Biased coin simulation
├── calculate_bet_size()         # Strategy-specific betting
└── run_simulation()             # Runs multi-strategy comparison

BettingStrategy           # Tracks individual strategy performance
├── record_result()              # Records bet outcomes
├── is_bust()                    # Checks for bankruptcy
└── get_stats()                  # Calculates performance metrics
```

## Mathematical Background

### Why 20% for 60% Win Rate?

With a 60% win rate and even money (1:1 payout):

```
Expected Value = (0.6 × $1) - (0.4 × $1) = $0.20 per $1 bet
```

You have a 20% edge, so Kelly says bet 20% of bankroll.

### Why Not Bet More?

Betting more than Kelly increases risk of ruin exponentially:
- 30% bet → Higher volatility, slower growth
- 50% bet → Much higher risk of significant drawdown
- 100% bet → Guaranteed bust on any losing streak

### Why Not Bet Less?

Betting less than Kelly:
- Reduces growth rate
- Leaves edge on the table
- Still safe, just slower

## Practical Applications

The Kelly Criterion applies to:
- **Sports Betting** - Optimal stake sizing
- **Stock Trading** - Position sizing
- **Venture Capital** - Portfolio allocation
- **Poker** - Bankroll management
- **Any Positive EV Situation** - Where you have an edge

## Advanced Topics

### Estimation Error

In practice, you rarely know exact probabilities:
- Use conservative estimates
- Many pros use Half Kelly for safety margin
- Overestimating edge is dangerous

### Correlation

Kelly assumes independent bets:
- Correlated bets require adjustments
- Diversification reduces risk

### Psychological Factors

Full Kelly can be psychologically challenging:
- Large swings are normal
- Drawdowns of 30-50% can occur
- Most people prefer fractional Kelly

## License

This is educational software. Feel free to use, modify, and distribute.

## Further Reading

- ["A New Interpretation of Information Rate" by J.L. Kelly Jr. (1956)](https://www.princeton.edu/~wbialek/rome/refs/kelly_56.pdf)
- ["Fortune's Formula" by William Poundstone](https://en.wikipedia.org/wiki/Fortune%27s_Formula)
- [Kelly Criterion on Wikipedia](https://en.wikipedia.org/wiki/Kelly_criterion)

---

**Created**: 2026-01-22
**Author**: Claude (Anthropic AI)
**Purpose**: Educational demonstration of optimal betting strategy
