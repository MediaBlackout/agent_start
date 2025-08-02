"""
Uptime Dashboard - Minimal Flask app to monitor service availability.

Install requirements (preferably in a virtualenv):
    pip install flask pyyaml requests

Usage:
    1. Create a config.yaml file (example below).
    2. Run the app:
        python uptime_dashboard.py
    3. Visit http://localhost:5000 to view status.

Example config.yaml:
    services:
      - name: Google
        url: https://www.google.com
      - name: Localhost Service
        url: http://localhost:8000/health

Edit config.yaml to add/remove services — no need to restart.
"""

import threading
import time
import requests
import yaml
import os
from flask import Flask, render_template_string
from datetime import datetime

CONFIG_FILE = 'config.yaml'
CHECK_INTERVAL = 60  # seconds

app = Flask(__name__)
service_status = {}

# Template for displaying the status page
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Uptime Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; padding: 2em; background: #f9f9f9; }
        h1 { color: #333; }
        table { width: 100%; border-collapse: collapse; margin-top: 1em; }
        th, td { padding: 0.5em; text-align: left; border-bottom: 1px solid #ccc; }
        .up { color: green; }
        .down { color: red; }
        .error { color: #b00; font-size: 0.9em; }
    </style>
</head>
<body>
    <h1>Uptime Dashboard</h1>
    <table>
        <thead>
            <tr><th>Service</th><th>Status</th><th>Last Checked</th><th>Error</th></tr>
        </thead>
        <tbody>
        {% for service in services %}
            <tr>
                <td>{{ service.name }}</td>
                <td class="{{ 'up' if service.status == 'up' else 'down' }}">{{ service.status }}</td>
                <td>{{ service.last_checked }}</td>
                <td class="error">{{ service.error or '' }}</td>
            </tr>
        {% endfor %}
        </tbody>
    </table>
    <p><em>Refreshes every minute. Edit config.yaml to modify services.</em></p>
</body>
</html>
"""

def load_config():
    """Load service config from YAML file."""
    if not os.path.exists(CONFIG_FILE):
        return []
    with open(CONFIG_FILE, 'r') as f:
        config = yaml.safe_load(f)
        return config.get('services', [])

def check_services():
    """Background thread that pings each service periodically."""
    while True:
        services = load_config()
        for svc in services:
            name = svc.get('name')
            url = svc.get('url')
            try:
                resp = requests.get(url, timeout=5)
                status = 'up' if resp.status_code == 200 else 'down'
                error = '' if status == 'up' else f'Status {resp.status_code}'
            except Exception as e:
                status = 'down'
                error = str(e)

            service_status[name] = {
                'name': name,
                'url': url,
                'status': status,
                'last_checked': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'),
                'error': error,
            }
        time.sleep(CHECK_INTERVAL)

@app.route('/')
def dashboard():
    current_services = load_config()
    services = []
    for svc in current_services:
        name = svc.get('name')
        status_entry = service_status.get(name, {
            'name': name,
            'status': 'unknown',
            'last_checked': 'never',
            'error': 'Waiting for initial check...'
        })
        services.append(status_entry)
    return render_template_string(HTML_TEMPLATE, services=services)

def start_background_checker():
    thread = threading.Thread(target=check_services, daemon=True)
    thread.start()

if __name__ == '__main__':
    start_background_checker()
    app.run(debug=True)
