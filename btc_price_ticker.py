from datetime import datetime
import requests
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

def fetch_btc_price():
    try:
        response = requests.get("https://api.coindesk.com/v1/bpi/currentprice/BTC.json")
        data = response.json()
        usd_price = data["bpi"]["USD"]["rate"]
        return usd_price
    except Exception as e:
        return f"Error fetching price: {e}"

def display_price():
    price = fetch_btc_price()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    print()
    print(Fore.YELLOW + "="*50)
    print(Fore.CYAN + f"🪙  Bitcoin Price Ticker".center(50))
    print(Fore.YELLOW + "="*50)
    
    if "Error" in price:
        print(Fore.RED + f"Failed to load BTC price: {price}")
    else:
        print(Fore.GREEN + f"💰 BTC/USD: ${price}".center(50))
        print(Fore.MAGENTA + f"⌚ Retrieved at: {now}".center(50))
    
    print(Fore.YELLOW + "="*50)
    print()

if __name__ == "__main__":
    display_price()
