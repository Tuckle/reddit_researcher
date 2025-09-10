#!/usr/bin/env python3
"""
Pipeline Health Check Utility

This script performs comprehensive health checks on the Reddit pipeline:
1. Validates pipeline status in database vs actual running processes
2. Detects and fixes stale states
3. Checks for orphaned pipeline processes
4. Validates pipeline runtime duration
5. Auto-repairs database inconsistencies

Can be run standalone or imported by other modules.
"""

import os
import sys
import time
import yaml
import psycopg2
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# Add the parent directory to the path so we can import from reddit_researcher
sys.path.append(str(Path(__file__).parent.parent))

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    print("Warning: psutil not available. Using fallback process detection.")

def load_config():
    """Load configuration from config.yaml"""
    config_path = Path(__file__).parent.parent / 'config.yaml'
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def get_db_connection(db_config):
    """Get database connection"""
    return psycopg2.connect(**db_config)

def is_pipeline_process_running(pid):
    """Check if a specific PID is a running pipeline process"""
    if not pid:
        return False, "No PID provided"
    
    if PSUTIL_AVAILABLE:
        try:
            if not psutil.pid_exists(pid):
                return False, f"PID {pid} does not exist"
            
            process = psutil.Process(pid)
            
            # Check if process is zombie/defunct
            if process.status() == psutil.STATUS_ZOMBIE:
                return False, f"PID {pid} is zombie/defunct"
            
            # Check if it's actually our pipeline process
            cmdline = ' '.join(process.cmdline())
            if any(keyword in cmdline for keyword in ['run_daily_reddit_pipeline', 'ingest.py', 'run_gemini_analysis.py']):
                return True, f"PID {pid} is running pipeline process"
            else:
                return False, f"PID {pid} exists but is not a pipeline process: {cmdline}"
                
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            return False, f"PID {pid} error: {e}"
    else:
        # Fallback without psutil
        try:
            os.kill(pid, 0)  # Check if process exists
            
            # Check if it's zombie using ps
            result = subprocess.run(['ps', '-p', str(pid), '-o', 'stat=,comm='], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if lines:
                    stat_comm = lines[0].split()
                    if len(stat_comm) >= 2:
                        stat, comm = stat_comm[0], ' '.join(stat_comm[1:])
                        if 'Z' in stat or '<defunct>' in comm:
                            return False, f"PID {pid} is zombie/defunct"
                        return True, f"PID {pid} is running: {comm}"
            return False, f"PID {pid} status unknown"
            
        except (OSError, ProcessLookupError):
            return False, f"PID {pid} does not exist"
        except subprocess.TimeoutExpired:
            return True, f"PID {pid} exists (timeout checking status)"

def find_orphaned_pipeline_processes():
    """Find any orphaned pipeline processes not tracked in database"""
    orphaned = []
    
    if PSUTIL_AVAILABLE:
        for proc in psutil.process_iter(['pid', 'cmdline', 'create_time']):
            try:
                cmdline = ' '.join(proc.info['cmdline'] or [])
                if any(keyword in cmdline for keyword in ['run_daily_reddit_pipeline', 'ingest.py', 'run_gemini_analysis.py']):
                    orphaned.append({
                        'pid': proc.info['pid'],
                        'cmdline': cmdline,
                        'create_time': proc.info['create_time']
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    else:
        # Fallback using ps
        try:
            result = subprocess.run(['ps', 'aux'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if any(keyword in line for keyword in ['run_daily_reddit_pipeline', 'ingest.py', 'run_gemini_analysis.py']):
                        parts = line.split()
                        if len(parts) >= 2:
                            try:
                                pid = int(parts[1])
                                orphaned.append({
                                    'pid': pid,
                                    'cmdline': ' '.join(parts[10:]),
                                    'create_time': None
                                })
                            except ValueError:
                                continue
        except subprocess.TimeoutExpired:
            pass
    
    return orphaned

def get_pipeline_status_from_db(db_config):
    """Get pipeline status from database"""
    try:
        conn = get_db_connection(db_config)
        cur = conn.cursor()
        
        cur.execute("""
            SELECT last_run_timestamp, is_running, last_completion_timestamp, process_pid 
            FROM pipeline_status WHERE id = 1;
        """)
        result = cur.fetchone()
        conn.close()
        
        if result:
            last_run, is_running, last_completion, process_pid = result
            return {
                'last_run': last_run,
                'is_running': is_running,
                'last_completion': last_completion,
                'process_pid': process_pid
            }
        else:
            return None
            
    except Exception as e:
        print(f"Error getting pipeline status from database: {e}")
        return None

def fix_stale_pipeline_status(db_config, reason):
    """Fix stale pipeline status in database"""
    try:
        conn = get_db_connection(db_config)
        cur = conn.cursor()
        
        cur.execute("""
            UPDATE pipeline_status 
            SET is_running = FALSE, process_pid = NULL 
            WHERE id = 1;
        """)
        
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        print(f"Error fixing stale pipeline status: {e}")
        return False

def perform_health_check(verbose=True):
    """Perform comprehensive pipeline health check"""
    if verbose:
        print("🔍 Starting Pipeline Health Check...")
        print("=" * 50)
    
    issues_found = []
    fixes_applied = []
    
    try:
        # Load configuration
        config = load_config()
        db_config = config['database']
        
        # Get database status
        db_status = get_pipeline_status_from_db(db_config)
        
        if not db_status:
            issues_found.append("No pipeline status found in database")
            if verbose:
                print("⚠️  No pipeline status found in database")
        else:
            if verbose:
                print(f"📊 Database Status:")
                print(f"   is_running: {db_status['is_running']}")
                print(f"   process_pid: {db_status['process_pid']}")
                print(f"   last_run: {db_status['last_run']}")
                print(f"   last_completion: {db_status['last_completion']}")
            
            # Check if marked as running but process doesn't exist
            if db_status['is_running'] and db_status['process_pid']:
                is_running, reason = is_pipeline_process_running(db_status['process_pid'])
                
                if not is_running:
                    issue = f"Pipeline marked as running but {reason}"
                    issues_found.append(issue)
                    
                    if verbose:
                        print(f"❌ {issue}")
                        print("🔧 Auto-fixing stale status...")
                    
                    if fix_stale_pipeline_status(db_config, reason):
                        fix = f"Fixed stale pipeline status (was PID {db_status['process_pid']})"
                        fixes_applied.append(fix)
                        if verbose:
                            print(f"✅ {fix}")
                    else:
                        if verbose:
                            print("❌ Failed to fix stale status")
                else:
                    if verbose:
                        print(f"✅ Pipeline process validation: {reason}")
            
            # Check for long-running pipelines (over 2 hours)
            if db_status['is_running'] and db_status['last_run']:
                runtime = datetime.now(timezone.utc) - db_status['last_run']
                runtime_hours = runtime.total_seconds() / 3600
                
                if runtime_hours > 2:
                    issue = f"Pipeline has been running for {runtime_hours:.1f} hours (possibly stuck)"
                    issues_found.append(issue)
                    if verbose:
                        print(f"⚠️  {issue}")
        
        # Check for orphaned processes
        if verbose:
            print("\n🔍 Checking for orphaned pipeline processes...")
        
        orphaned = find_orphaned_pipeline_processes()
        if orphaned:
            for proc in orphaned:
                # Check if this PID matches the database PID
                if db_status and proc['pid'] == db_status['process_pid']:
                    continue  # This is the tracked process
                
                issue = f"Orphaned pipeline process found: PID {proc['pid']} - {proc['cmdline']}"
                issues_found.append(issue)
                if verbose:
                    print(f"⚠️  {issue}")
        else:
            if verbose:
                print("✅ No orphaned pipeline processes found")
        
        # Summary
        if verbose:
            print("\n" + "=" * 50)
            print("📋 Health Check Summary:")
            print(f"   Issues found: {len(issues_found)}")
            print(f"   Fixes applied: {len(fixes_applied)}")
            
            if issues_found:
                print("\n❌ Issues:")
                for issue in issues_found:
                    print(f"   - {issue}")
            
            if fixes_applied:
                print("\n✅ Fixes Applied:")
                for fix in fixes_applied:
                    print(f"   - {fix}")
            
            if not issues_found:
                print("✅ All checks passed - pipeline is healthy!")
        
        return {
            'healthy': len(issues_found) == 0,
            'issues': issues_found,
            'fixes': fixes_applied
        }
        
    except Exception as e:
        error = f"Health check failed: {e}"
        if verbose:
            print(f"❌ {error}")
        return {
            'healthy': False,
            'issues': [error],
            'fixes': []
        }

def main():
    """Main function for standalone execution"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Reddit Pipeline Health Check')
    parser.add_argument('--quiet', '-q', action='store_true', help='Quiet mode (less verbose output)')
    parser.add_argument('--fix', '-f', action='store_true', help='Automatically fix issues (default behavior)')
    
    args = parser.parse_args()
    
    result = perform_health_check(verbose=not args.quiet)
    
    # Exit with non-zero code if issues found
    sys.exit(0 if result['healthy'] else 1)

if __name__ == '__main__':
    main() 