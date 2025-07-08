import datetime

def main():
    now = datetime.datetime.now()
    formatted_time = now.strftime('%A, %B %d, %Y at %I:%M %p')
    print(f"Current date and time: {formatted_time}")

if __name__ == '__main__':
    main()