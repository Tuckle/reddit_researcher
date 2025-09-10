import sys
import os
import json
import time
import psycopg2
from psycopg2 import sql
from datetime import datetime, timezone
import re # For parsing API response
import google.generativeai as genai

# Add the parent directory to the path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables first
import load_env

# Import configuration
from config import (
    get_database_config,
    get_gemini_api_key,
    get_processing_config,
    get_db_connection_dict,
    load_prompt
)

def get_db_connection(db_config_dict):
    """Create and return a database connection."""
    conn = psycopg2.connect(
        dbname=db_config_dict['dbname'],
        user=db_config_dict['user'],
        password=db_config_dict['password'],
        host=db_config_dict.get('host', 'localhost'),
        port=db_config_dict.get('port', 5432)
    )
    return conn

def fetch_unprocessed_posts(conn, batch_size=42): # User changed batch_size
    """Fetch a batch of posts that haven't been scored by Gemini yet."""
    cur = conn.cursor()
    
    query = sql.SQL("""
        SELECT id, subreddit, created_utc, title, body, img_text, 
               link_flair_text, score, num_comments, url
        FROM posts_raw
        WHERE priority_score IS NULL
        ORDER BY created_utc DESC
        LIMIT %s;
    """)
    
    cur.execute(query, (batch_size,))
    posts = cur.fetchall()
    cur.close()
    return posts

def format_posts_for_gemini(posts):
    """Format posts data into JSON structure for Gemini."""
    formatted_posts = []
    for post_data in posts: # Renamed 'post' to 'post_data' to avoid conflict
        (post_id, subreddit, created_utc, title, body, img_text, 
         link_flair_text, score, num_comments, url) = post_data
        
        formatted_post = {
            "id": post_id,
            "subreddit": subreddit,
            "created_utc": created_utc.isoformat() if created_utc else "",
            "title": title or "",
            "body": body or "",
            "img_text": img_text or "",
            "link_flair_text": link_flair_text or "",
            "score": score or 0,
            "num_comments": num_comments or 0,
            "url": url or ""
        }
        formatted_posts.append(formatted_post)
    return formatted_posts

def create_gemini_prompt_for_api(posts_data_list):
    """Create the prompt for Gemini API analysis, embedding the posts data directly."""
    posts_json_string = json.dumps(posts_data_list, indent=2)
    prompt = f"""You are an elite content-curation AI, "Analyst Prime," specifically programmed to assist world-class dating coach Garrett Darling (GD). Your primary function is to analyze Reddit posts and identify prime content opportunities with exceptional accuracy and adherence to the criteria outlined below. Perform your analysis step-by-step for each post to ensure thoroughness.

⸻

Content Tags Classification

In addition to scoring posts, you will classify each post with relevant content tags from the following lists. Select 1-5 most relevant tags per post based on the actual content, themes, and context. Do not force tags that don't clearly apply.

**Men's Content Tags:**
looksmaxing, alpha, sigma, redpill, blackpill, hustle, porn, gooning, submission, marriage, nightlife, gym, fashion, anxiety, depression, game, social_circle, baddies, training, purpose, dating, dates, feminism, wife, girlfriend, attractive, rejection, fuckboy, masculine, feminine, cold_approach, vision, society, nofap, semen_retention

**Women's Content Tags:**
genderfluid, trans, drag_queen, trans_in_schools, trans_books, onlyfans, sexwork, polyamory, nonbinary, lesbian, patriarchy, marriage, trans_surgery_regrets, new_age, meditation, yoga, vegan, self_development, weed, drinking, nightclubs, festivals, feminism, fashion_obsessed, self_image_obsessed, astrology, social_media, instagram, tiktok, fame, validation, status, family, children, being_a_mother, dog_mom, cat_mom, community, medication, anti_anxiety, anti_depressant, luxury_living, travel, therapy, girl_math, soft_girl_aesthetic, hot_girl_summer, old_money, baddie, female_empowerment, manifestation, journaling, incel, dating, dates, husband, boyfriend, fuckboy

**Universal Tags (apply to any gender):**
relationships, breakup, heartbreak, loneliness, confidence, self_esteem, mental_health, therapy, communication, social_skills, career, money, lifestyle, hobbies, health, fitness, style, technology, advice, support

⸻

Input

You will receive a JSON array named posts[]. Each object in this array represents a Reddit post and contains the following fields:

id • subreddit • title • body • img_text (may be an empty string) • link_flair_text • score • num_comments • created_utc (ISO-8601 format) • url

The specific posts for your analysis are provided in: {posts_json_string}

⸻

Mission

Your mission is to surface Reddit posts that ask questions or present scenarios most likely to:
1.  Provide maximum practical dating and social life transformation value to single men (and men re-entering the dating scene).
2.  Spark high engagement when GD creates short, impactful Loom-style video replies.

⸻

Core Directives & Definitions

To ensure consistent and accurate processing, adhere to the following definitions:

* **GD Classroom Themes**: These are recurring topics and frameworks Garrett Darling emphasizes in his coaching. Examples include (but are not limited to):
    * Set analysis (observing and understanding social dynamics in real-time)
    * Focus points (maintaining appropriate attention during interactions)
    * Behaviour interpretation (understanding the subtext of actions and words)
    * Frame control
    * Building genuine confidence
    * Effective communication strategies (including texting and in-person)
    * Value demonstration
    * Handling rejection constructively
    * Developing an attractive lifestyle
    * *User: Please add/modify any other specific themes Garrett focuses on here.*

* **Deducing Author Attributes**:
    * **Gender/Age**: Base deductions *only* on explicit statements (e.g., "I'm a 28M", "As a woman...", "my husband and I"), strong contextual clues within the post body, or highly indicative flair (e.g., "Male seeking advice"). Avoid stereotyping. If gender or age is ambiguous or not clearly determinable, note this in your internal assessment and do not score points that depend on uncertain attributes. For the 'man' field in the output, only mark true/false if reasonably certain.
    * **Purchasing Power**: Infer potential for investing in coaching (e.g., >$2,000/month) from explicit mentions of income, budget, high-cost hobbies, profession (e.g., "I'm a software engineer in NYC", "my business revenue is..."), or significant financial decisions discussed in the post. Do not assume; look for tangible indicators.
    * **Coachable Attitude**: Indicated by phrases like "What am I doing wrong?", "Need honest feedback", "Willing to try anything", "How can I improve?", clear articulation of self-improvement goals, and a non-defensive tone when describing failures.
    * **Dire Need & Urgency**: Evident through expressions of significant emotional pain, repeated failures, feelings of hopelessness, desperation for change, or critical life junctures (e.g., post-divorce, recently single after a long-term relationship).

⸻

Task

**1. Recognize Advice Requests & Filter Posts**

Evaluate each post against the following filters. If a post fails *any* filter, assign `priority_score = 0` to it, and it will be excluded from further scoring and the final output.

* **Filter 1: Recency**
    * Rule: `created_utc` must be within the last 72 hours (i.e., ≤ 72 hours old). Posts ≤ 24 hours old are ideal and scored higher.
* **Filter 2: Author Focus & Profile**
    * Rule: The post's author should ideally be a male aged 25 years or older.
    * Deduce gender and probable age using the "Deducing Author Attributes" guidelines.
    * Female-authored posts are acceptable and valuable but will be managed to ensure a balanced output (see Scoring and Ratio Enforcement).
    * If the author is clearly identifiable as non-binary, an organization/company, or a bot, the post is rejected (`priority_score = 0`).
* **Filter 3: Purchasing Power Indication**
    * Rule: Preference given to posts where the author appears to be USA-based (inferred from language, spelling, subreddits, location mentions) AND/OR shows indicators of having the purchasing power for coaching (see "Deducing Author Attributes"). This is a preference, not a hard rejection criterion, but contributes to the score.
* **Filter 4: Advice Topic Relevance**
    * Rule: The post must seek advice—explicitly or implicitly—on one or more of the following topics relevant to dating and self-improvement for men:
        * Approach Mechanics & Field Work (initiating conversations, overcoming approach anxiety)
        * Vibe & Confidence (inner game, self-belief, projecting attractive energy)
        * Text / Online Dating Game (messaging strategies, profile optimization, app use)
        * Game Fundamentals (core principles of attraction and social dynamics)
        * Lifestyle elements that directly boost dating success (e.g., testosterone optimization, self-image improvement, fitness impact on dating, effective time-management for social life).
* **Filter 5: Content Length**
    * Rule: The combined length of `title`, `body`, and `img_text` must be ≤ 1,000 words.
* **Filter 6: Content Safety & Appropriateness**
    * Rule: The post must not contain gender-war rants, hateful or overtly political screeds, pornography, or content that violates common subreddit rules. It should be a genuine request for help or discussion.

**2. Score Each Kept Post (0 - 100 points)**

For posts that pass ALL filters, calculate `priority_score` as the sum of `value_score` and `virality_score` (capped at 100).

**`value_score` (Maximum 80 points)**
Award points based on the following criteria. Refer to "Deducing Author Attributes" and "GD Classroom Themes" for guidance.

* **USA-Based with Budget Indication**: +15 points if the author is likely USA-based AND there's an indication of a budget/income compatible with spending >$2,000/month on coaching/courses.
* **Target Male Author**: +15 points if the author is clearly a male, aged 25 or older, and states or implies he is single or re-entering the dating scene.
* **Highly Coachable Attitude**: +15 points if the author demonstrates a strong willingness to learn, take responsibility, and apply advice.
* **Dire Need & Urgency**: +15 points if the post conveys significant pain, repeated struggles, or a desperate desire for change.
* **Core Dating-Skill Request**: +10 points if the primary advice sought relates directly to core dating skills such as approach, pulling, vibe management, advanced texting strategies, or detailed field reports seeking analysis.
* **Direct Tie-in to GD Classroom Themes**: +10 points if the post's topic or question strongly aligns with one or more of the "GD Classroom Themes" defined above.
* **Female Post Bonus**: +6 points. This bonus is *only* applicable if the author is identified as female. It helps ensure valuable female perspectives are considered, aiming for the target ratio mentioned in Task 4, without outranking the highest-value male-authored posts. (This means a female post cannot get points for "Target Male Author").
* **Length Penalty**: -5 points if the combined content (title + body + img_text) appears to be longer than 2-3 paragraphs (approximately more than 6-8 sentences of substantial content). This penalty encourages concise, focused posts that are easier to address in short video responses.

**`virality_score` (Maximum 20 points)**
Award points based on indicators of potential engagement:

* **Recency Bonus**:
    * Post created_utc ≤ 24 hours ago: +8 points
    * Post created_utc > 24 hours and ≤ 72 hours ago: +4 points
* **High Existing Engagement**: +6 points if the post's `score` (upvotes) > 50 OR `num_comments` > 15.
* **Emotionally Charged / Controversial Topic**: +6 points if the topic is inherently emotionally charged or commonly debated (e.g., ghosting, handling rejection, debates around modern masculinity, friend-zone dynamics), making it ripe for discussion.

*A post can only reach 100 points if it exceptionally meets criteria across both value and virality components.*

**3. Prepare Output Content**

For each post that has a `priority_score` > 0, formulate the following fields:

* `id`: The original post ID.
* `priority_score`: The calculated score (0-100).
* `man`: Boolean. `true` if the author is deduced to be male; `false` if deduced to be female. If gender cannot be reasonably determined or is non-binary, the post should have been filtered out (priority_score = 0).
* `concise_theme`: A very brief (3-6 words) theme of the post (e.g., "Struggles with texting after first date").
* `short_summary`: A one-sentence summary of the author's situation and core question (max 25 words).
* `tags`: Array of 1-5 relevant content tags from the predefined tag lists above. Select tags that most accurately describe the post's content and themes. Use exact tag names from the lists provided.
* `rationale_for_value`: Briefly explain *why* this post is valuable for GD's audience, citing specific scoring criteria met (e.g., "Male 30s, clear financial capacity, urgent need due to recent divorce, coachable attitude, core issue is approach anxiety.").
* `rationale_for_views`: Briefly explain *why* this post might get views/engagement, citing specific scoring criteria (e.g., "Recent post on ghosting, already has 70 comments, highly emotional.").
* `suggested_angle_for_coach`: Propose a specific, actionable angle or hook GD could use for a video reply. Focus on providing unique insight or a concise takeaway. (e.g., "GD breaks down the top 3 reasons she might have ghosted and how to reframe for next time.").
* `url`: The original post URL.

**4. Final Output Generation**

Return a single JSON object in the exact format specified below:

```json
{{
  "result": [
    {{
      "id": "<post id>",
      "priority_score": 97,
      "man": true,
      "concise_theme": "She ghosted after first date",
      "short_summary": "29-year-old US guy with good job keeps losing matches after great first dates; asks what he's doing wrong.",
      "tags": ["dating", "rejection", "game", "anxiety"],
      "rationale_for_value": "Male 29, high income, clear pain, core texting/retention issue.",
      "rationale_for_views": "Ghosting topic + 60 upvotes + 34 comments in 12 h.",
      "suggested_angle_for_coach": "Deep dive on why women vanish, frame control, follow-up logistics.",
      "url": "[https://reddit.com/](https://reddit.com/)…"
    }}
    // ... more post objects
  ],
  "more": false
}}
```

**Field Specifications for Final Output:**
* `result`: An array containing up to the 20 highest-scoring post objects, sorted by `priority_score` in descending order.
* `more`: Boolean. Set to `true` if there are more than 20 posts that met the filtering criteria and received a `priority_score` > 0; otherwise, set to `false`.

**Ratio Enforcement (Applied to the `result` array):**
* After selecting the top 20 posts (or fewer, if not enough qualify), if the number of selected posts is greater than 10, review the `man` field. Ensure that posts where `man` is `false` (female authors) do not exceed 20% of the total posts in the `result` array.
* If the ratio is exceeded, replace the lowest-scoring female-authored post(s) with the next highest-scoring male-authored post(s) that did not initially make the top 20, until the ratio is met or there are no more qualified male posts. If there are fewer than 5 posts, this specific ratio rule can be relaxed, but maintain a strong preference for male-authored content as per scoring.

⸻

Return Rules for the Final Output

* You MUST return ONLY the single JSON object described above. Do not include any explanatory text, acknowledgements, or markdown formatting (like ```json ... ```) around the JSON output.
* All strings within the JSON must be on a single line (i.e., no embedded `\n` characters). Escape characters as necessary for valid JSON.
* Omit any keys from the output objects that are not explicitly specified in the "Final Output Generation" section.
* Ensure all calculations and filtering logic are strictly followed to maximize accuracy.
"""
    return prompt

def process_batch_with_api(formatted_posts, api_key):
    """Process a batch of posts with Gemini API."""
    genai.configure(api_key=api_key)
    # Using gemini-2.5-flash-preview-05-20 for processing
    model = genai.GenerativeModel(model_name='gemini-2.5-flash-preview-05-20',
                                  generation_config={"response_mime_type": "application/json"})


    prompt_text = create_gemini_prompt_for_api(formatted_posts)
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"Sending batch to Gemini API (Attempt {attempt + 1}/{max_retries})...")
            response = model.generate_content(prompt_text)
            
            # Assuming response.text is the JSON string as per response_mime_type
            response_json_str = response.text
            
            api_response_data = json.loads(response_json_str)
            
            # Log the 'more' flag for observation
            more_flag = api_response_data.get('more', False)
            print(f"Gemini API response 'more' flag: {more_flag}")
            
            return api_response_data.get('result', [])
            
        except Exception as e:
            print(f"Error calling Gemini API or parsing response (Attempt {attempt + 1}): {e}")
            if 'response' in locals() and hasattr(response, 'text'):
                 print(f"Raw API response text: {response.text[:500]}...") # Print first 500 chars
            if attempt < max_retries - 1:
                # Exponential backoff: wait longer after each failure
                wait_time = 5 * (2 ** attempt)  # 5s, 10s, 20s
                print(f"Retrying after {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                print("Max retries reached. Failed to process batch.")
                return [] # Return empty list on failure after retries
    return [] # Should not be reached if retries are handled properly

def update_processed_posts(conn, analyzed_posts, all_post_ids):
    """Update the database with Gemini analysis results. Returns the connection (may be recreated)."""
    # Check if connection is still alive and reconnect if needed
    max_reconnect_attempts = 3
    for attempt in range(max_reconnect_attempts):
        try:
            # Test the connection with a simple query
            test_cur = conn.cursor()
            test_cur.execute("SELECT 1")
            test_cur.close()
            break  # Connection is good
        except:
            if attempt < max_reconnect_attempts - 1:
                print(f"Database connection lost, reconnecting (attempt {attempt + 1}/{max_reconnect_attempts})...")
                try:
                    conn.close()
                except:
                    pass
                # Recreate connection
                db_config = get_db_connection_dict()
                conn = get_db_connection(db_config)
                print("Database reconnected successfully.")
            else:
                print("Failed to reconnect to database after multiple attempts.")
                raise psycopg2.InterfaceError("Database connection failed")
    
    cur = conn.cursor()
    try:
        analysis_results_dict = {post['id']: post for post in analyzed_posts if 'id' in post}
        updates = []
        for post_id in all_post_ids:
            analysis = analysis_results_dict.get(post_id)
            if analysis:
                priority_score = analysis.get('priority_score', 0)
                concise_theme = analysis.get('concise_theme')
                # Truncate concise_theme if it exceeds 100 characters
                if concise_theme and len(concise_theme) > 100:
                    concise_theme = concise_theme[:100]
                    print(f"Warning: Truncated concise_theme for post {post_id} to 100 characters.")
                
                short_summary = analysis.get('short_summary')
                # Truncate short_summary if it exceeds 250 characters
                if short_summary and len(short_summary) > 250:
                    short_summary = short_summary[:250]
                    print(f"Warning: Truncated short_summary for post {post_id} to 250 characters.")
                
                rationale_for_value = analysis.get('rationale_for_value')
                rationale_for_views = analysis.get('rationale_for_views')
                suggested_angle_for_coach = analysis.get('suggested_angle_for_coach')
                
                # Extract gender information from Gemini analysis
                is_male_author = analysis.get('man')  # This comes as boolean from Gemini
                
                # Extract tags from Gemini analysis
                tags = analysis.get('tags', [])  # Default to empty array if not provided
                
                updates.append((True, priority_score, concise_theme, short_summary,
                                rationale_for_value, rationale_for_views, suggested_angle_for_coach, 
                                is_male_author, tags, post_id))
            else:
                updates.append((True, 0, None, None, None, None, None, None, [], post_id))
        
        update_query = sql.SQL("""
            UPDATE posts_raw SET processed = %s, priority_score = %s, concise_theme = %s,
            short_summary = %s, rationale_for_value = %s, rationale_for_views = %s,
            suggested_angle_for_coach = %s, is_male_author = %s, tags = %s WHERE id = %s;
        """)
        cur.executemany(update_query, updates)
        conn.commit()
        print(f"Updated {len(all_post_ids)} posts in the database.")
        print(f"Set priority scores and details for {len(analysis_results_dict)} relevant posts, 0 for {len(all_post_ids) - len(analysis_results_dict)} non-relevant posts.")
    except Exception as e:
        conn.rollback()
        print(f"Error updating database: {e}")
        raise
    finally:
        cur.close()
    
    return conn  # Return the connection (may have been recreated)

def process_posts_with_gemini():
    """Main function to process unanalyzed posts with Gemini API."""
    try:
        db_config = get_db_connection_dict()
        api_key = get_gemini_api_key()
        processing_config = get_processing_config()
        
        if not api_key:
            print("❌ Gemini API key not found. Please set GEMINI_API_KEY environment variable.")
            return
        
        print("Starting Reddit posts analysis with Gemini API...")
        
        conn = None
        batch_size = processing_config['gemini_batch_size']
        total_processed = 0
        total_relevant = 0
        consecutive_failures = 0
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        return
    
    try:
        conn = get_db_connection(db_config)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM posts_raw WHERE priority_score IS NULL;")
        total_unprocessed = cur.fetchone()[0]
        cur.close()
        
        if total_unprocessed == 0:
            print("No posts found that need Gemini scoring.")
            return
        
        print(f"Found {total_unprocessed} total posts that need Gemini scoring.")
        print(f"Processing in batches of {batch_size}...")
        
        batch_number = 0
        while True:
            batch_number += 1
            posts = fetch_unprocessed_posts(conn, batch_size)
            if not posts:
                print("All posts have been scored by Gemini!")
                break
            
            print(f"\n--- Batch {batch_number}: Processing {len(posts)} posts ---")
            
            formatted_posts = format_posts_for_gemini(posts)
            all_post_ids = [post_data[0] for post_data in posts]
            
            print(f"Processing batch {batch_number} with Gemini API...")
            analyzed_posts = process_batch_with_api(formatted_posts, api_key)
            
            batch_relevant = len(analyzed_posts)
            print(f"Batch {batch_number}: Gemini API identified {batch_relevant} relevant posts out of {len(posts)} analyzed.")
            
            # Track consecutive failures
            if batch_relevant == 0 and len(posts) > 0:
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    print(f"\n⚠️  WARNING: {consecutive_failures} consecutive batches failed.")
                    print("This might indicate persistent API issues. Consider waiting and trying again later.")
                    print("The script will continue, but you may want to interrupt (Ctrl+C) and retry later.\n")
            else:
                consecutive_failures = 0  # Reset on success
            
            if analyzed_posts:
                print(f"Example results from batch {batch_number}:")
                for i, result in enumerate(analyzed_posts[:2]):
                    print(f"  Post {result.get('id', 'N/A')}: Score {result.get('priority_score', 'N/A')} - {result.get('concise_theme', 'No theme')}")
            
            # Update database (connection recovery handled internally)
            conn = update_processed_posts(conn, analyzed_posts, all_post_ids)
            
            total_processed += len(posts)
            total_relevant += batch_relevant
            
            print(f"Batch {batch_number} completed. Progress: {total_processed}/{total_unprocessed} posts scored.")
            
            if posts and len(posts) == batch_size:
                print("Pausing 5 seconds before next batch...")
                time.sleep(5)
        
        print(f"\n🎉 ALL ANALYSIS COMPLETED!")
        print(f"📊 Total posts scored: {total_processed}")
        print(f"✅ Total relevant posts found: {total_relevant}")
        if total_processed > 0 :
            print(f"📈 Relevance rate: {(total_relevant/total_processed*100):.1f}%")
        else:
            print(f"📈 Relevance rate: 0.0%")
        print(f"🔢 Non-relevant posts (scored 0): {total_processed - total_relevant}")
        
    except Exception as e:
        print(f"Error during processing: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        if conn:
            conn.close()
            print("Database connection closed.")
        # No browser driver to close

if __name__ == "__main__":
    process_posts_with_gemini() 