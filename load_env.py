#!/usr/bin/env python3

"""
Environment Variable Loader
===========================

This utility loads environment variables from a .env file.
It should be imported at the beginning of main scripts to ensure
environment variables are available for the config module.

Usage:
    import load_env  # This automatically loads the .env file
    from config import get_database_config
"""

import os
from pathlib import Path

def load_environment():
    """Load environment variables from .env file"""
    try:
        from dotenv import load_dotenv
        
        # Look for .env file in the project root (same directory as this script)
        env_file = Path(__file__).parent / '.env'
        
        if env_file.exists():
            load_dotenv(env_file)
            print(f"✅ Loaded environment variables from {env_file}")
            return True
        else:
            print(f"⚠️ No .env file found at {env_file}")
            print("⚠️ Using system environment variables only")
            return False
            
    except ImportError:
        print("⚠️ python-dotenv not installed. Using system environment variables only.")
        print("⚠️ Install with: pip install python-dotenv")
        return False
    except Exception as e:
        print(f"❌ Error loading environment variables: {e}")
        return False

# Automatically load environment variables when this module is imported
load_environment() 