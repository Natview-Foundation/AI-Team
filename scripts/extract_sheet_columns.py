"""
extract_sheet_columns.py
────────────────────────
Connects to the Google Spreadsheet and extracts the header row (column names)
from each named worksheet listed in SHEETS_TO_EXTRACT.

Output:
  • Prints a JSON-formatted preview of all column names grouped by sheet name.
  • Writes the result to  data/reference/sheet_columns_raw.json
    so you can inspect it before deciding on categories.

Usage (from the project root):
  python scripts/extract_sheet_columns.py

The script uses the same credentials and spreadsheet name already configured
in your .env file (GOOGLE_SHEETS_CREDENTIALS_PATH, GOOGLE_SHEET_NAME).
"""

import json
import logging
import sys
from pathlib import Path

# ─── Make sure the project root is on the path ───────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

import gspread
from config import GOOGLE_SHEETS_CREDENTIALS_PATH, GOOGLE_SHEET_NAME

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Sheet tab names to extract.
# Order here determines output order in sheet_columns_raw.json.
# ─────────────────────────────────────────────────────────────────────────────
SHEETS_TO_EXTRACT: list[str] = [
    "Baseline data_LS1",
    "HRH, EM and Vaccine Data",
    "Bi-Weekly Staff Roaster Data",
    "Days Service Offered Detail",
    "Bi Weekly Health Worker Availability- Total Data",
    "Bi-Weekly Health Worker Absenteeism Data",
    "Permanent Health Worker Absenteeism Data",
    "facility details",
    "LS facilities List",
    "DHIS2_Master_Lookup",
]

OUTPUT_PATH = PROJECT_ROOT / "data" / "reference" / "sheet_columns_raw.json"


# ─────────────────────────────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────────────────────────────
def get_gspread_client() -> gspread.Client:
    """Authenticate and return a gspread client."""
    if GOOGLE_SHEETS_CREDENTIALS_PATH:
        logger.info(f"Authenticating with service account: {GOOGLE_SHEETS_CREDENTIALS_PATH}")
        return gspread.service_account(filename=GOOGLE_SHEETS_CREDENTIALS_PATH)
    else:
        import google.auth
        logger.warning("No service account path set — trying Application Default Credentials.")
        creds, _ = google.auth.default()
        return gspread.authorize(creds)


# ─────────────────────────────────────────────────────────────────────────────
# Core extraction
# ─────────────────────────────────────────────────────────────────────────────
def extract_columns(gc: gspread.Client, spreadsheet_name: str) -> dict[str, list[str]]:
    """
    Opens the spreadsheet by name and reads the first row (headers) from
    each worksheet listed in SHEETS_TO_EXTRACT.

    Returns:
        { sheet_tab_name: [col1, col2, ...], ... }
    """
    logger.info(f"Opening spreadsheet: '{spreadsheet_name}'")
    spreadsheet = gc.open(spreadsheet_name)

    # Build a lookup of all available worksheet titles for helpful error messages
    available_titles = [ws.title for ws in spreadsheet.worksheets()]
    logger.info(f"Available worksheets in this spreadsheet: {available_titles}")

    result: dict[str, list[str]] = {}

    for sheet_name in SHEETS_TO_EXTRACT:
        if sheet_name not in available_titles:
            logger.warning(
                f"  ⚠  Sheet '{sheet_name}' NOT FOUND in spreadsheet. "
                f"Available sheets: {available_titles}"
            )
            result[sheet_name] = []
            continue

        try:
            ws = spreadsheet.worksheet(sheet_name)

            # Fetch only the first row to avoid downloading the entire sheet.
            # row_values(1) returns the first row as a plain list of strings.
            header_row: list[str] = ws.row_values(1)

            # Strip surrounding whitespace from every header
            cleaned = [col.strip() for col in header_row]

            # Drop trailing empty strings (common artifact of wide Google Sheets)
            while cleaned and cleaned[-1] == "":
                cleaned.pop()

            logger.info(f"  ✓  '{sheet_name}' → {len(cleaned)} columns found")
            result[sheet_name] = cleaned

        except Exception as e:
            logger.error(f"  ✗  Failed to read sheet '{sheet_name}': {e}")
            result[sheet_name] = []

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
def main():
    gc = get_gspread_client()
    columns_by_sheet = extract_columns(gc, GOOGLE_SHEET_NAME)

    # ── Pretty-print to console ──────────────────────────────────────────────
    print("\n" + "═" * 70)
    print("  EXTRACTED COLUMN NAMES BY SHEET")
    print("═" * 70)

    for sheet_name, cols in columns_by_sheet.items():
        print(f"\n[{sheet_name}]  ({len(cols)} columns)")
        if cols:
            for i, col in enumerate(cols, 1):
                print(f"  {i:>3}.  {col}")
        else:
            print("       (no columns found — sheet may be missing or empty)")

    # ── Write raw dump to file ───────────────────────────────────────────────
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(columns_by_sheet, f, indent=2, ensure_ascii=False)

    print(f"\n{'═' * 70}")
    print(f"  Raw column dump written to:")
    print(f"  {OUTPUT_PATH}")
    print(f"{'═' * 70}")
    print()
    print("Next steps:")
    print("  1. Review sheet_columns_raw.json — verify all sheets were found")
    print("     and all expected column names are present.")
    print()
    print("  2. Decide on category groupings for each new sheet.")
    print()
    print("  3. Update data/reference/entities.json  →  'columns' key")
    print("     New structure (one key per sheet/table):")
    print("""
     "columns": {
       "baseline_data_ls2": {          ← existing, already categorised
         "geographic": [...],
         "operations": [...],
         ...
       },
       "baseline_data_ls1": {          ← new sheets get the same treatment
         "category_a": [...],
         ...
       },
       "hrh_em_vaccine": {
         ...
       }
     }
    """)


if __name__ == "__main__":
    main()
