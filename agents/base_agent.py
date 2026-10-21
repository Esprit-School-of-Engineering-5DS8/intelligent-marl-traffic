"""
agents/base_agent.py
Abstract base class for all traffic light agents.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseTrafficAgent(ABC):
    """All agent implementations must inherit from this."""

    def __init__(self, tls_id: str):
        self.tls_id = tls_id

    @abstractmethod
    def select_action(self, state: Dict[str, Any]) -> int:
        """
        Given the current state observation, return an action:
          0 = North-South Green
          1 = East-West Green
        """
        ...

    def __repr__(self):
        return f"{self.__class__.__name__}(tls_id={self.tls_id})"
