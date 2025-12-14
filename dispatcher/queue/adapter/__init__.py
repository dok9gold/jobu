"""Queue adapters"""
from dispatcher.queue.adapter.base import BaseQueueAdapter
from dispatcher.queue.adapter.kafka import KafkaAdapter

__all__ = ["BaseQueueAdapter", "KafkaAdapter"]
