#!/usr/bin/env python3
"""
Migration script to add users table and update posts_raw table
Run this script to update existing databases with user functionality
"""

import os
import sys
import yaml
import psycopg2
from psycopg2 import sql

def load_config(config_path='../config.yaml'):
    """Load configuration from config.yaml"""
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # If config_path is relative, look for it relative to the script's directory
    if not os.path.isabs(config_path):
        config_path = os.path.join(script_dir, config_path)
    
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        return config
    except FileNotFoundError:
        print(f"Config file not found at: {config_path}")
        return None
    except yaml.YAMLError as e:
        print(f"Error parsing config file: {e}")
        return None

def get_db_connection(db_config):
    """Create database connection"""
    try:
        conn = psycopg2.connect(
            dbname=db_config['dbname'],
            user=db_config['user'],
            password=db_config['password'],
            host=db_config.get('host', 'localhost'),
            port=db_config.get('port', 5432)
        )
        return conn
    except psycopg2.Error as e:
        print(f"Error connecting to database: {e}")
        return None

def run_migration():
    """Run the migration script"""
    print("Starting database migration to add users table...")
    
    # Load configuration
    config = load_config()
    if not config:
        print("Failed to load configuration. Exiting.")
        return False
    
    db_config = config.get('database', {})
    if not db_config:
        print("Database configuration not found in config.yaml. Exiting.")
        return False
    
    # Connect to database
    conn = get_db_connection(db_config)
    if not conn:
        print("Failed to connect to database. Exiting.")
        return False
    
    try:
        cur = conn.cursor()
        
        # Read migration SQL file
        script_dir = os.path.dirname(os.path.abspath(__file__))
        migration_file = os.path.join(script_dir, 'migrate_add_users.sql')
        
        if not os.path.exists(migration_file):
            print(f"Migration file not found: {migration_file}")
            return False
        
        with open(migration_file, 'r') as f:
            migration_sql = f.read()
        
        print("Executing migration...")
        
        # Execute migration
        cur.execute(migration_sql)
        conn.commit()
        
        print("✅ Migration completed successfully!")
        print("The database now includes:")
        print("  - users table for storing Reddit user information")
        print("  - author_id column in posts_raw table")
        print("  - Foreign key relationship between posts and users")
        print("  - Appropriate indexes for performance")
        
        return True
        
    except psycopg2.Error as e:
        print(f"❌ Error during migration: {e}")
        conn.rollback()
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    print("Reddit Researcher Database Migration")
    print("=" * 40)
    
    success = run_migration()
    
    if success:
        print("\n🎉 Migration completed successfully!")
        print("You can now run the ingestion script to start collecting user data.")
    else:
        print("\n💥 Migration failed!")
        print("Please check the error messages above and try again.")
        sys.exit(1) 