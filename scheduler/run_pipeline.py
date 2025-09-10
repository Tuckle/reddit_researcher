import subprocess
import sys
import time
import os
from apscheduler.schedulers.blocking import BlockingScheduler

def run_script(script_path):
    """Runs a Python script using subprocess."""
    print(f"\nRunning {script_path}...")
    # Use sys.executable to ensure the script is run with the same Python interpreter
    result = subprocess.run([sys.executable, script_path], capture_output=True, text=True)
    print(f"--- {script_path} Output ---")
    print(result.stdout)
    if result.stderr:
        print(f"--- {script_path} Error ---")
        print(result.stderr)
    print(f"--- Finished {script_path} ---")

    if result.returncode != 0:
        print(f"Error: {script_path} failed with return code {result.returncode}")
        # Depending on requirements, you might want to exit or handle the error differently
        # For now, we'll just print a warning.

def run_full_pipeline():
    """Runs the complete data processing and email digest pipeline."""
    print("\nStarting the full data pipeline...")
    
    # Get the directory where this script is located and go up one level to reddit_researcher
    script_dir = os.path.dirname(os.path.abspath(__file__))
    reddit_researcher_dir = os.path.dirname(script_dir)
    
    # Define the paths to your scripts relative to the reddit_researcher directory
    script_names = [
        'ingestor/ingest.py',
        'scorer/score_posts.py',
        'processing/generate_embeddings.py',
        'processing/process_posts.py',
        'email_digest/send_digest.py'
    ]
    
    scripts = [os.path.join(reddit_researcher_dir, script_name) for script_name in script_names]

    for script in scripts:
        run_script(script)
        # Add a small delay between scripts if needed
        # time.sleep(1)

    print("\nFull data pipeline finished.")

def main():
    print("Starting the Reddit Researcher Scheduler...")
    scheduler = BlockingScheduler()

    # Schedule the full pipeline job
    # Example: Run the pipeline daily at 3:00 AM
    scheduler.add_job(run_full_pipeline, 'cron', hour=3, minute=0)

    print("Scheduler started. Press Ctrl+C to exit.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass # Handle manual interruption

if __name__ == "__main__":
    # You can also run the pipeline manually for testing:
    # run_full_pipeline()

    main() 