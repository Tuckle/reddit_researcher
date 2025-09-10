-- Migration script to add users table and update posts_raw table
-- Run this script on existing databases to add user functionality

-- Create users table if it doesn't exist
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(20) PRIMARY KEY, -- Reddit user ID (e.g., t2_1w72)
    username VARCHAR(50) NOT NULL UNIQUE, -- Reddit username without u/ prefix
    created_utc TIMESTAMP WITH TIME ZONE, -- When the user account was created
    comment_karma INTEGER, -- User's comment karma
    link_karma INTEGER, -- User's link karma
    is_verified BOOLEAN DEFAULT FALSE, -- Whether user has verified email
    first_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW() -- When we first encountered this user
);

-- Add author_id column to posts_raw if it doesn't exist
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'posts_raw' AND column_name = 'author_id') THEN
        ALTER TABLE posts_raw ADD COLUMN author_id VARCHAR(20);
    END IF;
END $$;

-- Add foreign key constraint if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints 
                   WHERE constraint_name = 'fk_author' AND table_name = 'posts_raw') THEN
        ALTER TABLE posts_raw
        ADD CONSTRAINT fk_author
        FOREIGN KEY (author_id)
        REFERENCES users (id)
        ON DELETE SET NULL;
    END IF;
END $$;

-- Create indexes if they don't exist
CREATE INDEX IF NOT EXISTS idx_posts_raw_author_id ON posts_raw (author_id);
CREATE INDEX IF NOT EXISTS idx_users_username ON users (username);

-- Display migration completion message
DO $$
BEGIN
    RAISE NOTICE 'Migration completed successfully. Users table and author_id column added.';
END $$; 