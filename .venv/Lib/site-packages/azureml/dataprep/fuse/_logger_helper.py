from azureml.dataprep.api._loggerfactory import _LoggerFactory


def get_trace_with_invocation_id(logger, invocation_id: str):
    def trace(message, custom_dimensions={}):
        custom_dimensions['invocation_id'] = invocation_id
        _LoggerFactory.trace(logger, message, custom_dimensions)

    return trace
