import datetime
from typing import List

from .._constants import EXCEPTION_EVENT_NAME, EXCEPTION_EVENT_TYPE_KEY, EXCEPTION_EVENT_MESSAGE_KEY
from ._exporter import SpanExporter
from ._span import Span


class OCApplicationInsightsTraceExporter(SpanExporter):
    """Application Insights span exporter for OpenCensus."""

    def __init__(self, telemetry_client):
        self._client = telemetry_client

    def export(self, spans: List[Span]) -> None:
        for span in spans:
            try:
                name, result_code, trace_id, span_id, parent_id, success, duration = self._extract_generic_properties(span)

                has_exception = False
                for evt in span.events or []:
                    if evt.name != EXCEPTION_EVENT_NAME:
                        continue
                    has_exception = True
                    self._track_exception_telemetry(evt, trace_id, span_id)

                self._track_span_telemetry(span, name, result_code, trace_id, span_id, parent_id, success, duration, has_exception)
            except Exception as e:
                _get_logger().error(str(e))

    def shutdown(self) -> None:
        self._client.flush()

    def _track_span_telemetry(self, span: Span, name: str, result_code: str, trace_id: str, span_id: str, parent_id: str, success: bool, duration: str, has_exception: bool):
        try:
            from applicationinsights import channel
        except ImportError:
            return

        if span.kind == 'Client':
            data = channel.contracts.RemoteDependencyData()
            data.result_code = result_code
            data.type = 'Http'
        else:
            data = channel.contracts.RequestData()
            data.response_code = result_code
        data.name = name
        data.id = span_id
        data.duration = duration
        data.success = success is True and has_exception is False
        for key in span.attributes or []:
            data.properties[key] = span.attributes[key]
        self._track(data, span.start_time, trace_id, parent_id)

    def _track_exception_telemetry(self, event, trace_id: str, span_id: str):
        try:
            from applicationinsights import channel
        except ImportError:
            return

        details = channel.contracts.ExceptionDetails()
        details.id = 1
        details.outer_id = 0
        details.has_full_stack = False
        details.type_name = event.attributes.get(EXCEPTION_EVENT_TYPE_KEY, '<Unknown>')
        details.message = event.attributes.get(EXCEPTION_EVENT_MESSAGE_KEY, '<Empty>')
        data = channel.contracts.ExceptionData()
        data.exceptions.append(details)
        for key in event.attributes or []:
            data.properties[key] = event.attributes[key]
        self._track(data, event.timestamp, trace_id, span_id)

    def _track(self, data, timestamp: int, trace_id: str, parent_id: str):
        try:
            from applicationinsights.channel import contracts
        except ImportError:
            return
        envelope = contracts.Envelope()
        envelope.data = contracts.Data()
        envelope.data.base_data = data
        envelope.data.base_type = data.DATA_TYPE_NAME
        envelope.name = data.ENVELOPE_TYPE_NAME
        envelope.time = timestamp
        context = self._client.context
        envelope.ikey = context.instrumentation_key
        for key, value in self._get_context_tags():
            envelope.tags[key] = value
        envelope.tags['ai.operation.id'] = trace_id
        if parent_id:
            envelope.tags['ai.operation.parentId'] = parent_id
        self._client.channel.queue.put(envelope)

    def _get_context_tags(self):
        context = self._client.context
        for item in [context.device, context.cloud, context.application, context.user,
                     context.session, context.location, context.operation]:
            if not item:
                continue
            for pair in item.write().items():
                yield pair

    def _extract_generic_properties(self, span: Span):
        name = span.name
        result_code = str(span._span.status.canonical_code)
        trace_id = '{:016x}'.format(span.get_context().trace_id)
        span_id = '{:016x}'.format(span.get_context().span_id)
        parent = span.parent
        if isinstance(parent, Span):
            parent = parent.get_context()
        if parent:
            parent_id = '{:016x}'.format(parent.span_id)
        else:
            parent_id = None
        success = span._span.status.is_ok
        duration = _to_duration(span.start_time, span.end_time)

        return name, result_code, trace_id, span_id, parent_id, success, duration


_logger = None
def _get_logger():
    global _logger
    if _logger is None:
        from .._loggerfactory import _LoggerFactory
        _logger = _LoggerFactory.get_logger(__file__)
    return _logger


def _to_duration(start_time: str, end_time: str) -> str:
    format = '%Y-%m-%dT%H:%M:%S.%fZ'
    start = datetime.datetime.strptime(start_time, format)
    end = datetime.datetime.strptime(end_time, format)
    diff = end - start
    value, microseconds = divmod(diff.microseconds, 1000000)
    value, seconds = divmod(value, 60)
    value, minutes = divmod(value, 60)
    days, hours = divmod(value, 24)
    return '{:d}.{:02d}:{:02d}:{:02d}.{:03d}'.format(
        days, hours, minutes, seconds, microseconds
    )
