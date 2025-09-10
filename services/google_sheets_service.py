import gspread
from google.oauth2.service_account import Credentials
import os
import datetime
import pytz
import json
import tempfile
from typing import List, Dict, Any, Optional


class GoogleSheetsService:
    """Service for interacting with Google Sheets"""
    
    def __init__(self, credentials_file: str = None, spreadsheet_name: str = None, worksheet_name: str = "Sheet1"):
        """
        Initialize Google Sheets service
        
        Args:
            credentials_file: Path to the service account JSON file (deprecated - use env vars)
            spreadsheet_name: Name of the Google Sheets spreadsheet
            worksheet_name: Name of the worksheet/tab (default: Sheet1)
        """
        self.credentials_file = credentials_file
        self.spreadsheet_name = spreadsheet_name or os.getenv("GOOGLE_SPREADSHEET_NAME", "GLeads")
        self.worksheet_name = worksheet_name or os.getenv("GOOGLE_WORKSHEET_NAME", "Sheet1")
        self._client = None
        self._spreadsheet = None
        self._worksheet = None
        
        # Cache for multiple worksheets
        self._worksheets_cache = {}
        
        # Define the scope for Google Sheets API
        self.scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
    
    def _has_env_credentials(self) -> bool:
        """Check if Google credentials are available in environment variables"""
        required_vars = [
            'GOOGLE_SERVICE_ACCOUNT_TYPE',
            'GOOGLE_SERVICE_ACCOUNT_PROJECT_ID',
            'GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY',
            'GOOGLE_SERVICE_ACCOUNT_CLIENT_EMAIL'
        ]
        return all(os.getenv(var) for var in required_vars)
    
    def _get_credentials_from_env(self) -> Optional[Credentials]:
        """Create credentials from environment variables"""
        try:
            # Build the service account info dictionary from environment variables
            service_account_info = {
                "type": os.getenv("GOOGLE_SERVICE_ACCOUNT_TYPE", "service_account"),
                "project_id": os.getenv("GOOGLE_SERVICE_ACCOUNT_PROJECT_ID"),
                "private_key_id": os.getenv("GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY_ID"),
                "private_key": os.getenv("GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY", "").replace('\\n', '\n'),
                "client_email": os.getenv("GOOGLE_SERVICE_ACCOUNT_CLIENT_EMAIL"),
                "client_id": os.getenv("GOOGLE_SERVICE_ACCOUNT_CLIENT_ID"),
                "auth_uri": os.getenv("GOOGLE_SERVICE_ACCOUNT_AUTH_URI", "https://accounts.google.com/o/oauth2/auth"),
                "token_uri": os.getenv("GOOGLE_SERVICE_ACCOUNT_TOKEN_URI", "https://oauth2.googleapis.com/token"),
                "auth_provider_x509_cert_url": os.getenv("GOOGLE_SERVICE_ACCOUNT_AUTH_PROVIDER_X509_CERT_URL", "https://www.googleapis.com/oauth2/v1/certs"),
                "client_x509_cert_url": os.getenv("GOOGLE_SERVICE_ACCOUNT_CLIENT_X509_CERT_URL"),
                "universe_domain": os.getenv("GOOGLE_SERVICE_ACCOUNT_UNIVERSE_DOMAIN", "googleapis.com")
            }
            
            # Remove None values
            service_account_info = {k: v for k, v in service_account_info.items() if v is not None}
            
            # Create credentials from the service account info
            creds = Credentials.from_service_account_info(service_account_info, scopes=self.scope)
            return creds
            
        except Exception as e:
            print(f"Error creating credentials from environment variables: {e}")
            return None

    def _get_credentials_path(self) -> str:
        """Get the full path to the credentials file"""
        if not self.credentials_file:
            return ""
            
        if os.path.isabs(self.credentials_file):
            return self.credentials_file
        
        # If relative path, look relative to this script's directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Go up one level to the reddit_researcher directory
        return os.path.join(script_dir, '..', self.credentials_file)
    
    def _authenticate(self) -> bool:
        """Authenticate with Google Sheets API using environment variables or file"""
        try:
            # Try environment variables first (preferred method)
            if self._has_env_credentials():
                creds = self._get_credentials_from_env()
                if creds:
                    self._client = gspread.authorize(creds)
                    return True
            
            # Fallback to file-based credentials
            if self.credentials_file:
                credentials_path = self._get_credentials_path()
                
                if not os.path.exists(credentials_path):
                    print(f"Google Sheets credentials file not found at: {credentials_path}")
                    return False
                
                # Load credentials from service account file
                creds = Credentials.from_service_account_file(credentials_path, scopes=self.scope)
                
                # Create gspread client
                self._client = gspread.authorize(creds)
                
                return True
            
            print("No Google Sheets credentials found. Please set environment variables or provide credentials file.")
            return False
            
        except Exception as e:
            print(f"Error authenticating with Google Sheets: {e}")
            return False
    
    def _get_worksheet(self, worksheet_name: str = None):
        """Get the worksheet object with caching support"""
        # Use provided worksheet_name or fall back to instance default
        target_worksheet = worksheet_name or self.worksheet_name
        
        # Check cache first
        if target_worksheet in self._worksheets_cache:
            return self._worksheets_cache[target_worksheet]
        
        if not self._authenticate():
            return None
        
        try:
            # Open the spreadsheet by name if not already open
            if not self._spreadsheet:
                self._spreadsheet = self._client.open(self.spreadsheet_name)
            
            # Get the specific worksheet
            worksheet = self._spreadsheet.worksheet(target_worksheet)
            
            # Cache the worksheet
            self._worksheets_cache[target_worksheet] = worksheet
            
            # Also set as main worksheet if it's the default
            if target_worksheet == self.worksheet_name:
                self._worksheet = worksheet
            
            return worksheet
            
        except gspread.SpreadsheetNotFound:
            print(f"Spreadsheet '{self.spreadsheet_name}' not found. Please make sure:")
            print(f"1. The spreadsheet name is correct")
            print(f"2. The spreadsheet is shared with the service account")
            return None
        except gspread.WorksheetNotFound:
            print(f"Worksheet '{target_worksheet}' not found in spreadsheet '{self.spreadsheet_name}'")
            print("Available worksheets:")
            try:
                if not self._spreadsheet:
                    self._spreadsheet = self._client.open(self.spreadsheet_name)
                worksheets = self._spreadsheet.worksheets()
                for ws in worksheets:
                    print(f"  - {ws.title}")
            except Exception as e:
                print(f"  Could not list worksheets: {e}")
            return None
        except Exception as e:
            print(f"Error accessing Google Sheets: {e}")
            return None
    
    def setup_headers(self, worksheet_name: str = None, headers: List[str] = None) -> bool:
        """Setup the header row if it doesn't exist"""
        try:
            worksheet = self._get_worksheet(worksheet_name)
            if not worksheet:
                return False
            
            # Use provided headers or default to Reddit post headers
            if headers is None:
                headers = ['source', 'title', 'createdat', 'link', 'username', 'loom', 'added_at_date']
            
            # Check if headers already exist
            try:
                existing_headers = worksheet.row_values(1)
                if existing_headers == headers:
                    print(f"Headers already exist and match expected format in {worksheet_name or self.worksheet_name}")
                    return True
            except:
                pass  # No existing headers or error reading them
            
            # Set up headers
            end_col = chr(ord('A') + len(headers) - 1)
            worksheet.update(f'A1:{end_col}1', [headers])
            print(f"Headers set up in {self.spreadsheet_name}/{worksheet_name or self.worksheet_name}")
            
            return True
            
        except Exception as e:
            print(f"Error setting up headers: {e}")
            return False
    
    def setup_content_headers(self, worksheet_name: str = "Content") -> bool:
        """Setup headers specifically for multi-content tracking"""
        content_headers = [
            'Date',           # DD.MM.YYYY format
            'Type',           # Breakdown, Classroom, Q&A Show, React Reels
            '#Number',        # Number extracted from folder names
            'Raw Folder',     # Clickable Dropbox link
            '(#) Long-Form',  # Manual entry - number of long-form content
            '(#) Reels',      # Number of video files (calculated)
            'Raw Time',       # Total duration of media files
            'LF Time',        # Manual entry - long-form processing time
            'LF Usage',       # Manual entry - long-form usage percentage
            'R Time',         # Manual entry - reels processing time  
            'R Usage',        # Manual entry - reels usage percentage
            'Reaction Title(s)', # Extracted titles (especially for Breakdown)
            'LF-Done',        # Boolean - LF-Done status
            'R-Done'          # Boolean - R-Done status
        ]
        
        return self.setup_headers(worksheet_name, content_headers)
    
    def setup_checkbox_validation(self, worksheet_name: str = "Content") -> bool:
        """Setup checkbox validation for LF-Done and R-Done columns"""
        try:
            worksheet = self._get_worksheet(worksheet_name)
            if not worksheet:
                return False
            
            # Get current data to determine range
            data = worksheet.get_all_values()
            if len(data) <= 1:
                return True  # No data rows, nothing to set up
            
            # Create the checkbox validation rule
            checkbox_validation = {
                'condition': {
                    'type': 'BOOLEAN'
                }
            }
            
            # Prepare batch update request for both columns
            requests = [
                {
                    'setDataValidation': {
                        'range': {
                            'sheetId': worksheet.id,
                            'startRowIndex': 1,  # Row 2 (0-indexed)
                            'endRowIndex': len(data),
                            'startColumnIndex': 12,  # Column M (0-indexed) - LF-Done
                            'endColumnIndex': 13
                        },
                        'rule': checkbox_validation
                    }
                },
                {
                    'setDataValidation': {
                        'range': {
                            'sheetId': worksheet.id,
                            'startRowIndex': 1,  # Row 2 (0-indexed)
                            'endRowIndex': len(data),
                            'startColumnIndex': 13,  # Column N (0-indexed) - R-Done
                            'endColumnIndex': 14
                        },
                        'rule': checkbox_validation
                    }
                }
            ]
            
            # Execute the batch update
            body = {'requests': requests}
            self._spreadsheet.batch_update(body)
            
            print(f"✅ Checkbox validation set up for {worksheet_name} (rows 2-{len(data)})")
            return True
            
        except Exception as e:
            print(f"⚠️  Could not set up checkbox validation: {e}")
            return False
    
    def add_posts(self, posts_data: List[Dict[str, Any]], worksheet_name: str = None) -> bool:
        """Add posts data to Google Sheets"""
        try:
            worksheet = self._get_worksheet(worksheet_name)
            if not worksheet:
                return False
            
            # Prepare data for insertion
            rows_to_add = []
            for post in posts_data:
                # Convert datetime to string if needed
                created_date = post.get('created_utc')
                if isinstance(created_date, datetime.datetime):
                    # Convert to EST and format
                    est = pytz.timezone('US/Eastern')
                    created_date_est = created_date.astimezone(est)
                    formatted_date = created_date_est.strftime('%Y-%m-%d %H:%M:%S EST')
                else:
                    formatted_date = str(created_date) if created_date else ''
                
                # Current timestamp for added_at_date
                current_time = datetime.datetime.now(pytz.timezone('US/Eastern'))
                added_at = current_time.strftime('%Y-%m-%d %H:%M:%S EST')
                
                row = [
                    post.get('source', 'reddit'),  # source
                    post.get('title', ''),         # title
                    formatted_date,                # createdat
                    post.get('url', ''),           # link
                    post.get('author', ''),        # username
                    '',                            # loom (empty for now)
                    added_at                       # added_at_date
                ]
                rows_to_add.append(row)
            
            # Add rows to the sheet
            if rows_to_add:
                worksheet.append_rows(rows_to_add)
                print(f"Successfully added {len(rows_to_add)} posts to {self.spreadsheet_name}/{worksheet_name or self.worksheet_name}")
                return True
            else:
                print("No posts to add")
                return True
                
        except Exception as e:
            print(f"Error adding posts to Google Sheets: {e}")
            return False
    
    def add_content_entries(self, content_data: List[Dict[str, Any]], worksheet_name: str = "Content") -> bool:
        """Add content entries to Google Sheets with proper formatting"""
        try:
            worksheet = self._get_worksheet(worksheet_name)
            if not worksheet:
                return False
            
            # Setup headers if they don't exist
            if not self.setup_content_headers(worksheet_name):
                print("Failed to setup content headers")
                return False
            
            # Prepare data for insertion
            rows_to_add = []
            for entry in content_data:
                # Create clickable "Open" link for Dropbox folder
                dropbox_url = entry.get('Raw Folder', '')
                if dropbox_url:
                    # Create a hyperlink formula: =HYPERLINK("url", "Open")
                    clickable_link = f'=HYPERLINK("{dropbox_url}","Open")'
                else:
                    clickable_link = ''
                
                row = [
                    entry.get('Date', ''),                    # Date (DD.MM.YYYY)
                    entry.get('Type', ''),                    # Type (Breakdown, Classroom, etc.)
                    entry.get('#Number', ''),                 # Number
                    clickable_link,                           # Clickable "Open" link to Dropbox
                    entry.get('(#) Long-Form', ''),           # Long-form count (manual)
                    entry.get('(#) Reels', ''),               # Reels count (calculated)
                    entry.get('Raw Time', ''),                # Raw time duration
                    entry.get('LF Time', ''),                 # LF processing time (manual)
                    entry.get('LF Usage', ''),                # LF usage % (manual)
                    entry.get('R Time', ''),                  # Reels processing time (manual)
                    entry.get('R Usage', ''),                 # Reels usage % (manual)
                    entry.get('Reaction Title(s)', ''),       # Reaction titles
                    entry.get('LF-Done', False),                         # LF-Done boolean (actual boolean)
                    entry.get('R-Done', False)                           # R-Done boolean (actual boolean)
                ]
                rows_to_add.append(row)
            
            # Add rows to the sheet
            if rows_to_add:
                # Use batch update for better formula handling
                start_row = len(worksheet.get_all_values()) + 1
                end_row = start_row + len(rows_to_add) - 1
                range_name = f'A{start_row}:N{end_row}'
                
                # Update with USER_ENTERED to ensure formulas are processed
                worksheet.update(range_name=range_name, values=rows_to_add, value_input_option='USER_ENTERED')
                print(f"Successfully added {len(rows_to_add)} content entries to {self.spreadsheet_name}/{worksheet_name}")
                
                # Set up checkbox validation for the new entries
                self.setup_checkbox_validation(worksheet_name)
                
                return True
            else:
                print("No content entries to add")
                return True
                
        except Exception as e:
            print(f"Error adding content entries to Google Sheets: {e}")
            return False
    
    def test_connection(self, worksheet_name: str = None) -> bool:
        """Test the connection to Google Sheets"""
        try:
            worksheet = self._get_worksheet(worksheet_name)
            if worksheet:
                print(f"✅ Successfully connected to '{self.spreadsheet_name}/{worksheet_name or self.worksheet_name}'")
                print(f"📊 Spreadsheet URL: https://docs.google.com/spreadsheets/d/{self._spreadsheet.id}")
                return True
            else:
                print(f"❌ Failed to connect to Google Sheets")
                return False
        except Exception as e:
            print(f"❌ Connection test failed: {e}")
            return False
    
    def append_rows(self, worksheet_name: str, rows: List[List[str]], headers: List[str] = None) -> bool:
        """Append rows to a specific worksheet with optional header setup"""
        try:
            # Setup headers if provided
            if headers:
                if not self.setup_headers(worksheet_name, headers):
                    print(f"Failed to setup headers for {worksheet_name}")
                    return False
            
            worksheet = self._get_worksheet(worksheet_name)
            if not worksheet:
                return False
            
            # Add rows to the sheet
            if rows:
                worksheet.append_rows(rows)
                print(f"Successfully added {len(rows)} rows to {self.spreadsheet_name}/{worksheet_name}")
                return True
            else:
                print("No rows to add")
                return True
                
        except Exception as e:
            print(f"Error appending rows to Google Sheets: {e}")
            return False

    def get_all_data(self, worksheet_name: str = "Content") -> List[List[str]]:
        """Get all data from a worksheet as a list of rows"""
        try:
            worksheet = self._get_worksheet(worksheet_name)
            if not worksheet:
                return []
            
            return worksheet.get_all_values()
        except Exception as e:
            print(f"Error getting all data from Google Sheets: {e}")
            return []

    def find_matching_rows(self, worksheet_name: str, search_criteria: Dict[str, str]) -> List[Dict[str, Any]]:
        """Find rows that match given criteria
        
        Args:
            worksheet_name: Name of the worksheet to search
            search_criteria: Dictionary of column_name: value pairs to match
            
        Returns:
            List of dictionaries with row data and row index
        """
        try:
            worksheet = self._get_worksheet(worksheet_name)
            if not worksheet:
                return []
            
            all_data = worksheet.get_all_values()
            if len(all_data) < 1:
                return []
            
            headers = all_data[0]
            matching_rows = []
            
            for row_idx, row in enumerate(all_data[1:], start=2):  # Start from row 2 (skip header)
                row_dict = dict(zip(headers, row))
                
                # Check if this row matches all search criteria
                match = True
                for column_name, search_value in search_criteria.items():
                    if column_name in row_dict:
                        if row_dict[column_name] != search_value:
                            match = False
                            break
                    else:
                        match = False
                        break
                
                if match:
                    row_dict['_row_index'] = row_idx
                    matching_rows.append(row_dict)
            
            return matching_rows
            
        except Exception as e:
            print(f"Error finding matching rows in Google Sheets: {e}")
            return []

    def update_cell(self, worksheet_name: str, row: int, column: str, value: Any) -> bool:
        """Update a specific cell in the worksheet
        
        Args:
            worksheet_name: Name of the worksheet
            row: Row number (1-indexed)
            column: Column letter (e.g., 'A', 'B', 'C')
            value: Value to set
            
        Returns:
            True if successful, False otherwise
        """
        try:
            worksheet = self._get_worksheet(worksheet_name)
            if not worksheet:
                return False
            
            cell_address = f"{column}{row}"
            # Wrap value in list for proper API format
            worksheet.update(cell_address, [[value]])
            print(f"✅ Updated cell {cell_address} in {worksheet_name} with value: {value}")
            return True
            
        except Exception as e:
            print(f"❌ Error updating cell in Google Sheets: {e}")
            return False

    def update_cell_by_column_name(self, worksheet_name: str, row_index: int, column_name: str, value: Any) -> bool:
        """Update a cell by column name instead of letter
        
        Args:
            worksheet_name: Name of the worksheet
            row_index: Row number (1-indexed)
            column_name: Name of the column (must match header)
            value: Value to set
            
        Returns:
            True if successful, False otherwise
        """
        try:
            worksheet = self._get_worksheet(worksheet_name)
            if not worksheet:
                return False
            
            # Get headers to find column index
            all_data = worksheet.get_all_values()
            if len(all_data) < 1:
                print(f"No data found in worksheet {worksheet_name}")
                return False
            
            headers = all_data[0]
            
            try:
                column_index = headers.index(column_name)
                column_letter = chr(ord('A') + column_index)
                
                return self.update_cell(worksheet_name, row_index, column_letter, value)
                
            except ValueError:
                print(f"Column '{column_name}' not found in headers: {headers}")
                return False
                
        except Exception as e:
            print(f"❌ Error updating cell by column name: {e}")
            return False

    def get_content_rows_with_dropbox_links(self, worksheet_name: str = "Content") -> List[Dict[str, Any]]:
        """Get all content rows that have Dropbox links in the Raw Folder column
        
        Returns:
            List of dictionaries with row data including row index
        """
        try:
            worksheet = self._get_worksheet(worksheet_name)
            if not worksheet:
                return []
            
            all_data = worksheet.get_all_values()
            if len(all_data) < 1:
                return []
            
            headers = all_data[0]
            rows_with_links = []
            
            # Find the Raw Folder column index
            raw_folder_col_index = None
            for i, header in enumerate(headers):
                if 'Raw Folder' in header or 'Dropbox' in header:
                    raw_folder_col_index = i
                    break
            
            if raw_folder_col_index is None:
                print("No 'Raw Folder' column found in headers")
                return []
            
            for row_idx, row in enumerate(all_data[1:], start=2):  # Start from row 2 (skip header)
                if len(row) > raw_folder_col_index and row[raw_folder_col_index]:
                    # Extract actual URL if it's a hyperlink formula
                    raw_folder_value = row[raw_folder_col_index]
                    
                    row_dict = dict(zip(headers, row))
                    row_dict['_row_index'] = row_idx
                    row_dict['_raw_folder_value'] = raw_folder_value
                    rows_with_links.append(row_dict)
            
            return rows_with_links
            
        except Exception as e:
            print(f"Error getting content rows with Dropbox links: {e}")
            return []


def test_google_sheets_service():
    """Test function for the Google Sheets service"""
    print("🧪 Testing Google Sheets Service...")
    
    # Test with credentials file
    service = GoogleSheetsService(credentials_file='google_credentials.json')
    
    # Test connection
    if service.test_connection():
        print("✅ Connection test passed")
    else:
        print("❌ Connection test failed")
        return False
    
    # Test header setup
    if service.setup_headers():
        print("✅ Header setup test passed")
    else:
        print("❌ Header setup test failed")
        return False
    
    print("🎉 All tests passed!")
    return True


if __name__ == "__main__":
    test_google_sheets_service() 