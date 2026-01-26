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
├── kelly_criterion_game.py     # Kelly Criterion coin flip simulation (Python)
├── kelly_visualization.py      # Visualization tools for Kelly simulations (Python)
├── kelly_game.html             # Kelly Criterion web app (mobile-friendly)
├── serve.py                    # Simple HTTP server for web app
├── KELLY_GAME_README.md        # Detailed documentation for Python version
└── WEB_APP_README.md           # Web app documentation and usage guide
```

## Projects

### 🪙 Kelly Criterion Coin Flip Game

An interactive simulation demonstrating optimal betting strategies using the Kelly Criterion. Available in both **web** and **Python** versions!

#### 📱 Web App (Mobile-Friendly)

Play directly in your browser on any device - **perfect for phones!**

**Quick Start:**
```bash
# Option 1: Open directly in browser
open kelly_game.html

# Option 2: Serve on local network (access from phone)
python3 serve.py
# Then visit http://YOUR_IP:8000/kelly_game.html from any device
```

**Features:**
- 🎮 Four interactive tabs: Play, Simulate, Learn, Compare
- 📱 Mobile-optimized responsive design
- 📊 Real-time charts with Chart.js
- ⚡ No installation required - just open and play
- 🔒 Works offline after first load
- 💾 Single 34KB file

**To play on your phone:**
- Transfer `kelly_game.html` to your phone via email, cloud storage, or AirDrop
- Open in Safari (iOS) or Chrome (Android)
- Or host locally and access via your network

**Learn More:** See [WEB_APP_README.md](WEB_APP_README.md) for detailed web app guide.

#### 🐍 Python CLI Version

Full-featured command-line version with advanced simulation capabilities.

**Quick Start:**
```bash
# Play the interactive game
python3 kelly_criterion_game.py

# Generate visualizations (requires matplotlib)
python3 kelly_visualization.py
```

**Features:**
- Interactive gameplay modes
- Multiple betting strategy comparisons (Kelly, Half Kelly, Fixed %, All-In)
- Real-time performance tracking and statistics
- Visual charts with matplotlib
- Educational explanations of the Kelly formula

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

**Status**: Active - Kelly Criterion game available in web and Python versions

**Last Updated**: 2026-01-26
