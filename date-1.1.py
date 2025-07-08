from datetime import date

def get_current_date():
    """
    Returns the current local date.
    """
    return date.today()

def get_formatted_date(format_string="%Y-%m-%d"):
    """
    Returns the current date formatted as a string.
    :param format_string: Format to output the date (default is YYYY-MM-DD)
    """
    return date.today().strftime(format_string)

if __name__ == "__main__":
    print("Current Date:", get_current_date())
    print("Formatted Date:", get_formatted_date())
