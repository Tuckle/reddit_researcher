#!/usr/bin/env python3
"""
Runner script for Reddit posts analysis with Gemini AI.

This script processes unanalyzed Reddit posts from the database using the Gemini API
to score their relevance for dating coach content. It sends posts in batches
and updates the database with the results.

Usage:
    python run_gemini_analysis.py

Prerequisites:
    - Gemini API key configured in config.yaml
    - google-generativeai Python package installed
    - Database configured in config.yaml
    - Internet connection
"""

import sys
import os

# Add the current directory to the path to import gemini_processor
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from gemini_processor import process_posts_with_gemini

def main():
    print("=" * 60)
    print("Reddit Posts Analysis with Gemini API")
    print("=" * 60)
    print()
    print("This script will:")
    print("1. Fetch unprocessed Reddit posts from the database")
    print("2. Send them in batches to the Gemini API for relevance analysis")
    print("3. Update the database with scores and detailed analysis")
    print()
    print("Prerequisites:")
    print("- Gemini API key in config.yaml (gemini_api_key: YOUR_KEY)")
    print("- google-generativeai package installed (pip install google-generativeai)")
    print("- Database properly configured")
    print()
    
    print("Starting analysis using Gemini API...")
    print("-" * 40)
    
    try:
        process_posts_with_gemini()
    except KeyboardInterrupt:
        print("\nAnalysis interrupted by user.")
    except Exception as e:
        print(f"\nError during analysis: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
