import os
import threading
from uuid import uuid4

from azureml.dataprep import read_preppy
from azureml.dataprep.api._loggerfactory import _LoggerFactory


log = _LoggerFactory.get_logger('dprep.fuse._cached_dataflow')


class CachedDataflow:
    def __init__(self, dataflow, cache_dir):
        self._dataflow = dataflow
        self._cache_dir = os.path.join(cache_dir, '__dprep_preppy_{}__'.format(str(uuid4())))
        self._cache_lock = threading.Lock()
        self._preppy_dataflow = None

        def _cache_to_preppy():
            log.debug('Caching thread started.')
            try:
                self._dataflow.write_to_preppy(self._cache_dir).run_local()
                log.debug('Caching dataflow to preppy is done')
            except Exception as e:
                log.warning('Error encountered while caching dataflow to preppy due to: {}'.format(repr(e)))

        self._cache_to_preppy_fn = _cache_to_preppy
        self._start_caching()

    def dataflow(self, wait_for_cache):
        if wait_for_cache:
            log.debug('Waiting for cache done.')
            self._caching_thread.join()
        try:
            self._cache_lock.acquire()
            if not os.path.exists(os.path.join(self._cache_dir, '_SUCCESS')):
                if not self._caching_thread.is_alive():
                    self._start_caching()
                log.debug('Caching is in progress, returning original dataflow.')
                return self._dataflow
            if self._preppy_dataflow is None:
                self._preppy_dataflow = read_preppy(self._cache_dir, include_path=True, verify_exists=True)
            return self._preppy_dataflow
        except Exception as e:
            log.warning('Error encountered while reading cached dataflow from preppy due to: {}'.format(repr(e)))
            self._preppy_dataflow = None
            # fallback to use raw dataflow without cache
            return self._dataflow
        finally:
            self._cache_lock.release()

    def _start_caching(self):
        log.debug('Starting caching in another thread.')
        self._caching_thread = threading.Thread(target=self._cache_to_preppy_fn)
        self._caching_thread.start()
