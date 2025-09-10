import streamlit as st
import psycopg2
import os
import subprocess
import threading
import time
from psycopg2 import sql
import pandas as pd
import datetime
import smtplib
from email.mime.text import MIMEText
import pytz
import sys
from functools import wraps

# Add the parent directory to the path to import services and config
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Load environment variables first
import load_env

# Import configuration and services
from config import (
    get_database_config, 
    get_email_config, 
    get_google_sheets_config,
    get_processing_config,
    get_db_connection_dict
)
from services.google_sheets_service import GoogleSheetsService

# Cache configuration from centralized config
processing_config = get_processing_config()
CACHE_TTL = processing_config['cache_ttl']
STATS_CACHE_TTL = processing_config['stats_cache_ttl']

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

def run_pipeline_script():
    """Run the daily Reddit pipeline script in background"""
    try:
        # Get the absolute path to the script - it's in the reddit_researcher directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))
        script_path = os.path.join(script_dir, '..', 'run_daily_reddit_pipeline.sh')
        script_path = os.path.abspath(script_path)
        
        # Debug: print the path being used
        print(f"Looking for script at: {script_path}")
        
        # Check if script exists
        if not os.path.exists(script_path):
            st.error(f"Pipeline script not found at: {script_path}")
            return False
        
        # Make sure the script is executable
        os.chmod(script_path, 0o755)
        
        # Run the script in background and capture the process
        process = subprocess.Popen([script_path], 
                        cwd=project_root,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True)
        
        # Store the PID in the database for tracking
        db_config = get_db_connection_dict()
        if db_config:
            store_pipeline_pid(db_config, process.pid)
        
        return True
    except Exception as e:
        st.error(f"Error running pipeline: {e}")
        return False

def store_pipeline_pid(db_config, pid):
    """Store the pipeline process ID in database"""
    try:
        conn = get_db_connection(db_config)
        cur = conn.cursor()
        
        # Add PID column if it doesn't exist
        try:
            cur.execute("ALTER TABLE pipeline_status ADD COLUMN IF NOT EXISTS process_pid INTEGER;")
        except:
            pass
        
        # Update with PID
        cur.execute("""
            INSERT INTO pipeline_status (id, process_pid) 
            VALUES (1, %s)
            ON CONFLICT (id) 
            DO UPDATE SET process_pid = EXCLUDED.process_pid;
        """, (pid,))
        
        conn.commit()
        conn.close()
        print(f"Stored pipeline PID: {pid}")
        
    except Exception as e:
        print(f"Error storing pipeline PID: {e}")

def is_process_running(pid):
    """Check if a process with given PID is still running and not a zombie"""
    if not pid:
        return False
    
    try:
        import psutil
        if psutil.pid_exists(pid):
            try:
                process = psutil.Process(pid)
                # Check if process is zombie/defunct
                if process.status() == psutil.STATUS_ZOMBIE:
                    return False
                # Check if it's actually our pipeline process
                cmdline = ' '.join(process.cmdline())
                if 'run_daily_reddit_pipeline' in cmdline or 'ingest.py' in cmdline or 'run_gemini_analysis.py' in cmdline:
                    return True
                else:
                    return False  # PID exists but it's a different process
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return False
        return False
    except ImportError:
        # Fallback method without psutil - check for zombie processes
        try:
            os.kill(pid, 0)  # Send signal 0 to check if process exists
            # Additional check using ps to see if it's zombie
            import subprocess
            try:
                result = subprocess.run(['ps', '-p', str(pid), '-o', 'stat='], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    stat = result.stdout.strip()
                    # Z indicates zombie process
                    if 'Z' in stat or '<defunct>' in stat:
                        return False
                    return True
                return False
            except (subprocess.TimeoutExpired, subprocess.SubprocessError):
                return True  # Assume running if we can't check status
        except (OSError, ProcessLookupError):
            return False

def get_pipeline_status(db_config):
    """Get the pipeline status from database"""
    try:
        conn = get_db_connection(db_config)
        cur = conn.cursor()
        
        # Create pipeline_status table if it doesn't exist with new columns
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_status (
                id INTEGER PRIMARY KEY DEFAULT 1,
                last_run_timestamp TIMESTAMP WITH TIME ZONE,
                is_running BOOLEAN DEFAULT FALSE,
                last_completion_timestamp TIMESTAMP WITH TIME ZONE,
                process_pid INTEGER,
                CONSTRAINT single_row CHECK (id = 1)
            );
        """)
        
        # Add new columns if they don't exist (for existing tables)
        try:
            cur.execute("ALTER TABLE pipeline_status ADD COLUMN IF NOT EXISTS is_running BOOLEAN DEFAULT FALSE;")
            cur.execute("ALTER TABLE pipeline_status ADD COLUMN IF NOT EXISTS last_completion_timestamp TIMESTAMP WITH TIME ZONE;")
            cur.execute("ALTER TABLE pipeline_status ADD COLUMN IF NOT EXISTS process_pid INTEGER;")
        except:
            pass  # Columns might already exist
        
        # Get the pipeline status
        cur.execute("SELECT last_run_timestamp, is_running, last_completion_timestamp, process_pid FROM pipeline_status WHERE id = 1;")
        result = cur.fetchone()
        
        conn.commit()
        conn.close()
        
        if result:
            last_run, is_running, last_completion, process_pid = result
            
            # Validate if the process is actually running
            if is_running and process_pid:
                if not is_process_running(process_pid):
                    print(f"Pipeline marked as running but PID {process_pid} not found or is zombie. Auto-fixing stale state.")
                    # Auto-fix stale state
                    update_pipeline_status(db_config, time.time(), 'failed')
                    is_running = False
                    # Show a notification in Streamlit if available
                    try:
                        import streamlit as st
                        st.warning(f"🔧 Auto-fixed stale pipeline status (PID {process_pid} was not running)")
                    except:
                        pass
            
            return {
                'last_run': last_run.timestamp() if last_run else 0,
                'is_running': is_running or False,
                'last_completion': last_completion.timestamp() if last_completion else 0,
                'process_pid': process_pid
            }
        else:
            return {'last_run': 0, 'is_running': False, 'last_completion': 0, 'process_pid': None}
            
    except Exception as e:
        print(f"Error getting pipeline status: {e}")
        return {'last_run': 0, 'is_running': False, 'last_completion': 0, 'process_pid': None}

def update_pipeline_status(db_config, timestamp, action='start'):
    """Update the pipeline status in database"""
    try:
        conn = get_db_connection(db_config)
        cur = conn.cursor()
        
        if action == 'start':
            # Mark pipeline as started and running
            cur.execute("""
                INSERT INTO pipeline_status (id, last_run_timestamp, is_running) 
                VALUES (1, %s, TRUE)
                ON CONFLICT (id) 
                DO UPDATE SET 
                    last_run_timestamp = EXCLUDED.last_run_timestamp,
                    is_running = TRUE;
            """, (datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc),))
        elif action == 'complete':
            # Mark pipeline as completed and not running
            cur.execute("""
                INSERT INTO pipeline_status (id, last_completion_timestamp, is_running) 
                VALUES (1, %s, FALSE)
                ON CONFLICT (id) 
                DO UPDATE SET 
                    last_completion_timestamp = EXCLUDED.last_completion_timestamp,
                    is_running = FALSE;
            """, (datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc),))
        elif action == 'failed':
            # Mark pipeline as failed and not running (for auto-fix scenarios)
            cur.execute("""
                INSERT INTO pipeline_status (id, is_running, process_pid) 
                VALUES (1, FALSE, NULL)
                ON CONFLICT (id) 
                DO UPDATE SET 
                    is_running = FALSE,
                    process_pid = NULL;
            """)
        
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        print(f"Error updating pipeline status: {e}")
        return False

def check_pipeline_completion(db_config):
    """Check if pipeline has completed by looking for new posts in database"""
    try:
        conn = get_db_connection(db_config)
        cur = conn.cursor()
        
        # Get pipeline status
        status = get_pipeline_status(db_config)
        
        if not status['is_running']:
            return True  # Not running, so it's "complete"
        
        # Check if there are any posts newer than the last run timestamp
        cur.execute("""
            SELECT COUNT(*) FROM posts_raw 
            WHERE created_utc > %s;
        """, (datetime.datetime.fromtimestamp(status['last_run'], tz=datetime.timezone.utc),))
        
        new_posts_count = cur.fetchone()[0]
        conn.close()
        
        # If we have new posts and pipeline was running, mark it as complete
        if new_posts_count > 0 and status['is_running']:
            update_pipeline_status(db_config, time.time(), 'complete')
            return True
        
        return not status['is_running']
        
    except Exception as e:
        print(f"Error checking pipeline completion: {e}")
        return True  # Assume complete on error

def send_email(subject, body, sender_email, sender_password, recipient_emails, smtp_server, smtp_port):
    """Send an email with the given parameters to multiple recipients"""
    # Handle both single string and list of recipients
    if isinstance(recipient_emails, str):
        recipient_emails = [recipient_emails]
    
    msg = MIMEText(body, 'html')
    msg['Subject'] = subject
    msg['From'] = sender_email
    msg['To'] = ', '.join(recipient_emails)  # Join multiple recipients with comma

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()  # Secure the connection
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient_emails, msg.as_bytes())
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False

def get_selected_posts_count(db_config):
    """Get the actual count of selected posts in the database"""
    try:
        conn = get_db_connection(db_config)
        cur = conn.cursor()
        
        # Count all selected posts
        count_query = """
            SELECT COUNT(*) FROM posts_raw WHERE status = 'selected';
        """
        cur.execute(count_query)
        count = cur.fetchone()[0]
        
        conn.close()
        return count
        
    except Exception as e:
        print(f"Error getting selected posts count: {e}")
        return 0

def get_selected_posts_for_email(db_config, limit=None):
    """Get the most recent selected posts for email"""
    try:
        conn = get_db_connection(db_config)
        cur = conn.cursor()
        
        # Get the most recent selected posts ordered by created_utc descending (newest first)
        # Include username by joining with users table
        select_query = """
            SELECT
                p.subreddit,
                p.priority_score,
                p.title,
                p.num_comments,
                p.url,
                p.link_flair_text,
                p.created_utc,
                p.concise_theme,
                p.short_summary,
                p.rationale_for_value,
                p.rationale_for_views,
                p.suggested_angle_for_coach,
                p.is_male_author,
                p.tags,
                u.username
            FROM posts_raw p
            LEFT JOIN users u ON p.author_id = u.id
            WHERE p.status = 'selected'
            ORDER BY p.created_utc DESC
        """
        if limit:
            select_query += f" LIMIT {limit}"
        cur.execute(select_query)
        posts_data = cur.fetchall()

        conn.close()
        return posts_data
        
    except Exception as e:
        print(f"Error getting selected posts: {e}")
        return []

def build_selected_posts_email_body(posts_data):
    """Build HTML email body for selected posts"""
    if not posts_data:
        return ""
    
    # Get current time in Miami timezone for the email header
    miami_tz = pytz.timezone('America/New_York')  # Miami uses Eastern Time
    current_miami_time = datetime.datetime.now(miami_tz)
    email_timestamp = current_miami_time.strftime("%B %d, %Y at %I:%M %p %Z")
    
    html_body = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .header {{ background-color: #f4f4f4; padding: 20px; text-align: center; }}
            .post {{ border: 1px solid #ddd; margin: 20px 0; padding: 15px; border-radius: 5px; }}
            .post-title {{ font-size: 18px; font-weight: bold; color: #2c3e50; margin-bottom: 10px; }}
            .post-meta {{ color: #7f8c8d; font-size: 14px; margin-bottom: 10px; }}
            .post-summary {{ background-color: #f8f9fa; padding: 10px; border-left: 4px solid #3498db; margin: 10px 0; }}
            .post-theme {{ background-color: #e8f5e8; padding: 8px; border-radius: 3px; margin: 5px 0; }}
            .post-angle {{ background-color: #fff3cd; padding: 8px; border-radius: 3px; margin: 5px 0; }}
            .score-badge {{ display: inline-block; background-color: #28a745; color: white; padding: 5px 10px; border-radius: 15px; font-weight: bold; }}
            .reddit-link {{ display: inline-block; background-color: #ff4500; color: white; padding: 8px 15px; text-decoration: none; border-radius: 5px; margin: 10px 0; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🚀 Selected Reddit Ideas - Outbound Report</h1>
            <p>Here are the most recent selected Reddit posts for content creation</p>
            <p style="color: #666; font-size: 12px;">Generated on {email_timestamp}</p>
        </div>
    """
    
    for i, post in enumerate(posts_data, 1):
        (subreddit, priority_score, title, num_comments, url, flair, created_utc,
         concise_theme, short_summary, rationale_for_value, rationale_for_views, 
         suggested_angle_for_coach, is_male_author, tags, username) = post
        
        # Format the created date in Miami timezone
        if created_utc:
            try:
                # created_utc is already a datetime object, convert to Miami timezone
                miami_tz = pytz.timezone('America/New_York')  # Miami uses Eastern Time
                
                # Ensure the datetime is timezone-aware (UTC)
                if created_utc.tzinfo is None:
                    created_utc = created_utc.replace(tzinfo=pytz.UTC)
                
                # Convert to Miami timezone
                miami_time = created_utc.astimezone(miami_tz)
                post_date = miami_time.strftime("%B %d, %Y at %I:%M %p %Z")
            except Exception as e:
                post_date = f"Date error: {e}"
        else:
            post_date = "Unknown date"
        
        # Format gender for email display
        if is_male_author is True:
            gender_badge = '<span style="background-color: #007bff; color: white; padding: 3px 8px; border-radius: 10px; font-size: 12px; margin-right: 5px;">👨 MALE</span>'
        elif is_male_author is False:
            gender_badge = '<span style="background-color: #e91e63; color: white; padding: 3px 8px; border-radius: 10px; font-size: 12px; margin-right: 5px;">👩 FEMALE</span>'
        else:
            gender_badge = '<span style="background-color: #6c757d; color: white; padding: 3px 8px; border-radius: 10px; font-size: 12px; margin-right: 5px;">❓ UNKNOWN</span>'
        
        html_body += f"""
        <div class="post">
            <div class="post-title">#{i}. {title or 'No title'}</div>
            <div class="post-meta">
                <span class="score-badge">{priority_score or 0}</span>
                {gender_badge}
                r/{subreddit or 'Unknown'} • u/{username or 'Unknown'} • {num_comments or 0} comments • {post_date}
                {f' • {flair}' if flair else ''}
                • <a href="{url}" class="reddit-link" target="_blank" style="display: inline; background-color: #ff4500; color: white; padding: 4px 8px; text-decoration: none; border-radius: 3px; font-size: 12px;">🔗 View Post</a>
            </div>
            
            {f'<div class="post-theme"><strong>🎯 Theme:</strong> {concise_theme}</div>' if concise_theme else ''}
            
            {f'<div class="post-summary"><strong>📝 Summary:</strong> {short_summary}</div>' if short_summary else ''}
            
            {f'<div style="background-color: #f0f8ff; padding: 8px; border-radius: 3px; margin: 5px 0;"><strong>🏷️ Tags:</strong> {", ".join(tags)}</div>' if tags and len(tags) > 0 else ''}
        </div>
        """
    
    html_body += """
    </body>
    </html>
    """
    
    return html_body

def send_selected_posts_email(db_config):
    """Send email with selected posts and mark them as sent"""
    try:
        # Get ALL selected posts (no limit)
        posts_data = get_selected_posts_for_email(db_config, limit=None)
        
        if not posts_data:
            return False, "No selected posts found to send"
        
        # Load email configuration from environment variables
        email_config = get_email_config()
        
        if not email_config.sender_email or not email_config.sender_password:
            return False, "Email configuration is incomplete. Please check EMAIL_SENDER and EMAIL_PASSWORD environment variables."
        
        # Build email body
        email_body = build_selected_posts_email_body(posts_data)
        subject = f"[Outbound] Selected {len(posts_data)} ideas"
        
        # Use recipients from environment config
        recipients = email_config.recipient_emails
        if not recipients:
            recipients = ["your-email@example.com"]  # fallback - configure EMAIL_RECIPIENTS in .env
        
        # Send email
        success = send_email(
            subject,
            email_body,
            email_config.sender_email,
            email_config.sender_password,
            recipients,
            email_config.smtp_server,
            email_config.smtp_port
        )
        
        if success:
            # Mark all sent posts as 'sent' status
            conn = get_db_connection(db_config)
            cur = conn.cursor()
            
            # Get URLs of the posts we just sent
            post_urls = [post[4] for post in posts_data]  # URL is still at index 4
            
            # Update status to 'sent'
            update_query = """
                UPDATE posts_raw
                SET status = 'sent'
                WHERE url = ANY(%s) AND status = 'selected';
            """
            cur.execute(update_query, (post_urls,))
            conn.commit()
            conn.close()
            
            # Start background sync to Google Sheets
            sync_to_google_sheets_background(db_config)
            
            return True, f"Successfully sent email with {len(posts_data)} posts to {len(recipients)} recipients"
        else:
            return False, "Failed to send email"
            
    except Exception as e:
        return False, f"Error sending email: {e}"

def sync_sent_posts_to_google_sheets(db_config):
    """Sync posts with status='sent' to Google Sheets and mark them as 'lead'"""
    try:
        # Load Google Sheets configuration from environment variables
        sheets_config = get_google_sheets_config()
        
        if not sheets_config.credentials_file or not sheets_config.spreadsheet_name:
            return False, "Google Sheets configuration is incomplete. Please check GOOGLE_CREDENTIALS_FILE and GOOGLE_SPREADSHEET_NAME environment variables."
        
        # Get posts with status='sent'
        conn = get_db_connection(db_config)
        cur = conn.cursor()
        
        # Get sent posts that haven't been synced to Google Sheets yet, including username and gender
        select_query = """
            SELECT p.title, p.created_utc, p.url, u.username, p.is_male_author
            FROM posts_raw p
            LEFT JOIN users u ON p.author_id = u.id
            WHERE p.status = 'sent'
            ORDER BY p.created_utc DESC;
        """
        cur.execute(select_query)
        sent_posts = cur.fetchall()
        
        if not sent_posts:
            conn.close()
            return True, "No sent posts found to sync to Google Sheets"
        
        # Convert to list of dictionaries for the Google Sheets service
        posts_data = []
        
        # Get current Miami time for added_at_date
        miami_tz = pytz.timezone('America/New_York')  # Miami uses Eastern Time
        current_miami_time = datetime.datetime.now(miami_tz)
        added_at_date = current_miami_time.strftime("%m/%d/%Y")  # Format: 5/28/2025
        
        for post in sent_posts:
            title, created_utc, url, username, is_male_author = post
            
            # Add gender emoji prefix to title
            gender_prefix = ""
            if is_male_author is True:
                gender_prefix = "👨 "
            elif is_male_author is False:
                gender_prefix = "👩 "
            else:
                gender_prefix = "❓ "  # Unknown gender
            
            # Combine prefix with title
            prefixed_title = f"{gender_prefix}{title or ''}"
            
            # Format created_utc for createdat column
            createdat = ""
            if created_utc:
                try:
                    # Ensure the datetime is timezone-aware (UTC)
                    if created_utc.tzinfo is None:
                        created_utc = created_utc.replace(tzinfo=pytz.UTC)
                    
                    # Convert to Miami timezone
                    miami_time = created_utc.astimezone(miami_tz)
                    createdat = miami_time.strftime("%m/%d/%Y %I:%M %p")  # Format: 5/28/2025 3:45 PM
                except Exception as e:
                    createdat = "Date error"
            
            posts_data.append({
                'source': 'reddit',
                'title': prefixed_title,
                'createdat': createdat,
                'link': url or '',
                'username': username or 'Unknown',
                'loom': '',  # Empty column as specified
                'added_at_date': added_at_date
            })
        
        # Initialize Google Sheets service
        sheets_service = GoogleSheetsService(
            credentials_file=sheets_config.credentials_file,
            spreadsheet_name=sheets_config.spreadsheet_name,
            worksheet_name=sheets_config.worksheet_name
        )
        
        # Add posts to Google Sheets
        success = sheets_service.add_posts(posts_data)
        
        if success:
            # Mark all sent posts as 'lead' status
            post_urls = [post[2] for post in sent_posts]  # URL is at index 2
            
            update_query = """
                UPDATE posts_raw
                SET status = 'lead'
                WHERE url = ANY(%s) AND status = 'sent';
            """
            cur.execute(update_query, (post_urls,))
            conn.commit()
            conn.close()
            
            return True, f"Successfully synced {len(sent_posts)} posts to Google Sheets and marked as leads"
        else:
            conn.close()
            return False, "Failed to sync posts to Google Sheets"
            
    except Exception as e:
        if 'conn' in locals():
            conn.close()
        return False, f"Error syncing to Google Sheets: {e}"

def sync_to_google_sheets_background(db_config):
    """Run Google Sheets sync in background thread"""
    def background_sync():
        try:
            success, message = sync_sent_posts_to_google_sheets(db_config)
            print(f"Google Sheets sync result: {message}")
        except Exception as e:
            print(f"Background Google Sheets sync error: {e}")
    
    # Start background thread
    thread = threading.Thread(target=background_sync, daemon=True)
    thread.start()
    return True

@st.cache_data(ttl=STATS_CACHE_TTL, show_spinner=False)
def get_posts_stats(db_config_str):
    """Get cached statistics about posts"""
    try:
        # Parse db_config from string (needed for caching)
        import json
        db_config = json.loads(db_config_str)
        
        conn = get_db_connection(db_config)
        cur = conn.cursor()
        
        # Get basic stats
        cur.execute("""
            SELECT 
                COUNT(*) as total_posts,
                COUNT(CASE WHEN p.priority_score > 0 THEN 1 END) as relevant_posts,
                AVG(CASE WHEN p.priority_score > 0 THEN p.priority_score END) as avg_score,
                COUNT(CASE WHEN p.priority_score > 0 AND p.is_male_author = true THEN 1 END) as male_posts,
                COUNT(CASE WHEN p.priority_score > 0 AND p.is_male_author = false THEN 1 END) as female_posts,
                COUNT(CASE WHEN p.status = 'selected' THEN 1 END) as selected_posts
            FROM posts_raw p
            WHERE p.priority_score IS NOT NULL 
            AND p.status NOT IN ('ignored', 'sent', 'lead')
        """)
        
        stats = cur.fetchone()
        conn.close()
        
        total_posts, relevant_posts, avg_score, male_posts, female_posts, selected_posts = stats
        relevance_rate = (relevant_posts / total_posts * 100) if total_posts > 0 else 0
        
        return {
            'total_posts': total_posts,
            'relevant_posts': relevant_posts,
            'relevance_rate': relevance_rate,
            'avg_score': avg_score or 0,
            'male_posts': male_posts,
            'female_posts': female_posts,
            'selected_posts': selected_posts
        }
    except Exception as e:
        print(f"Error getting stats: {e}")
        return {}

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def get_subreddit_options(db_config_str):
    """Get cached list of subreddits for filter dropdown"""
    try:
        import json
        db_config = json.loads(db_config_str)
        
        conn = get_db_connection(db_config)
        cur = conn.cursor()
        
        cur.execute("""
            SELECT DISTINCT p.subreddit 
            FROM posts_raw p
            WHERE p.priority_score IS NOT NULL 
            AND p.status NOT IN ('ignored', 'sent', 'lead')
            AND p.subreddit IS NOT NULL
            ORDER BY p.subreddit
        """)
        
        subreddits = [row[0] for row in cur.fetchall()]
        conn.close()
        
        return ["All Subreddits"] + [f"r/{sr}" for sr in subreddits]
    except Exception as e:
        print(f"Error getting subreddits: {e}")
        return ["All Subreddits"]

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def get_tag_options(db_config_str):
    """Get cached list of tags for filter dropdown"""
    try:
        import json
        db_config = json.loads(db_config_str)
        
        conn = get_db_connection(db_config)
        cur = conn.cursor()
        
        cur.execute("""
            SELECT DISTINCT unnest(p.tags) as tag
            FROM posts_raw p
            WHERE p.status NOT IN ('ignored', 'sent', 'lead')
            AND p.tags IS NOT NULL
            AND array_length(p.tags, 1) > 0
            ORDER BY tag
        """)
        
        tags = [row[0] for row in cur.fetchall()]
        conn.close()
        
        return ["All Tags"] + tags
    except Exception as e:
        print(f"Error getting tags: {e}")
        return ["All Tags"]

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def get_posts_paginated(db_config_str, page_number, posts_per_page, 
                       score_filter="All Relevant Posts (Score > 0)", 
                       subreddit_filter="All Subreddits",
                       gender_filter="all",
                       tag_filters=[],
                       show_selected_only=False):
    """Get paginated posts with filters applied at database level"""
    try:
        import json
        db_config = json.loads(db_config_str)
        
        conn = get_db_connection(db_config)
        cur = conn.cursor()
        
        # Build WHERE clause based on filters
        # If tags are selected, show both scored and unscored posts with those tags
        # Otherwise, only show scored posts
        if tag_filters and len(tag_filters) > 0:
            where_conditions = [
                "p.status NOT IN ('ignored', 'sent', 'lead')"
            ]
        else:
            where_conditions = [
                "p.priority_score IS NOT NULL",
                "p.status NOT IN ('ignored', 'sent', 'lead')"
            ]
        params = []
        
        # Apply score filter
        if score_filter == "High Priority (Score ≥ 70)":
            where_conditions.append("p.priority_score >= 70")
        elif score_filter == "Medium Priority (Score 40-69)":
            where_conditions.append("p.priority_score >= 40 AND p.priority_score < 70")
        elif score_filter == "Low Priority (Score 1-39)":
            where_conditions.append("p.priority_score >= 1 AND p.priority_score < 40")
        # "All Relevant Posts" doesn't need additional filter
        
        # Apply subreddit filter
        if subreddit_filter != "All Subreddits":
            subreddit_name = subreddit_filter.replace('r/', '')
            where_conditions.append("p.subreddit = %s")
            params.append(subreddit_name)
        
        # Apply gender filter
        if gender_filter == "male":
            where_conditions.append("p.is_male_author = true")
        elif gender_filter == "female":
            where_conditions.append("p.is_male_author = false")
        
        # Apply tag filters (multiple tags)
        if tag_filters and len(tag_filters) > 0:
            where_conditions.append("p.tags && %s")  # PostgreSQL array overlap operator
            params.append(tag_filters)
        
        # Apply selected filter
        if show_selected_only:
            where_conditions.append("p.status = 'selected'")
        
        # Calculate offset
        offset = (page_number - 1) * posts_per_page
        
        # Get total count for pagination
        count_query = f"""
            SELECT COUNT(*) 
            FROM posts_raw p
            LEFT JOIN users u ON p.author_id = u.id
            WHERE {' AND '.join(where_conditions)}
        """
        cur.execute(count_query, params)
        total_count = cur.fetchone()[0]
        
        # Get paginated data
        data_query = f"""
            SELECT
                p.subreddit,
                p.priority_score,
                p.title,
                p.num_comments,
                p.url,
                p.link_flair_text,
                p.created_utc,
                p.concise_theme,
                p.short_summary,
                p.rationale_for_value,
                p.rationale_for_views,
                p.suggested_angle_for_coach,
                p.status,
                p.is_male_author,
                p.tags,
                u.username
            FROM posts_raw p
            LEFT JOIN users u ON p.author_id = u.id
            WHERE {' AND '.join(where_conditions)}
            ORDER BY p.priority_score DESC NULLS LAST, p.created_utc DESC
            LIMIT %s OFFSET %s
        """
        
        cur.execute(data_query, params + [posts_per_page, offset])
        posts_data = cur.fetchall()
        conn.close()
        
        return {
            'posts': posts_data,
            'total_count': total_count,
            'total_pages': max(1, (total_count + posts_per_page - 1) // posts_per_page)
        }
        
    except Exception as e:
        print(f"Error getting paginated posts: {e}")
        return {'posts': [], 'total_count': 0, 'total_pages': 1}

def invalidate_caches():
    """Clear all cached data when posts are modified"""
    # Clear Streamlit caches
    get_posts_stats.clear()
    get_posts_paginated.clear()
    get_subreddit_options.clear()
    get_tag_options.clear()

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def process_posts_for_display(posts_data):
    """Process raw post data for display with caching"""
    df_data = []
    
    for post in posts_data:
        (subreddit, priority_score, title, num_comments, url, flair, created_utc,
         concise_theme, short_summary, rationale_for_value, rationale_for_views, 
         suggested_angle_for_coach, status, is_male_author, tags, username) = post
        
        # Truncate title if too long for better display
        display_title = title[:80] + "..." if len(title) > 80 else title
        
        # Format timestamp in Miami timezone
        miami_timestamp = "Unknown"
        if created_utc:
            try:
                miami_tz = pytz.timezone('America/New_York')  # Miami uses Eastern Time
                
                # Ensure the datetime is timezone-aware (UTC)
                if created_utc.tzinfo is None:
                    created_utc = created_utc.replace(tzinfo=pytz.UTC)
                
                # Convert to Miami timezone
                miami_time = created_utc.astimezone(miami_tz)
                miami_timestamp = miami_time.strftime("%m/%d %I:%M %p")
            except Exception as e:
                miami_timestamp = f"Error: {e}"
        
        # Format gender for display
        if is_male_author is True:
            gender_display = "👨 M"
        elif is_male_author is False:
            gender_display = "👩 F"
        else:
            gender_display = "❓ ?"
        
        df_data.append({
            'Subreddit': f"r/{subreddit}",
            'Score': priority_score if priority_score is not None else 0,
            'Gender': gender_display,
            'Title': display_title,
            'Theme': concise_theme or '',
            'Summary': short_summary or '',
            'Tags': tags or [],  # Add tags to the data
            'Num Comments': num_comments or 0,
            'Flair': flair if flair else '',
            'URL': url,
            'Rationale Value': rationale_for_value or '',
            'Rationale Views': rationale_for_views or '',
            'Coach Angle': suggested_angle_for_coach or '',
            'Status': status or '',
            'Timestamp': miami_timestamp,
            'Full Title': title,  # Keep full title for display in expander
            'Is Male Author': is_male_author,  # Keep raw boolean for logic
            'Username': username or 'Unknown'  # Add username to the data
        })
    
    return pd.DataFrame(df_data)

def update_post_status(db_config, post_url, new_status):
    """Update post status and invalidate caches"""
    try:
        conn = get_db_connection(db_config)
        cur = conn.cursor()
        update_query = """
            UPDATE posts_raw
            SET status = %s
            WHERE url = %s;
        """
        cur.execute(update_query, (new_status, post_url))
        conn.commit()
        conn.close()
        
        # Invalidate caches after status change
        invalidate_caches()
        
        return True, f"Status updated to '{new_status}'"
    except Exception as e:
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return False, f"Error updating status: {e}"

def main():
    # Get configuration from environment variables
    try:
        db_config = get_db_connection_dict()
        
        # Validate configuration
        from config import validate_configuration
        config_errors = validate_configuration()
        if config_errors:
            st.error("Configuration errors:")
            for error in config_errors:
                st.error(f"• {error}")
            st.info("Please check your .env file and ensure all required environment variables are set.")
            return
            
    except Exception as e:
        st.error(f"Failed to load configuration: {e}")
        st.info("Please ensure your .env file is properly configured.")
        return

    # Convert db_config to string for caching (cache functions need hashable parameters)
    import json
    db_config_str = json.dumps(db_config, sort_keys=True)

    # Get pipeline status from database
    pipeline_status = get_pipeline_status(db_config)
    
    # Check if pipeline has completed (this will auto-update status if needed)
    pipeline_complete = check_pipeline_completion(db_config)
    
    # Refresh status after completion check
    if not pipeline_complete:
        pipeline_status = get_pipeline_status(db_config)
    
    # Calculate time since last run for display purposes
    current_time = time.time()
    time_since_last_run = current_time - pipeline_status['last_run']
    
    # Create columns for title and refresh button
    col1, col2 = st.columns([6, 1])
    
    with col1:
        st.title('Social Qs')
    
    with col2:
        # Add some vertical spacing to align with title
        st.write("")
        
        # Determine button state and text
        if pipeline_status['is_running'] and not pipeline_complete:
            # Pipeline is running - show status and disable button
            minutes_running = int(time_since_last_run // 60)
            seconds_running = int(time_since_last_run % 60)
            button_text = f"🔄 Running ({minutes_running}:{seconds_running:02d})"
            help_text = f"Pipeline is running... Started {minutes_running}:{seconds_running:02d} ago"
            button_disabled = True
        else:
            # Pipeline is not running - button available
            button_text = "🔄"
            help_text = "Run Reddit Pipeline"
            button_disabled = False
        
        if st.button(button_text, help=help_text, key="refresh_pipeline", disabled=button_disabled):
            if run_pipeline_script():
                # Update the database to mark pipeline as started
                if update_pipeline_status(db_config, current_time, 'start'):
                    # Invalidate caches when pipeline starts
                    invalidate_caches()
                    # Show brief toast notification
                    st.toast("🚀 Pipeline started! Data will refresh when complete.", icon="✅")
                    # Force rerun to update button state immediately
                    st.rerun()
                else:
                    st.toast("⚠️ Pipeline started but status update failed", icon="🟡")
            else:
                st.toast("❌ Failed to start pipeline", icon="🚨")
        
        # Auto-refresh every 15 seconds when pipeline is running (silent)
        if pipeline_status['is_running'] and not pipeline_complete:
            # Use session state to track last refresh time
            current_time_key = 'last_refresh_time'
            if current_time_key not in st.session_state:
                st.session_state[current_time_key] = current_time
            
            # Check if 15 seconds have passed since last refresh
            time_since_refresh = current_time - st.session_state[current_time_key]
            if time_since_refresh >= 15:
                st.session_state[current_time_key] = current_time
                invalidate_caches()  # Refresh cached data
                st.rerun()
        else:
            # Clear the refresh timer when pipeline is not running
            if 'last_refresh_time' in st.session_state:
                del st.session_state.last_refresh_time

    # Get cached statistics
    stats = get_posts_stats(db_config_str)
    
    if not stats:
        st.error("Unable to fetch post statistics.")
        return

    st.subheader('Reddit Posts Ranked by Gemini AI Score')

    # Initialize session state for filters
    if 'show_selected_only' not in st.session_state:
        st.session_state.show_selected_only = False
    if 'gender_filter' not in st.session_state:
        st.session_state.gender_filter = 'all'  # 'all', 'male', 'female'
    if 'page_number' not in st.session_state:
        st.session_state.page_number = 1

    # Display stats with optimized clickable filters
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        st.metric("Total Posts", stats['total_posts'])
    with col2:
        st.metric("Relevant Posts (Score > 0)", stats['relevant_posts'])
    with col3:
        st.metric("Relevance Rate", f"{stats['relevance_rate']:.1f}%")
    with col4:
        st.metric("Avg Score (Relevant)", f"{stats['avg_score']:.1f}")
    with col5:
        # Make male posts metric clickable
        if st.button(f"👨 Male Posts\n{stats['male_posts']}", key="male_filter_button", use_container_width=True):
            if st.session_state.gender_filter == 'male':
                st.session_state.gender_filter = 'all'  # Toggle off if already selected
            else:
                st.session_state.gender_filter = 'male'
            st.session_state.page_number = 1  # Reset to first page
            st.rerun()
    with col6:
        # Make female posts metric clickable
        if st.button(f"👩 Female Posts\n{stats['female_posts']}", key="female_filter_button", use_container_width=True):
            if st.session_state.gender_filter == 'female':
                st.session_state.gender_filter = 'all'  # Toggle off if already selected
            else:
                st.session_state.gender_filter = 'female'
            st.session_state.page_number = 1  # Reset to first page
            st.rerun()
    
    st.markdown("---")
    
    # Add filter options with cached subreddit and tag options
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        score_filter = st.selectbox(
            "Filter by Score:",
            options=["All Relevant Posts (Score > 0)", "High Priority (Score ≥ 70)", "Medium Priority (Score 40-69)", "Low Priority (Score 1-39)"],
            index=0,
            key="score_filter"
        )
    with col2:
        subreddit_options = get_subreddit_options(db_config_str)
        subreddit_filter = st.selectbox(
            "Filter by Subreddit:",
            options=subreddit_options,
            index=0,
            key="subreddit_filter"
        )
    with col3:
        tag_options = get_tag_options(db_config_str)
        # Remove "All Tags" from options since multiselect doesn't need it
        available_tags = [tag for tag in tag_options if tag != "All Tags"]
        tag_filters = st.multiselect(
            "Filter by Tags:",
            options=available_tags,
            default=[],
            key="tag_filters",
            help="Select multiple tags to filter posts"
        )
    with col4:
        # Display current gender filter status
        gender_filter_display = {
            'all': "All Genders",
            'male': "👨 Male Only",
            'female': "👩 Female Only"
        }
        st.info(f"**Gender Filter:** {gender_filter_display[st.session_state.gender_filter]}")
    
    # Reset page when filters change
    current_filters = (score_filter, subreddit_filter, tuple(tag_filters), st.session_state.gender_filter, st.session_state.show_selected_only)
    if 'last_filters' not in st.session_state:
        st.session_state.last_filters = current_filters
    elif st.session_state.last_filters != current_filters:
        st.session_state.page_number = 1
        st.session_state.last_filters = current_filters

    # Get paginated data with all filters applied at database level
    posts_per_page = 10
    pagination_data = get_posts_paginated(
        db_config_str, 
        st.session_state.page_number, 
        posts_per_page,
        score_filter=score_filter,
        subreddit_filter=subreddit_filter,
        gender_filter=st.session_state.gender_filter,
        tag_filters=tag_filters,
        show_selected_only=st.session_state.show_selected_only
    )
    
    posts_data = pagination_data['posts']
    total_filtered_posts = pagination_data['total_count']
    total_pages = pagination_data['total_pages']

    # Ensure page number is within valid range
    if st.session_state.page_number > total_pages:
        st.session_state.page_number = total_pages
    elif st.session_state.page_number < 1:
        st.session_state.page_number = 1

    if total_filtered_posts > 0:
        # Create pagination controls
        col1, col2, col3, col4, col5 = st.columns([1, 1, 2, 1, 1])
        
        with col1:
            if st.button("⬅️ Previous", disabled=(st.session_state.page_number <= 1), key="prev_top"):
                st.session_state.page_number -= 1
                st.rerun()
        
        with col2:
            st.write(f"Page {st.session_state.page_number}")
        
        with col3:
            # Page selector dropdown
            new_page = st.selectbox(
                "Jump to page:",
                options=list(range(1, total_pages + 1)),
                index=st.session_state.page_number - 1,
                format_func=lambda x: f"Page {x} of {total_pages}",
                key="page_selector"
            )
            if new_page != st.session_state.page_number:
                st.session_state.page_number = new_page
                st.rerun()
        
        with col4:
            st.write(f"of {total_pages}")
        
        with col5:
            if st.button("Next ➡️", disabled=(st.session_state.page_number >= total_pages), key="next_top"):
                st.session_state.page_number += 1
                st.rerun()
        
        # Create columns for "Showing posts" text, Send button, and Filter button
        show_col, send_col, filter_col = st.columns([3, 1, 1])
        
        with show_col:
            start_idx = (st.session_state.page_number - 1) * posts_per_page
            end_idx = min(start_idx + posts_per_page, total_filtered_posts)
            filter_text = " (showing selected only)" if st.session_state.show_selected_only else ""
            gender_text = ""
            if st.session_state.gender_filter == 'male':
                gender_text = " (👨 male only)"
            elif st.session_state.gender_filter == 'female':
                gender_text = " (👩 female only)"
            
            tags_text = ""
            if tag_filters and len(tag_filters) > 0:
                if len(tag_filters) == 1:
                    tags_text = f" (🏷️ tag: {tag_filters[0]})"
                else:
                    tags_text = f" (🏷️ {len(tag_filters)} tags: {', '.join(tag_filters[:3])}{'...' if len(tag_filters) > 3 else ''})"
            
            st.write(f"Showing posts {start_idx + 1}-{end_idx} of {total_filtered_posts} total filtered posts{filter_text}{gender_text}{tags_text}:")
        
        with send_col:
            # Get count of selected posts for button label
            selected_count = stats['selected_posts']
            
            if selected_count > 0:
                if st.button(f"📧 Send ({selected_count})", key="send_email_button", help=f"Send email with {selected_count} selected posts"):
                    success, message = send_selected_posts_email(db_config)
                    if success:
                        invalidate_caches()  # Refresh cache after sending
                        st.success(f"✅ {message}")
                        st.rerun()  # Refresh to update the button count
                    else:
                        st.error(f"❌ {message}")
            else:
                st.button("📧 Send (0)", disabled=True, help="No selected posts to send")
        
        with filter_col:
            # Filter button for selected posts
            filter_button_text = "⭐ Show All" if st.session_state.show_selected_only else "⭐ Selected Only"
            filter_help_text = "Show all posts" if st.session_state.show_selected_only else "Show only selected posts"
            
            if st.button(filter_button_text, key="filter_selected_button", help=filter_help_text):
                st.session_state.show_selected_only = not st.session_state.show_selected_only
                st.session_state.page_number = 1  # Reset to first page when filter changes
                st.rerun()

        # Process and display posts using cached function
        if posts_data:
            df = process_posts_for_display(posts_data)
            
            # Display the posts with enhanced information
            for idx, row in df.iterrows():
                # Create color-coded score display
                score = row['Score']
                is_unscored = (priority_score is None for priority_score in [post[1] for post in posts_data if post[4] == row['URL']])
                # Check if this is an unscored post by looking at the original data
                original_post = next((post for post in posts_data if post[4] == row['URL']), None)
                is_unscored = original_post and original_post[1] is None
                
                if is_unscored:
                    score_color = "#9e9e9e"  # Gray for unscored posts
                    score_display = "UNSCORED"
                elif score >= 70:
                    score_color = "#00ff00"  # Green for high priority
                    score_display = str(score)
                elif score >= 40:
                    score_color = "#ffa500"  # Orange for medium priority
                    score_display = str(score)
                elif score > 0:
                    score_color = "#ffff00"  # Yellow for low priority
                    score_display = str(score)
                else:
                    score_color = "#ff0000"  # Red for not relevant
                    score_display = str(score)
                
                # Create enhanced display for each post with new Gemini analysis fields
                # Add a simple indicator for answered posts at the beginning of the title
                answered_indicator = "✅ ANSWERED | " if row['Status'] == 'answered' else ""
                selected_indicator = "⭐ SELECTED | " if row['Status'] == 'selected' else ""
                status_indicator = answered_indicator + selected_indicator
                timestamp_display = f"{row['Timestamp']} | " if row['Timestamp'] != 'Unknown' else ""
                gender_display = f"{row['Gender']} | " if row['Gender'] != '❓ ?' else ""
                username_display = f"u/{row['Username']} | " if row['Username'] != 'Unknown' else ""
                # Format tags for display in expander title
                tags_display = ""
                if row['Tags'] and len(row['Tags']) > 0:
                    tags_str = ", ".join(row['Tags'][:3])  # Show up to 3 tags in title
                    if len(row['Tags']) > 3:
                        tags_str += f" +{len(row['Tags']) - 3}"
                    tags_display = f"[{tags_str}] | "
                with st.expander(f"{status_indicator}{timestamp_display}{gender_display}{username_display}{tags_display}🔥 {score_display} | {row['Subreddit']} | {row['Theme']} | {row['Title'][:60]}{'...' if len(row['Title']) > 60 else ''}", expanded=False):

                    col1, col2 = st.columns([2, 1])
                    
                    with col1:
                        st.markdown(f"**Title:** {row['Full Title'] if row['Full Title'] else 'No title'}")
                        if row['Summary'] and str(row['Summary']).strip():
                            st.markdown(f"**Summary:** {row['Summary']}")
                        if row['Theme'] and str(row['Theme']).strip():
                            st.markdown(f"**Theme:** {row['Theme']}")
                        # Display tags with styling
                        if row['Tags'] and len(row['Tags']) > 0:
                            tags_html = " ".join([f'<span style="background-color: #e1f5fe; color: #01579b; padding: 2px 6px; border-radius: 10px; font-size: 12px; margin-right: 4px;">{tag}</span>' for tag in row['Tags']])
                            st.markdown(f"**🏷️ Tags:** {tags_html}", unsafe_allow_html=True)
                        if row['Coach Angle'] and str(row['Coach Angle']).strip():
                            st.markdown(f"**💡 Suggested Angle:** {row['Coach Angle']}")
                        
                        # Show rationales in simple sections for relevant posts (no nested expanders)
                        if score > 0:
                            if row['Rationale Value'] and str(row['Rationale Value']).strip():
                                st.markdown("**📈 Value Rationale:**")
                                st.info(row['Rationale Value'])
                            if row['Rationale Views'] and str(row['Rationale Views']).strip():
                                st.markdown("**👁️ Virality Rationale:**")
                                st.info(row['Rationale Views'])
                    
                    with col2:
                        # Reddit Link at the top - use st.link_button for better functionality
                        st.link_button("🔗 Open Reddit Post", row['URL'], use_container_width=True)
                        
                        # Display score and comments info
                        st.markdown(f"""
                        <div style="text-align: center; margin: 15px 0;">
                            <div style="background-color: {score_color}; color: black; padding: 10px; border-radius: 5px; font-weight: bold; font-size: 24px; margin-bottom: 10px;">
                                {score_display}
                            </div>
                            <div style="margin-bottom: 10px;">
                                <strong>{row['Subreddit'] if row['Subreddit'] else 'Unknown'}</strong><br>
                                u/{row['Username'] if row['Username'] != 'Unknown' else 'Unknown'}<br>
                                {row['Num Comments'] if row['Num Comments'] is not None else 0} Comments<br>
                                <span style="color: #666;">{row['Flair'] if row['Flair'] else ''}</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

                        # Use optimized status update function
                        post_url = row['URL']
                        current_status = row['Status']
                        
                        # Answered/Not Answered button
                        answered_button_label = "Mark as Open" if current_status == 'answered' else "Mark as Answered"
                        if st.button(answered_button_label, key=f"answered_{idx}_{st.session_state.page_number}", use_container_width=True):
                            new_status = 'open' if current_status == 'answered' else 'answered'
                            success, message = update_post_status(db_config, post_url, new_status)
                            if success:
                                st.success(message)
                                st.rerun()
                            else:
                                st.error(message)

                        # Select/Unselect button
                        select_button_label = "Unselect" if current_status == 'selected' else "Select"
                        if st.button(select_button_label, key=f"select_{idx}_{st.session_state.page_number}", use_container_width=True):
                            new_status = 'open' if current_status == 'selected' else 'selected'
                            success, message = update_post_status(db_config, post_url, new_status)
                            if success:
                                st.success(message)
                                st.rerun()
                            else:
                                st.error(message)

                        # Ignore button
                        if st.button("Ignore", key=f"ignore_{idx}_{st.session_state.page_number}", use_container_width=True, type='secondary'):
                            success, message = update_post_status(db_config, post_url, 'ignored')
                            if success:
                                st.success("Post marked as ignored.")
                                st.rerun()
                            else:
                                st.error(message)
        
        # Add bottom pagination controls (only if there are multiple pages)
        if total_pages > 1:
            st.markdown("---")  # Add a separator line
            
            # Bottom pagination controls - simpler version
            bottom_col1, bottom_col2, bottom_col3 = st.columns([1, 2, 1])
            
            with bottom_col1:
                if st.button("⬅️ Previous Page", disabled=(st.session_state.page_number <= 1), key="bottom_prev"):
                    st.session_state.page_number -= 1
                    st.rerun()
            
            with bottom_col2:
                st.markdown(f"<div style='text-align: center; padding: 8px;'><strong>Page {st.session_state.page_number} of {total_pages}</strong></div>", unsafe_allow_html=True)
            
            with bottom_col3:
                if st.button("Next Page ➡️", disabled=(st.session_state.page_number >= total_pages), key="bottom_next"):
                    st.session_state.page_number += 1
                    st.rerun()

    else:
        st.info("No posts match the current filters.")

if __name__ == "__main__":
    main()
