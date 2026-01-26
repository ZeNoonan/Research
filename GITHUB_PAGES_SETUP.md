# GitHub Pages Setup Guide

This guide will help you deploy the Kelly Criterion game to GitHub Pages so you can play it from any device with a simple URL.

## Quick Setup (5 minutes)

### Step 1: Merge to Main Branch

Since the code is currently on a `claude/` branch, you need to merge it to your main branch:

1. Go to your GitHub repository: https://github.com/ZeNoonan/Research
2. Click on **"Pull requests"** tab
3. Click **"New pull request"**
4. Set:
   - **Base branch**: `main` (or `master`)
   - **Compare branch**: `claude/claude-md-mkpygsdlfw9patex-qULHg`
5. Click **"Create pull request"**
6. Add a title like: "Add Kelly Criterion Game"
7. Click **"Create pull request"** again
8. Click **"Merge pull request"**
9. Click **"Confirm merge"**

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

The `index.html` will automatically redirect to the game, or you can directly access:
```
https://zenoonan.github.io/Research/kelly_game.html
```

---

## Alternative: Deploy from Claude Branch Directly

If you want to deploy directly from the current branch without merging:

1. Go to **Settings** → **Pages**
2. Under **"Source"**, select:
   - **Branch**: `claude/claude-md-mkpygsdlfw9patex-qULHg`
   - **Folder**: `/ (root)`
3. Click **"Save"**

**URL will be the same:**
```
https://zenoonan.github.io/Research/
```

---

## Troubleshooting

### "GitHub Pages is not available"
- Make sure your repository is public (GitHub Pages is free for public repos)
- If private, you need GitHub Pro for GitHub Pages

### "404 - Page not found"
- Wait a few more minutes for deployment to complete
- Check that `index.html` and `kelly_game.html` are in the repository root
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
- ✅ `index.html` - Landing page (auto-redirects to game)
- ✅ `kelly_game.html` - Main game application
- ✅ All supporting documentation (README, guides, etc.)

---

## Share Your Game

Once deployed, share your game URL with anyone:
- **Main URL**: `https://zenoonan.github.io/Research/`
- **Direct link**: `https://zenoonan.github.io/Research/kelly_game.html`

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
