from fastapi import FastAPI
from pydantic import BaseModel
from session_manager import SessionManager
from task_queue import TaskQueue
import subprocess


class NeoAgent:
    """Very simple planner that delegates directory listings to Trinity."""

    def handle(self, payload, session):
        text = payload.get("text", "")
        if "list" in text.lower() or "directory" in text.lower():
            return {"delegate": "Trinity", "command": "ls"}
        return {"response": "I only know how to list directories for now."}


class TrinityAgent:
    """Executes shell commands with a tiny allow-list."""

    ALLOW = {"ls"}

    def handle(self, payload, session):
        cmd = payload.get("command", "")
        base = cmd.split()[0]
        if base not in self.ALLOW:
            return {"status": "error", "output": "Command not allowed."}
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return {"status": "success", "output": proc.stdout.strip()}


class Morpheus:
    def __init__(self):
        self.sessions = SessionManager()
        self.queue = TaskQueue()
        self.agents = {"Neo": NeoAgent(), "Trinity": TrinityAgent()}

    def handle_message(self, session_id: str, message: str):
        self.queue.push({"agent": "Neo", "session_id": session_id, "payload": {"text": message}})
        result = None
        while True:
            task = self.queue.pop()
            if not task:
                break
            agent = self.agents[task["agent"]]
            session = self.sessions.get(task["session_id"])
            res = agent.handle(task["payload"], session)
            self.sessions.append(task["session_id"], {task["agent"]: res})
            if task["agent"] == "Neo" and res.get("delegate"):
                self.queue.push({
                    "agent": res["delegate"],
                    "session_id": task["session_id"],
                    "payload": {"command": res["command"]},
                })
            else:
                result = res
        return result


morpheus = Morpheus()
app = FastAPI()


class ChatRequest(BaseModel):
    session_id: str
    message: str


@app.post("/chat")
def chat(req: ChatRequest):
    return morpheus.handle_message(req.session_id, req.message)


if __name__ == "__main__":
    output = morpheus.handle_message("demo", "Please list the current directory")
    print(output)
