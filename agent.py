import os
import re
import json
import logging
import base64
import smtplib
from email.mime.text import MIMEText
from typing import Tuple, List, Optional

import openai
import requests

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# Load environment config
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")  # Example: "username/repo"
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")
GITHUB_PATH = os.getenv("GITHUB_PATH", "")  # Relative path inside repo (folder)

AWS_SES_SMTP_USER = os.getenv("AWS_SES_SMTP_USER")
AWS_SES_SMTP_PASS = os.getenv("AWS_SES_SMTP_PASS")
SES_EMAIL_FROM = os.getenv("SES_EMAIL_FROM", "noreply@mediablackout.ai")
SES_EMAIL_TO = os.getenv("SES_EMAIL_TO", "contact@mediablackout.ai")
SES_SMTP_HOST = os.getenv("SES_SMTP_HOST", "email-smtp.us-east-1.amazonaws.com")
SES_SMTP_PORT = int(os.getenv("SES_SMTP_PORT", 587))

# Validate essential configs
required_env_vars = [
    "OPENAI_API_KEY", "GITHUB_TOKEN", "GITHUB_REPO",
    "AWS_SES_SMTP_USER", "AWS_SES_SMTP_PASS"
]
missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    raise EnvironmentError(f"Missing required environment variables: {missing_vars}")

openai.api_key = OPENAI_API_KEY

def generate_code_with_openai(file_description: str) -> str:
    logging.info("Generating code using OpenAI GPT API...")
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a senior software engineer. Generate clean, modular, and production-ready code "
                        "based on the following project description. Output only code, no explanations."
                    ),
                },
                {
                    "role": "user",
                    "content": file_description,
                },
            ],
            temperature=0.3,
            max_tokens=2048,
        )
        code_block = response.choices[0].message.content

        # Extract code from Markdown block if present
        code = re.search(r"```(?:python)?(.*?)```", code_block, re.DOTALL)
        return code.group(1).strip() if code else code_block.strip()
    except Exception as e:
        logging.exception("Failed to generate code with OpenAI.")
        raise e

def list_repo_files(path: str) -> List[str]:
    logging.info(f"Listing files in GitHub repository path: {path}")
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 404:
        return []  # Path does not exist yet
    elif response.status_code != 200:
        logging.error(f"Failed to list repo contents: {response.text}")
        raise Exception("GitHub list contents request failed.")
    return [item["name"] for item in response.json() if item["type"] == "file"]

def version_filename(filename: str, existing_filenames: List[str]) -> str:
    name, ext = os.path.splitext(filename)
    escaped_name = re.escape(name)
    versioned_pattern = re.compile(rf'^{escaped_name}-(\d+)\.(\d+){re.escape(ext)}$')
    max_major, max_minor = 0, 0

    for fname in existing_filenames:
        if fname == filename:
            # Start versioning from 1.0
            max_major = max(max_major, 1)
            max_minor = max(max_minor, 0)
        match = versioned_pattern.match(fname)
        if match:
            major, minor = map(int, match.groups())
            if (major, minor) > (max_major, max_minor):
                max_major, max_minor = major, minor

    if f"{name}{ext}" not in existing_filenames:
        return filename
    new_filename = f"{name}-{max_major}.{max_minor + 1}{ext}"
    logging.info(f"Filename conflict detected. New versioned filename: {new_filename}")
    return new_filename

def commit_file_to_github(filename: str, content: str) -> str:
    logging.info(f"Committing file '{filename}' to GitHub...")
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}/{filename}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Content-Type": "application/json",
    }
    message = f"Add generated file: {filename}"
    encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    payload = {
        "message": message,
        "content": encoded_content,
        "branch": GITHUB_BRANCH,
    }
    response = requests.put(url, headers=headers, data=json.dumps(payload))
    if response.status_code not in (201, 200):
        logging.error(f"GitHub commit failed: {response.text}")
        raise Exception("GitHub commit failed.")
    commit_data = response.json()
    html_url = commit_data.get("content", {}).get("html_url", "URL not available")
    logging.info(f"Committed file to GitHub at: {html_url}")
    return html_url

def send_email(subject: str, body: str):
    logging.info(f"Sending email to {SES_EMAIL_TO}...")
    msg = MIMEText(body, "html")
    msg["Subject"] = subject
    msg["From"] = SES_EMAIL_FROM
    msg["To"] = SES_EMAIL_TO

    try:
        server = smtplib.SMTP(SES_SMTP_HOST, SES_SMTP_PORT)
        server.starttls()
        server.login(AWS_SES_SMTP_USER, AWS_SES_SMTP_PASS)
        server.sendmail(SES_EMAIL_FROM, [SES_EMAIL_TO], msg.as_string())
        server.quit()
        logging.info("Email sent successfully.")
    except Exception as e:
        logging.exception("Email sending failed.")
        raise e

def orchestrate(payload: dict) -> Optional[str]:
    try:
        original_filename = payload.get("fileName")
        description = payload.get("description")

        if not original_filename or not description:
            raise ValueError("Missing 'fileName' or 'description' in payload.")

        code_content = generate_code_with_openai(description)
        existing_files = list_repo_files(GITHUB_PATH)
        final_filename = version_filename(original_filename, existing_files)
        commit_url = commit_file_to_github(final_filename, code_content)

        email_subject = f"[AGENT.PY] Generated and committed: {final_filename}"
        email_body = f"""
            <h2>File successfully generated and committed</h2>
            <p><b>Description:</b> {description}</p>
            <p><b>Filename:</b> {final_filename}</p>
            <p><b>GitHub URL:</b> <a href=\"{commit_url}\">{commit_url}</a></p>
        """
        send_email(email_subject, email_body)
        return commit_url

    except Exception as e:
        logging.exception("Orchestration failed.")
        return None

# Example usage
if __name__ == "__main__":
    # Example payload, you can replace this with actual data
    sample_payload = {
        "fileName": "example.py",
        "description": "A Python script that fetches weather data from OpenWeatherMap API and plots a temperature chart using matplotlib."
    }
    orchestrate(sample_payload)
