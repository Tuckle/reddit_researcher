#!/usr/bin/env python3
"""
Create Performance Indexes for Reddit Researcher Database

This script creates optimized indexes for better query performance,
especially for the Streamlit UI queries.
"""

import psycopg2
import yaml
import sys
from pathlib import Path

def load_config():
    """Load database configuration"""
    config_path = Path(__file__).parent.parent / 'config.yaml'
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def create_indexes():
    """Create all performance indexes"""
    
    # Index definitions - most critical first
    indexes = [
        {
            'name': 'idx_posts_ui_main',
            'sql': """CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_posts_ui_main 
                     ON posts_raw (priority_score DESC, created_utc DESC) 
                     WHERE priority_score IS NOT NULL AND status NOT IN ('ignored', 'sent')""",
            'description': 'Main UI query optimization'
        },
        {
            'name': 'idx_posts_status',
            'sql': """CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_posts_status 
                     ON posts_raw (status)""",
            'description': 'Status filtering'
        },
        {
            'name': 'idx_posts_priority_score',
            'sql': """CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_posts_priority_score 
                     ON posts_raw (priority_score DESC) 
                     WHERE priority_score IS NOT NULL""",
            'description': 'Priority score sorting'
        },
        {
            'name': 'idx_posts_selected_email',
            'sql': """CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_posts_selected_email 
                     ON posts_raw (created_utc DESC) 
                     WHERE status = 'selected'""",
            'description': 'Selected posts for email'
        },
        {
            'name': 'idx_posts_subreddit',
            'sql': """CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_posts_subreddit 
                     ON posts_raw (subreddit)""",
            'description': 'Subreddit filtering'
        },
        {
            'name': 'idx_posts_unprocessed',
            'sql': """CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_posts_unprocessed 
                     ON posts_raw (processed, created_utc DESC) 
                     WHERE processed = FALSE""",
            'description': 'Unprocessed posts pipeline'
        },
        {
            'name': 'idx_posts_gemini_pending',
            'sql': """CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_posts_gemini_pending 
                     ON posts_raw (created_utc DESC) 
                     WHERE priority_score IS NULL""",
            'description': 'Posts needing Gemini analysis'
        },
        {
            'name': 'idx_posts_url_unique',
            'sql': """CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_posts_url_unique 
                     ON posts_raw (url)""",
            'description': 'URL uniqueness and lookup'
        },
        {
            'name': 'idx_posts_created_utc',
            'sql': """CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_posts_created_utc 
                     ON posts_raw (created_utc DESC)""",
            'description': 'Time-based sorting'
        },
        {
            'name': 'idx_posts_status_priority',
            'sql': """CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_posts_status_priority 
                     ON posts_raw (status, priority_score DESC, created_utc DESC)""",
            'description': 'Status + priority composite'
        }
    ]
    
    try:
        # Load configuration
        config = load_config()
        db_config = config['database']
        
        # Connect with autocommit for CONCURRENTLY indexes
        conn = psycopg2.connect(**db_config)
        conn.autocommit = True
        cur = conn.cursor()
        
        print("🚀 Creating performance indexes for Reddit Researcher...")
        print("=" * 60)
        
        success_count = 0
        total_count = len(indexes)
        
        for i, index in enumerate(indexes, 1):
            print(f"\n[{i}/{total_count}] Creating {index['name']}...")
            print(f"    Purpose: {index['description']}")
            
            try:
                cur.execute(index['sql'])
                print(f"    ✅ Success")
                success_count += 1
            except psycopg2.errors.DuplicateTable:
                print(f"    ⚠️  Already exists (skipped)")
                success_count += 1
            except Exception as e:
                print(f"    ❌ Failed: {e}")
        
        # Update table statistics
        print(f"\n📊 Updating table statistics...")
        try:
            cur.execute("ANALYZE posts_raw;")
            cur.execute("ANALYZE pipeline_status;")
            print("    ✅ Statistics updated")
        except Exception as e:
            print(f"    ⚠️  Statistics update failed: {e}")
        
        print("\n" + "=" * 60)
        print(f"📋 Summary:")
        print(f"    Indexes created/verified: {success_count}/{total_count}")
        print(f"    Database performance should be significantly improved!")
        
        if success_count == total_count:
            print("    🎉 All indexes created successfully!")
        else:
            print(f"    ⚠️  {total_count - success_count} indexes had issues")
        
        conn.close()
        return success_count == total_count
        
    except Exception as e:
        print(f"❌ Error creating indexes: {e}")
        return False

def check_existing_indexes():
    """Check what indexes already exist"""
    try:
        config = load_config()
        conn = psycopg2.connect(**config['database'])
        cur = conn.cursor()
        
        cur.execute("""
            SELECT indexname, tablename 
            FROM pg_indexes 
            WHERE schemaname = 'public' AND tablename = 'posts_raw'
            ORDER BY indexname;
        """)
        
        indexes = cur.fetchall()
        
        print("📋 Existing indexes on posts_raw:")
        for index_name, table_name in indexes:
            print(f"    - {index_name}")
        
        conn.close()
        
    except Exception as e:
        print(f"Error checking indexes: {e}")

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Create performance indexes for Reddit Researcher')
    parser.add_argument('--check', action='store_true', help='Check existing indexes')
    parser.add_argument('--create', action='store_true', help='Create new indexes')
    
    args = parser.parse_args()
    
    if args.check:
        check_existing_indexes()
    elif args.create:
        success = create_indexes()
        sys.exit(0 if success else 1)
    else:
        # Default: create indexes
        success = create_indexes()
        sys.exit(0 if success else 1)

if __name__ == '__main__':
    main() 