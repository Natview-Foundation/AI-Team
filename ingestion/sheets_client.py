"""
Google Sheets API Client.
Connects to Google Sheets to download the raw staging table data.
"""

import pandas as pd
import gspread
import logging

from config import GOOGLE_SHEETS_CREDENTIALS_PATH, GOOGLE_SHEET_NAME

logger = logging.getLogger(__name__)

def fetch_sheet_data(sheet_tab_name: str) -> pd.DataFrame:
    """
    Connects to Google Sheets and downloads the specified staging table as a Pandas DataFrame.
    """
    logger.info(f"Connecting to Google Sheets to fetch '{GOOGLE_SHEET_NAME}' -> '{sheet_tab_name}'...")
    
    try:
        if GOOGLE_SHEETS_CREDENTIALS_PATH:
            # Server-to-server auth using a service account JSON file
            gc = gspread.service_account(filename=GOOGLE_SHEETS_CREDENTIALS_PATH)
        else:
            # Try Application Default Credentials (ADC)
            import google.auth
            logger.warning("No service account credentials path provided. Attempting Google Auth Default Credentials...")
            creds, _ = google.auth.default()
            gc = gspread.authorize(creds)
            
        spreadsheet = gc.open(GOOGLE_SHEET_NAME)
        worksheet = spreadsheet.worksheet(sheet_tab_name)
        
        # Get all values
        data = worksheet.get_all_values()
        
        if not data:
            raise ValueError(f"The Google Sheet '{sheet_tab_name}' returned empty data.")
            
        # First row is headers
        headers = data[0]
        
        cleaned_headers = []
        for i, h in enumerate(headers):
            h_str = str(h).strip()
            if h_str == "":
                cleaned_headers.append(f"Unnamed_{i}")
            else:
                cleaned_headers.append(h_str)
                
        # Drop trailing empty strings (common artifact of wide Google Sheets)
        while cleaned_headers and cleaned_headers[-1].startswith("Unnamed_"):
            cleaned_headers.pop()
            
        # Truncate each row to match the length of cleaned_headers
        num_cols = len(cleaned_headers)
        rows = [row[:num_cols] for row in data[1:]]
        
        df = pd.DataFrame(rows, columns=cleaned_headers)
        
        logger.info(f"Successfully fetched {len(df)} rows from Google Sheets tab '{sheet_tab_name}'.")
        return df
        
    except Exception as e:
        logger.error(f"Failed to fetch Google Sheets data for '{sheet_tab_name}': {e}")
        raise
