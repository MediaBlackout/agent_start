import time
import logging
import requests
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from datetime import datetime

# Configure logging
logging.basicConfig(filename='health_check.log',
                    level=logging.INFO,
                    format='%(asctime)s %(levelname)s: %(message)s')

# Email settings
AWS_REGION = "us-east-1"  # Change as needed
EMAIL_FROM = "SENDER_EMAIL@example.com"   # Must be verified in SES
EMAIL_TO = "RECIPIENT_EMAIL@example.com" # Must be verified or SES sandbox lifted
EMAIL_SUBJECT = "API Health Check Alert"

ses_client = boto3.client('ses', region_name=AWS_REGION)

def send_alert_email(broken_urls):
    try:
        body_text = "The following URLs are DOWN as of {}:\n\n{}".format(
            datetime.utcnow().isoformat(),
            "\n".join(broken_urls)
        )
        response = ses_client.send_email(
            Source=EMAIL_FROM,
            Destination={
                'ToAddresses': [
                    EMAIL_TO,
                ]
            },
            Message={
                'Subject': {
                    'Data': EMAIL_SUBJECT
                },
                'Body': {
                    'Text': {
                        'Data': body_text
                    }
                }
            }
        )
        logging.info(f"Sent alert email for {len(broken_urls)} URLs.")
    except (BotoCoreError, ClientError) as e:
        logging.error(f"Failed to send alert email: {e}")

def read_urls(file_path='urls.txt'):
    try:
        with open(file_path, 'r') as file:
            return [line.strip() for line in file if line.strip()]
    except FileNotFoundError:
        logging.error(f"URL file '{file_path}' not found.")
        return []

def check_urls(urls):
    down_urls = []
    for url in urls:
        try:
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                logging.warning(f"{url} returned status {response.status_code}")
                down_urls.append(f"{url} (Status: {response.status_code})")
        except requests.RequestException as e:
            logging.error(f"Error checking {url}: {e}")
            down_urls.append(f"{url} (ERROR: {e})")
    return down_urls

def main_loop():
    while True:
        urls = read_urls()
        if not urls:
            logging.warning("No URLs to check.")
        else:
            logging.info("Starting health check...")
            down_urls = check_urls(urls)
            if down_urls:
                logging.info(f"{len(down_urls)} URLs down. Logging errors and emailing.")
                for url_err in down_urls:
                    logging.error(f"DOWN: {url_err}")
                send_alert_email(down_urls)
            else:
                logging.info("All URLs are healthy.")
        time.sleep(300)  # Wait 5 minutes

if __name__ == "__main__":
    main_loop()