# date.py

"""
This module provides functionality to get the current date.
"""

from datetime import datetime

def get_current_date():
    """
    Returns the current date in YYYY-MM-DD format.
    """
    return datetime.now().date()

if __name__ == "__main__":
    print("Current Date:", get_current_date())
