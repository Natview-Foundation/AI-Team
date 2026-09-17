"""
Google Sheets API Client.
Connects to Google Sheets to download the raw staging table data.
"""

import pandas as pd
import gspread
import logging

from config import GOOGLE_SHEETS_CREDENTIALS_PATH, GOOGLE_SHEET_NAME

logger = logging.getLogger(__name__)

def fetch_sheet_data() -> pd.DataFrame:
    """
    Connects to Google Sheets and downloads the staging table as a Pandas DataFrame.
    """
    logger.info(f"Connecting to Google Sheets to fetch '{GOOGLE_SHEET_NAME}'...")
    
    try:
        if GOOGLE_SHEETS_CREDENTIALS_PATH:
            # Server-to-server auth using a service account JSON file
            gc = gspread.service_account(filename=GOOGLE_SHEETS_CREDENTIALS_PATH)
        else:
            # Try Application Default Credentials (ADC)
            # This works if you run `gcloud auth application-default login` locally
            import google.auth
            logger.warning("No service account credentials path provided. Attempting Google Auth Default Credentials...")
            creds, _ = google.auth.default()
            gc = gspread.authorize(creds)
            
        spreadsheet = gc.open(GOOGLE_SHEET_NAME)
        worksheet = spreadsheet.get_worksheet(0)
        
        # Get all values
        data = worksheet.get_all_values()
        
        if not data:
            raise ValueError("The Google Sheet returned empty data.")
            
        # First row is headers
        df = pd.DataFrame(data[1:], columns=data[0])
        
        logger.info(f"Successfully fetched {len(df)} rows from Google Sheets.")
        return df
        
    except Exception as e:
        logger.error(f"Failed to fetch Google Sheets data: {e}")
        raise
