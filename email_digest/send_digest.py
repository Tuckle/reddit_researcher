import smtplib
from email.mime.text import MIMEText
import psycopg2
import yaml
import os
from psycopg2 import sql
from apscheduler.schedulers.blocking import BlockingScheduler

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

def send_email(subject, body, sender_email, sender_password, recipient_email, smtp_server, smtp_port):
    msg = MIMEText(body, 'html')
    msg['Subject'] = subject
    msg['From'] = sender_email
    msg['To'] = recipient_email

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls() # Secure the connection
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient_email, msg.as_bytes())
        print("Email sent successfully!")
    except Exception as e:
        print(f"Failed to send email: {e}")

def build_email_body(themes, conn):
    html_body = "<h1>Garrett Darling Daily Research Digest</h1>"
    html_body += "<p>Here are the top unanswered themes/questions based on recent Reddit posts:</p>"
    html_body += "<ul>"

    cur = conn.cursor()

    for theme in themes:
        theme_id, theme_text, score_agg = theme
        html_body += f"<li><h2>Theme (Score: {score_agg:.2f}): {theme_text}</h2>"

        # Fetch example posts for this theme
        # Need to get example_post_ids from themes table first
        fetch_post_ids_query = "SELECT example_post_ids FROM themes WHERE theme_id = %s;"
        cur.execute(fetch_post_ids_query, (theme_id,))
        example_post_ids = cur.fetchone()[0] or [] # Handle case where array might be null

        if example_post_ids:
            # Fetch post URLs for the example IDs
            # Using ANY operator with an array of IDs
            fetch_posts_query = sql.SQL("SELECT url, title FROM posts_raw WHERE id = ANY(%s);")
            cur.execute(fetch_posts_query, (example_post_ids,))
            example_posts = cur.fetchall()

            if example_posts:
                html_body += "<p>Relevant Posts:</p><ul>"
                for post_url, post_title in example_posts:
                    html_body += f'<li><a href="{post_url}">{post_title}</a></li>'
                html_body += "</ul>"
        else:
             html_body += "<p>No example posts found for this theme.</p>"

        html_body += "</li>"

    html_body += "</ul>"
    return html_body

def send_digest_job():
    config = load_config()
    db_config = config.get('database', {})
    email_config = config.get('email', {})

    if not db_config:
        print("Database configuration not found in config.yaml.")
        return
    if not email_config or not all(key in email_config for key in ['smtp_server', 'smtp_port', 'sender_email', 'sender_password', 'recipient_email']):
         print("Email configuration is incomplete in config.yaml.")
         return

    conn = None
    try:
        conn = get_db_connection(db_config)
        cur = conn.cursor()

        # Fetch top 10 unanswered themes ordered by aggregated score
        select_themes_query = "SELECT theme_id, theme_text, score_agg FROM themes WHERE status = 'open' ORDER BY score_agg DESC LIMIT 10;"
        cur.execute(select_themes_query)
        top_themes = cur.fetchall()

        if not top_themes:
            print("No unanswered themes found to send in the digest.")
            return

        print(f"Found {len(top_themes)} top themes to include in the digest.")

        # Build the email body
        email_body = build_email_body(top_themes, conn)
        subject = "Garrett Darling Daily Reddit Research Digest"

        # Send the email
        send_email(
            subject,
            email_body,
            email_config['sender_email'],
            email_config['sender_password'],
            email_config['recipient_email'],
            email_config['smtp_server'],
            email_config['smtp_port']
        )

    except Exception as e:
        print(f"An error occurred during email digest generation: {e}")
    finally:
        if conn:
            conn.close()
            print("Database connection closed.")

def main():
    # This main function can be used to run the job manually or set up scheduling
    # For simple manual run:
    # send_digest_job()

    # For scheduling, uncomment the following lines and configure the schedule
    print("Setting up email digest scheduler...")
    scheduler = BlockingScheduler()
    # Schedule the job to run daily, for example
    # scheduler.add_job(send_digest_job, 'interval', days=1)
    # Or at a specific time each day (e.g., 9:00 AM)
    # scheduler.add_job(send_digest_job, 'cron', hour=9, minute=0)
    print("Scheduler started. Press Ctrl+C to exit.")
    try:
        # scheduler.start()
        # For now, just run the job once for testing
        send_digest_job()
    except (KeyboardInterrupt, SystemExit):
        pass # Handle manual interruption

if __name__ == "__main__":
    main() 