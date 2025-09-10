#!/bin/bash

# Setup Health Monitoring for Reddit Pipeline
# This script configures automated health monitoring using cron

set -e

# Get the absolute path to the project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HEALTH_CHECK_SCRIPT="$PROJECT_DIR/reddit_researcher/utils/pipeline_health_check.py"
PYTHON_PATH="$PROJECT_DIR/venv/bin/python"
LOG_DIR="$PROJECT_DIR/logs"

echo "🏥 Setting up Pipeline Health Monitoring"
echo "=" * 50

# Check if health check script exists
if [ ! -f "$HEALTH_CHECK_SCRIPT" ]; then
    echo "❌ Health check script not found at: $HEALTH_CHECK_SCRIPT"
    exit 1
fi

# Check if Python virtual environment exists
if [ ! -f "$PYTHON_PATH" ]; then
    echo "❌ Python virtual environment not found at: $PYTHON_PATH"
    echo "Please ensure the virtual environment is set up correctly."
    exit 1
fi

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Make health check script executable
chmod +x "$HEALTH_CHECK_SCRIPT"

echo "✅ Project directory: $PROJECT_DIR"
echo "✅ Health check script: $HEALTH_CHECK_SCRIPT"
echo "✅ Python path: $PYTHON_PATH"
echo "✅ Log directory: $LOG_DIR"

# Create the cron job command
CRON_COMMAND="*/15 * * * * cd $PROJECT_DIR && $PYTHON_PATH $HEALTH_CHECK_SCRIPT --quiet >> $LOG_DIR/health_check.log 2>&1"

echo ""
echo "📅 Setting up cron job to run health check every 15 minutes..."

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "pipeline_health_check.py"; then
    echo "⚠️  Cron job for pipeline health check already exists."
    echo "Current cron jobs containing 'pipeline_health_check.py':"
    crontab -l 2>/dev/null | grep "pipeline_health_check.py" || true
    echo ""
    read -p "Do you want to replace the existing cron job? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "❌ Setup cancelled."
        exit 0
    fi
    
    # Remove existing cron job
    echo "🗑️  Removing existing cron job..."
    (crontab -l 2>/dev/null | grep -v "pipeline_health_check.py") | crontab -
fi

# Add new cron job
echo "➕ Adding new cron job..."
(crontab -l 2>/dev/null; echo "$CRON_COMMAND") | crontab -

echo "✅ Cron job added successfully!"
echo ""
echo "📋 Current cron configuration:"
crontab -l | grep "pipeline_health_check.py"

echo ""
echo "🔍 Testing health check script..."
cd "$PROJECT_DIR"
if "$PYTHON_PATH" "$HEALTH_CHECK_SCRIPT" --quiet; then
    echo "✅ Health check script test passed!"
else
    echo "⚠️  Health check script test had issues (this may be normal if pipeline has problems)"
fi

echo ""
echo "📊 Health monitoring setup complete!"
echo ""
echo "The health check will now run every 15 minutes and:"
echo "  • Check for stale pipeline states"
echo "  • Detect zombie/defunct processes"
echo "  • Find orphaned pipeline processes"
echo "  • Auto-fix database inconsistencies"
echo "  • Log results to: $LOG_DIR/health_check.log"
echo ""
echo "To view the health check log:"
echo "  tail -f $LOG_DIR/health_check.log"
echo ""
echo "To manually run a health check:"
echo "  cd $PROJECT_DIR && $PYTHON_PATH $HEALTH_CHECK_SCRIPT"
echo ""
echo "To remove the cron job:"
echo "  crontab -e  # then delete the line containing 'pipeline_health_check.py'"

# Set up log rotation to prevent log files from growing too large
echo ""
echo "📝 Setting up log rotation..."

# Create logrotate configuration
LOGROTATE_CONFIG="/tmp/reddit_pipeline_health_logrotate"
cat > "$LOGROTATE_CONFIG" << EOF
$LOG_DIR/health_check.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 644 $(whoami) $(id -gn)
}
EOF

# Check if we can install logrotate config (requires sudo)
if command -v logrotate >/dev/null 2>&1; then
    echo "📁 Logrotate configuration created at: $LOGROTATE_CONFIG"
    echo "To install log rotation (requires sudo):"
    echo "  sudo cp $LOGROTATE_CONFIG /etc/logrotate.d/reddit_pipeline_health"
    echo "  sudo chown root:root /etc/logrotate.d/reddit_pipeline_health"
else
    echo "⚠️  logrotate not found. Log rotation not configured."
fi

echo ""
echo "🎉 Setup complete! Health monitoring is now active." 