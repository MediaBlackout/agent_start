# time.py
import datetime
from colorama import init, Fore, Back, Style

# Initialize Colorama to make ANSI escape character sequences work under Windows.
# autoreset=True ensures that the color and style are reset after each print statement.
init(autoreset=True)

def get_formatted_datetime():
    """Fetches the current datetime and formats it into date and time strings."""
    now = datetime.datetime.now()
    date_str = now.strftime("%A, %B %d, %Y")
    time_str = now.strftime("%I:%M:%S %p")
    return date_str, time_str

def print_colorful_datetime():
    """Prints the formatted date and time with colorful styling."""
    date_str, time_str = get_formatted_datetime()

    # Print the date with a blue background, white text, and bright style.
    print(f"{Back.BLUE}{Fore.WHITE}{Style.BRIGHT}📅 Date: {date_str}")
    
    # Print the time with a green background, black text, and bright style.
    print(f"{Back.GREEN}{Fore.BLACK}{Style.BRIGHT}⏰ Time: {time_str}")

if __name__ == "__main__":
    print_colorful_datetime()
