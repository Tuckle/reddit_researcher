# Reddit Researcher

A comprehensive AI-powered system for analyzing Reddit posts from dating and relationship subreddits to identify valuable content opportunities for social media and coaching purposes.

## 🎯 Purpose

Reddit Researcher is designed to help dating coaches and content creators systematically discover, analyze, and curate high-value questions and discussions from Reddit's dating communities. The system uses advanced AI analysis to score posts based on their potential value for creating educational content, coaching responses, and social media engagement.

## 🚀 Core Features

### **Intelligent Content Discovery**
- **Multi-Subreddit Monitoring**: Automatically fetches posts from 15+ dating-related subreddits including r/dating, r/relationships, r/Tinder, r/seduction, and more
- **Real-time Ingestion**: Continuously monitors for new posts using Reddit's official API
- **Image Text Extraction**: Uses OCR technology to extract text from dating app screenshots and images
- **Duplicate Detection**: Prevents duplicate content with intelligent URL-based deduplication

### **AI-Powered Analysis**
- **Gemini AI Scoring**: Each post is analyzed by Google's Gemini AI using a sophisticated 100-point scoring system
- **Multi-Factor Evaluation**: Posts are scored based on:
  - **Value Score (80 points)**: Actionability, target audience fit, coaching potential, urgency of need
  - **Virality Score (20 points)**: Engagement potential, recency, emotional resonance
- **Gender Detection**: Automatically identifies post author gender for targeted content curation
- **Theme Extraction**: AI generates concise themes and summaries for each relevant post
- **Coaching Angle Suggestions**: AI provides specific angles for creating response content

### **Streamlined Review Interface**
- **Web Dashboard**: Modern Streamlit-based interface for reviewing and managing posts
- **Smart Filtering**: Filter by score ranges, subreddits, gender, and selection status
- **Bulk Operations**: Select multiple posts for email campaigns
- **Real-time Pipeline Monitoring**: Track data ingestion and processing status
- **Performance Optimized**: Database indexes ensure fast loading even with large datasets

### **Automated Content Distribution**
- **Email Campaigns**: Generate and send HTML email reports with selected posts
- **Google Sheets Integration**: Automatically sync selected content to spreadsheets for team collaboration
- **Lead Management**: Track posts through the entire content creation workflow
- **Template System**: Consistent formatting for all outbound communications

### **Robust Data Management**
- **PostgreSQL Database**: Scalable database with performance optimizations
- **User Tracking**: Associates posts with Reddit usernames for audience insights
- **Status Management**: Track posts through multiple states (open, selected, sent, answered)
- **Data Retention**: Configurable cleanup policies for old posts

## 🏗️ System Architecture

### **Core Components**

#### **Data Ingestion Layer** (`ingestor/`)
- `ingest.py`: Main ingestion engine using Reddit API and Pushshift fallback
- Handles rate limiting, error recovery, and data validation
- Extracts text from images using EasyOCR
- Manages user tracking and post deduplication

#### **AI Processing Layer** (`processing/`)
- `gemini_processor.py`: Gemini AI integration for post analysis and scoring
- `generate_embeddings.py`: Vector embeddings for similarity analysis
- `process_posts.py`: Post clustering and theme generation
- `run_gemini_analysis.py`: Batch processing controller

#### **Scoring Engine** (`scorer/`)
- `score_posts.py`: Legacy scoring algorithm for posts
- Keyword-based relevance scoring
- Engagement metrics calculation

#### **Web Interface** (`app/`)
- `streamlit_app.py`: Complete web dashboard for post review and management
- Real-time filtering and pagination
- Email campaign management
- Google Sheets synchronization

#### **Communication Systems** (`email_digest/`, `services/`)
- `send_digest.py`: Email digest generation and delivery
- `google_sheets_service.py`: Google Sheets API integration
- HTML email templating with post details

#### **Automation & Monitoring** (`scheduler/`, `utils/`)
- `run_pipeline.py`: Automated daily pipeline execution
- `pipeline_health_check.py`: System health monitoring and auto-repair
- Process tracking and stale state detection

### **Database Schema**
- **posts_raw**: Main posts table with AI analysis results
- **users**: Reddit user tracking and metadata
- **themes**: Post clustering and theme management
- **pipeline_status**: System status and monitoring

### **Configuration Management**
- Environment variable-based configuration (`.env`)
- Centralized configuration in `config.py`
- Support for multiple environments (development, production)

## 🛠️ Setup & Installation

### **Prerequisites**
- Python 3.8+
- PostgreSQL database with pgvector extension
- Reddit API credentials
- Google Gemini API access
- Gmail account for email sending
- Google Sheets API credentials (optional)

### **Quick Start**
1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment:**
   ```bash
   cp _env.template .env
   # Edit .env with your actual credentials
   ```

3. **Setup database:**
   ```bash
   psql reddit_researcher < database/schema.sql
   ```

4. **Run the system:**
   ```bash
   # Start the web interface
   streamlit run app/streamlit_app.py
   
   # Or run individual components
   python ingestor/ingest.py          # Fetch new posts
   python processing/gemini_processor.py  # AI analysis
   python email_digest/send_digest.py     # Send email reports
   ```

### **Environment Variables**
Required configuration in `.env`:
```bash
# Database
DB_NAME=your_database
DB_PASSWORD=your_password

# API Keys
GEMINI_API_KEY=your_gemini_key
REDDIT_CLIENT_ID=your_reddit_id
REDDIT_CLIENT_SECRET=your_reddit_secret

# Email (optional)
EMAIL_SENDER=your_email@gmail.com
EMAIL_PASSWORD=your_app_password
EMAIL_RECIPIENTS=recipient@email.com
```

## 📊 Usage Workflow

### **Typical Daily Workflow**
1. **Automatic Ingestion**: System fetches new posts from monitored subreddits
2. **AI Analysis**: Gemini AI scores posts for relevance and value
3. **Manual Review**: Use web interface to review high-scoring posts
4. **Content Selection**: Mark relevant posts for content creation
5. **Email Campaign**: Send selected posts to team members
6. **Google Sheets Sync**: Selected posts automatically sync to spreadsheets
7. **Content Creation**: Team creates responses based on curated posts

### **Key Features in Action**
- **Smart Filtering**: Quickly find posts by score, gender, subreddit
- **Batch Selection**: Select multiple posts for email campaigns
- **Real-time Updates**: System automatically refreshes when new data is available
- **Performance Optimized**: Handles thousands of posts with sub-second response times

## 🎯 Target Use Cases

### **Dating Coaches & Content Creators**
- Identify trending questions and pain points in dating communities
- Generate content ideas based on real user problems
- Track engagement potential of different topics
- Build systematic content pipelines

### **Social Media Managers**
- Discover viral-worthy content in niche communities
- Monitor competitor discussions and trending topics
- Generate response content for maximum engagement
- Track content performance and audience preferences

### **Market Researchers**
- Analyze discussion patterns in target demographics
- Identify emerging trends and pain points
- Generate insights for product development
- Track sentiment and language changes over time

## 🔧 Technical Highlights

### **Performance & Scalability**
- **Database Indexing**: Comprehensive indexing strategy for fast queries
- **Caching**: Multi-layer caching for improved response times
- **Batch Processing**: Efficient handling of large datasets
- **Async Operations**: Background processing for time-intensive tasks

### **AI & Machine Learning**
- **Advanced Prompt Engineering**: Sophisticated prompts for consistent AI analysis
- **Multi-criteria Scoring**: Balanced evaluation across multiple dimensions
- **Natural Language Processing**: Theme extraction and content summarization
- **Gender Detection**: Audience targeting based on post author demographics

### **Integration & APIs**
- **Reddit API**: Official API integration with fallback systems
- **Google Services**: Gmail and Google Sheets integration
- **OCR Processing**: Image text extraction for multimedia content
- **Webhook Support**: Extensible architecture for additional integrations

### **Monitoring & Reliability**
- **Health Checks**: Automated system health monitoring
- **Error Recovery**: Robust error handling and retry mechanisms
- **Process Tracking**: Pipeline status monitoring and alerting
- **Data Validation**: Comprehensive input validation and sanitization

## 📈 Benefits

- **Time Efficiency**: Automates hours of manual Reddit browsing
- **Quality Assurance**: AI filtering ensures only high-value content surfaces
- **Systematic Approach**: Consistent methodology for content discovery
- **Scalability**: Handles growing data volumes without performance degradation
- **Team Collaboration**: Centralized platform for content team coordination
- **Data-Driven Insights**: Analytics and metrics for content strategy optimization

---

*Reddit Researcher transforms the chaotic landscape of social media into a structured, AI-powered content discovery engine that helps coaches and creators consistently find and leverage the most valuable opportunities for audience engagement and business growth.* 