-- Migration to add gender field to posts_raw table
-- Run this on existing databases to add the new column

ALTER TABLE posts_raw 
ADD COLUMN IF NOT EXISTS is_male_author BOOLEAN; -- TRUE for male, FALSE for female, NULL for unknown/non-binary

-- Add comment for clarity
COMMENT ON COLUMN posts_raw.is_male_author IS 'Gender analysis from Gemini: TRUE for male, FALSE for female, NULL for unknown/non-binary'; 