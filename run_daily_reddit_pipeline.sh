#!/bin/bash

# Reddit Pipeline Daily Runner
# Runs data ingestion followed by Gemini analysis
# Miami time: 12 PM and 7 PM daily

# Function to update pipeline status in database
update_pipeline_status() {
    local action=$1
    local timestamp=$(date -u +"%Y-%m-%d %H:%M:%S")
    
    python3 -c "
import sys
import os
import psycopg2
from datetime import datetime, timezone

# Add the reddit_researcher directory to Python path
sys.path.append('reddit_researcher')

# Change to the project directory for proper imports
os.chdir('/Users/Tuckle/Projects/misc/gaimaw')

try:
    # Load environment variables
    sys.path.append('reddit_researcher')
    import load_env
    
    # Import configuration
    from config import get_db_connection_dict
    
    db_config = get_db_connection_dict()
    
    conn = psycopg2.connect(
        dbname=db_config['dbname'],
        user=db_config['user'],
        password=db_config['password'],
        host=db_config['host'],
        port=db_config['port']
    )
    cur = conn.cursor()
    
    if '$action' == 'start':
        cur.execute('''
            INSERT INTO pipeline_status (id, last_run_timestamp, is_running) 
            VALUES (1, %s, TRUE)
            ON CONFLICT (id) 
            DO UPDATE SET 
                last_run_timestamp = EXCLUDED.last_run_timestamp,
                is_running = TRUE;
        ''', (datetime.now(timezone.utc),))
        print('Pipeline status: STARTED')
    elif '$action' == 'complete':
        cur.execute('''
            INSERT INTO pipeline_status (id, last_completion_timestamp, is_running) 
            VALUES (1, %s, FALSE)
            ON CONFLICT (id) 
            DO UPDATE SET 
                last_completion_timestamp = EXCLUDED.last_completion_timestamp,
                is_running = FALSE;
        ''', (datetime.now(timezone.utc),))
        print('Pipeline status: COMPLETED')
    elif '$action' == 'failed':
        cur.execute('''
            INSERT INTO pipeline_status (id, is_running) 
            VALUES (1, FALSE)
            ON CONFLICT (id) 
            DO UPDATE SET is_running = FALSE;
        ''')
        print('Pipeline status: FAILED - marked as not running')
    
    conn.commit()
    conn.close()
except Exception as e:
    print(f'Error updating pipeline status: {e}')
"
}

# Function to cleanup on exit (called on any exit - success, failure, or interruption)
cleanup_on_exit() {
    echo "============================================================" | tee -a "$LOG_FILE"
    echo "Pipeline cleanup triggered at $(date)" | tee -a "$LOG_FILE"
    
    # Always mark pipeline as not running when script exits
    if [ $? -eq 0 ]; then
        echo "Pipeline completed successfully" | tee -a "$LOG_FILE"
        update_pipeline_status "complete"
    else
        echo "Pipeline failed or was interrupted" | tee -a "$LOG_FILE"
        update_pipeline_status "failed"
    fi
    
    echo "============================================================" | tee -a "$LOG_FILE"
}

# Set up signal handlers for graceful shutdown
trap cleanup_on_exit EXIT
trap 'echo "Received SIGINT (Ctrl+C)" | tee -a "$LOG_FILE"; exit 130' INT
trap 'echo "Received SIGTERM" | tee -a "$LOG_FILE"; exit 143' TERM

# Change to the project directory
cd /Users/Tuckle/Projects/misc/gaimaw

# Create logs directory if it doesn't exist in reddit_researcher
mkdir -p reddit_researcher/logs

# Set up logging with timestamp in the reddit_researcher/logs directory
TIMESTAMP=$(date '+%Y-%m-%d_%H-%M-%S')
LOG_FILE="reddit_researcher/logs/reddit_pipeline_$TIMESTAMP.log"

echo "============================================================" | tee -a "$LOG_FILE"
echo "Reddit Pipeline Started at $(date)" | tee -a "$LOG_FILE"
echo "============================================================" | tee -a "$LOG_FILE"

# Mark pipeline as started in database
update_pipeline_status "start"

# Run ingest.py
echo "Starting Reddit data ingestion..." | tee -a "$LOG_FILE"
/Users/Tuckle/Projects/misc/gaimaw/venv/bin/python reddit_researcher/ingestor/ingest.py >> "$LOG_FILE" 2>&1

INGEST_EXIT_CODE=$?
if [ $INGEST_EXIT_CODE -eq 0 ]; then
    echo "✅ Ingestion completed successfully" | tee -a "$LOG_FILE"
else
    echo "❌ Ingestion failed with exit code $INGEST_EXIT_CODE" | tee -a "$LOG_FILE"
    echo "❌ Skipping Gemini analysis due to ingestion failure" | tee -a "$LOG_FILE"
    exit $INGEST_EXIT_CODE
fi

echo "------------------------------------------------------------" | tee -a "$LOG_FILE"

# Run Gemini analysis
echo "Starting Gemini analysis..." | tee -a "$LOG_FILE"
/Users/Tuckle/Projects/misc/gaimaw/venv/bin/python reddit_researcher/processing/run_gemini_analysis.py >> "$LOG_FILE" 2>&1

ANALYSIS_EXIT_CODE=$?
if [ $ANALYSIS_EXIT_CODE -eq 0 ]; then
    echo "✅ Gemini analysis completed successfully" | tee -a "$LOG_FILE"
else
    echo "❌ Gemini analysis failed with exit code $ANALYSIS_EXIT_CODE" | tee -a "$LOG_FILE"
fi

echo "------------------------------------------------------------" | tee -a "$LOG_FILE"

# Clean up log files older than 2 days to prevent disk space issues
echo "Cleaning up old log files..."
DELETED_COUNT=$(find reddit_researcher/logs -name "reddit_pipeline_*.log" -mtime +2 -type f 2>/dev/null | wc -l)
find reddit_researcher/logs -name "reddit_pipeline_*.log" -mtime +2 -type f -delete 2>/dev/null
if [ $DELETED_COUNT -gt 0 ]; then
    echo "Deleted $DELETED_COUNT log files older than 2 days"
else
    echo "No old log files to clean up"
fi

# Exit with the analysis exit code (cleanup_on_exit will be called automatically)
exit $ANALYSIS_EXIT_CODE 