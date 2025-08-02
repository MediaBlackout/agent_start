#!/usr/bin/env python3

import os
import sys
import json
import logging
import requests

from typing import Optional

# Configure basic logging
LOG_FILE = 'slack_notifier.log'
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

def print_usage():
    usage = (
        "Usage:\n"
        "  python slack_notifier.py 'Your message here'\n"
        "  echo 'Your message here' | python slack_notifier.py\n\n"
        "Ensure SLACK_WEBHOOK_URL environment variable is set."
    )
    print(usage)

def read_message() -> Optional[str]:
    # If message is passed as a command-line argument
    if len(sys.argv) > 1:
        return ' '.join(sys.argv[1:])
    # If message is passed via STDIN
    elif not sys.stdin.isatty():
        return sys.stdin.read().strip()
    else:
        return None

def send_to_slack(message: str, webhook_url: str) -> bool:
    payload = { "text": message }
    headers = { 'Content-Type': 'application/json' }

    try:
        response = requests.post(webhook_url, data=json.dumps(payload), headers=headers, timeout=10)
        if response.status_code == 200:
            logging.info("Message sent successfully: %s", message)
            return True
        else:
            logging.error("Failed to send message. HTTP %s: %s", response.status_code, response.text)
            return False
    except Exception as e:
        logging.exception("Exception occurred while sending message to Slack.")
        return False

def main():
    webhook_url = os.getenv('SLACK_WEBHOOK_URL')
    if not webhook_url:
        print("Error: SLACK_WEBHOOK_URL environment variable not set.")
        logging.error("Environment variable SLACK_WEBHOOK_URL not set.")
        print_usage()
        sys.exit(1)

    message = read_message()
    if not message:
        print("Error: No message provided.")
        logging.error("No message provided on command line or stdin.")
        print_usage()
        sys.exit(1)

    success = send_to_slack(message, webhook_url)
    if not success:
        print("Failed to send message to Slack. See log for details.")

if __name__ == '__main__':
    main()

# Instructions:

# 1️⃣ Set your Slack webhook URL as an environment variable:

# export SLACK_WEBHOOK_URL='https://hooks.slack.com/services/XXX/YYYY/ZZZ'

# 2️⃣ Run the script from the command line:

# python slack_notifier.py "Hello from script!"

# or use with echo and pipe:
#
echo "Deployment successful." | python slack_notifier.py

# 3️⃣ Check slack_notifier.log for logs:
#
tail -f slack_notifier.log

# Requirements:

# Install requests if not already:

# pip install requests

# This script validates inputs, handles exceptions, logs all actions, and provides usage instructions for ease of use. Let me know if you'd like this turned into a systemd service, Docker image, or integrated with cron or CI/CD!