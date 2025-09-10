import psycopg2
import yaml
import datetime
import os
from psycopg2 import sql

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

def calculate_score(post):
    # post is expected to be a dictionary or object with necessary attributes
    upvotes = post.get('score', 0)
    comments = post.get('num_comments', 0)
    created_utc = post.get('created_utc')
    title = post.get('title', '').lower()
    body = post.get('body', '').lower()
    img_text = post.get('img_text', '').lower() if post.get('img_text') else ''
    flair = post.get('link_flair_text', '').lower() if post.get('link_flair_text') else ''

    # Calculate age in days
    age_seconds = (datetime.datetime.now(datetime.timezone.utc) - created_utc).total_seconds()
    age_days = age_seconds / (60 * 60 * 24)

    # Base score
    base_score = (upvotes + comments) / max(1, age_days)

    # Bonuses
    keyword_bonus = 0
    # Include img_text in keyword search
    combined_text = f"{title} {body} {img_text}"
    if any(keyword in combined_text for keyword in ['dating', 'relationship', 'texting']):
        keyword_bonus = 2

    flair_bonus = 0
    if any(f == flair for f in ['advice', 'question']):
        flair_bonus = 1

    total_score = base_score + keyword_bonus + flair_bonus

    return total_score

def main():
    config = load_config()
    db_config = config.get('database', {})

    if not db_config:
        print("Database configuration not found in config.yaml.")
        return

    conn = None
    try:
        conn = get_db_connection(db_config)
        cur = conn.cursor()

        # Fetch unprocessed posts
        select_query = "SELECT id, created_utc, title, body, img_text, score, num_comments, link_flair_text FROM posts_raw WHERE processed = FALSE;"
        cur.execute(select_query)
        unprocessed_posts = cur.fetchall()

        print(f"Found {len(unprocessed_posts)} unprocessed posts to score.")

        for post_row in unprocessed_posts:
            # Convert row to dictionary for easier access
            # Assumes the order of columns in the select_query
            post = {
                'id': post_row[0],
                'created_utc': post_row[1],
                'title': post_row[2],
                'body': post_row[3],
                'img_text': post_row[4],
                'score': post_row[5],
                'num_comments': post_row[6],
                'link_flair_text': post_row[7]
            }

            total_score = calculate_score(post)

            # Update post with total score and set processed to TRUE
            update_query = sql.SQL("""
                UPDATE posts_raw
                SET score_total = %s, processed = TRUE
                WHERE id = %s;
            """)
            cur.execute(update_query, (total_score, post['id']))

        conn.commit()
        print(f"Scored and processed {len(unprocessed_posts)} posts.")

    except Exception as e:
        print(f"An error occurred during scoring: {e}")
    finally:
        if conn:
            conn.close()
            print("Database connection closed.")

if __name__ == "__main__":
    main() 