-- Enable the pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Table for Reddit users (Created first)
CREATE TABLE users (
    id VARCHAR(50) PRIMARY KEY, -- Reddit user ID (e.g., t2_1w72) - increased to 50 chars
    username VARCHAR(50) NOT NULL UNIQUE, -- Reddit username without u/ prefix
    created_utc TIMESTAMP WITH TIME ZONE, -- When the user account was created
    comment_karma INTEGER, -- User's comment karma
    link_karma INTEGER, -- User's link karma
    is_verified BOOLEAN DEFAULT FALSE, -- Whether user has verified email
    first_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW() -- When we first encountered this user
);

-- Table for grouped themes/questions (Created second)
CREATE TABLE themes (
    theme_id SERIAL PRIMARY KEY,
    theme_text TEXT NOT NULL, -- Representative text for the theme
    vector vector(384), -- Embedding vector for the theme
    example_post_ids VARCHAR(20)[], -- Array of post IDs belonging to this theme
    score_agg FLOAT, -- Aggregated score for the theme
    status VARCHAR(20) DEFAULT 'open' -- e.g., open, answered
);

-- Table for raw Reddit posts (Created third)
CREATE TABLE posts_raw (
    id VARCHAR(20) PRIMARY KEY, -- Reddit post ID
    subreddit VARCHAR(50) NOT NULL,
    created_utc TIMESTAMP WITH TIME ZONE NOT NULL,
    title TEXT,
    body TEXT,
    img_text TEXT, -- Text extracted from images
    score INTEGER, -- Pushshift score (upvotes - downvotes)
    num_comments INTEGER,
    url VARCHAR(255) NOT NULL,
    link_flair_text VARCHAR(100), -- Added flair text
    author_id VARCHAR(50), -- Foreign key to users table - increased to 50 chars
    vector vector(384), -- Embedding vector (Sentence-Transformers output size)
    status VARCHAR(20) DEFAULT 'open', -- e.g., open, answered, irrelevant
    processed BOOLEAN DEFAULT FALSE, -- Flag to indicate if the post has been scored
    score_total FLOAT, -- Calculated total score based on the formula
    clustered BOOLEAN DEFAULT FALSE, -- Flag to indicate if the post has been embedded and clustered
    theme_id INTEGER -- Foreign key to themes table
);

-- Add foreign key constraint to posts_raw for themes (Added after themes table is created)
ALTER TABLE posts_raw
ADD CONSTRAINT fk_theme
FOREIGN KEY (theme_id)
REFERENCES themes (theme_id)
ON DELETE SET NULL;

-- Add foreign key constraint to posts_raw for users (Added after users table is created)
ALTER TABLE posts_raw
ADD CONSTRAINT fk_author
FOREIGN KEY (author_id)
REFERENCES users (id)
ON DELETE SET NULL;

-- Add a column for the Gemini relevance score
ALTER TABLE posts_raw
ADD COLUMN priority_score INTEGER;

-- Add columns for detailed Gemini analysis results
ALTER TABLE posts_raw
ADD COLUMN concise_theme VARCHAR(100);
ALTER TABLE posts_raw
ADD COLUMN short_summary VARCHAR(250);
ALTER TABLE posts_raw
ADD COLUMN rationale_for_value TEXT;
ALTER TABLE posts_raw
ADD COLUMN rationale_for_views TEXT;
ALTER TABLE posts_raw
ADD COLUMN suggested_angle_for_coach TEXT;
ALTER TABLE posts_raw
ADD COLUMN is_male_author BOOLEAN; -- TRUE for male, FALSE for female, NULL for unknown/non-binary
ALTER TABLE posts_raw
ADD COLUMN tags TEXT[]; -- Array of AI-classified content tags

-- Create indexes for efficient querying
CREATE INDEX idx_posts_raw_processed ON posts_raw (processed);
CREATE INDEX idx_posts_raw_author_id ON posts_raw (author_id);
CREATE INDEX idx_users_username ON users (username);
CREATE INDEX idx_posts_raw_tags ON posts_raw USING GIN (tags); 