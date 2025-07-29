# Setting up Automatic Gist Updates

This repository includes a GitHub Actions workflow that automatically updates a GitHub Gist whenever the blueprint files are modified.

## Setup Instructions

1. **Create a Personal Access Token**
   - Go to GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)
   - Click "Generate new token (classic)"
   - Give it a descriptive name like "Gist Update Token"
   - Select the `gist` scope
   - Click "Generate token"
   - Copy the token (you won't be able to see it again!)

2. **Add the Token to Repository Secrets**
   - Go to your repository on GitHub
   - Navigate to Settings → Secrets and variables → Actions
   - Click "New repository secret"
   - Name: `GIST_TOKEN`
   - Value: Paste the token you copied
   - Click "Add secret"

3. **Optional: Set Gist ID**
   If you want to use a specific existing gist instead of creating a new one:
   - Add another repository secret:
   - Name: `GIST_ID`
   - Value: Your existing gist ID (the long string in the gist URL)

## How It Works

- The workflow triggers automatically when blueprint YAML files are pushed to the main branch
- It uses the GitHub CLI to update the gist with the latest blueprint content
- The gist ID is stored in `.gist_id` file for future updates
- You can also manually trigger the workflow from the Actions tab

## Manual Update

To manually update the gist from your local machine:

```bash
python3 publish_to_gist.py
```

Make sure you have the GitHub CLI installed and authenticated:
```bash
# Install GitHub CLI
brew install gh  # macOS
# or see https://cli.github.com/manual/installation for other platforms

# Authenticate
gh auth login
```