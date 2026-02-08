# Mock implementation of AgentField for demonstration purposes
import inspect
from typing import Any, Callable, Dict, Optional, Type

class Agent:
    name: str = "base_agent"
    description: str = ""
    tags: list[str] = []

class App:
    def __init__(self):
        self.agents: Dict[str, Any] = {}
        self.skills: Dict[str, Dict[str, Callable]] = {}
        self.reasoners: Dict[str, Dict[str, Callable]] = {}
        self.memory_store: Dict[str, Any] = {}

    def agent(self, cls: Type[Agent]):
        """Decorator to register an agent class."""
        instance = cls()
        self.agents[instance.name] = instance
        # Auto-register methods decorated as skills/reasoners
        self.skills[instance.name] = {}
        self.reasoners[instance.name] = {}
        
        for name, method in inspect.getmembers(instance, predicate=inspect.ismethod):
            if hasattr(method, "_is_skill"):
                self.skills[instance.name][name] = method
            if hasattr(method, "_is_reasoner"):
                self.reasoners[instance.name][name] = method
        
        return cls

    def skill(self, func: Callable):
        """Decorator to mark a method as a skill."""
        func._is_skill = True
        return func

    def reasoner(self, func: Callable):
        """Decorator to mark a method as a reasoner."""
        func._is_reasoner = True
        return func

    def discover(self, tags: list[str]) -> list[str]:
        """Finds agents with matching tags."""
        matches = []
        for name, agent in self.agents.items():
            if any(t in agent.tags for t in tags):
                matches.append(name)
        return matches

    def call(self, agent_name: str, skill_name: str, **kwargs) -> Any:
        """Invokes a skill on an agent."""
        if agent_name not in self.agents:
            raise ValueError(f"Agent {agent_name} not found")
        if skill_name not in self.skills[agent_name]:
             # Try reasoners too
            if skill_name in self.reasoners[agent_name]:
                 return self.reasoners[agent_name][skill_name](**kwargs)
            raise ValueError(f"Skill {skill_name} not found on {agent_name}")
        
        return self.skills[agent_name][skill_name](**kwargs)
    
    @property
    def memory(self):
        return self.memory_store

# Singleton instance
app = App()
