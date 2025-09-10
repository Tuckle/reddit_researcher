import psycopg2
import yaml
import os
from psycopg2 import sql
from sentence_transformers import SentenceTransformer
import numpy as np
import hdbscan
import pandas as pd # Using pandas DataFrames can make handling fetched data easier
import ast # Import the ast module

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

    # Load Sentence Transformer model (only needed if re-generating embeddings)
    # In this clustering step, we assume embeddings are already generated.
    # try:
    #     model = SentenceTransformer('all-MiniLM-L6-v2')
    #     print("Sentence-Transformer model loaded.")
    # except Exception as e:
    #     print(f"Error loading Sentence-Transformer model: {e}")
    #     print("Please ensure you have an internet connection or the model is cached locally.")
    #     return

    conn = None
    try:
        conn = get_db_connection(db_config)
        cur = conn.cursor()

        # Fetch processed and embedded but not yet clustered posts
        # We need id, title, body, img_text, vector, and score_total
        select_query = "SELECT id, title, body, img_text, vector, score_total FROM posts_raw WHERE processed = TRUE AND vector IS NOT NULL AND clustered = FALSE;"
        cur.execute(select_query)
        posts_to_cluster = cur.fetchall()

        print(f"Found {len(posts_to_cluster)} posts to cluster.")

        if not posts_to_cluster:
            print("No posts to process for clustering.")
            return
            
        # Convert fetched data to a pandas DataFrame for easier handling
        df = pd.DataFrame(posts_to_cluster, columns=['id', 'title', 'body', 'img_text', 'vector', 'score_total'])

        # Explicitly convert vector string representation to list of floats
        try:
            df['vector'] = df['vector'].apply(lambda x: ast.literal_eval(x) if isinstance(x, str) else x)
        except (ValueError, SyntaxError) as e:
            print(f"Error evaluating vector string: {e}. Skipping clustering.")
            # Optionally mark these posts with an error flag or skip for now
            # For now, we'll just return
            return

        # Convert vector column (list of floats) to numpy array for HDBSCAN
        # Handle case with a single sample
        if len(df) == 1:
            embeddings = np.array(df['vector'].tolist()).reshape(1, -1)
        else:
            embeddings = np.array(df['vector'].tolist())

        # Apply HDBSCAN clustering
        print("Applying HDBSCAN clustering...")
        # You might need to tune min_cluster_size and min_samples based on your data
        clusterer = hdbscan.HDBSCAN(min_cluster_size=5, min_samples=None, metric='euclidean')

        # Check for minimum number of samples AFTER initializing the clusterer
        if len(posts_to_cluster) < clusterer.min_cluster_size:
             print(f"Not enough posts ({len(posts_to_cluster)}) to perform clustering with min_cluster_size={clusterer.min_cluster_size}.")
             # Optionally mark these posts as clustered to avoid reprocessing, or handle differently
             # For now, we'll just skip clustering and leave them for future runs
             # Mark posts as clustered to avoid reprocessing in the future
             post_ids_to_mark = [post[0] for post in posts_to_cluster]
             update_clustered_query = sql.SQL("""
                 UPDATE posts_raw
                 SET clustered = TRUE
                 WHERE id IN %s;
             """)
             cur.execute(update_clustered_query, (tuple(post_ids_to_mark),))
             conn.commit()
             print(f"Marked {len(post_ids_to_mark)} posts as clustered (skipped clustering due to low count).")
             return

        cluster_labels = clusterer.fit_predict(embeddings)
        print(f"Clustering finished. Found {len(set(cluster_labels)) - (1 if -1 in cluster_labels else 0)} clusters.")

        df['cluster_label'] = cluster_labels

        # Process clusters and update database
        print("Processing clusters and updating database...")
        theme_update_query = sql.SQL("""
            INSERT INTO themes (theme_text, vector, example_post_ids, score_agg, status)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING theme_id;
        """)

        post_update_query = sql.SQL("""
            UPDATE posts_raw
            SET theme_id = %s, clustered = TRUE
            WHERE id = %s;
        """)

        # Process each cluster
        for cluster_label in set(cluster_labels):
            # Get posts belonging to this cluster
            cluster_posts = df[df['cluster_label'] == cluster_label]

            if cluster_label == -1:
                # Handle noise points: treat each noise point as its own theme
                print(f"Processing {len(cluster_posts)} noise points (cluster -1)...")
                for index, post in cluster_posts.iterrows():
                    theme_text = post['title'] # Use post title as theme text for noise
                    theme_vector = post['vector']
                    example_post_ids = [post['id']]
                    score_agg = post['score_total'] # Use post score as theme score for noise

                    # Insert into themes table
                    cur.execute(theme_update_query, (theme_text, theme_vector, example_post_ids, score_agg, 'open'))
                    theme_id = cur.fetchone()[0]

                    # Update posts_raw table
                    cur.execute(post_update_query, (theme_id, post['id']))

            else:
                # Handle actual clusters
                print(f"Processing cluster {cluster_label} with {len(cluster_posts)} posts...")
                # Determine representative theme text (e.g., title of highest scoring post)
                representative_post = cluster_posts.loc[cluster_posts['score_total'].idxmax()]
                theme_text = representative_post['title']
                theme_vector = np.mean(cluster_posts['vector'].tolist(), axis=0).tolist() # Mean vector of cluster
                example_post_ids = cluster_posts['id'].tolist()
                score_agg = cluster_posts['score_total'].mean() # Mean score of cluster

                # Insert into themes table
                cur.execute(theme_update_query, (theme_text, theme_vector, example_post_ids, score_agg, 'open'))
                theme_id = cur.fetchone()[0]

                # Update posts_raw table for all posts in the cluster
                for post_id in example_post_ids:
                     cur.execute(post_update_query, (theme_id, post_id))

        conn.commit()
        print("Database updated with clustering results.")

    except Exception as e:
        print(f"An error occurred during clustering: {e}")
        if conn:
            conn.rollback() # Roll back changes if an error occurs
    finally:
        if conn:
            conn.close()
            print("Database connection closed.")

if __name__ == "__main__":
    main() 