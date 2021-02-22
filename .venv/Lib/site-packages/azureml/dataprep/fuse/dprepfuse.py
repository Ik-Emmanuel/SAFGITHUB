from ._cached_dataflow import CachedDataflow
from ._dataflowconstants import *
from ._filecache import FileCache
from ._fuse_base import FuseBase
from ._stat import create_stat, stat_to_dict
from ._streamingreader import StreamingReader, UnknownStreamSizeError
from ._streaminfo import get_stream_info_value, get_value, StreamDetails
from .daemon import MountContext
from .vendor.fuse import FuseOSError, FUSE
from azureml.dataprep import Dataflow, col, get_stream_properties, SummaryColumnsValue, SummaryFunction, cond
from azureml.dataprep.api._loggerfactory import _LoggerFactory, session_id, trace
from azureml.dataprep.api.engineapi.typedefinitions import DownloadStreamInfoMessageArguments
from azureml.dataprep.api.expressions import FunctionExpression, IdentifierExpression, InvokeExpression
from azureml.dataprep.api.functions import get_portable_path
from azureml.dataprep.api._rslex_executor import get_rslex_context
from azureml.dataprep.api.tracing._context import Context
from azureml.dataprep.api.tracing._open_telemetry_adapter import to_dprep_span_context
from azureml.dataprep.native import DataPrepError
from azureml.dataprep.rslex import _rslex_loader
from errno import EFBIG, ENOENT
from stat import S_IFREG, S_IFDIR
import os
import json
import atexit
from time import perf_counter
from typing import List, Optional


log = _LoggerFactory.get_logger('dprep.fuse')
tracer = trace.get_tracer(__name__)
SENTINEL_FILE_NAME = '__dprep_sentinel_fac0fa29-1396-4461-9056-f34bdd8dc3c6__'
_SENTINEL_PATH = '/' + SENTINEL_FILE_NAME


class MountOptions:
    def __init__(self,
                 data_dir: str = None,
                 max_size: int = None,
                 free_space_required: int = None):
        """
        Configuration options for file mounting.

        .. remarks::

            Depending on the source of the streams mounted, it might be necessary to fully download a file locally
                before it can be opened by the file system. For sources that support streaming, access to the file
                can be provided without this requirement. In both cases, it is possible to configure the system
                to cache the data locally. This can be useful when specific files will be accessed multiple times
                and the source of the data is remote to the current compute. These downloaded and cached files will
                be stored in the system's tmp folder by default, but this can be overriden by manually specifying a
                data_dir.

            The max_size and free_space_required parameters can be used to limit how much data will be downloaded
                or cached locally. If accessing a file requires that it be downloaded, then the least recently used
                files will be deleted after the download completes in order to stay within these parameters. If a file
                that needs to be downloaded before it can be opened by the file system does not fit within the available
                space, an error will be returned.

        :param data_dir: The directory to use to download or cache files locally. If None is provided, the system's
            temp folder is used.
        :param max_size: The maximum amount of memory, in bytes, that can be stored in data_dir.
        :param free_space_required: How much space should be kept available in the data_dir volume.
        """
        self.data_dir = data_dir
        self.max_size = max_size
        self.free_space_required = free_space_required


class _DPrepFuse(FuseBase):
    """Read-only fuse."""

    def __init__(self,
                 dataflow: Dataflow,
                 files_column: str,
                 base_path: str = None,
                 mount_options: MountOptions = None,
                 invocation_id: str = None,
                 caller_session_id: str = None,
                 span_context: Optional[Context] = None):
        super().__init__(log, invocation_id, mount_options, span_context or tracer.start_span(self.__class__.__name__))
        self._files_column = files_column
        self._cache = FileCache(self._mount_options.data_dir,
                                self._mount_options.max_size,
                                self._mount_options.free_space_required,
                                self._download_stream,
                                self._get_handle,
                                invocation_id=invocation_id)
        dataflow = dataflow \
            .add_column(get_portable_path(col(files_column), base_path), PORTABLE_PATH, files_column) \
            .add_column(get_stream_properties(col(files_column)), STREAM_PROPERTIES, PORTABLE_PATH)
        self._cached_dataflow = CachedDataflow(dataflow, self._mount_options.data_dir)
        self._streaming_reader = StreamingReader(self._cached_dataflow,
                                                 files_column,
                                                 self._mount_timestamp,
                                                 self._engine_api,
                                                 self._get_handle)
        self._open_dirs = {}
        self._cached_dirs = {}
        self._known_dirs = set()
        self._cached_entry_details = {}
        # Starts at 1 because 0 is reserved for _SENTINEL_PATH
        self._handle = 1

        try:
            log.debug("Getting RsLexContext...")
            rslex_context = get_rslex_context(caller_session_id)
            log.debug("Getting StreamDownloader")
            self._downloader = _rslex_loader.create_downloader(self._cache.data_dir, rslex_context)
            atexit.register(lambda: _rslex_loader.release_downloader(self._downloader))
        except Exception as e:
            log.error('Create downloader failed with rslex\nFallback to clex.')
            self._downloader = None

    def _get_handle(self):
        self._handle += 1
        return self._handle

    def _list_entries(self, path: str) -> List[str]:
        with tracer.start_as_current_span('_DPrepFuse._list_entries', trace.get_current_span()):
            path = _ensure_directory_path(path)
            entries = self._cached_dirs.get(path)

            if entries is not None:
                return entries

            path_col = col(PORTABLE_PATH)
            child_path_fn = FunctionExpression([DELIMITER_INDEX],
                                               {},
                                               cond(IdentifierExpression(DELIMITER_INDEX) != - 1,
                                                    col(RELATIVE_PATH).substring(0, IdentifierExpression(DELIMITER_INDEX)),
                                                    col(RELATIVE_PATH)))

            results = self._cached_dataflow.dataflow(wait_for_cache=True).filter(path_col.starts_with(path)) \
                .add_column(col(PORTABLE_PATH).substring(len(path)), RELATIVE_PATH, PORTABLE_PATH) \
                .add_column(InvokeExpression(child_path_fn, [col(RELATIVE_PATH).index_of('/')]), CHILD_PATH, RELATIVE_PATH) \
                .add_column(cond(col(RELATIVE_PATH) == col(CHILD_PATH), col(self._files_column), None), CHILD_FILE, CHILD_PATH) \
                .summarize([
                    SummaryColumnsValue(CHILD_FILE, SummaryFunction.SINGLE, self._files_column),
                    SummaryColumnsValue(PORTABLE_PATH, SummaryFunction.SINGLE, PORTABLE_PATH),
                    SummaryColumnsValue(STREAM_PROPERTIES, SummaryFunction.SINGLE, STREAM_PROPERTIES)
                ], group_by_columns=[CHILD_PATH]) \
                .summarize([
                    SummaryColumnsValue(self._files_column, SummaryFunction.TOLIST, STREAMS_LIST),
                    SummaryColumnsValue(CHILD_PATH, SummaryFunction.TOLIST, CHILD_PATHS_LIST),
                    SummaryColumnsValue(PORTABLE_PATH, SummaryFunction.TOLIST, PORTABLE_PATHS_LIST),
                    SummaryColumnsValue(STREAM_PROPERTIES, SummaryFunction.TOLIST, STREAMS_PROPERTIES_LIST)
                ]) \
                ._to_pyrecords()
            entries = ['.', '..']
            if len(results) == 0:
                return entries

            children = results[0][CHILD_PATHS_LIST]
            matching_streams = results[0][STREAMS_LIST]
            portable_paths = results[0][PORTABLE_PATHS_LIST]
            stream_properties = results[0][STREAMS_PROPERTIES_LIST]
            children_data = zip(matching_streams, portable_paths, stream_properties, children)
            for matching_stream, portable_path, properties, relative_path in children_data:
                if isinstance(matching_stream, DataPrepError):
                    if matching_stream.errorCode == "Microsoft.DPrep.ErrorCodes.SingleValueExpected":
                        self._known_dirs.add(_ensure_directory_path(path + relative_path))
                    continue

                if matching_stream is None:
                    continue

                if not portable_path.endswith(relative_path):
                    self._known_dirs.add(_ensure_directory_path(relative_path))

                # caching entry should be skipped for stream with unknown size, which will
                # make getattr download the stream into filecache for its true size
                if properties.get(STREAM_SIZE) is None:
                    continue

                self._cached_entry_details[portable_path] = {
                    STREAM_INFO: matching_stream,
                    PORTABLE_PATH: portable_path,
                    STREAM_SIZE: properties.get(STREAM_SIZE),
                    LAST_MODIFIED: properties.get(LAST_MODIFIED),
                    CAN_SEEK: properties.get(CAN_SEEK)
                }

            entries = entries + children
            self._cached_dirs[path] = entries
            return entries

    def _download_stream(self, stream_details: StreamDetails, target_path: str) -> str:
        stream_info_value = get_stream_info_value(stream_details.stream_info)
        span = trace.get_current_span()
        try:
            if self._downloader is None:
                raise Exception("downloader is None")
            si_dto = stream_info_value['streaminfo']
            si_dto['session_properties'] = {
                'size': get_value(stream_details.size),
                'createdTime': get_value(stream_details.last_modified),
                'modifiedTime': get_value(stream_details.last_modified),
                'isSeekable': get_value(stream_details.can_seek)
            }
            si_dto_json = json.dumps(si_dto, ensure_ascii=False)
            return _rslex_loader.download(si_dto_json, self._downloader)
        except Exception as e:
            err_msg = 'Download failed with rslex due to {}.'.format(repr(e))
            if '_TEST_DISABLE_DOWNLOAD_FALLBACK' in os.environ:
                raise Exception(err_msg) from e
            log.error('%s\nFallback to clex.', err_msg)
            self._engine_api.download_stream_info(DownloadStreamInfoMessageArguments(
                to_dprep_span_context(span.get_context() if span else None), stream_info_value, target_path))
            return target_path

    def _get_stream_details_for_path(self, path) -> Optional[StreamDetails]:
        log.debug('Getting stream details for path %s', path)
        with tracer.start_as_current_span('_DPrepFuse._get_stream_details_for_path', trace.get_current_span()):
            cached_entry = self._cached_entry_details.get(path)
            if cached_entry is not None:
                log.debug('Stream details in cache.')
            else:
                log.debug('Executing to retrieve stream details.')
                matching_rows = self._cached_dataflow.dataflow(wait_for_cache=False).filter(col(PORTABLE_PATH) == path) \
                    .add_column(col(STREAM_SIZE, col(STREAM_PROPERTIES)), STREAM_SIZE, STREAM_PROPERTIES) \
                    .add_column(col(LAST_MODIFIED, col(STREAM_PROPERTIES)), LAST_MODIFIED, STREAM_SIZE) \
                    .add_column(col(CAN_SEEK, col(STREAM_PROPERTIES)), CAN_SEEK, LAST_MODIFIED) \
                    .take(1) \
                    ._to_pyrecords()
                if len(matching_rows) == 0:
                    return None

                row = matching_rows[0]
                cached_entry = {
                    STREAM_INFO: row[self._files_column],
                    PORTABLE_PATH: row[PORTABLE_PATH],
                    STREAM_SIZE: row[STREAM_SIZE],
                    LAST_MODIFIED: row[LAST_MODIFIED],
                    CAN_SEEK: row[CAN_SEEK]
                }
                self._cached_entry_details[path] = cached_entry

            return StreamDetails(cached_entry[STREAM_INFO],
                                 cached_entry[PORTABLE_PATH],
                                 cached_entry[STREAM_SIZE],
                                 cached_entry[LAST_MODIFIED],
                                 cached_entry[CAN_SEEK])

    def _cache_path(self, path: str):
        stream_details = self._get_stream_details_for_path(path)
        stream_last_modified = int(stream_details.last_modified.timestamp() if stream_details.last_modified is not None
                                   else self._mount_timestamp)
        stat = create_stat(S_IFREG,
                           stream_details.size,
                           stream_last_modified,
                           stream_last_modified,
                           stream_last_modified)
        self._cache.push(path, stream_details, stat)

    def getattr(self, path: str, fh=None):
        with tracer.start_as_current_span('_DPrepFuse.getattr', self._span_context):
            log.debug('getattr(path=%s)', path, extra=dict(path=path))

            if path == _SENTINEL_PATH:
                return self._sentinel_attr

            if path.startswith('/.Trash'):
                # .Trash files are used by Ubuntu to store deleted files in a mounted volume. As such, we can't actually
                # mount files with this name. Since this is also a read-only file system, we don't support deletion.
                # We'll take a shortcut and just return ENOENT instead of doing a lookup.
                raise FuseOSError(ENOENT)

            if path in self._cache:
                log.debug('Path found in cache.', extra=dict(path=path))
                return stat_to_dict(self._cache.get_attributes(path))

            if path in self._cached_entry_details:
                log.debug('Path found in cached entries.', extra=dict(path=path))
                entry = self._cached_entry_details[path]
                stream_last_modified = int(entry[LAST_MODIFIED].timestamp() if entry[LAST_MODIFIED] is not None
                                           else self._mount_timestamp)
                return {
                    'st_mode': S_IFREG,
                    'st_size': entry[STREAM_SIZE],
                    'st_atime': stream_last_modified,
                    'st_mtime': stream_last_modified,
                    'st_ctime': stream_last_modified
                }

            ensured_path = _ensure_directory_path(path)
            if ensured_path in self._cached_dirs or ensured_path in self._known_dirs:
                log.debug('Path found in directory cache.', extra=dict(path=path))
                return {
                    'st_mode': S_IFDIR,
                    'st_size': 0,
                    'st_atime': self._mount_timestamp,
                    'st_mtime': self._mount_timestamp,
                    'st_ctime': self._mount_timestamp
                }

            try:
                log.debug('Attempting to stream attributes. (path=%s)', path, extra=dict(path=path))
                stat, stream_details = self._streaming_reader.get_attributes_and_stream_details(path)
                if stream_details:
                    self._cached_entry_details[path] = {
                        STREAM_INFO: stream_details.stream_info,
                        PORTABLE_PATH: stream_details.portable_path,
                        STREAM_SIZE: stream_details.size,
                        LAST_MODIFIED: stream_details.last_modified,
                        CAN_SEEK: stream_details.can_seek
                    }
                else:
                    self._known_dirs.add(ensured_path)
                return stat_to_dict(stat)
            except UnknownStreamSizeError:
                log.debug('Unknown size for specified path. (path=%s)', path, extra=dict(path=path))
                self._cache_path(path)
                return stat_to_dict(self._cache.get_attributes(path))

    def opendir(self, path):
        with tracer.start_as_current_span('_DPrepFuse.opendir', self._span_context):
            log.debug('opendir(path=%s)', path)
            handle = self._get_handle()
            self._open_dirs[handle] = self._list_entries(path)
            log.debug('Entries retrieved.')
            return handle

    def readdir(self, path, fh):
        with tracer.start_as_current_span('_DPrepFuse.readdir', self._span_context):
            log.debug('readdir(path=%s, fh=%s)', path, fh, extra=dict(handle=fh))
            dir_entries = self._open_dirs.get(fh)
            if dir_entries is None:
                log.warning('No entries found in cache. Was opendir not called?', extra=dict(handle=fh))
                dir_entries = self._list_entries(path)

            log.debug('Returning entries.', extra=dict(handle=fh))
            return dir_entries

    def releasedir(self, path, fh):
        try:
            log.debug('releasedir(handle=%s)', fh)
            self._open_dirs.pop(fh)
        except KeyError:
            log.warning('Failed to release directory.', extra=dict(handle=fh))
            log.error('Unexpected error during releasedir.')
            raise FuseOSError(ENOENT)

    def open(self, path, flags, raw_fi=None):
        log.debug('open(path=%s, flags=%s)', path, flags, extra=dict(path=path, flags=flags))

        with tracer.start_as_current_span('_DPrepFuse.open', self._span_context):
            if path == _SENTINEL_PATH:
                log.debug('_SENTINEL_PATH opened: %s (handle=%s)', path, 0, extra=dict(path=path, handle=0))
                return 0

            try:
                if path not in self._cache:
                    log.debug('Caching path: %s', path, extra=dict(path=path))
                    self._cache_path(path)

                log.debug('Reading from cache: %s', path, extra=dict(path=path))
                handle = self._cache.open(path)
                log.debug('File opened from cache: %s (handle=%s)', path, handle, extra=dict(path=path, handle=handle))
                return handle
            except Exception as e:
                log.debug('Error encountered while opening file: %s', path, extra=dict(path=path))
                if type(e).__name__ != FuseOSError.__name__ or e.errno != EFBIG:
                    raise

            # If we failed because the file is too big to download, try to stream it
            log.debug('File too big to download. Streaming: %s', path, extra=dict(path=path))
            try:
                return self._streaming_reader.open(path)
            except Exception:
                log.debug('Failed to stream file: %s', path, extra=dict(path=path))
                self._trace('Failed to stream file.')
                raise

    def read(self, path, size, offset, fh, buffer):
        log.debug('read(path=%s, size=%s, offset=%s, fh=%s)',
                  path,
                  size,
                  offset,
                  fh,
                  extra=dict(path=path, size=size, offset=offset, fh=fh))

        if path == _SENTINEL_PATH and fh == 0:
            log.debug('Reading _SENTINEL_PATH: %s (handle=%s)', path, fh, extra=dict(path=path, handle=fh))
            contents = self._sentinel_contents
            contents_len = len(contents)
            for i, c in enumerate(contents):
                buffer[offset+i] = contents[i]
            return contents_len

        if path in self._cache:
            log.debug('Reading file from cache: %s (handle=%s)', path, fh, extra=dict(path=path, handle=fh))
            return self._cache.read(fh, size, offset, buffer)
        else:
            log.debug('Streaming file read: %s (handle=%s)', path, fh, extra=dict(path=path, handle=fh))
            return self._streaming_reader.read(fh, size, offset, buffer)

    def release(self, path, fh):
        log.debug('release(path=%s, fh=%s)', path, fh, extra=dict(path=path, handle=fh))

        if path == _SENTINEL_PATH and fh == 0:
            log.debug('Releasing _SENTINEL_PATH: %s (handle=%s)', path, fh, extra=dict(path=path, handle=fh))
            return

        if path in self._cache:
            log.debug('Releasing file from cache: %s (handle=%s)', path, fh, extra=dict(path=path, handle=fh))
            return self._cache.release(fh)
        else:
            log.debug('Releasing file from streaming reader: %s (handle=%s)',
                      path, fh, extra=dict(path=path, handle=fh))
            return self._streaming_reader.release(fh)

    def destroy(self, path):
        log.info('Tearing down mount (%s)', self._invocation_id, extra=dict(invocation_id=self._invocation_id))
        self._cache.clear()


def _ensure_directory_path(path):
    # Ensure directories end with /
    return path + '/' if path[-1] != '/' else path


def mount(dataflow: Optional[Dataflow],
          files_column: Optional[str],
          mount_point: str,
          base_path: str = None,
          options: MountOptions = None,
          destination: tuple = None,
          foreground = True,
          invocation_id: str = None,
          span_context: Optional[Context] = None,
          **kwargs) -> Optional[MountContext]:
    if foreground:
        spawn_process_timestamp = float(kwargs.get('spawn_process_timestamp', -1))
        process_spawn_duration = -1 if spawn_process_timestamp == -1 else perf_counter() - spawn_process_timestamp
        caller_session_id = kwargs.get('caller_session_id')
        _LoggerFactory.trace(log, 'starting dataprep mount in foreground', {
            'invocationId': invocation_id,
            'callerSessionId': caller_session_id,
            'sessionId': session_id,
            'process_spawn_duration': process_spawn_duration
        })
        if caller_session_id is not None:
            _LoggerFactory.add_default_custom_dimensions({'caller_session_id': caller_session_id})
        if not dataflow and not destination:
            raise ValueError('Invalid mount arguments. You must either pass in a dataflow or a destination.')
        if dataflow is not None:
            fuse_opts = _DPrepFuse(dataflow, files_column, base_path, options, invocation_id, caller_session_id, span_context)
        else:
            from azureml.dataprep.fuse._writable_fuse import WritableFuse
            fuse_opts = WritableFuse(destination, options, invocation_id, span_context)
        try:
            FUSE(fuse_opts, mount_point, foreground=True)
            return None
        except:
            log.error('an exception occurred during dataprep mount')
            raise
    else:
        return MountContext(dataflow, files_column, mount_point, base_path, options, invocation_id, destination)
