import atexit


def register_atexit():
    atexit.register(_shutdown_engine)


def _shutdown_engine():
    from .engineapi.api import _engine_api, kill_engine_api
    if _engine_api is not None:
        try:
            _engine_api.shutdown_engine(5)  # timeout in 5 sec
            kill_engine_api()
        except Exception as e:
            from ._loggerfactory import _LoggerFactory
            _LoggerFactory.get_logger('atexit').error('Error during engine shutdown: {}'.format(e.__class__))
