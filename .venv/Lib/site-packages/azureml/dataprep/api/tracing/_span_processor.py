from abc import ABC, abstractmethod

logger = None
_run_id = None


def get_logger():
    global logger
    if logger is not None:
        return logger

    from .._loggerfactory import _LoggerFactory

    logger = _LoggerFactory.get_logger("SpanProcessor")
    return logger


class SpanProcessor(ABC):
    @abstractmethod
    def on_start(self, span: 'Span') -> None:
        pass

    @abstractmethod
    def on_end(self, span: 'Span') -> None:
        pass

    @abstractmethod
    def shutdown(self) -> None:
        pass

    @abstractmethod
    def force_flush(self, timeout_millis: int = 30000) -> bool:
        pass


class AmlSimpleSpanProcessor(SpanProcessor):
    def __init__(self, span_exporter: 'SpanExporter'):
        self._span_exporter = span_exporter

    def on_start(self, span: 'Span') -> None:
        _add_aml_context(span)

    def on_end(self, span: 'Span') -> None:
        try:
            self._span_exporter.export((span,))
        except Exception as e:
            get_logger().error('Exception of type {} while exporting spans.'.format(type(e).__name__))

    def shutdown(self) -> None:
        self._span_exporter.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


def _get_run_id():
    global _run_id
    if _run_id is not None:
        return _run_id
    try:
        from azureml.core import Run
        _run_id = Run.get_context().id
        return _run_id
    except:
        _run_id = '[Unavailable]'


def _add_aml_context(span: 'Span'):
    from .._loggerfactory import session_id
    run_id = _get_run_id()

    span.set_attribute('sessionId', session_id)
    span.set_attribute('runId', run_id)
