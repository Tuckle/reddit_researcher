#!/usr/bin/env python3
"""
Test script for Google Sheets integration
"""

import sys
import os
import datetime
import pytz

# Add the current directory to the path
sys.path.append(os.path.dirname(__file__))

from services.google_sheets_service import GoogleSheetsService

def test_google_sheets_connection():
    """Test the Google Sheets connection and functionality"""
    print("🧪 Testing Google Sheets Integration...")
    print("=" * 50)
    
    # Initialize the service (now uses environment variables)
    service = GoogleSheetsService()
    
    # Test connection
    print("1. Testing connection...")
    if service.test_connection():
        print("✅ Connection successful!")
    else:
        print("❌ Connection failed!")
        return False
    
    print("\n2. Testing header setup...")
    if service.setup_headers():
        print("✅ Headers setup successful!")
    else:
        print("❌ Headers setup failed!")
        return False
    
    print("\n3. Testing adding sample data...")
    # Create sample posts data
    sample_posts = [
        {
            'title': 'Test Reddit Post #1 - Google Sheets Integration',
            'created_utc': datetime.datetime.now(pytz.UTC),
            'url': 'https://reddit.com/r/test/comments/123456/test1'
        },
        {
            'title': 'Test Reddit Post #2 - Automated Sync',
            'created_utc': datetime.datetime.now(pytz.UTC) - datetime.timedelta(hours=1),
            'url': 'https://reddit.com/r/test/comments/789012/test2'
        }
    ]
    
    if service.add_posts(sample_posts):
        print("✅ Sample data added successfully!")
        print(f"   Added {len(sample_posts)} test posts")
    else:
        print("❌ Failed to add sample data!")
        return False
    
    print("\n🎉 All tests passed! Google Sheets integration is working correctly.")
    print("\n📋 Next steps:")
    print("1. Check your 'GLeads' spreadsheet to see the test data")
    print("2. Make sure to share the spreadsheet with: sacc-178@summahry.iam.gserviceaccount.com")
    print("3. You can now use the Streamlit app to send emails and sync to Google Sheets")
    
    return True

if __name__ == "__main__":
    try:
        test_google_sheets_connection()
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        print("\n🔧 Troubleshooting tips:")
        print("1. Make sure you have created a 'GLeads' spreadsheet in Google Sheets")
        print("2. Share the spreadsheet with: sacc-178@summahry.iam.gserviceaccount.com")
        print("3. Make sure the google_credentials.json file is in the reddit_researcher directory")
        print("4. Install required packages: pip install gspread google-auth google-auth-oauthlib google-auth-httplib2") 