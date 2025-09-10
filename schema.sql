-- Add this at the end of the file after all table definitions

-- Performance indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_posts_priority_score ON posts_raw(priority_score DESC) WHERE priority_score IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_posts_status ON posts_raw(status) WHERE status NOT IN ('ignored', 'sent', 'lead');
CREATE INDEX IF NOT EXISTS idx_posts_created_utc ON posts_raw(created_utc DESC);
CREATE INDEX IF NOT EXISTS idx_posts_subreddit ON posts_raw(subreddit) WHERE subreddit IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_posts_gender ON posts_raw(is_male_author) WHERE is_male_author IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_posts_composite ON posts_raw(priority_score DESC, created_utc DESC) WHERE priority_score IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_posts_author_id ON posts_raw(author_id) WHERE author_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_users_id ON users(id);

-- Composite indexes for common filter combinations
CREATE INDEX IF NOT EXISTS idx_posts_status_priority ON posts_raw(status, priority_score DESC) WHERE priority_score IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_posts_subreddit_priority ON posts_raw(subreddit, priority_score DESC) WHERE priority_score IS NOT NULL AND subreddit IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_posts_gender_priority ON posts_raw(is_male_author, priority_score DESC) WHERE priority_score IS NOT NULL; 