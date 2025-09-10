#!/usr/bin/env python3

"""
Environment Setup Script for Reddit Researcher
==============================================

This script helps migrate from config.yaml to environment variables.
It reads configuration from backup files and guides you through setting up
the .env file properly.

Usage:
    python setup_environment.py
"""

import os
import yaml
import json
from pathlib import Path
from config import validate_configuration

def load_backup_config():
    """Load configuration from backup files"""
    config_backup = Path(__file__).parent / "config.yaml.backup"
    
    if config_backup.exists():
        with open(config_backup, 'r') as f:
            return yaml.safe_load(f)
    else:
        print("❌ No config.yaml.backup found. Cannot migrate configuration.")
        return None

def load_google_credentials_backup():
    """Load Google credentials from backup file"""
    creds_backup = Path(__file__).parent / "google_credentials.json.backup"
    
    if creds_backup.exists():
        with open(creds_backup, 'r') as f:
            return json.load(f)
    else:
        print("❌ No google_credentials.json.backup found.")
        return None

def create_env_file(config_data, google_creds):
    """Create .env file from configuration data"""
    env_file = Path(__file__).parent / ".env"
    
    if env_file.exists():
        response = input("⚠️ .env file already exists. Overwrite? (y/N): ").strip().lower()
        if response != 'y':
            print("❌ Aborted. Existing .env file preserved.")
            return False
    
    print("📝 Creating .env file...")
    
    with open(env_file, 'w') as f:
        f.write("# Environment Variables for Reddit Researcher\n")
        f.write("# ============================================\n")
        f.write("# Generated automatically from configuration backup\n\n")
        
        # Database configuration
        if 'database' in config_data:
            db = config_data['database']
            f.write("# Database Configuration\n")
            f.write(f"DB_NAME={db.get('dbname', '')}\n")
            f.write(f"DB_USER={db.get('user', '')}\n")
            f.write(f"DB_PASSWORD={db.get('password', '')}\n")
            f.write(f"DB_HOST={db.get('host', 'localhost')}\n")
            f.write(f"DB_PORT={db.get('port', 5432)}\n\n")
        
        # API keys
        f.write("# API Keys\n")
        f.write(f"GEMINI_API_KEY={config_data.get('gemini_api_key', '')}\n\n")
        
        # Reddit API
        if 'reddit_api' in config_data:
            reddit = config_data['reddit_api']
            f.write("# Reddit API Configuration\n")
            f.write(f"REDDIT_CLIENT_ID={reddit.get('client_id', '')}\n")
            f.write(f"REDDIT_CLIENT_SECRET={reddit.get('client_secret', '')}\n")
            f.write(f"REDDIT_USER_AGENT={reddit.get('user_agent', '')}\n\n")
        
        # Email configuration
        if 'email' in config_data:
            email = config_data['email']
            f.write("# Email Configuration\n")
            f.write(f"EMAIL_SMTP_SERVER={email.get('smtp_server', 'smtp.gmail.com')}\n")
            f.write(f"EMAIL_SMTP_PORT={email.get('smtp_port', 587)}\n")
            f.write(f"EMAIL_SENDER={email.get('sender_email', '')}\n")
            f.write(f"EMAIL_PASSWORD={email.get('sender_password', '')}\n")
            
            # Handle recipient emails
            recipients = []
            if 'recipient_email' in email:
                recipients.append(email['recipient_email'])
            if 'recipient_emails' in email:
                if isinstance(email['recipient_emails'], list):
                    recipients.extend(email['recipient_emails'])
                else:
                    recipients.append(email['recipient_emails'])
            
            f.write(f"EMAIL_RECIPIENTS={','.join(recipients)}\n\n")
        
        # Google Sheets
        if 'google_sheets' in config_data:
            sheets = config_data['google_sheets']
            f.write("# Google Sheets Configuration\n")
            f.write(f"GOOGLE_CREDENTIALS_FILE={sheets.get('credentials_file', 'google_credentials.json')}\n")
            f.write(f"GOOGLE_SPREADSHEET_NAME={sheets.get('spreadsheet_name', 'GLeads')}\n")
            f.write(f"GOOGLE_WORKSHEET_NAME={sheets.get('worksheet_name', 'Main')}\n\n")
        
        # Subreddits
        if 'subreddits' in config_data and config_data['subreddits']:
            f.write("# Subreddits to monitor\n")
            f.write(f"SUBREDDITS={','.join(config_data['subreddits'])}\n\n")
        
        # Processing configuration
        f.write("# Processing Configuration (Optional - has defaults)\n")
        f.write("GEMINI_BATCH_SIZE=25\n")
        f.write("GEMINI_MODEL=gemini-1.5-flash\n")
        f.write("MAX_DURATION_HOURS=4\n")
        f.write("MAX_RETRIES=3\n")
        f.write("PARALLEL_WORKERS=3\n")
        f.write("CACHE_TTL=300\n")
        f.write("STATS_CACHE_TTL=60\n")
    
    print(f"✅ Created .env file: {env_file}")
    return True

def restore_google_credentials(google_creds):
    """Restore Google credentials file"""
    if not google_creds:
        print("⚠️ No Google credentials backup found. Skipping restoration.")
        return False
    
    creds_file = Path(__file__).parent / "google_credentials.json"
    
    if creds_file.exists():
        response = input("⚠️ google_credentials.json already exists. Overwrite? (y/N): ").strip().lower()
        if response != 'y':
            print("❌ Skipped Google credentials restoration.")
            return False
    
    with open(creds_file, 'w') as f:
        json.dump(google_creds, f, indent=2)
    
    print(f"✅ Restored Google credentials: {creds_file}")
    return True

def validate_setup():
    """Validate the environment setup"""
    print("\n🔍 Validating configuration...")
    
    # Load environment variables
    from dotenv import load_dotenv
    env_file = Path(__file__).parent / ".env"
    load_dotenv(env_file)
    
    # Validate configuration
    errors = validate_configuration()
    
    if not errors:
        print("✅ Configuration validation passed!")
        return True
    else:
        print("❌ Configuration validation failed:")
        for error in errors:
            print(f"   • {error}")
        return False

def main():
    """Main setup function"""
    print("🚀 Reddit Researcher Environment Setup")
    print("=" * 50)
    
    # Check if already configured
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        print("📝 .env file already exists.")
        choice = input("Would you like to:\n1) Validate existing configuration\n2) Recreate from backup\n3) Exit\nChoice (1-3): ").strip()
        
        if choice == "1":
            if validate_setup():
                print("\n🎉 Your environment is properly configured!")
            else:
                print("\n🔧 Please fix the configuration errors and try again.")
            return
        elif choice == "3":
            print("👋 Goodbye!")
            return
        # Continue with recreation for choice == "2"
    
    # Load backup configuration
    print("\n📂 Loading configuration from backup files...")
    config_data = load_backup_config()
    
    if not config_data:
        print("❌ Cannot proceed without configuration backup.")
        return
    
    google_creds = load_google_credentials_backup()
    
    # Create .env file
    if create_env_file(config_data, google_creds):
        # Restore Google credentials if needed
        restore_google_credentials(google_creds)
        
        # Validate setup
        print("\n🔍 Validating new configuration...")
        if validate_setup():
            print("\n🎉 Environment setup completed successfully!")
            print("\n📋 Next steps:")
            print("1. Review the .env file and adjust any settings if needed")
            print("2. Run: pip install -r requirements.txt")
            print("3. Test the configuration with: python -c 'import load_env; from config import validate_configuration; print(\"OK\" if not validate_configuration() else \"Issues found\")'")
        else:
            print("\n🔧 Please review and fix the configuration errors.")
    else:
        print("❌ Failed to create .env file.")

if __name__ == "__main__":
    main() 