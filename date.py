from datetime import datetime, timedelta

def get_today():
    """Returns today's date"""
    return datetime.today().date()

def get_future_date(days):
    """Returns the date after a given number of days"""
    return datetime.today().date() + timedelta(days=days)

def get_past_date(days):
    """Returns the date before a given number of days"""
    return datetime.today().date() - timedelta(days=days)

if __name__ == "__main__":
    print("Today's Date:", get_today())
    print("Date 7 days from now:", get_future_date(7))
    print("Date 30 days ago:", get_past_date(30))
