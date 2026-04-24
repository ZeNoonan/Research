# GitHub Pages Setup Guide

This guide will help you deploy the Kelly Criterion game to GitHub Pages so you can play it from any device with a simple URL.

## Repository Layout

The web app lives in the `kelly_sim/` folder. A lightweight `index.html` at the repository root redirects to `kelly_sim/kelly_game.html`, so the GitHub Pages URL below works out of the box without any extra configuration.

## Quick Setup (5 minutes)

### Step 1: Merge to Main Branch

If your changes are on a feature branch (for example, `claude/...`), merge them into `main` first:

1. Go to your GitHub repository: https://github.com/ZeNoonan/Research
2. Open the **"Pull requests"** tab and click **"New pull request"**
3. Set the base branch to `main` and the compare branch to your feature branch
4. Create and merge the pull request

**Note:** If `main` branch doesn't exist, GitHub will create it automatically when you merge.

### Step 2: Enable GitHub Pages

1. In your repository, click **"Settings"** (top right)
2. In the left sidebar, click **"Pages"** (under "Code and automation")
3. Under **"Source"**, select:
   - **Branch**: `main` (or `master`)
   - **Folder**: `/ (root)`
4. Click **"Save"**

### Step 3: Wait for Deployment

- GitHub will automatically deploy your site
- This usually takes 1-3 minutes
- You'll see a message: "Your site is live at https://zenoonan.github.io/Research/"

### Step 4: Access Your Game!

Once deployed, visit:
```
https://zenoonan.github.io/Research/
```

The root `index.html` redirects to the game, or you can go directly to:
```
https://zenoonan.github.io/Research/kelly_sim/kelly_game.html
```

---

## Troubleshooting

### "GitHub Pages is not available"
- Make sure your repository is public (GitHub Pages is free for public repos)
- If private, you need GitHub Pro for GitHub Pages

### "404 - Page not found"
- Wait a few more minutes for deployment to complete
- Check that the root `index.html` and `kelly_sim/kelly_game.html` are committed
- Refresh the GitHub Pages settings page to see deployment status

### "Site not updating"
- GitHub Pages caching can take 5-10 minutes
- Try clearing your browser cache
- Add `?v=1` to the URL to force reload: `https://zenoonan.github.io/Research/?v=1`

### Custom Domain (Optional)
If you want a custom domain like `kelly.yourdomain.com`:
1. Add a `CNAME` file with your domain
2. Configure DNS settings with your domain provider
3. Update GitHub Pages settings with your custom domain

---

## Files Included

Your repository now includes:
- ✅ `index.html` - Root landing page (auto-redirects to the game)
- ✅ `kelly_sim/index.html` - Folder-level landing page
- ✅ `kelly_sim/kelly_game.html` - Main game application
- ✅ All supporting documentation (README, guides, etc.)

---

## Share Your Game

Once deployed, share your game URL with anyone:
- **Main URL**: `https://zenoonan.github.io/Research/`
- **Direct link**: `https://zenoonan.github.io/Research/kelly_sim/kelly_game.html`

Anyone with the link can play on:
- 📱 Mobile phones (iOS/Android)
- 💻 Desktop computers
- 🖥️ Tablets
- 🌐 Any modern web browser

No installation required - just click and play!

---

## Updating the Game

When you make changes:
1. Commit and push to your main branch
2. GitHub Pages will automatically rebuild (takes 1-3 minutes)
3. Clear browser cache to see changes immediately

---

## Technical Details

- **Hosting**: GitHub Pages (free)
- **Domain**: `username.github.io/repository-name`
- **SSL**: Automatic HTTPS
- **CDN**: Global content delivery
- **Uptime**: 99.9%+ (GitHub's infrastructure)
- **Bandwidth**: Generous limits for normal use

---

## Need Help?

If you encounter issues:
1. Check the [GitHub Pages documentation](https://docs.github.com/en/pages)
2. Verify deployment status in Settings → Pages
3. Look for build errors in the Actions tab
4. Ensure all files are committed and pushed

---

**Last Updated**: 2026-01-26
**Repository**: https://github.com/ZeNoonan/Research
