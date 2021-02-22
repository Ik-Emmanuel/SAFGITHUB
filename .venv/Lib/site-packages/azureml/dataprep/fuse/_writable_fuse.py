from .vendor.fuse import FuseOSError
from .dprepfuse import MountOptions
from ._fuse_base import FuseBase
from ._local_dir import LocalDir
from azureml.dataprep.api._datastore_helper import _to_stream_info_value
from azureml.dataprep.api._loggerfactory import _LoggerFactory, trace
from azureml.dataprep.api.engineapi.typedefinitions import UploadFileMessageArguments, DeleteMessageArguments, MoveFileMessageArguments, CreateFolderMessageArguments
from azureml.dataprep.api.tracing._open_telemetry_adapter import to_dprep_span_context
from azureml.dataprep.api.tracing._context import Context
from ._file_object import FileObject
from ._dir_object import DirObject
from ._handle_object import HandleObject
from ._local_driver import LocalDriver
from ._reference_count import ReferenceCount
import os
import errno
import threading
from typing import Union, Optional

log = _LoggerFactory.get_logger('dprep.writable_fuse')
tracer = trace.get_tracer(__name__)


class WritableFuse(FuseBase):
    def __init__(self,
                 destination: 'Value' = None,
                 mount_options: MountOptions = None,
                 invocation_id: str = None,
                 span_context: Optional[Context] = None):
        super().__init__(log, invocation_id, mount_options, span_context or tracer.start_span(self.__class__.__name__))
        self._datastore = None
        self._remote_base = None
        if destination is not None:
            self._datastore = destination[0]
            self._remote_base = destination[1]
        self._data_dir = LocalDir(self._mount_options.data_dir)
        self._handle_table = {}
        self._local_driver = LocalDriver(self._data_dir)
        self._references = {}
        self._lock = threading.Lock()
        self._busy_event = threading.Event()
        self._file_locks = {}

    def _create_reference(self, path):
        with self._lock:
            self._busy_event.clear()
            reference = self._references.get(path)
            if reference is None:
                reference = ReferenceCount()
                self._references[path] = reference
                self._file_locks[path] = threading.Lock()
            else:
                reference.add_reference()
            return reference

    def _get_reference(self, path):
        with self._lock:
            return self._references.get(path)

    def _has_reference(self, path):
        ref = self._get_reference(path)
        return ref is not None and ref.has_reference()

    def _release_reference(self, path):
        with self._lock:
            reference = self._references.get(path)
            if reference is None:
                return
            self._file_locks.pop(path)
            if reference.release() == 0:
                self._references.pop(path)
            if len(self._references.keys()) == 0:
                self._busy_event.set()

    def _get_file_obj(self, handle) -> Union[FileObject, DirObject]:
        return self._handle_table.get(handle)

    def _remove_file_obj(self, handle):
        self._handle_table.pop(handle)

    def _get_remote_stream_info(self, path=None):
        if path is None:
            remote_path = self._remote_base
        else:
            relative_path = path.lstrip('/')
            remote_path = os.path.join(self._remote_base, relative_path)
        return _to_stream_info_value(self._datastore, remote_path)

    def access(self, path, mode):
        return 0 if self._local_driver.access(path, mode) else -1

    def create(self, path, mode, flags, fi=None):
        '''
        When fi is None and create should return a numerical file handle.

        When fi is not None the file handle should be set directly by create
        and return 0.
        '''

        self._local_driver.mknod(path, mode, 0)
        return self.open(path, flags, fi)

    def flush(self, path, fh):
        with tracer.start_as_current_span('WritableFuse.flush', self._span_context) as span:
            file = self._get_file_obj(fh)
            if file is None or not file.is_dirty or not self._datastore:
                return 0
            file_lock = self._file_locks[path]
            with file_lock:
                try:
                    self._engine_api.upload_file(UploadFileMessageArguments(
                        base_path=self._data_dir.get_local_root(),
                        destination=self._get_remote_stream_info(),
                        local_path=self._data_dir.get_target_path(path),
                        overwrite=True,
                        span_context=to_dprep_span_context(span.get_context())
                    ))
                except Exception as e:
                    self.__class__._print_and_log_ex(e, 'flush', 'Upload file')
                    raise FuseOSError(errno.EIO)
            return 0

    def getattr(self, path, fh=None):
        from .dprepfuse import _SENTINEL_PATH
        if path == _SENTINEL_PATH:
            return self._sentinel_attr

        stat = self._local_driver.get_attributes(path)
        return {
            'st_mode': stat.st_mode,
            'st_size': stat.st_size,
            'st_atime': stat.st_atime,
            'st_mtime': stat.st_mtime,
            'st_ctime': stat.st_ctime,
            'st_uid': stat.st_uid,
            'st_gid': stat.st_gid
        }

    def mkdir(self, path, mode):
        with tracer.start_as_current_span('WritableFuse.mkdir', self._span_context) as span:
            try:
                self._local_driver.mkdir(path, mode)
                if self._datastore is not None:
                    self._engine_api.create_folder(CreateFolderMessageArguments(
                        remote_folder_path=self._get_remote_stream_info(path),
                        span_context=to_dprep_span_context(span.get_context())
                    ))
            except FileExistsError:
                raise FuseOSError(errno.EEXIST)
            except Exception as e:
                self.__class__._print_and_log_ex(e, 'mkdir', 'Create folder')
                raise FuseOSError(errno.EIO)
            return 0

    def mknod(self, path, mode, dev):
        return self._local_driver.mknod(path, mode, dev)

    def open(self, path, flags, fh=None):
        if self._create_reference(path) is None:
            return 0
        handle = HandleObject.new_handle(fh)
        self._handle_table[handle] = FileObject(handle, path, flags, self._local_driver)
        return handle

    def opendir(self, path):
        if self._create_reference(path) is None:
            return 0
        handle = HandleObject.new_handle()
        self._handle_table[handle] = DirObject(handle, path, self._local_driver)
        return handle

    def read(self, path, size, offset, fh, buffer):
        file = self._get_file_obj(fh)
        if file is not None:
            return file.read(size, offset, buffer)
        raise FuseOSError(errno.EBADF)

    def readdir(self, path, fh):
        directory = self._get_file_obj(fh)
        if directory is not None:
            return ['.', '..'] + directory.readdir()
        raise FuseOSError(errno.EBADF)

    def release(self, path, fh):
        self._remove_file_obj(fh)
        self._release_reference(path)
        return 0

    def releasedir(self, path, fh):
        self._release_reference(path)
        return 0

    def rename(self, old, new):
        with tracer.start_as_current_span('WritableFuse.rename', self._span_context) as span:
            # can only change file name if there is no reference
            if not self._has_reference(old):
                if self._datastore is not None:
                    try:
                        self._engine_api.move_file(MoveFileMessageArguments(
                            destination_base_path=self._get_remote_stream_info(), new_relative_path=new,
                            old_relative_path=old, overwrite=False,
                            span_context=to_dprep_span_context(span.get_context())
                        ))
                    except Exception as e:
                        self.__class__._print_and_log_ex(e, 'rename', 'Rename')
                        raise FuseOSError(errno.EIO)
                return self._local_driver.rename(old, new)
            raise FuseOSError(errno.EBUSY)

    def rmdir(self, path):
        with tracer.start_as_current_span('WritableFuse.rmdir', self._span_context) as span:
            if self._has_reference(path):
                raise FuseOSError(errno.EBUSY)
            if self._datastore is not None:
                try:
                    self._engine_api.delete(DeleteMessageArguments(
                        destination_path=self._get_remote_stream_info(path),
                        span_context=to_dprep_span_context(span.get_context())
                    ))
                except Exception as e:
                    self.__class__._print_and_log_ex(e, 'rmdir', 'Remove folder')
                    raise FuseOSError(errno.EIO)
            return self._local_driver.rmdir(path)

    def truncate(self, path, length, fh=None):
        if not self._has_reference(path):
            return self._local_driver.truncate(path, length)

    def write(self, path, size, offset, fh, buffer):
        file = self._get_file_obj(fh)
        if file is not None:
            return file.write(size, offset, buffer)
        return errno.EBADF

    def unlink(self, path):
        with tracer.start_as_current_span('WritableFuse.unlink', self._span_context) as span:
            if self._has_reference(path):
                raise FuseOSError(errno.EBUSY)
            if self._datastore is not None:
                try:
                    self._engine_api.delete(DeleteMessageArguments(
                        destination_path=self._get_remote_stream_info(path),
                        span_context=to_dprep_span_context(span.get_context())
                    ))
                except Exception as e:
                    self.__class__._print_and_log_ex(e, 'unlink', 'Delete')
                    raise FuseOSError(errno.EIO)
            return self._local_driver.unlink(path)

    def destroy(self, path):
        if len(self._references.keys()) != 0:
            self._busy_event.wait()

    def chmod(self, path, mode):
        self._local_driver.chmod(path, mode)

    def chown(self, path, uid, gid):
        self._local_driver.chown(path, uid, gid)

    @staticmethod
    def _print_and_log_ex(ex, method, op):
        print('{} failed with exception:\n{}'.format(op, ex))
        log.info('{} - {} failed with exception type {}.'.format(method, op, type(ex).__name__))
