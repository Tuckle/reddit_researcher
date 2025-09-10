-- Migration script to fix user ID length issues
-- Reddit user IDs can be longer than 20 characters

-- Increase the length of users.id field
ALTER TABLE users ALTER COLUMN id TYPE VARCHAR(50);

-- Increase the length of posts_raw.author_id field to match
ALTER TABLE posts_raw ALTER COLUMN author_id TYPE VARCHAR(50);

-- Update the comment for clarity
COMMENT ON COLUMN users.id IS 'Reddit user ID (e.g., t2_1w72) - increased to 50 chars to accommodate longer IDs';
COMMENT ON COLUMN posts_raw.author_id IS 'Foreign key to users table - increased to 50 chars to match users.id';

-- Verify the changes
SELECT 
    table_name, 
    column_name, 
    data_type, 
    character_maximum_length 
FROM information_schema.columns 
WHERE table_name IN ('users', 'posts_raw') 
AND column_name IN ('id', 'author_id')
ORDER BY table_name, column_name; 