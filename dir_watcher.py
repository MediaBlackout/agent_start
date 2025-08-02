#!/usr/bin/env python3

import sys
import os
import time
import logging
import boto3
import threading
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from botocore.exceptions import ClientError

#########################
# Configuration
#########################

# Environment variable fallback
DEFAULT_WATCH_DIR = os.getenv('WATCH_DIR', '.')

# Set your AWS SES email details
SES_REGION = "us-east-1"  # Replace with your AWS SES region
SENDER_EMAIL = "sender@example.com"   # Must be a verified email in AWS SES
RECIPIENT_EMAIL = "recipient@example.com"  # Must be verified if in sandbox

#########################
# Logging setup
#########################

LOG_FILE = "dir_changes.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)

#########################
# Email Client
#########################

ses_client = boto3.client('ses', region_name=SES_REGION)

def send_email_alert(subject, body):
    try:
        response = ses_client.send_email(
            Source=SENDER_EMAIL,
            Destination={
                'ToAddresses': [RECIPIENT_EMAIL]
            },
            Message={
                'Subject': {'Data': subject},
                'Body': {'Text': {'Data': body}}
            }
        )
        logging.info(f"AWS SES alert sent: {response['MessageId']}")
    except ClientError as e:
        logging.error(f"Failed to send SES alert: {e.response['Error']['Message']}")

#########################
# Directory Watcher
#########################

class DirectoryEventHandler(FileSystemEventHandler):
    def process_event(self, event_type, file_path):
        filename = os.path.basename(file_path)
        log_message = f"{event_type} - {filename}"
        logging.info(log_message)

        # Trigger SES for .py files
        if filename.endswith(".py"):
            subject = f"[DirWatcher] Python file {event_type}: {filename}"
            body = f"A .py file was {event_type}:\nPath: {file_path}\nTime: {datetime.now().isoformat()}"
            # Send email in a separate thread to avoid blocking
            threading.Thread(target=send_email_alert, args=(subject, body), daemon=True).start()

    def on_created(self, event):
        if not event.is_directory:
            self.process_event("CREATED", event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self.process_event("MODIFIED", event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            self.process_event("DELETED", event.src_path)

#########################
# Main
#########################

def main():
    # Parse directory from CLI or env
    if len(sys.argv) > 1:
        watch_dir = sys.argv[1]
    else:
        watch_dir = DEFAULT_WATCH_DIR

    if not os.path.isdir(watch_dir):
        print(f"Error: {watch_dir} is not a valid directory.")
        sys.exit(1)

    logging.info(f"Starting directory watcher on: {watch_dir}")

    event_handler = DirectoryEventHandler()
    observer = Observer()
    observer.schedule(event_handler, path=watch_dir, recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Shutting down directory watcher...")
        observer.stop()
    observer.join()
    logging.info("Directory watcher stopped cleanly.")

if __name__ == "__main__":
    main()
