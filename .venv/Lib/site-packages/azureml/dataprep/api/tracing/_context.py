from azureml.dataprep.api.engineapi.typedefinitions import ActivityTraceFlags


class Context:
    def __init__(self, trace_id: int, span_id: int):
        self.trace_id = trace_id
        self.span_id = span_id
        self.is_remote = False
        self.trace_flags = ActivityTraceFlags.RECORDED
        self.trace_state = {}
