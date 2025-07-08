"""Main orchestrator module."""
from __future__ import annotations

import threading
from typing import Dict, List, Any

import openai
from tasks import Task, OrchestratorState
from agents.social_media_agent import SocialMediaAgent
from agents.aws_agent import AWSAgent
from agents.ceo_agent import CEOAgent
from agents.codex_agent import CodexAgent


class Orchestrator:
    """Coordinates specialist agents to accomplish a goal."""

    def __init__(self, use_openai: bool = False):
        self.state = OrchestratorState.IDLE
        self.agents: Dict[str, Any] = {
            "social_media": SocialMediaAgent(),
            "aws": AWSAgent(),
            "ceo": CEOAgent(),
            "codex": CodexAgent(),
        }
        self.log: List[str] = []
        self.current_step = 0
        self.plan_steps: List[Task] = []
        self.use_openai = use_openai
        # Approval handling
        self._approval_event = threading.Event()
        self._approval_result: str | None = None

    # -------------- Planning -----------------
    def plan(self, goal: str) -> List[Task]:
        self.state = OrchestratorState.PLANNING
        self.log.append(f"Planning goal: {goal}")
        print(f"Planning goal: {goal}")

        if self.use_openai:
            # Placeholder OpenAI call
            prompt = (
                "You are an orchestration AI. Plan steps for the goal: "
                f"{goal}. Respond with JSON list of steps in the format "
                "[{'agent': 'social_media', 'action': 'post about x'}]"
            )
            try:
                resp = openai.ChatCompletion.create(
                    model="gpt-4", messages=[{"role": "user", "content": prompt}]
                )
                plan_text = resp["choices"][0]["message"]["content"]
                # In practice we would parse JSON; here we just simulate
                self.log.append(f"LLM plan: {plan_text}")
            except Exception as exc:
                self.log.append(f"OpenAI planning failed: {exc}")
                plan_text = ""

        # For now create a simple stub plan
        self.plan_steps = [
            Task(agent="social_media", action="post tweet about the goal"),
            Task(agent="codex", action="generate helper script"),
            Task(agent="aws", action="deploy infrastructure", requires_approval=True),
        ]
        return self.plan_steps

    # -------------- Execution -----------------
    def execute_plan(self, plan: List[Task]):
        self.state = OrchestratorState.EXECUTING
        for idx, task in enumerate(plan, 1):
            self.current_step = idx
            msg = f"Executing step {idx}/{len(plan)} with {task.agent}: {task.action}"
            print(msg)
            self.log.append(msg)

            if task.requires_approval:
                approval_msg = f"Awaiting approval for task {idx}: {task.action}"
                print(approval_msg)
                self.log.append(approval_msg)
                # Wait for approval via the approve() method
                self._approval_event.clear()
                self._approval_event.wait()  # Block until approval provided
                if self._approval_result != "approved":
                    deny_msg = f"Task {idx} denied"
                    print(deny_msg)
                    self.log.append(deny_msg)
                    continue

            agent = self.agents.get(task.agent)
            if not agent:
                err = f"Unknown agent: {task.agent}"
                print(err)
                self.log.append(err)
                task.result = err
                continue

            if hasattr(agent, "execute"):
                result = agent.execute(task.action)
            elif hasattr(agent, "decide"):
                result = agent.decide(task.action)
            else:
                result = f"Agent {task.agent} has no executable interface"
                print(result)
            task.result = result

    # -------------- Review -----------------
    def review(self, goal: str, results: List[Task]) -> str:
        self.state = OrchestratorState.REVIEWING
        self.log.append("Reviewing results")
        print("Reviewing results")

        if self.use_openai:
            summary = "; ".join([t.result or "" for t in results])
            prompt = (
                f"Goal: {goal}. Steps results: {summary}. Did we achieve the goal?"
            )
            try:
                resp = openai.ChatCompletion.create(
                    model="gpt-4", messages=[{"role": "user", "content": prompt}]
                )
                decision = resp["choices"][0]["message"]["content"]
            except Exception as exc:
                decision = f"OpenAI review failed: {exc}"
        else:
            decision = "Goal completed"

        self.log.append(f"Review decision: {decision}")
        return decision

    # -------------- Approval handling --------------
    def approve(self, decision: str):
        """Called externally to provide approval or denial."""
        self._approval_result = decision
        self._approval_event.set()

    # -------------- Orchestration entry point --------------
    def start(self, goal: str):
        self.state = OrchestratorState.PLANNING
        plan = self.plan(goal)
        self.execute_plan(plan)
        decision = self.review(goal, plan)
        self.state = OrchestratorState.COMPLETE
        return decision



if __name__ == "__main__":
    import threading, time

    orch = Orchestrator()

    def auto_approve():
        time.sleep(1)
        orch.approve("approved")

    threading.Thread(target=auto_approve).start()
    final = orch.start("Launch marketing campaign")
    print("Orchestrator finished:", final)
