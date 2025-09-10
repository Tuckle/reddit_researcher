#!/usr/bin/env python3

"""
Centralized Configuration for Reddit Researcher
===============================================

This file contains all configuration settings that are shared across multiple scripts
in the Reddit Researcher project. It loads sensitive data from environment variables
and provides default configurations for all components.

Usage:
    from config import get_database_config, get_reddit_api_config, ...
"""

import os
from typing import Dict, List, Optional
from dataclasses import dataclass
from pathlib import Path

# ============================================================================
# Project Structure
# ============================================================================

# Base project directory
PROJECT_ROOT = Path(__file__).parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
PROMPTS_DIR = SCRIPTS_DIR / "prompts" 
DATABASE_DIR = PROJECT_ROOT / "database"
LOGS_DIR = PROJECT_ROOT / "logs"

# Ensure logs directory exists
LOGS_DIR.mkdir(exist_ok=True)

# ============================================================================
# Configuration Classes
# ============================================================================

@dataclass
class DatabaseConfig:
    """Database connection configuration"""
    dbname: str
    user: str
    password: str
    host: str = "localhost"
    port: int = 5432

@dataclass
class RedditAPIConfig:
    """Reddit API configuration"""
    client_id: str
    client_secret: str
    user_agent: str

@dataclass
class EmailConfig:
    """Email configuration"""
    smtp_server: str
    smtp_port: int
    sender_email: str
    sender_password: str
    recipient_emails: List[str]

@dataclass
class GoogleSheetsConfig:
    """Google Sheets configuration"""
    credentials_file: Optional[str]
    spreadsheet_name: str
    worksheet_name: str = "Sheet1"

# ============================================================================
# Environment Variable Loaders
# ============================================================================

def get_database_config() -> DatabaseConfig:
    """Load database configuration from environment variables"""
    return DatabaseConfig(
        dbname=os.getenv("DB_NAME", "reddit_researcher"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432"))
    )

def get_reddit_api_config() -> RedditAPIConfig:
    """Load Reddit API configuration from environment variables"""
    return RedditAPIConfig(
        client_id=os.getenv("REDDIT_CLIENT_ID", ""),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET", ""),
        user_agent=os.getenv("REDDIT_USER_AGENT", "reddit_researcher:v1.0")
    )

def get_email_config() -> EmailConfig:
    """Load email configuration from environment variables"""
    recipients = os.getenv("EMAIL_RECIPIENTS", "").split(",")
    recipients = [email.strip() for email in recipients if email.strip()]
    
    return EmailConfig(
        smtp_server=os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com"),
        smtp_port=int(os.getenv("EMAIL_SMTP_PORT", "587")),
        sender_email=os.getenv("EMAIL_SENDER", ""),
        sender_password=os.getenv("EMAIL_PASSWORD", ""),
        recipient_emails=recipients
    )

def get_google_sheets_config() -> GoogleSheetsConfig:
    """Load Google Sheets configuration from environment variables"""
    credentials_file = os.getenv("GOOGLE_CREDENTIALS_FILE")  # Optional - can be None for env-based auth
    
    # If credentials file is specified and relative path, make it relative to project root
    if credentials_file and not os.path.isabs(credentials_file):
        credentials_file = str(PROJECT_ROOT / credentials_file)
    
    return GoogleSheetsConfig(
        credentials_file=credentials_file,
        spreadsheet_name=os.getenv("GOOGLE_SPREADSHEET_NAME", "GLeads"),
        worksheet_name=os.getenv("GOOGLE_WORKSHEET_NAME", "Main")
    )

def get_gemini_api_key() -> str:
    """Get Gemini API key from environment variables"""
    return os.getenv("GEMINI_API_KEY", "")

# ============================================================================
# Application Configuration
# ============================================================================

def get_subreddits() -> List[str]:
    """Get list of subreddits to monitor"""
    subreddits_env = os.getenv("SUBREDDITS", "")
    if subreddits_env:
        return [sr.strip() for sr in subreddits_env.split(",") if sr.strip()]
    
    # Default subreddits if not set in environment
    return [
        "Rizz",
        "dating", 
        "relationships",
        "Tinder",
        "relationship_advice",
        "PickUpArtist",
        "seduction",
        "dating_advice",
        "AskMenRelationships",
        "OnlineDating",
        "datingoverthirty",
        "bodylanguage",
        "datingadviceformen",
        "pickup",
        "Bumble"
    ]

# ============================================================================
# Processing Configuration
# ============================================================================

def get_processing_config() -> Dict:
    """Get configuration for various processing parameters"""
    return {
        "gemini_batch_size": int(os.getenv("GEMINI_BATCH_SIZE", "25")),
        "gemini_model": os.getenv("GEMINI_MODEL", "gemini-1.5-flash"),
        "max_duration_hours": int(os.getenv("MAX_DURATION_HOURS", "4")),
        "max_retries": int(os.getenv("MAX_RETRIES", "3")),
        "parallel_workers": int(os.getenv("PARALLEL_WORKERS", "3")),
        "cache_ttl": int(os.getenv("CACHE_TTL", "300")),  # 5 minutes
        "stats_cache_ttl": int(os.getenv("STATS_CACHE_TTL", "60"))  # 1 minute
    }

# ============================================================================
# Utility Functions
# ============================================================================

def load_prompt(prompt_name: str) -> str:
    """Load a prompt from the prompts folder"""
    prompt_file = PROMPTS_DIR / f"{prompt_name}.txt"
    try:
        return prompt_file.read_text(encoding='utf-8').strip()
    except FileNotFoundError:
        raise FileNotFoundError(f"Prompt file not found: {prompt_file}")

def validate_configuration() -> List[str]:
    """Validate that all required configuration is present"""
    errors = []
    
    # Check database config
    db_config = get_database_config()
    if not db_config.dbname:
        errors.append("DB_NAME environment variable is required")
    if not db_config.password:
        errors.append("DB_PASSWORD environment variable is required")
    
    # Check Reddit API config
    reddit_config = get_reddit_api_config()
    if not reddit_config.client_id:
        errors.append("REDDIT_CLIENT_ID environment variable is required")
    if not reddit_config.client_secret:
        errors.append("REDDIT_CLIENT_SECRET environment variable is required")
    
    # Check Gemini API key
    if not get_gemini_api_key():
        errors.append("GEMINI_API_KEY environment variable is required")
    
    # Check email config (optional for some components)
    email_config = get_email_config()
    if email_config.sender_email and not email_config.sender_password:
        errors.append("EMAIL_PASSWORD is required when EMAIL_SENDER is set")
    
    return errors

def get_db_connection_dict() -> Dict:
    """Get database configuration as a dictionary (for backward compatibility)"""
    config = get_database_config()
    return {
        "dbname": config.dbname,
        "user": config.user,
        "password": config.password,
        "host": config.host,
        "port": config.port
    }

# ============================================================================
# Legacy Support (for gradual migration)
# ============================================================================

def load_config_yaml() -> Dict:
    """
    Load configuration from YAML file (deprecated - use environment variables instead)
    This function is kept for backward compatibility during migration.
    """
    import yaml
    
    config_file = PROJECT_ROOT / "config.yaml"
    if config_file.exists():
        with open(config_file, 'r') as f:
            return yaml.safe_load(f)
    return {} 