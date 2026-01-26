# Research

A flexible repository for experimental projects, proof-of-concepts, and research work.

## Overview

This repository serves as a workspace for research activities, experimental implementations, and learning projects. It's designed to be adaptable to various types of research and development work.

## Getting Started

### Prerequisites
_To be documented as the project develops_

### Installation
```bash
# Clone the repository
git clone <repository-url>
cd Research

# Setup instructions will be added as the project grows
```

## Project Structure

```
Research/
├── CLAUDE.md                   # AI assistant guidelines and development conventions
├── README.md                   # This file
├── .gitignore                  # Git ignore patterns
├── kelly_criterion_game.py     # Kelly Criterion coin flip simulation
├── kelly_visualization.py      # Visualization tools for Kelly simulations
└── KELLY_GAME_README.md        # Detailed documentation for Kelly game
```

## Projects

### 🪙 Kelly Criterion Coin Flip Game

An interactive Python simulation demonstrating optimal betting strategies using the Kelly Criterion. This educational tool shows how mathematical bet sizing can maximize long-term wealth growth.

**Features:**
- Interactive gameplay modes
- Multiple betting strategy comparisons (Kelly, Half Kelly, Fixed %, All-In)
- Real-time performance tracking and statistics
- Visual charts (with matplotlib)
- Educational explanations of the Kelly formula

**Quick Start:**
```bash
# Play the interactive game
python3 kelly_criterion_game.py

# Generate visualizations (requires matplotlib)
python3 kelly_visualization.py
```

**Learn More:** See [KELLY_GAME_README.md](KELLY_GAME_README.md) for comprehensive documentation.

**What is the Kelly Criterion?**
```
Formula: f* = (bp - q) / b

Example with 60% win rate:
f* = 0.2 or 20% of bankroll per bet
```

This demonstrates why proper bet sizing matters - bet too much and you risk ruin, bet too little and you leave profits on the table.

## Usage

Refer to individual project documentation for specific usage instructions.

## Development

### For AI Assistants
Please refer to [CLAUDE.md](CLAUDE.md) for comprehensive guidelines on:
- Codebase structure and conventions
- Development workflows
- Git practices
- Code modification guidelines

### Contributing
_Contribution guidelines will be added as needed_

## Documentation

- **CLAUDE.md**: Comprehensive guide for AI assistants working with this repository
- Additional documentation will be added as the project grows

## License

_To be specified_

## Contact

_Contact information to be added_

---

**Status**: Initial setup - Repository ready for development

**Last Updated**: 2026-01-22
