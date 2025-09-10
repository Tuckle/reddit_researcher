# exit()
import sys
import os
import datetime
import psycopg2
from psycopg2 import sql
import requests
import easyocr
import time # Needed for rate limiting delays

# Add the parent directory to the path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables first
import load_env

# Import configuration
from config import (
    get_database_config,
    get_reddit_api_config,
    get_subreddits,
    get_db_connection_dict
)

# Initialize EasyOCR reader (languages can be configured)
reader = easyocr.Reader(['en'])

def get_db_connection(db_config_dict):
    """Create database connection from config dictionary"""
    conn = psycopg2.connect(
        dbname=db_config_dict['dbname'],
        user=db_config_dict['user'],
        password=db_config_dict['password'],
        host=db_config_dict.get('host', 'localhost'),
        port=db_config_dict.get('port', 5432)
    )
    return conn

def extract_text_from_image(image_url):
    """Downloads an image and extracts text using EasyOCR."""
    img_text = None
    temp_image_path = None  # Initialize to None so it's always defined
    
    if not image_url or not isinstance(image_url, str):
        return None

    # Basic check if it looks like an image URL (can be improved)
    if not any(image_url.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif']):
        return None

    try:
        # Download the image
        response = requests.get(image_url, stream=True)
        response.raise_for_status() # Raise an exception for bad status codes

        # Save the image temporarily
        # Using a simple temporary filename. In production, consider more robust temp file handling.
        temp_image_path = f"temp_image_{os.path.basename(image_url)}"
        with open(temp_image_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        # Perform OCR
        result = reader.readtext(temp_image_path)

        # Extract text from the result
        extracted_texts = [text[1] for text in result]
        img_text = "\n".join(extracted_texts)

        # Clean up the temporary file
        os.remove(temp_image_path)

    except requests.exceptions.RequestException as e:
        print(f"Error downloading image {image_url}: {e}")
    except Exception as e:
        print(f"Error during OCR processing for {image_url}: {e}")
    finally:
        # Ensure the temporary file is removed even if errors occur
        if temp_image_path and os.path.exists(temp_image_path):
            os.remove(temp_image_path)

    return img_text

def ingest_with_reddit_api(db_config_dict):
    """Alternative ingestion using official Reddit API (PRAW)"""
    reddit_config = get_reddit_api_config()

    if not reddit_config.client_id or not reddit_config.client_secret:
        print("Reddit API configuration not found or incomplete.")
        print("Please check REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET environment variables.")
        return False

    # Initialize Reddit API
    import praw
    reddit = praw.Reddit(
        client_id=reddit_config.client_id,
        client_secret=reddit_config.client_secret,
        user_agent=reddit_config.user_agent
    )

    print("Using Reddit API (PRAW) for ingestion...")

    conn = None
    try:
        conn = get_db_connection(db_config_dict)
        cur = conn.cursor()

        subreddits = get_subreddits()

        # --- Ingest recent posts (newest first, stop when processed) ---
        print("\n--- Ingesting recent posts (newest first) ---")
        three_days_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=3)

        for subreddit_name in subreddits:
            print(f"Fetching new posts from r/{subreddit_name}...")
            count = 0
            skipped_existing_users = 0
            replaced_posts = 0
            # Fetch 'new' posts, limit to a reasonable number to avoid excessive fetching
            # We will stop early if we find an already processed post
            try:
                subreddit = reddit.subreddit(subreddit_name)
                for submission in subreddit.new(limit=2000): # Increased limit to fetch more potential new posts

                    # Check if post is older than 3 days
                    created_time = datetime.datetime.fromtimestamp(submission.created_utc, tz=datetime.timezone.utc)
                    if created_time < three_days_ago:
                        print(f"Post {submission.id} is older than 3 days. Stopping 'new' ingestion for r/{subreddit_name}.")
                        break # Stop if post is older than 3 days

                    # Check if the post ID already exists in the database
                    cur.execute(sql.SQL("SELECT 1 FROM posts_raw WHERE id = %s;"), (submission.id,))
                    if cur.fetchone():
                        print(f"Post {submission.id} already exists. Stopping 'new' ingestion for r/{subreddit_name}.")
                        break # Stop if post is already processed

                    # Get author information
                    author = submission.author
                    if author is None:
                        print(f"Post {submission.id} has no author (deleted user). Skipping.")
                        continue

                    author_username = author.name
                    # Use the actual Reddit user ID from the API instead of constructing it
                    try:
                        author_id = author.fullname  # This gives the actual Reddit ID like "t2_xxxxx"
                    except AttributeError:
                        # Fallback to constructed ID if fullname is not available
                        author_id = f"t2_{author.name}"
                    
                    # Ensure author_id is not too long for the database
                    if len(author_id) > 50:
                        print(f"Author ID too long ({len(author_id)} chars): {author_id[:50]}... Skipping post {submission.id}.")
                        continue

                    # Check if we already have a post from this user in the database
                    cur.execute(sql.SQL("SELECT id, status, title, subreddit FROM posts_raw WHERE author_id = %s;"), (author_id,))
                    existing_post = cur.fetchone()
                    
                    if existing_post:
                        existing_post_id, existing_status, existing_title, existing_subreddit = existing_post
                        
                        # If existing post has status 'sent', 'selected', or 'answered', keep the old post
                        if existing_status in ['sent', 'selected', 'answered']:
                            print(f"User {author_username} already has a post with protected status '{existing_status}' (ID: {existing_post_id}). Skipping new post {submission.id}.")
                            skipped_existing_users += 1
                            continue
                        
                        # Check if the posts are identical (same username, title, and subreddit)
                        if (existing_title == submission.title and 
                            existing_subreddit == submission.subreddit.display_name):
                            print(f"User {author_username} already has identical post (same title and subreddit). Skipping duplicate {submission.id}.")
                            skipped_existing_users += 1
                            continue
                        
                        # Otherwise, delete the existing post to replace it with the new one
                        print(f"Replacing existing post {existing_post_id} (status: {existing_status}) from user {author_username} with new post {submission.id}.")
                        cur.execute(sql.SQL("DELETE FROM posts_raw WHERE id = %s;"), (existing_post_id,))
                        replaced_posts += 1

                    # Check if user exists in users table using the same author_id, if not create them
                    cur.execute(sql.SQL("SELECT 1 FROM users WHERE id = %s;"), (author_id,))
                    if not cur.fetchone():
                        # Get additional author information if available
                        author_created_utc = None
                        comment_karma = None
                        link_karma = None
                        is_verified = False

                        try:
                            # These attributes might not be available for all users
                            if hasattr(author, 'created_utc'):
                                author_created_utc = datetime.datetime.fromtimestamp(author.created_utc, tz=datetime.timezone.utc)
                            if hasattr(author, 'comment_karma'):
                                comment_karma = author.comment_karma
                            if hasattr(author, 'link_karma'):
                                link_karma = author.link_karma
                            if hasattr(author, 'has_verified_email'):
                                is_verified = author.has_verified_email
                        except Exception as e:
                            print(f"Warning: Could not fetch all author details for {author_username}: {e}")

                        # Insert user into users table
                        user_data = (
                            author_id,
                            author_username,
                            author_created_utc,
                            comment_karma,
                            link_karma,
                            is_verified
                        )

                        try:
                            insert_user_query = sql.SQL("""
                                INSERT INTO users (id, username, created_utc, comment_karma, link_karma, is_verified)
                                VALUES (%s, %s, %s, %s, %s, %s)
                                ON CONFLICT (id) DO UPDATE SET
                                    username = EXCLUDED.username,
                                    created_utc = COALESCE(EXCLUDED.created_utc, users.created_utc),
                                    comment_karma = COALESCE(EXCLUDED.comment_karma, users.comment_karma),
                                    link_karma = COALESCE(EXCLUDED.link_karma, users.link_karma),
                                    is_verified = COALESCE(EXCLUDED.is_verified, users.is_verified);
                            """)
                            cur.execute(insert_user_query, user_data)
                        except Exception as e:
                            # If there's still a username conflict, rollback and skip this entire post
                            if "users_username_key" in str(e):
                                print(f"Username {author_username} already exists with different ID. Skipping post {submission.id}.")
                                conn.rollback()  # Rollback the transaction
                                continue  # Skip this entire post
                            else:
                                print(f"Error inserting user {author_username}: {e}")
                                conn.rollback()  # Rollback the transaction on error
                                continue

                    # Process the new submission
                    img_text = None
                    is_image_post = (hasattr(submission, 'post_hint') and
                                   submission.post_hint == 'image') or \
                                  any(submission.url.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif'])

                    if is_image_post:
                        print(f"Processing image post: {submission.url}")
                        img_text = extract_text_from_image(submission.url)
                        if img_text:
                            print(f"Extracted text: {img_text[:100]}...")

                    # Prepare data for insertion
                    post_data = (
                        submission.id,
                        submission.subreddit.display_name,
                        created_time,
                        submission.title,
                        submission.selftext or '',
                        img_text,
                        submission.link_flair_text,
                        submission.score,
                        submission.num_comments,
                        f"https://reddit.com{submission.permalink}",
                        author_id  # Add author_id to the post data
                    )

                    # Insert into posts_raw
                    try:
                        insert_query = sql.SQL("""
                            INSERT INTO posts_raw (id, subreddit, created_utc, title, body, img_text, link_flair_text, score, num_comments, url, author_id)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (id) DO NOTHING;
                        """)
                        cur.execute(insert_query, post_data)
                        count += 1
                    except Exception as e:
                        print(f"Error inserting post {submission.id} from user {author_username}: {e}")
                        conn.rollback()  # Rollback the transaction on error
                        continue

                conn.commit()
                print(f"Finished fetching {count} new posts from r/{subreddit_name}.")
                if skipped_existing_users > 0:
                    print(f"Skipped {skipped_existing_users} posts from users with protected status ('sent', 'selected', 'answered').")
                if replaced_posts > 0:
                    print(f"Replaced {replaced_posts} posts from users who already have posts in database.")

            except Exception as e:
                print(f"Error accessing subreddit r/{subreddit_name} for new posts: {e}")
                # If it's a rate limiting error, add a delay before continuing
                if "429" in str(e) or "rate" in str(e).lower():
                    print(f"Rate limiting detected for r/{subreddit_name}. Waiting 60 seconds before continuing...")
                    time.sleep(60)
                conn.rollback() # Rollback changes for this subreddit

        return True

    except Exception as e:
        print(f"An error occurred with Reddit API ingestion: {e}")
        return False
    finally:
        if conn:
            conn.close()

def ingest_with_pushshift(db_config_dict):
    """Original ingestion using Pushshift API - Kept as fallback, but primary logic is in PRAW"""
    # This function is kept as a fallback but is not modified to match the new requirements
    # as the PRAW method is preferred and implemented above.
    from psaw import PushshiftAPI
    api = PushshiftAPI()

    print("Attempting Pushshift API ingestion (fallback)...")

    conn = None
    try:
        conn = get_db_connection(db_config_dict)
        cur = conn.cursor()

        # Calculate timestamp for 3 days ago
        three_days_ago = int((datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=3)).timestamp())

        subreddits = get_subreddits()

        for subreddit in subreddits:
            print(f"Fetching posts from r/{subreddit}...")
            # Fetch posts from the last 3 days, including 'is_video' and 'url' to check for images
            submissions = api.search_submissions(
                subreddit=subreddit,
                after=three_days_ago,
                filter=['id', 'subreddit', 'created_utc', 'title', 'selftext', 'score', 'num_comments', 'full_link', 'link_flair_text', 'is_video', 'url', 'author'],
                limit=1000 # Added a limit for Pushshift fallback
            )

            count = 0
            skipped_existing_users = 0
            replaced_posts = 0
            for submission in submissions:
                try:
                    # Check if the post ID already exists in the database (added check here too)
                    cur.execute(sql.SQL("SELECT 1 FROM posts_raw WHERE id = %s;"), (submission.id,))
                    if cur.fetchone():
                        # print(f"Pushshift: Post {getattr(submission, 'id', 'N/A')} already exists. Skipping.") # Too verbose
                        continue # Skip if post is already processed

                    # Get author information from Pushshift (limited data)
                    author_username = getattr(submission, 'author', None)
                    if not author_username or author_username == '[deleted]':
                        print(f"Pushshift: Post {submission.id} has no author or deleted user. Skipping.")
                        continue

                    # For Pushshift, we have to construct the ID since we don't have access to fullname
                    author_id = f"t2_{author_username}"
                    
                    # Ensure author_id is not too long for the database
                    if len(author_id) > 50:
                        print(f"Pushshift: Author ID too long ({len(author_id)} chars): {author_id[:50]}... Skipping post {submission.id}.")
                        continue

                    # Check if we already have a post from this user in the database
                    cur.execute(sql.SQL("SELECT id, status, title, subreddit FROM posts_raw WHERE author_id = %s;"), (author_id,))
                    existing_post = cur.fetchone()
                    
                    if existing_post:
                        existing_post_id, existing_status, existing_title, existing_subreddit = existing_post
                        
                        # If existing post has status 'sent', 'selected', or 'answered', keep the old post
                        if existing_status in ['sent', 'selected', 'answered']:
                            print(f"User {author_username} already has a post with protected status '{existing_status}' (ID: {existing_post_id}). Skipping new post {submission.id}.")
                            skipped_existing_users += 1
                            continue
                        
                        # Check if the posts are identical (same username, title, and subreddit)
                        if (existing_title == submission.title and 
                            existing_subreddit == submission.subreddit.display_name):
                            print(f"User {author_username} already has identical post (same title and subreddit). Skipping duplicate {submission.id}.")
                            skipped_existing_users += 1
                            continue
                        
                        # Otherwise, delete the existing post to replace it with the new one
                        print(f"Replacing existing post {existing_post_id} (status: {existing_status}) from user {author_username} with new post {submission.id}.")
                        cur.execute(sql.SQL("DELETE FROM posts_raw WHERE id = %s;"), (existing_post_id,))
                        replaced_posts += 1

                    # Check if user exists in users table using the same author_id, if not create them
                    cur.execute(sql.SQL("SELECT 1 FROM users WHERE id = %s;"), (author_id,))
                    if not cur.fetchone():
                        # Insert user into users table (with limited Pushshift data)
                        user_data = (
                            author_id,
                            author_username,
                            None,  # created_utc not available from Pushshift
                            None,  # comment_karma not available from Pushshift
                            None,  # link_karma not available from Pushshift
                            False  # is_verified not available from Pushshift
                        )

                        try:
                            insert_user_query = sql.SQL("""
                                INSERT INTO users (id, username, created_utc, comment_karma, link_karma, is_verified)
                                VALUES (%s, %s, %s, %s, %s, %s)
                                ON CONFLICT (id) DO UPDATE SET
                                    username = EXCLUDED.username,
                                    created_utc = COALESCE(EXCLUDED.created_utc, users.created_utc),
                                    comment_karma = COALESCE(EXCLUDED.comment_karma, users.comment_karma),
                                    link_karma = COALESCE(EXCLUDED.link_karma, users.link_karma),
                                    is_verified = COALESCE(EXCLUDED.is_verified, users.is_verified);
                            """)
                            cur.execute(insert_user_query, user_data)
                        except Exception as e:
                            # If there's still a username conflict, rollback and skip this entire post
                            if "users_username_key" in str(e):
                                print(f"Username {author_username} already exists with different ID. Skipping post {submission.id}.")
                                conn.rollback()  # Rollback the transaction
                                continue  # Skip this entire post
                            else:
                                print(f"Error inserting user {author_username}: {e}")
                                conn.rollback()  # Rollback the transaction on error
                                continue

                    img_text = None
                    # Check if the submission is potentially an image post
                    is_image_post = not getattr(submission, 'is_video', False) and any(getattr(submission, 'url', '').lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif'])

                    if is_image_post:
                        # print(f"Pushshift: Processing image post: {getattr(submission, 'full_link', 'N/A')}") # Too verbose
                        img_text = extract_text_from_image(getattr(submission, 'url', None))
                        # if img_text: # Too verbose
                            # print(f"Pushshift: Extracted text: {img_text[:100]}...")

                    # Prepare data for insertion
                    post_data = (
                        submission.id,
                        submission.subreddit,
                        datetime.datetime.fromtimestamp(submission.created_utc, tz=datetime.timezone.utc),
                        submission.title,
                        getattr(submission, 'selftext', ''),
                        img_text,
                        getattr(submission, 'link_flair_text', None),
                        submission.score,
                        submission.num_comments,
                        submission.full_link,
                        author_id  # Add author_id to the post data
                    )

                    # Insert into posts_raw, ignore if ID already exists
                    try:
                        insert_query = sql.SQL("""
                            INSERT INTO posts_raw (id, subreddit, created_utc, title, body, img_text, link_flair_text, score, num_comments, url, author_id)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (id) DO NOTHING;
                        """)
                        cur.execute(insert_query, post_data)
                        count += 1
                    except Exception as e:
                        print(f"Error inserting post {submission.id} from user {author_username}: {e}")
                        conn.rollback()  # Rollback the transaction on error
                        continue
                except Exception as e:
                    print(f"Pushshift: Error processing submission {getattr(submission, 'id', 'N/A')}: {e}")

            conn.commit()
            print(f"Pushshift: Finished fetching {count} posts from r/{subreddit}.")
            if skipped_existing_users > 0:
                print(f"Pushshift: Skipped {skipped_existing_users} posts from users with protected status ('sent', 'selected', 'answered').")
            if replaced_posts > 0:
                print(f"Pushshift: Replaced {replaced_posts} posts from users who already have posts in database.")

        return True

    except Exception as e:
        print(f"An error occurred with Pushshift: {e}")
        return False
    finally:
        if conn:
            conn.close()

def cleanup_old_posts(db_config_dict):
    """Delete posts older than 5 days unless they have status 'selected', 'answered', 'sent', or 'lead'"""
    conn = None
    try:
        conn = get_db_connection(db_config_dict)
        cur = conn.cursor()
        
        # Calculate timestamp for 5 days ago
        five_days_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=5)
        
        print(f"\nCleaning up posts older than {five_days_ago.strftime('%Y-%m-%d %H:%M:%S UTC')} that are not marked as 'selected', 'answered', 'sent', or 'lead'...")
        
        # First, count how many posts will be deleted for reporting
        count_query = sql.SQL("""
            SELECT COUNT(*) FROM posts_raw 
            WHERE created_utc < %s 
            AND (status IS NULL OR (status NOT IN ('selected', 'answered', 'sent', 'lead')));
        """)
        cur.execute(count_query, (five_days_ago,))
        posts_to_delete = cur.fetchone()[0]
        
        if posts_to_delete > 0:
            # Delete posts older than 5 days that are not marked as protected
            delete_query = sql.SQL("""
                DELETE FROM posts_raw 
                WHERE created_utc < %s 
                AND (status IS NULL OR (status NOT IN ('selected', 'answered', 'sent', 'lead')));
            """)
            cur.execute(delete_query, (five_days_ago,))
            conn.commit()
            
            print(f"Successfully deleted {posts_to_delete} old posts (not marked as 'selected', 'answered', 'sent', or 'lead').")
        else:
            print("No old posts found to delete.")
            
        return True
        
    except Exception as e:
        print(f"Error during cleanup: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def main():
    try:
        # Load configuration from environment variables
        db_config = get_db_connection_dict()
        subreddits = get_subreddits()

        if not subreddits:
            print("No subreddits found in configuration. Please check SUBREDDITS environment variable.")
            return

        if not db_config or not db_config.get('dbname'):
            print("Database configuration not found. Please check your environment variables.")
            return

        print(f"Starting ingestion for subreddits: {', '.join(subreddits)}")

        # Try Reddit API first, fallback to Pushshift
        success = ingest_with_reddit_api(db_config)

        if not success:
            print("\nReddit API failed, trying Pushshift as fallback...")
            success = ingest_with_pushshift(db_config)

        if success:
            print("Ingestion completed successfully!")
            
            # After successful ingestion, cleanup old posts
            cleanup_success = cleanup_old_posts(db_config)
            if cleanup_success:
                print("Post cleanup completed successfully!")
            else:
                print("Post cleanup encountered errors.")
        else:
            print("Both Reddit API and Pushshift failed. Please check your configuration.")
            
    except Exception as e:
        print(f"Error in main: {e}")
        return False

if __name__ == "__main__":
    main()
