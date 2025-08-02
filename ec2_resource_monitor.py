#!/usr/bin/env python3
"""
ec2_resource_monitor.py

Description:
    Monitors CPU, memory, disk, and network usage on an Ubuntu EC2 instance.
    Logs system statistics to /var/log/ec2_stats.csv every 5 minutes.
    Sends alert email via AWS SES if thresholds are exceeded.
    Logs detailed activity to /var/log/ec2_resource_monitor.log.
    Designed to run as a cron job or service.

Author: MediaBlackout.ai for matt@mediablackout.ai

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SETUP INSTRUCTIONS:

1. Install required libraries (only boto3 is non-standard):
    sudo apt update
    sudo apt install python3-pip
    pip3 install boto3

2. Ensure AWS credentials (ACCESS KEY, SECRET KEY) are configured under:
   ~/.aws/credentials  OR  use instance IAM Role with SES access permissions

3. Verify SES sender/recipient emails are verified in the same AWS region.

4. Give script execute permission:
    chmod +x ec2_resource_monitor.py

5. Set up cron to run every 5 minutes:
    sudo crontab -e

    Add the line:
    */5 * * * * /usr/bin/python3 /path/to/ec2_resource_monitor.py

6. Monitor log:
    tail -f /var/log/ec2_resource_monitor.log

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
import time
import csv
import logging
import smtplib
import subprocess
from datetime import datetime
import boto3
from botocore.exceptions import BotoCoreError, ClientError

# Configuration Constants
LOG_FILE = "/var/log/ec2_resource_monitor.log"
CSV_FILE = "/var/log/ec2_stats.csv"
ALERT_EMAIL = "matt@mediablackout.ai"
AWS_REGION = "us-east-1"  # Change if needed
SES_SENDER = "matt@mediablackout.ai"  # Verified sender in SES
THRESHOLDS = {
    'cpu': 80.0,
    'memory': 80.0,
    'disk': 90.0,
    'network': 100.0  # MB/s
}

# Setup logging
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

def ensure_file_exists(filepath, headers=None):
    """Creates the log/CSV file if they don't exist."""
    if not os.path.exists(filepath):
        try:
            with open(filepath, 'w') as f:
                if headers:
                    writer = csv.writer(f)
                    writer.writerow(headers)
            logging.info(f"Created file: {filepath}")
        except Exception as e:
            logging.error(f"Failed to create {filepath}: {e}")

def get_cpu_usage():
    """Returns CPU usage percentage."""
    try:
        load = os.getloadavg()[0]  # 1-minute load average
        cpu_count = os.cpu_count() or 1
        cpu_usage = (load / cpu_count) * 100
        return round(cpu_usage, 2)
    except Exception as e:
        logging.error(f"Error getting CPU usage: {e}")
        return 0.0

def get_memory_usage():
    """Returns memory usage percentage."""
    try:
        with open('/proc/meminfo') as f:
            lines = f.readlines()
            mem_info = {line.split(':')[0]: float(line.split()[1]) for line in lines if ':' in line}
            total = mem_info.get('MemTotal', 1)
            available = mem_info.get('MemAvailable', 0)
            used = total - available
            return round((used / total) * 100, 2)
    except Exception as e:
        logging.error(f"Error getting memory usage: {e}")
        return 0.0

def get_disk_usage(path):
    """Returns disk usage % for given path."""
    try:
        stat = os.statvfs(path)
        total = stat.f_frsize * stat.f_blocks
        free = stat.f_frsize * stat.f_bavail
        used = total - free
        usage_percent = (used / total) * 100 if total else 0
        return round(usage_percent, 2)
    except Exception as e:
        logging.error(f"Error getting disk usage for {path}: {e}")
        return 0.0

def get_network_usage():
    """
    Returns (inbound_MBps, outbound_MBps).
    Measure data over 1 second interval.
    """
    def read_bytes():
        with open("/proc/net/dev") as f:
            lines = f.readlines()
            eth_lines = [l for l in lines if ':' in l]
            rx, tx = 0, 0
            for line in eth_lines:
                iface, data = line.split(':')
                values = data.split()
                rx += int(values[0])  # Receive bytes
                tx += int(values[8])  # Transmit bytes
            return rx, tx

    try:
        rx1, tx1 = read_bytes()
        time.sleep(1)
        rx2, tx2 = read_bytes()
        inbound = (rx2 - rx1) / (1024 * 1024)  # bytes to MB
        outbound = (tx2 - tx1) / (1024 * 1024)
        return round(inbound, 2), round(outbound, 2)
    except Exception as e:
        logging.error(f"Error getting network usage: {e}")
        return 0.0, 0.0

def send_alert(subject, body):
    """Send email alert via AWS SES."""
    try:
        client = boto3.client('ses', region_name=AWS_REGION)
        response = client.send_email(
            Source=SES_SENDER,
            Destination={'ToAddresses': [ALERT_EMAIL]},
            Message={
                'Subject': {'Data': subject},
                'Body': {'Text': {'Data': body}}
            }
        )
        logging.info(f"Alert email sent: {subject}")
    except (BotoCoreError, ClientError) as e:
        logging.error(f"Failed to send SES email: {e}")

def check_thresholds_and_alert(metrics):
    """Check if any metric exceeds thresholds and send alert."""
    alerts = []
    if metrics['cpu'] > THRESHOLDS['cpu']:
        alerts.append(f"High CPU usage: {metrics['cpu']}%")
    if metrics['memory'] > THRESHOLDS['memory']:
        alerts.append(f"High memory usage: {metrics['memory']}%")
    if metrics['disk_root'] > THRESHOLDS['disk']:
        alerts.append(f"High disk usage on /: {metrics['disk_root']}%")
    if 'disk_home' in metrics and metrics['disk_home'] > THRESHOLDS['disk']:
        alerts.append(f"High disk usage on /home: {metrics['disk_home']}%")
    if metrics['net_in'] > THRESHOLDS['network']:
        alerts.append(f"High Network In: {metrics['net_in']} MB/s")
    if metrics['net_out'] > THRESHOLDS['network']:
        alerts.append(f"High Network Out: {metrics['net_out']} MB/s")

    if alerts:
        subject = "[ALERT] EC2 Resource Usage Exceeded"
        body = "\n".join(alerts) + f"\nTimestamp: {metrics['timestamp']}"
        logging.warning("Thresholds exceeded:\n" + body)
        send_alert(subject, body)

def collect_metrics():
    """Collect system metrics."""
    timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    cpu = get_cpu_usage()
    memory = get_memory_usage()
    disk_root = get_disk_usage('/')
    disk_home = get_disk_usage('/home') if os.path.exists('/home') else None
    net_in, net_out = get_network_usage()

    metrics = {
        'timestamp': timestamp,
        'cpu': cpu,
        'memory': memory,
        'disk_root': disk_root,
        'disk_home': disk_home,
        'net_in': net_in,
        'net_out': net_out
    }

    logging.info("Collected metrics: " + str(metrics))
    return metrics

def write_to_csv(metrics):
    """Append metrics to CSV."""
    row = [
        metrics['timestamp'],
        metrics['cpu'],
        metrics['memory'],
        metrics['disk_root'],
        metrics.get('disk_home', ''),
        metrics['net_in'],
        metrics['net_out']
    ]
    try:
        with open(CSV_FILE, 'a') as f:
            writer = csv.writer(f)
            writer.writerow(row)
        logging.info("Appended metrics to CSV.")
    except Exception as e:
        logging.error(f"Failed to write to CSV: {e}")

def main():
    try:
        ensure_file_exists(LOG_FILE)
        ensure_file_exists(CSV_FILE, headers=[
            'Timestamp', 'CPU_Usage(%)', 'Memory_Usage(%)',
            'Disk_Usage_/(%)', 'Disk_Usage_/home(%)',
            'Network_In(MBps)', 'Network_Out(MBps)'
        ])
        metrics = collect_metrics()
        write_to_csv(metrics)
        check_thresholds_and_alert(metrics)
    except Exception as e:
        logging.error(f"Unexpected error in main(): {e}")

if __name__ == "__main__":
    main()
