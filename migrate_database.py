#!/usr/bin/env python3
"""
Database migration script to add gemini_score column to posts_raw table.
"""

import psycopg2
from psycopg2 import sql
import yaml
import os

def load_config(config_path='config.yaml'):
    """Load configuration from YAML file."""
    if not os.path.isabs(config_path):
        # Get the directory where this script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # The config.yaml is in the same directory as the script
        config_path = os.path.join(script_dir, config_path)
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    return config

def get_db_connection(db_config):
    """Create and return a database connection."""
    conn = psycopg2.connect(
        dbname=db_config['dbname'],
        user=db_config['user'],
        password=db_config['password'],
        host=db_config.get('host', 'localhost'),
        port=db_config.get('port', 5432)
    )
    return conn

def check_column_exists(conn, table_name, column_name):
    """Check if a column exists in a table."""
    cur = conn.cursor()
    cur.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = %s AND column_name = %s;
    """, (table_name, column_name))
    result = cur.fetchone()
    cur.close()
    return result is not None

def reset_incomplete_analysis(conn):
    """Reset posts that don't have complete Gemini analysis data."""
    cur = conn.cursor()
    
    try:
        # Find posts that need to be reset (either no priority_score, score=0, or no concise_theme)
        cur.execute("""
            SELECT COUNT(*) FROM posts_raw 
            WHERE priority_score IS NULL OR priority_score = 0 OR concise_theme IS NULL OR concise_theme = '';
        """)
        posts_to_reset = cur.fetchone()[0]
        
        if posts_to_reset > 0:
            print(f"🔄 Found {posts_to_reset} posts with incomplete Gemini analysis data.")
            print("🔄 Resetting priority_score to NULL for reprocessing...")
            
            # Reset priority_score to NULL for posts that don't have complete analysis
            cur.execute("""
                UPDATE posts_raw 
                SET priority_score = NULL, processed = FALSE
                WHERE priority_score IS NULL OR priority_score = 0 OR concise_theme IS NULL OR concise_theme = '';
            """)
            
            affected_rows = cur.rowcount
            conn.commit()
            print(f"✅ Successfully reset {affected_rows} posts for reprocessing.")
            
            # Show count of posts that have complete analysis (will not be touched)
            cur.execute("""
                SELECT COUNT(*) FROM posts_raw 
                WHERE priority_score > 0 AND concise_theme IS NOT NULL AND concise_theme != '';
            """)
            complete_posts = cur.fetchone()[0]
            print(f"✅ {complete_posts} posts with complete analysis were preserved.")
            
        else:
            print("✅ No posts found that need to be reset.")
    
    except Exception as e:
        conn.rollback()
        print(f"❌ Error resetting incomplete analysis: {e}")
        raise
    finally:
        cur.close()

def reset_all_priority_scores(conn):
    """Reset ALL priority scores to NULL for complete reprocessing."""
    cur = conn.cursor()
    
    try:
        # Count all posts that currently have priority scores
        cur.execute("""
            SELECT COUNT(*) FROM posts_raw 
            WHERE priority_score IS NOT NULL;
        """)
        posts_with_scores = cur.fetchone()[0]
        
        if posts_with_scores > 0:
            print(f"🔄 Found {posts_with_scores} posts with existing priority scores.")
            print("🔄 Resetting ALL priority scores to NULL for complete reprocessing...")
            
            # Reset ALL priority scores to NULL and related Gemini analysis fields
            cur.execute("""
                UPDATE posts_raw 
                SET priority_score = NULL, 
                    processed = FALSE,
                    concise_theme = NULL,
                    short_summary = NULL,
                    rationale_for_value = NULL,
                    rationale_for_views = NULL,
                    suggested_angle_for_coach = NULL
                WHERE priority_score IS NOT NULL;
            """)
            
            affected_rows = cur.rowcount
            conn.commit()
            print(f"✅ Successfully reset {affected_rows} posts. All priority scores and Gemini analysis data cleared.")
            
        else:
            print("✅ No posts found with existing priority scores.")
    
    except Exception as e:
        conn.rollback()
        print(f"❌ Error resetting all priority scores: {e}")
        raise
    finally:
        cur.close()

def run_migration():
    """Run the database migration to add/update columns for Gemini analysis."""
    config = load_config()
    db_config = config.get('database', {})
    
    if not db_config:
        print("❌ Database configuration not found in config.yaml.")
        return False
    
    print("🔄 Connecting to database...")
    
    try:
        conn = get_db_connection(db_config)
        cur = conn.cursor()
        
        # Check and rename gemini_score to priority_score if gemini_score exists
        if check_column_exists(conn, 'posts_raw', 'gemini_score'):
            print("🔄 Renaming 'gemini_score' to 'priority_score'...")
            cur.execute("ALTER TABLE posts_raw RENAME COLUMN gemini_score TO priority_score;")
            conn.commit()
            print("✅ Successfully renamed 'gemini_score' to 'priority_score'.")

        # Check and add priority_score if it doesn't exist after potential rename
        if not check_column_exists(conn, 'posts_raw', 'priority_score'):
             print("➕ Adding 'priority_score' column to posts_raw table...")
             cur.execute("ALTER TABLE posts_raw ADD COLUMN priority_score INTEGER;")
             conn.commit()
             print("✅ Successfully added 'priority_score' column.")
        else:
            # Ensure priority_score is INTEGER if it exists
            print("✅ 'priority_score' column already exists. Ensuring correct type...")
            try:
                 cur.execute("ALTER TABLE posts_raw ALTER COLUMN priority_score TYPE INTEGER USING priority_score::INTEGER;")
                 conn.commit()
                 print("✅ 'priority_score' column type is INTEGER.")
            except Exception as e:
                 print(f"⚠️ Could not alter 'priority_score' column type to INTEGER: {e}")

        # Define the new columns to add
        new_columns = {
            'concise_theme': 'VARCHAR(100)',
            'short_summary': 'VARCHAR(250)',
            'rationale_for_value': 'TEXT',
            'rationale_for_views': 'TEXT',
            'suggested_angle_for_coach': 'TEXT'
        }

        # Check and add each new column
        for col_name, col_type in new_columns.items():
            if not check_column_exists(conn, 'posts_raw', col_name):
                print(f"➕ Adding '{col_name}' column to posts_raw table...")
                cur.execute(sql.SQL("ALTER TABLE posts_raw ADD COLUMN {col_name} {col_type}").format(
                    col_name=sql.Identifier(col_name),
                    col_type=sql.SQL(col_type) # Use sql.SQL for the type string
                ))
                conn.commit()
                print(f"✅ Successfully added '{col_name}' column.")
            else:
                print(f"✅ Column '{col_name}' already exists.")

        # Check if index exists and create if needed
        cur.execute("""
            SELECT indexname 
            FROM pg_indexes 
            WHERE tablename = 'posts_raw' AND indexname = 'idx_posts_raw_processed';
        """)
        index_exists = cur.fetchone()
        
        if index_exists:
            print("✅ Index 'idx_posts_raw_processed' already exists.")
        else:
            print("➕ Creating index on processed column...")
            cur.execute("CREATE INDEX idx_posts_raw_processed ON posts_raw (processed);")
            conn.commit()
            print("✅ Successfully created index.")
        
        cur.close()
        conn.close()
        
        print("\n🎉 Database migration completed successfully!")
        
        # Run the reset operation
        print("\n" + "=" * 50)
        print("Resetting ALL Priority Scores and Analysis Data")
        print("=" * 50)
        
        conn = get_db_connection(db_config)
        reset_all_priority_scores(conn)
        conn.close()
        
        print("All priority scores have been cleared. You can now run the Gemini analysis script.")
        
        return True
        
    except Exception as e:
        print(f"❌ Error during migration: {e}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("Database Migration for Gemini Analysis")
    print("=" * 50)
    print()
    
    success = run_migration()
    
    if success:
        print("\n✨ Migration completed! You can now run:")
        print("   cd processing")
        print("   python run_gemini_analysis.py")
    else:
        print("\n💥 Migration failed. Please check the error above.") 