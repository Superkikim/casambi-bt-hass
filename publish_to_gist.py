#!/usr/bin/env python3
"""
Publish Home Assistant blueprints to GitHub Gist
"""

import json
import os
import subprocess
import sys
from pathlib import Path

# Blueprint files to publish
BLUEPRINT_DIR = Path("blueprints/automation/casambi_bt")
BLUEPRINTS = [
    "button_toggle_and_dim.yaml",
    "button_short_long_press.yaml", 
    "button_cover_control.yaml"
]

def get_git_token():
    """Get GitHub token from git config or environment"""
    # Try environment variable first
    token = os.environ.get('GITHUB_TOKEN')
    if token:
        return token
    
    # Try git config
    try:
        result = subprocess.run(['git', 'config', '--get', 'github.token'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
    except:
        pass
    
    return None

def create_or_update_gist(files_content, description="Casambi Bluetooth Home Assistant Blueprints"):
    """Create or update a GitHub Gist with the blueprint files"""
    
    # Check if we have a stored gist ID
    gist_id_file = Path(".gist_id")
    gist_id = None
    if gist_id_file.exists():
        gist_id = gist_id_file.read_text().strip()
    
    # Prepare the gist data
    gist_data = {
        "description": description,
        "public": True,
        "files": {}
    }
    
    for filename, content in files_content.items():
        gist_data["files"][filename] = {"content": content}
    
    # Use GitHub CLI if available
    try:
        # Check if gh is installed
        subprocess.run(['gh', '--version'], capture_output=True, check=True)
        
        # Create temporary file with gist content
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(gist_data, f)
            temp_file = f.name
        
        try:
            if gist_id:
                # Update existing gist
                cmd = ['gh', 'api', f'gists/{gist_id}', '--method', 'PATCH', '--input', temp_file]
            else:
                # Create new gist
                cmd = ['gh', 'api', 'gists', '--method', 'POST', '--input', temp_file]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            response = json.loads(result.stdout)
            
            # Save gist ID for future updates
            if not gist_id:
                gist_id = response['id']
                gist_id_file.write_text(gist_id)
            
            return response['html_url'], response['files']
        finally:
            os.unlink(temp_file)
            
    except subprocess.CalledProcessError as e:
        print(f"Error using GitHub CLI: {e}")
        print("Please ensure you're authenticated with: gh auth login")
        sys.exit(1)
    except FileNotFoundError:
        print("GitHub CLI (gh) not found. Please install it:")
        print("  macOS: brew install gh")
        print("  Linux: See https://github.com/cli/cli#installation")
        sys.exit(1)

def main():
    """Main function"""
    # Read all blueprint files
    files_content = {}
    
    for blueprint in BLUEPRINTS:
        filepath = BLUEPRINT_DIR / blueprint
        if not filepath.exists():
            print(f"Warning: {filepath} not found, skipping...")
            continue
        
        content = filepath.read_text()
        files_content[blueprint] = content
        print(f"Read {blueprint}")
    
    if not files_content:
        print("No blueprint files found!")
        sys.exit(1)
    
    # Create or update gist
    print("\nPublishing to GitHub Gist...")
    gist_url, files = create_or_update_gist(files_content)
    
    print(f"\nGist published successfully!")
    print(f"Gist URL: {gist_url}")
    print(f"\nDirect links to blueprints:")
    
    for filename, file_info in files.items():
        print(f"  {filename}:")
        print(f"    Raw: {file_info['raw_url']}")
    
    # Create a README with import links
    readme_content = f"""# Casambi Bluetooth Home Assistant Blueprints

These blueprints allow you to control lights and covers using Casambi Bluetooth switches in Home Assistant.

## Available Blueprints

### 1. Button Toggle and Dim (v1.2.2)
Short press to toggle light, hold to dim.

**Import URL:**
```
{files.get('button_toggle_and_dim.yaml', {}).get('raw_url', 'N/A')}
```

### 2. Button Actions (v1.1.0)
Versatile button automation with customizable actions for different button events.

**Import URL:**
```
{files.get('button_short_long_press.yaml', {}).get('raw_url', 'N/A')}
```

### 3. Button Cover Control (v1.2.0)
Control blinds/covers - short press to open/close/stop, hold to open/close continuously.

**Import URL:**
```
{files.get('button_cover_control.yaml', {}).get('raw_url', 'N/A')}
```

## How to Import

1. In Home Assistant, go to **Settings** → **Automations & Scenes** → **Blueprints**
2. Click the **Import Blueprint** button
3. Paste one of the import URLs above
4. Click **Preview Import**
5. Click **Import Blueprint**

## Source Repository
https://github.com/rankjie/casambi-bt-hass
"""
    
    # Save README locally
    readme_file = Path("blueprints_gist_readme.md")
    readme_file.write_text(readme_content)
    print(f"\nREADME saved to: {readme_file}")

if __name__ == "__main__":
    main()