import psycopg2
import yaml
import os
from psycopg2 import sql
from sentence_transformers import SentenceTransformer
import numpy as np

def load_config(config_path='config.yaml'):
    # If config_path is relative, look for it relative to the script's directory
    if not os.path.isabs(config_path):
        # Get the directory where this script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Go up one level to the reddit_researcher directory where config.yaml is located
        config_path = os.path.join(script_dir, '..', config_path)
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    return config

def get_db_connection(db_config):
    conn = psycopg2.connect(
        dbname=db_config['dbname'],
        user=db_config['user'],
        password=db_config['password'],
        host=db_config.get('host', 'localhost'),
        port=db_config.get('port', 5432)
    )
    return conn

def main():
    config = load_config()
    db_config = config.get('database', {})

    if not db_config:
        print("Database configuration not found in config.yaml.")
        return

    # Load Sentence Transformer model
    try:
        model = SentenceTransformer('all-MiniLM-L6-v2')
        print("Sentence-Transformer model loaded.")
    except Exception as e:
        print(f"Error loading Sentence-Transformer model: {e}")
        print("Please ensure you have an internet connection or the model is cached locally.")
        return

    conn = None
    try:
        conn = get_db_connection(db_config)
        cur = conn.cursor()

        # Fetch processed but not yet embedded posts (vector is NULL)
        select_query = "SELECT id, title, body, img_text FROM posts_raw WHERE processed = TRUE AND vector IS NULL;"
        cur.execute(select_query)
        posts_to_embed = cur.fetchall()

        print(f"Found {len(posts_to_embed)} posts to generate embeddings for.")

        if not posts_to_embed:
            print("No posts to process for embeddings.")
            return

        # Prepare data for embedding
        post_ids = [post[0] for post in posts_to_embed]
        # Combine title, body, and img_text for embedding
        post_texts = []
        for post in posts_to_embed:
            title, body, img_text = post[1], post[2], post[3]
            combined_text = f"{title or ''} {body or ''} {img_text or ''}".strip()
            post_texts.append(combined_text)

        # Generate embeddings
        print("Generating embeddings...")
        embeddings = model.encode(post_texts, show_progress_bar=True)
        print("Embeddings generated.")

        # Update posts_raw table with embeddings
        print("Updating database with embeddings...")
        update_query = sql.SQL("""
            UPDATE posts_raw
            SET vector = %s
            WHERE id = %s;
        """)

        for i, post_id in enumerate(post_ids):
            # Convert numpy array to list for inserting into pgvector
            cur.execute(update_query, (embeddings[i].tolist(), post_id))

        conn.commit()
        print(f"Updated {len(posts_to_embed)} posts with embeddings.")

    except Exception as e:
        print(f"An error occurred during embedding generation: {e}")
    finally:
        if conn:
            conn.close()
            print("Database connection closed.")

if __name__ == "__main__":
    main() 