# Kelly Criterion Web App 🪙📱

A mobile-friendly, interactive web application demonstrating the Kelly Criterion betting strategy through a coin flipping game. Play it directly in your browser on any device!

## Quick Start

### Option 1: Local Usage (Recommended)

```bash
# Simply open the HTML file in your browser
open kelly_game.html          # macOS
xdg-open kelly_game.html      # Linux
start kelly_game.html         # Windows
```

Or drag and drop `kelly_game.html` into your browser window.

### Option 2: Mobile Phone

**Transfer the file to your phone:**

1. **Via Cloud Storage:**
   - Upload `kelly_game.html` to Dropbox, Google Drive, or iCloud
   - Open the file from your phone's cloud storage app
   - Choose "Open in Browser" or download and open locally

2. **Via Email:**
   - Email `kelly_game.html` to yourself
   - Open the attachment on your phone
   - Save and open in your mobile browser

3. **Via USB/AirDrop:**
   - Transfer file directly to your phone
   - Open with Safari (iOS) or Chrome (Android)

4. **Via Web Server:**
   - See "Hosting Options" below for serving over your local network

## Features

### 🎮 Four Main Tabs

#### 1. **Play** - Interactive Gameplay
- Real-time coin flipping with your money
- Choose from multiple betting strategies:
  - **Kelly (20%)** - Optimal mathematical bet
  - **Half Kelly (10%)** - Conservative approach
  - **Custom** - Bet any amount you want
- Live stats tracking:
  - Current bankroll
  - Number of flips
  - Win rate percentage
  - ROI (Return on Investment)
- Visual performance chart
- Animated coin flip results
- Bust detection and alerts

#### 2. **Simulate** - Strategy Testing
- Customize simulation parameters:
  - Number of flips (10-1000)
  - Win probability (50%-80%)
- Compare multiple strategies automatically
- See performance differences
- Logarithmic chart for better visualization
- Instant results display

#### 3. **Learn** - Educational Content
- Complete Kelly Criterion explanation
- Mathematical formula breakdown
- Example calculations
- Why it works
- Practical considerations
- Professional advice (Half Kelly, Quarter Kelly)
- Beautiful, easy-to-read format

#### 4. **Compare** - Strategy Showdown
- Runs 500-flip comparison
- Tests 6 different strategies:
  1. Kelly Criterion
  2. Half Kelly
  3. Quarter Kelly
  4. Fixed 10%
  5. Fixed 25%
  6. All-In (100%)
- Shows final rankings
- Bar chart visualization
- Demonstrates why All-In always busts

### 📱 Mobile-Optimized Features

- **Responsive Design** - Adapts to any screen size
- **Touch-Friendly** - Large, tappable buttons
- **Fast Loading** - Single file, loads instantly
- **Offline Ready** - No internet required after loading
- **PWA-Ready** - Can be added to home screen
- **No Installation** - Just open and play
- **Portrait Mode** - Optimized for phone screens
- **Smooth Animations** - Native-feeling interactions

### 📊 Interactive Charts

Uses Chart.js for beautiful, responsive visualizations:
- **Line Charts** - Track bankroll growth over time
- **Bar Charts** - Compare final results
- **Logarithmic Scale** - Better view of large differences
- **Touch Gestures** - Zoom and pan on mobile
- **Responsive** - Adapts to screen size

## Technical Details

### Technology Stack

- **HTML5** - Modern, semantic markup
- **CSS3** - Responsive design with flexbox/grid
- **Vanilla JavaScript** - No frameworks required
- **Chart.js** - Interactive charts (loaded via CDN)
- **Single File** - Everything in one HTML file

### Browser Compatibility

Works on all modern browsers:
- ✅ Chrome/Edge (Desktop & Mobile)
- ✅ Safari (macOS & iOS)
- ✅ Firefox (Desktop & Mobile)
- ✅ Samsung Internet
- ✅ Opera

Minimum requirements:
- ES6 JavaScript support
- CSS Grid and Flexbox
- HTML5 Canvas (for charts)

### File Structure

```
kelly_game.html (34KB)
├── HTML Structure
│   ├── Header with title
│   ├── Tab navigation
│   ├── Play interface
│   ├── Simulate controls
│   ├── Learn content
│   └── Compare results
├── Embedded CSS (~200 lines)
│   ├── Mobile-first responsive design
│   ├── Touch-optimized buttons
│   ├── Beautiful color scheme
│   └── Smooth animations
└── Embedded JavaScript (~600 lines)
    ├── Game state management
    ├── Kelly Criterion calculations
    ├── Betting logic
    ├── Chart.js integration
    └── UI interactions
```

## Hosting Options

### Option 1: Python HTTP Server

```bash
# Python 3
python3 -m http.server 8000

# Then access from any device on your network at:
# http://YOUR_IP:8000/kelly_game.html
```

### Option 2: Node.js HTTP Server

```bash
# Install http-server globally
npm install -g http-server

# Run server
http-server -p 8000

# Access at http://YOUR_IP:8000/kelly_game.html
```

### Option 3: Deploy Online

**GitHub Pages (Free):**
```bash
# 1. Push to GitHub
git add kelly_game.html
git commit -m "Add Kelly web app"
git push

# 2. Enable GitHub Pages in repository settings
# 3. Access at: https://yourusername.github.io/Research/kelly_game.html
```

**Netlify/Vercel (Free):**
- Drag and drop `kelly_game.html` to Netlify Drop
- Instant deployment with custom URL
- No configuration needed

### Option 4: Local Network Access

Find your local IP:
```bash
# macOS/Linux
ifconfig | grep "inet "

# Windows
ipconfig

# Then start any HTTP server and access from phone browser
```

## Usage Guide

### Playing the Game

1. **Start on the Play tab**
   - You begin with $100
   - Each flip has a 60% win probability

2. **Choose your betting strategy:**
   - Tap "Bet Kelly" for optimal 20% bets
   - Tap "Bet Half Kelly" for conservative 10% bets
   - Tap "Custom Bet" to choose your own amount

3. **Watch the results:**
   - See animated coin flip (✓ for win, ✗ for loss)
   - Track your bankroll in real-time
   - View performance chart updating live

4. **Try to avoid going bust:**
   - If bankroll hits $0, you're out!
   - Learn why proper bet sizing matters

### Running Simulations

1. **Switch to Simulate tab**
2. **Adjust sliders:**
   - Number of flips (10-1000)
   - Win probability (50%-80%)
3. **Tap "Run Simulation"**
4. **Review results:**
   - See which strategy performed best
   - Study the growth chart
   - Understand the differences

### Comparing Strategies

1. **Switch to Compare tab**
2. **Tap "Compare All Strategies"**
3. **Wait for results (instant)**
4. **Analyze rankings:**
   - Kelly usually wins long-term
   - All-In always busts eventually
   - Half Kelly balances growth and stability

## Educational Value

This app teaches:

1. **Optimal Bet Sizing** - Why 20% is optimal for 60% win rate
2. **Risk of Ruin** - Why betting too much guarantees failure
3. **Growth vs. Safety** - Trade-offs between strategies
4. **Law of Large Numbers** - Long-term convergence
5. **Practical Application** - Real-world betting decisions

### Real-World Applications

The Kelly Criterion applies to:
- **Sports Betting** - Optimal stake sizing
- **Stock Trading** - Position sizing
- **Poker** - Bankroll management
- **Venture Capital** - Portfolio allocation
- **Any Positive EV** - Wherever you have an edge

## Customization

### Change Win Probability

Edit the JavaScript `gameState.winProb` default:
```javascript
let gameState = {
    bankroll: 100,
    history: [100],
    wins: 0,
    losses: 0,
    winProb: 0.6,  // Change this (0.5 to 1.0)
    kellyFraction: 0.2
};
```

### Change Starting Bankroll

Update in `gameState.bankroll` and throughout:
```javascript
let gameState = {
    bankroll: 1000,  // Change starting amount
    history: [1000],
    // ...
};
```

### Modify Color Scheme

Edit CSS variables:
```css
:root {
    --primary: #2E86AB;      /* Main color */
    --secondary: #06A77D;    /* Success color */
    --danger: #C73E1D;       /* Loss color */
    --warning: #F18F01;      /* Warning color */
}
```

## Performance

- **File Size:** 34KB (small and fast)
- **Load Time:** < 1 second on any connection
- **Memory Usage:** < 10MB RAM
- **Battery Impact:** Minimal
- **Offline:** Works without internet (after first load)

## Troubleshooting

### Chart Not Showing

**Issue:** Charts don't display
**Solution:** Ensure internet connection for first load (Chart.js CDN)

**Offline Solution:**
Download Chart.js and update the script tag:
```html
<script src="chart.min.js"></script>
```

### Buttons Not Responsive

**Issue:** Buttons don't work on mobile
**Solution:** Ensure JavaScript is enabled in browser settings

### Layout Issues

**Issue:** Elements overlap or look wrong
**Solution:** Try a different browser or update to latest version

### Simulation Slow

**Issue:** Large simulations (1000 flips) take time
**Solution:** Normal on slower devices, reduce flip count

## Security & Privacy

- ✅ **No Data Collection** - Everything runs locally
- ✅ **No Tracking** - No analytics or cookies
- ✅ **No Ads** - Completely ad-free
- ✅ **No Login** - No account required
- ✅ **Offline Capable** - Works without internet
- ✅ **Open Source** - View and modify source code

## Future Enhancements

Potential additions:
- [ ] Save/load game state (localStorage)
- [ ] Multiple coin biases in same game
- [ ] Sound effects
- [ ] Dark mode toggle
- [ ] Shareable results
- [ ] More strategy presets
- [ ] Historical data export
- [ ] Advanced statistics

## Credits

- **Kelly Criterion Formula:** John L. Kelly Jr. (1956)
- **Chart Library:** Chart.js (chartjs.org)
- **Design:** Mobile-first responsive design
- **Created:** 2026-01-26

## License

This is educational software. Free to use, modify, and distribute.

## Support

Questions or issues? See the main README.md or KELLY_GAME_README.md for more information about the Kelly Criterion and betting strategies.

---

**Enjoy learning about optimal betting strategies! 🎲📈**

Remember: In the real world, always gamble responsibly and never bet more than you can afford to lose!
