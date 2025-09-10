-- Performance Indexes for Reddit Researcher Database
-- These indexes are optimized for the queries used in the Streamlit app and pipeline components

-- ============================================================================
-- CRITICAL INDEXES FOR STREAMLIT UI PERFORMANCE
-- ============================================================================

-- 1. Main UI query index - covers the most common query pattern
-- Query: WHERE priority_score IS NOT NULL AND status NOT IN ('ignored', 'sent') ORDER BY priority_score DESC, created_utc DESC
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_posts_ui_main 
ON posts_raw (priority_score DESC, created_utc DESC) 
WHERE priority_score IS NOT NULL AND status NOT IN ('ignored', 'sent');

-- 2. Status filtering index - for filtering by status
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_posts_status 
ON posts_raw (status);

-- 3. Priority score index - for score-based filtering and sorting
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_posts_priority_score 
ON posts_raw (priority_score DESC) 
WHERE priority_score IS NOT NULL;

-- 4. Selected posts for email query - covers status = 'selected' ORDER BY created_utc DESC
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_posts_selected_email 
ON posts_raw (created_utc DESC) 
WHERE status = 'selected';

-- 5. Subreddit filtering index - for subreddit dropdown filtering
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_posts_subreddit 
ON posts_raw (subreddit);

-- ============================================================================
-- PIPELINE PROCESSING INDEXES
-- ============================================================================

-- 6. Unprocessed posts index - for initial scoring pipeline
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_posts_unprocessed 
ON posts_raw (processed, created_utc DESC) 
WHERE processed = FALSE;

-- 7. Gemini analysis index - for posts needing priority scoring
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_posts_gemini_pending 
ON posts_raw (created_utc DESC) 
WHERE priority_score IS NULL;

-- 8. Embedding generation index - for posts needing vector embeddings
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_posts_embedding_pending 
ON posts_raw (processed, created_utc DESC) 
WHERE processed = TRUE AND vector IS NULL;

-- 9. Clustering index - for posts ready for clustering
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_posts_clustering_pending 
ON posts_raw (clustered, created_utc DESC) 
WHERE processed = TRUE AND vector IS NOT NULL AND clustered = FALSE;

-- ============================================================================
-- LOOKUP AND DEDUPLICATION INDEXES
-- ============================================================================

-- 10. URL lookup index - for duplicate detection and updates
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_posts_url_unique 
ON posts_raw (url);

-- 11. ID lookup index - for fast primary key lookups (already exists as PRIMARY KEY)
-- No need to create - PRIMARY KEY on 'id' already provides this

-- 12. Created timestamp index - for time-based queries and sorting
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_posts_created_utc 
ON posts_raw (created_utc DESC);

-- ============================================================================
-- COMPOSITE INDEXES FOR COMPLEX QUERIES
-- ============================================================================

-- 13. Status + Priority composite index - for filtered views
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_posts_status_priority 
ON posts_raw (status, priority_score DESC, created_utc DESC);

-- 14. Subreddit + Priority composite index - for subreddit-specific filtering
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_posts_subreddit_priority 
ON posts_raw (subreddit, priority_score DESC, created_utc DESC) 
WHERE priority_score IS NOT NULL;

-- ============================================================================
-- PIPELINE STATUS TABLE INDEXES
-- ============================================================================

-- 15. Pipeline status lookup - single row table but good to have
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_pipeline_status_id 
ON pipeline_status (id);

-- ============================================================================
-- THEMES TABLE INDEXES (if used)
-- ============================================================================

-- 16. Theme status index
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_themes_status 
ON themes (status);

-- 17. Theme score index
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_themes_score 
ON themes (score_agg DESC);

-- ============================================================================
-- MAINTENANCE COMMANDS
-- ============================================================================

-- Update table statistics after creating indexes
ANALYZE posts_raw;
ANALYZE pipeline_status;
ANALYZE themes;

-- Show index usage statistics (run this periodically to monitor performance)
-- SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read, idx_tup_fetch 
-- FROM pg_stat_user_indexes 
-- WHERE schemaname = 'public' 
-- ORDER BY idx_scan DESC;

-- Show table sizes and index sizes
-- SELECT 
--     schemaname,
--     tablename,
--     pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
--     pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) as table_size,
--     pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename) - pg_relation_size(schemaname||'.'||tablename)) as index_size
-- FROM pg_tables 
-- WHERE schemaname = 'public'
-- ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC; 