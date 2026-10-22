"""
Data Validation module for the ingested Google Sheets data.
Ensures the data schema matches the exact columns expected by the LLM.
"""

import pandas as pd
from dataclasses import dataclass

@dataclass
class ValidationReport:
    is_valid: bool
    errors: list[str]
    warnings: list[str]


def validate_dataframe(df: pd.DataFrame, expected_columns: list[str]) -> ValidationReport:
    """
    Validates that the dataframe contains all the expected columns.
    """
    errors = []
    warnings = []
    
    # 1. Check if DataFrame is empty
    if df.empty:
        errors.append("DataFrame is completely empty.")
        return ValidationReport(is_valid=False, errors=errors, warnings=warnings)
        
    # 2. Check for missing required columns
    df_columns_lower = {str(c).lower().strip() for c in df.columns}
    
    for required_col in expected_columns:
        # We do a case-insensitive check to be slightly forgiving to sheet typos
        if required_col.lower() not in df_columns_lower:
            errors.append(f"Missing required column: '{required_col}'")
            
    # 3. Check for critical geographic columns nulls
    for geo_col in ["lga", "ward", "facility", "facility_details-lga", "facility_details-ward", "facility_details-facility", "LGA", "Ward"]:
        # Find actual column name in df (case-insensitive mapping)
        actual_col = next((c for c in df.columns if str(c).lower().strip() == geo_col.lower()), None)
        if actual_col:
            empty_count = df[actual_col].replace("", pd.NA).isna().sum()
            if empty_count > 0:
                warnings.append(f"Found {empty_count} rows with missing or empty '{geo_col}'. These rows might be ignored by entity matching.")

    is_valid = len(errors) == 0
    
    return ValidationReport(
        is_valid=is_valid,
        errors=errors,
        warnings=warnings
    )
