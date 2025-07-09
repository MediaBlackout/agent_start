import os
import sys
import json
import logging
import base64
from typing import Optional, List
from urllib.parse import quote
from pathlib import Path
from datetime import datetime

import requests
import openai
import boto3
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from pydantic import BaseSettings, Field, ValidationError

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # ok if not present in prod


def setup_logger(log_level):
    logger = logging.getLogger("agent")
    logger.setLevel(log_level)
    log_format = {
        'ts': '%(asctime)s',
        'level': '%(levelname)s',
        'event': '%(message)s',
        'meta': '%(name)s'
    }
    formatter = logging.Formatter(json.dumps(log_format))
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    # Local fallback
    file_handler = logging.FileHandler("agent.log")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger


class Settings(BaseSettings):
    OPENAI_API_KEY: str
    GITHUB_PAT: str
    GITHUB_REPO_OWNER: str
    GITHUB_REPO_NAME: str
    GITHUB_BRANCH: str = "main"
    GITHUB_TARGET_PATH: str = "src/"
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_REGION: str
    SES_FROM_ADDRESS: str
    SES_TO_ADDRESS: str
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = None
logger = None

try:
    settings = Settings()
    logger = setup_logger(settings.LOG_LEVEL)
except ValidationError as ve:
    sys.stderr.write("Env/config error: %s\n" % ve)
    sys.exit(1)

openai.api_key = settings.OPENAI_API_KEY


def truncate_code_for_log(code):
    if len(code) < 200:
        return code
    return code[:96] + "...truncated..." + code[-96:]


class OpenAIClient:
    def __init__(self, api_key):
        self.api_key = api_key
        openai.api_key = api_key

    @retry(reraise=True, wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(4), retry=retry_if_exception_type(Exception))
    def generate_code(self, description: str) -> str:
        messages = [
            {"role": "system", "content": "You are an AI that writes production-quality code based on user instructions."},
            {"role": "user", "content": description}
        ]
        logger.info(json.dumps({"event": "openai/generate/start"}))
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4o",
                messages=messages,
                max_tokens=2048,
                temperature=0.15
            )
            result = response["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(json.dumps({"event": "openai/generate/error", "err": str(e)}))
            raise
        # Extract code block from markdown
        import re
        match = re.search(r"^```[\w+\-]*\n(.+?)```$", result.strip(), re.DOTALL|re.MULTILINE)
        if match:
            code = match.group(1)
        else:
            code = result.strip()
        logger.info(json.dumps({"event": "openai/generate/success", "code_preview": truncate_code_for_log(code)}))
        return code


class GitHubClient:
    def __init__(self, owner, repo, token, branch):
        self.owner = owner
        self.repo = repo
        self.token = token
        self.branch = branch
        self.api_base = f"https://api.github.com/repos/{owner}/{repo}"
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }

    @retry(reraise=True, wait=wait_exponential(multiplier=1, min=2, max=8), stop=stop_after_attempt(4), retry=retry_if_exception_type(Exception))
    def list_directory(self, path: str) -> List[str]:
        url = f"{self.api_base}/contents/{quote(path)}?ref={self.branch}"
        resp = requests.get(url, headers=self.headers)
        if resp.status_code == 404:
            return []  # Path not present
        resp.raise_for_status()
        data = resp.json()
        return [entry["name"] for entry in data if entry["type"] == "file"]

    @retry(reraise=True, wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(4), retry=retry_if_exception_type(Exception))
    def commit_file(self, path: str, content: str, message: str) -> dict:
        url = f"{self.api_base}/contents/{quote(path)}"
        b_content = base64.b64encode(content.encode("utf-8")).decode()
        payload = {
            "message": message,
            "content": b_content,
            "branch": self.branch
        }
        # See if replacing existing file (must supply sha)
        resp = requests.get(url + f"?ref={self.branch}", headers=self.headers)
        if resp.status_code == 200:
            payload["sha"] = resp.json()["sha"]
        elif resp.status_code != 404:
            resp.raise_for_status()
        resp = requests.put(url, headers=self.headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return {"sha": data["content"]["sha"], "html_url": data["content"]["html_url"]}


def resolve_version(filename: str, files_in_dir: List[str]) -> str:
    """If filename exists, increments version suffix, e.g. foo.py -> foo-1.0.py, foo-1.1.py, etc."""
    base, ext = os.path.splitext(filename)
    pattern = re.compile(rf"^{re.escape(base)}-(\\d+)\.(\\d+){re.escape(ext)}$")
    versions = [(int(m.group(1)), int(m.group(2)))
                for f in files_in_dir
                if (m := pattern.match(f))]
    if filename not in files_in_dir and not versions:
        return filename
    # start from 1.0 or next minor
    if not versions:
        return f"{base}-1.0{ext}"
    max_version = max(versions)
    return f"{base}-{max_version[0]}.{max_version[1] + 1}{ext}"


class SESClient:
    def __init__(self, region, key, secret):
        self.ses = boto3.client(
            "ses",
            region_name=region,
            aws_access_key_id=key,
            aws_secret_access_key=secret
        )

    @retry(reraise=True, wait=wait_exponential(multiplier=1, min=2, max=40), stop=stop_after_attempt(3), retry=retry_if_exception_type(Exception))
    def send_email(self, subject: str, body_html: str, body_txt: str, from_addr: str, to_addr: str):
        self.ses.send_email(
            Source=from_addr,
            Destination={"ToAddresses": [to_addr]},
            Message={
                "Subject": {"Data": subject},
                "Body": {
                    "Text": {"Data": body_txt},
                    "Html": {"Data": body_html}
                },
            },
        )


def format_email(subject, desc, filename, commit_url):
    html = f"""
    <html><body>
    <h2>Agent Code Commit Notification</h2>
    <b>File:</b> {filename}<br>
    <b>Description:</b> {desc}<br>
    <b>GitHub Commit:</b> <a href='{commit_url}'>{commit_url}</a>
    <hr/><i>Sent by Automation Agent at {datetime.utcnow().isoformat()} UTC</i>
    </body></html>
    """
    txt = f"File: {filename}\nDescription: {desc}\nCommit: {commit_url}\nSent at {datetime.utcnow().isoformat()} UTC"
    return subject, html, txt


def main():
    # 1. Input: JSON via CLI arg (--payload) or stdin
    if any(a.startswith("--payload=") for a in sys.argv):
        payload = next(a.split("=",1)[1] for a in sys.argv if a.startswith("--payload="))
    else:
        try:
            lines = sys.stdin.read()
            payload = lines.strip()
        except Exception:
            print("Missing payload.", file=sys.stderr)
            sys.exit(2)
    try:
        data = json.loads(payload)
        fileName = data["fileName"]
        description = data["description"]
    except Exception:
        logger.error(json.dumps({"event": "payload/decode-error", "payload_snippet": payload[:128]}))
        sys.exit(5)

    logger.info(json.dumps({"event": "main/start", "file": fileName, "desc": description[:100]}))
    openai_client = OpenAIClient(settings.OPENAI_API_KEY)
    github = GitHubClient(settings.GITHUB_REPO_OWNER, settings.GITHUB_REPO_NAME, settings.GITHUB_PAT, settings.GITHUB_BRANCH)
    ses = SESClient(settings.AWS_REGION, settings.AWS_ACCESS_KEY_ID, settings.AWS_SECRET_ACCESS_KEY)
    target_dir = settings.GITHUB_TARGET_PATH.rstrip("/") + "/"
    # 2. Generate code
    try:
        code = openai_client.generate_code(description)
    except Exception as e:
        logger.error(json.dumps({"event": "generate_code/error", "err": str(e)}))
        sys.exit(30)
    # 3. Resolve versioned filename
    try:
        files_in_dir = github.list_directory(target_dir)
    except Exception as e:
        logger.error(json.dumps({"event": "github/listdir/error", "err": str(e)}))
        files_in_dir = []
    versioned_name = resolve_version(fileName, files_in_dir)
    target_path = target_dir + versioned_name
    # 4. Commit to GitHub
    try:
        commit_result = github.commit_file(target_path, code, f"[agent] Add {versioned_name}")
        commit_url = commit_result["html_url"]
        logger.info(json.dumps({"event": "commit/success", "file": versioned_name, "commit": commit_url}))
    except Exception as e:
        logger.error(json.dumps({"event": "commit/error", "err": str(e)}))
        sys.exit(40)
    # 5. Send SES email
    subject, html, txt = format_email(f"New file committed: {versioned_name}", description, versioned_name, commit_url)
    try:
        ses.send_email(subject, html, txt, settings.SES_FROM_ADDRESS, settings.SES_TO_ADDRESS)
        logger.info(json.dumps({"event": "email/sent", "to": settings.SES_TO_ADDRESS}))
    except Exception as e:
        logger.warning(json.dumps({"event": "email/error", "err": str(e)}))
    logger.info(json.dumps({"event": "main/done"}))

if __name__ == "__main__":
    main()
