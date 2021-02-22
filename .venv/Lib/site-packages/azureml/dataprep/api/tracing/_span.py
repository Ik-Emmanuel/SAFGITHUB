import random
from datetime import datetime
from typing import Optional, List, Any, Dict, Union

from ._context import Context
from ._event import Event
from ._span_processor import SpanProcessor
from ._vendored import _execution_context as execution_context


class Span:
    def __init__(self, name: str, parent: Optional[Union['Span', Context]], span_processors: List[SpanProcessor]):
        self._name = name
        self._parent = parent
        self._trace_id = parent.trace_id if parent else generate_trace_id()
        self._span_id = generate_span_id()
        self._span_processors = span_processors
        self._start_time = None
        self._end_time = None
        self._attributes = {}
        self._events = []

    @property
    def parent(self):
        return self._parent

    @property
    def name(self):
        return self._name

    @property
    def trace_id(self):
        return self._trace_id

    @property
    def span_id(self):
        return self._span_id

    @property
    def start_time(self):
        return self._start_time

    @property
    def end_time(self):
        return self._end_time

    @property
    def kind(self):
        return 'Internal'

    @property
    def attributes(self):
        return self._attributes

    @property
    def events(self):
        return self._events

    def set_attribute(self, key: str, value: Any) -> None:
        self._attributes[key] = value

    def add_event(self, name: str, attributes: Dict[str, Any]):
        self._events.append(Event(name, datetime.utcnow(), attributes))

    def start(self):
        if self._start_time is not None:
            return

        self._start_time = datetime.utcnow()

        for span_processor in self._span_processors:
            span_processor.on_start(self)

    def set_as_current(self):
        execution_context.set_current_span(self)

    def end(self):
        if self._end_time is not None:
            return

        self._end_time = datetime.utcnow()

        for span_processor in self._span_processors:
            span_processor.on_end(self)

    def set_parent_as_current(self):
        execution_context.set_current_span(self._parent)

    def get_context(self) -> Context:
        return Context(self._trace_id, self._span_id)

    def __enter__(self):
        self.set_as_current()
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.set_parent_as_current()
        self.end()


def generate_span_id() -> int:
    return random.getrandbits(64)


def generate_trace_id() -> int:
    return random.getrandbits(128)
