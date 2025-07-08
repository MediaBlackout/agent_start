```python
"""
agent_core.py

Core module for the autonomous weather intelligence agent.
Provides context-aware decision making, natural language understanding, task execution,
proactive alerting, and learning capabilities with ethical and safe AI practices.

Dependencies:
- spacy
- transformers
- scikit-learn
- networkx
- redis
- sqlalchemy
- celery
- marshmallow
"""

import os
import logging
import json
import threading
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Dict, Any, List, Tuple, Optional

# NLP and ML Dependencies
import spacy
from transformers import pipeline
from sklearn.cluster import KMeans

# Backend/Infra Dependencies
import networkx as nx
import redis
from sqlalchemy import create_engine, Column, Integer, String, DateTime, JSON
from sqlalchemy.orm import sessionmaker, declarative_base
from celery import Celery
from marshmallow import Schema, fields

# Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AgentCore")

# Load NLP models
nlp = spacy.load("en_core_web_sm")
sentiment_pipeline = pipeline("sentiment-analysis")

# Redis and SQLAlchemy setup
redis_client = redis.Redis(host='localhost', port=6379, db=0)
Base = declarative_base()
engine = create_engine('sqlite:///agent_memory.db')
Session = sessionmaker(bind=engine)
session = Session()

# Celery setup
celery_app = Celery('agent_tasks', broker='redis://localhost:6379/0')

#############################
# STORAGE & CONFIGURATION
#############################

class UserPreference(Base):
    __tablename__ = 'user_preferences'
    id = Column(Integer, primary_key=True)
    key = Column(String)
    value = Column(JSON)
    timestamp = Column(DateTime, default=datetime.utcnow)

class LearningRecord(Base):
    __tablename__ = 'learning_history'
    id = Column(Integer, primary_key=True)
    type = Column(String)
    data = Column(JSON)
    timestamp = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(engine)


#############################
# ENUMS
#############################

class Intent(Enum):
    WEATHER_QUERY = auto()
    ALERT_SETTINGS = auto()
    REPORT_GENERATION = auto()
    UNKNOWN = auto()
    SYSTEM_STATUS = auto()
    SET_PREFERENCE = auto()

class PriorityLevel(Enum):
    HIGH = auto()
    MEDIUM = auto()
    LOW = auto()


#############################
# MEMORY MANAGEMENT
#############################

class ConversationMemory:
    def __init__(self):
        self.short_term = []
        self.max_length = 5

    def add(self, user_input: str, response: str):
        self.short_term.append((user_input, response))
        if len(self.short_term) > self.max_length:
            self.short_term.pop(0)

    def get_context(self):
        return self.short_term


class KnowledgeGraph:
    def __init__(self):
        self.graph = nx.Graph()

    def update_knowledge(self, topic: str, relation: str, value: Any):
        self.graph.add_edge(topic, value, relation=relation)

    def get_relations(self, topic: str) -> List[str]:
        return list(self.graph.neighbors(topic))


class ConfigManager:
    def __init__(self, filepath='agent_config.json'):
        self.filepath = filepath
        self.config = self._load()

    def _load(self):
        if not os.path.exists(self.filepath):
            return {}
        with open(self.filepath, 'r') as f:
            return json.load(f)

    def get(self, key: str, default=None):
        return self.config.get(key, default)

    def set(self, key: str, value: Any):
        self.config[key] = value
        with open(self.filepath, 'w') as f:
            json.dump(self.config, f, indent=2)

    
#############################
# NATURAL LANGUAGE UNDERSTANDING
#############################

class NLU:
    def __init__(self):
        self.context = []

    def parse(self, text: str) -> Dict[str, Any]:
        doc = nlp(text)
        intent = self._infer_intent(text)
        entities = self._extract_entities(doc)
        sentiment = sentiment_pipeline(text)[0]
        return {
            "intent": intent,
            "entities": entities,
            "sentiment": sentiment,
            "raw_text": text
        }

    def _infer_intent(self, text: str) -> Intent:
        text = text.lower()
        if "weather" in text:
            return Intent.WEATHER_QUERY
        elif "alert" in text:
            return Intent.ALERT_SETTINGS
        elif "report" in text:
            return Intent.REPORT_GENERATION
        elif "preference" in text or "setting" in text:
            return Intent.SET_PREFERENCE
        elif "status" in text:
            return Intent.SYSTEM_STATUS
        else:
            return Intent.UNKNOWN

    def _extract_entities(self, doc) -> Dict[str, str]:
        entities = {}
        for ent in doc.ents:
            entities[ent.label_] = ent.text
        return entities


#############################
# TASK SCHEDULER / MANAGER
#############################

class Task:
    def __init__(self, description: str, priority: PriorityLevel, action):
        self.description = description
        self.priority = priority
        self.action = action
        self.status = 'pending'
        self.retry_count = 0
        self.created_at = datetime.utcnow()
        self.last_attempt = None

    def execute(self):
        try:
            self.status = 'in_progress'
            self.last_attempt = datetime.utcnow()
            logger.info(f"Executing task: {self.description}")
            self.action()
            self.status = 'done'
        except Exception as e:
            logger.error(f"Task failed: {e}")
            self.status = 'failed'
            self.retry_count += 1


class TaskManager:
    def __init__(self):
        self.tasks: List[Task] = []

    def add_task(self, task: Task):
        logger.info(f"Added task: {task.description}")
        self.tasks.append(task)
        self.tasks.sort(key=lambda t: t.priority.value)

    def execute_all(self):
        for task in list(self.tasks):
            if task.status != 'done':
                task.execute()
                if task.status == 'done':
                    self.tasks.remove(task)


#############################
# DECISION ENGINE
#############################

class DecisionEngine:
    def __init__(self):
        self.rules = []
        self.context = {}

    def evaluate(self, parsed_input: Dict[str, Any]) -> List[Task]:
        intent = parsed_input["intent"]
        sentiment = parsed_input["sentiment"]
        tasks = []

        if intent == Intent.WEATHER_QUERY:
            task = Task(
                description='Respond to weather query',
                priority=PriorityLevel.MEDIUM,
                action=lambda: print("The weather is sunny over San Francisco.")
            )
            tasks.append(task)
        elif intent == Intent.ALERT_SETTINGS:
            task = Task(
                description='Adjust user alert settings',
                priority=PriorityLevel.HIGH,
                action=lambda: print("Alert settings updated")
            )
            tasks.append(task)
        elif intent == Intent.REPORT_GENERATION:
            task = Task(
                description='Generate weather report',
                priority=PriorityLevel.MEDIUM,
                action=lambda: print("Sending weather report...")
            )
            tasks.append(task)
        elif intent == Intent.SYSTEM_STATUS:
            task = Task(
                description='Check system health',
                priority=PriorityLevel.LOW,
                action=lambda: print("System operating normally.")
            )
            tasks.append(task)

        return tasks


#############################
# PROACTIVE INTELLIGENCE
#############################

class ProactiveEngine:
    def __init__(self):
        self.monitored_locations = ['New York', 'San Francisco']
        self.alert_thresholds = {
            'temperature': 35,
            'wind_speed': 50
        }

    def monitor_weather(self):
        for loc in self.monitored_locations:
            # Placeholder for data collection logic.
            weather = self._get_weather_dummy(loc)
            if weather['temperature'] > self.alert_thresholds['temperature']:
                print(f"🔥 High temperature alert for {loc}: {weather['temperature']}°C")

    def _get_weather_dummy(self, loc: str) -> Dict[str, Any]:
        return {
            'temperature': 36,
            'wind_speed': 20,
            'humidity': 75
        }


#############################
# LEARNING ENGINE
#############################

class LearningEngine:
    def __init__(self):
        self.query_history = []

    def incorporate_feedback(self, feedback: str):
        logger.info("Received user feedback: %s", feedback)

    def learn_from_queries(self, query: str):
        self.query_history.append(query)
        clusterer = KMeans(n_clusters=2)
        if len(self.query_history) >= 2:
            vectorized = [len(q) for q in self.query_history]
            try:
                clusterer.fit([[v] for v in vectorized])
                logger.info("Updated query model clustering.")
            except Exception as e:
                logger.warning(f"Clustering error: {e}")


#############################
# INTERACTION ENGINE
#############################

class ConversationInterface:
    def __init__(self):
        self.nlu = NLU()
        self.memory = ConversationMemory()

    def handle_user_input(self, text: str) -> str:
        parsed = self.nlu.parse(text)
        engine = DecisionEngine()
        task_manager = TaskManager()
        tasks = engine.evaluate(parsed)
        for t in tasks:
            task_manager.add_task(t)

        task_manager.execute_all()

        response = f"Processed your input about {parsed['intent'].name.lower().replace('_', ' ')}."
        self.memory.add(text, response)
        return response


#############################
# MAIN AGENT CORE
#############################

class AgentCore:
    def __init__(self):
        self.conversation_interface = ConversationInterface()
        self.proactive_engine = ProactiveEngine()
        self.learning_engine = LearningEngine()
        self.config_manager = ConfigManager()
        self.knowledge_graph = KnowledgeGraph()

    def handle_input(self, user_input: str) -> str:
        self.learning_engine.learn_from_queries(user_input)
        return self.conversation_interface.handle_user_input(user_input)

    def run_background_monitoring(self):
        def monitor_loop():
            while True:
                try:
                    logger.info("Running weather monitor")
                    self.proactive_engine.monitor_weather()
                    redis_client.set('last_monitor', datetime.utcnow().isoformat())
                    time.sleep(300)
                except Exception as e:
                    logger.error(f"Monitoring error: {str(e)}")

        t = threading.Thread(target=monitor_loop, daemon=True)
        t.start()

    def graceful_shutdown(self):
        logger.info("Shutting down agent gracefully.")


#############################
# API & AUTONOMOUS ENTRY
#############################

if __name__ == "__main__":
    import time

    agent = AgentCore()
    agent.run_background_monitoring()

    print("Weather Agent is running. Type your weather questions:")
    try:
        while True:
            user_input = input("You: ")
            response = agent.handle_input(user_input)
            print(f"Agent: {response}")
            time.sleep(0.25)
    except KeyboardInterrupt:
        agent.graceful_shutdown()
        print("Goodbye!")
```