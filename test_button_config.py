#!/usr/bin/env python3
"""Test script for updating button configuration in Casambi network."""

import asyncio
import logging
import sys
from pathlib import Path

# Add the casambi-bt source to path
sys.path.insert(0, str(Path(__file__).parent.parent / "casambi-bt" / "src"))

from CasambiBt import CasambiBt

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_button_config():
    """Test updating button configuration."""
    
    # Configuration - update these values as needed
    EMAIL = "your_email@example.com"  # Update with your email
    PASSWORD = "your_password"  # Update with your password
    NETWORK_ID = "your_network_id"  # Update with your network ID
    BT_ADDRESS = "AA:BB:CC:DD:EE:FF"  # Update with your gateway MAC address
    
    # Button configuration to test
    UNIT_ID = 31  # The switch unit ID
    BUTTON_INDEX = 1  # Button 2 (0-based index)
    ACTION_TYPE = "control_unit"  # Action type: "none", "control_unit", "scene", "cycle_modes"
    TARGET_UNIT_ID = 18  # Target unit to control (not needed for "none" or "cycle_modes")
    
    print(f"Testing button configuration update...")
    print(f"  Unit ID: {UNIT_ID}")
    print(f"  Button: {BUTTON_INDEX + 1} (index {BUTTON_INDEX})")
    print(f"  Action: {ACTION_TYPE}")
    print(f"  Target: {TARGET_UNIT_ID}")
    
    # Create CasambiBt instance
    casa = CasambiBt(cacheDir=Path(".cache"))
    
    try:
        # Connect to the network
        print("\nConnecting to Casambi network...")
        await casa.connect(
            email=EMAIL,
            password=PASSWORD,
            networkId=NETWORK_ID,
            address=BT_ADDRESS
        )
        print("Connected successfully!")
        
        # Wait a moment for initialization
        await asyncio.sleep(2)
        
        # Get unit info before update
        unit = casa.units.get(UNIT_ID)
        if unit:
            print(f"\nUnit {UNIT_ID} found: {unit.name}")
            switch_config = unit.unitConfig.get("switchConfig", {})
            buttons = switch_config.get("buttons", [])
            if len(buttons) > BUTTON_INDEX:
                print(f"Current button {BUTTON_INDEX + 1} config: {buttons[BUTTON_INDEX]}")
            else:
                print(f"Button {BUTTON_INDEX + 1} not configured yet")
        else:
            print(f"Unit {UNIT_ID} not found!")
            return
        
        # Update the button configuration
        print(f"\nUpdating button configuration...")
        await casa.update_button_config(
            unit_id=UNIT_ID,
            button_index=BUTTON_INDEX,
            action_type=ACTION_TYPE,
            target_unit_id=TARGET_UNIT_ID
        )
        print("Button configuration update sent!")
        
        # Wait for the network to process the update
        print("\nWaiting for network to process update...")
        await asyncio.sleep(5)
        
        # Check if configuration was updated
        # Note: The actual configuration might be broadcast back via NetworkConfig packets
        print("\nTest complete! Check if button now controls the target unit.")
        print("You can also verify in the Casambi app.")
        
    except Exception as e:
        print(f"\nError: {e}")
        logging.exception("Test failed")
    
    finally:
        # Disconnect
        print("\nDisconnecting...")
        await casa.disconnect()
        print("Disconnected.")

if __name__ == "__main__":
    print("Casambi Button Configuration Test")
    print("==================================")
    print("\nIMPORTANT: Update the configuration values in the script before running!")
    print("This test will update button 2 on unit 31 to control unit 18.")
    print("\nPress Ctrl+C to cancel, or Enter to continue...")
    
    try:
        input()
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(0)
    
    asyncio.run(test_button_config())