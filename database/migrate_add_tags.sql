-- Migration to add tags field to posts_raw table
-- Run this on existing databases to add the new column

ALTER TABLE posts_raw 
ADD COLUMN IF NOT EXISTS tags TEXT[]; -- Array of tags classified by AI

-- Add index on tags for efficient filtering
CREATE INDEX IF NOT EXISTS idx_posts_raw_tags ON posts_raw USING GIN (tags);

-- Add comment for clarity
COMMENT ON COLUMN posts_raw.tags IS 'AI-classified content tags for filtering and categorization (e.g., {alpha, gym, dating, anxiety})'; 