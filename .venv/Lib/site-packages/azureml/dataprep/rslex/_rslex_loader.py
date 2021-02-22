import ctypes
import os
import sys

if sys.platform == 'win32':
    lib_name = 'rslex_script.dll'
elif sys.platform == 'darwin':
    lib_name = 'librslex_script.dylib'
else:
    lib_name = 'librslex_script.so'

lib_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'lib', lib_name)
rslex = ctypes.cdll.LoadLibrary(lib_path)


class _ExecuteOutput(ctypes.Structure):
    _fields_ = [
        ('message', ctypes.c_void_p),
        ('batches', ctypes.c_void_p),
        ('schemas', ctypes.c_void_p),
        ('n_batches', ctypes.c_uint64)
    ]

class RsLexContext(ctypes.Structure):
    _fields_ = [
        ('message', ctypes.c_void_p),
        ('context_ptr', ctypes.c_void_p)
    ]

class _CreateDownloaderOutput(ctypes.Structure):
    _fields_ = [
        ('message', ctypes.c_void_p),
        ('downloader_ptr', ctypes.c_void_p),
        ('stream_accessor_ptr', ctypes.c_void_p),
        ('target_dir_ptr', ctypes.c_void_p)
    ]


class _DownloadOutput(ctypes.Structure):
    _fields_ = [
        ('has_error', ctypes.c_uint64),
        ('message', ctypes.c_void_p)
    ]


rslex.execute.argtypes = [ctypes.c_char_p, ctypes.c_bool, ctypes.c_bool, ctypes.c_bool, ctypes.c_bool, ctypes.c_void_p]
rslex.execute.restype = _ExecuteOutput
rslex.free_string.argtypes = [ctypes.c_void_p]
rslex.free_string.restype = None
rslex.free_arrays_buffer.argtypes = [ctypes.c_void_p]
rslex.free_arrays_buffer.restype = None
rslex.free_schemas_buffer.argtypes = [ctypes.c_void_p]
rslex.free_schemas_buffer.restype = None
rslex.create_downloader.argtypes = [ctypes.c_char_p, ctypes.c_void_p]
rslex.create_downloader.restype = _CreateDownloaderOutput
rslex.release_downloader.argtypes = [ctypes.c_void_p]
rslex.release_downloader.restype = None
rslex.download.argtypes = [ctypes.c_char_p, ctypes.c_void_p]
rslex.download.restype = _DownloadOutput

rslex.create_context.argtypes = [ctypes.c_uint64, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_bool, ctypes.c_char_p, ctypes.c_char_p]
rslex.create_context.restype = RsLexContext
rslex.release_context.argtypes = [ctypes.c_void_p]
rslex.release_context.restype = None


class Result:
    def __init__(self, message, batches):
        self.message = message
        self.batches = batches


def run_lariat(script: str,
               collect_results: bool,
               fail_on_error: bool,
               fail_on_mixed_types: bool,
               fail_on_out_of_range_datetime: bool,
               rslex_context: RsLexContext):
    result_ptr = rslex.execute(ctypes.c_char_p(script.encode('utf-8')),
                               ctypes.c_bool(collect_results),
                               ctypes.c_bool(fail_on_error),
                               ctypes.c_bool(fail_on_mixed_types),
                               ctypes.c_bool(fail_on_out_of_range_datetime),
                               rslex_context.context_ptr)
    result = ctypes.cast(result_ptr.message, ctypes.c_char_p).value
    rslex.free_string(result_ptr.message)

    n_batches = result_ptr.n_batches
    if n_batches > 0:
        batches = ctypes.cast(result_ptr.batches, ctypes.POINTER(ctypes.c_void_p))
        schemas = ctypes.cast(result_ptr.schemas, ctypes.POINTER(ctypes.c_void_p))

        def create_batch(batch_ptr, schema_ptr):
            import pyarrow as pa
            schema = pa.Schema._import_from_c(schema_ptr)
            batch = pa.RecordBatch._import_from_c(batch_ptr, schema)
            return batch

        batches = [create_batch(batches[i], schemas[i]) for i in range(0, n_batches)]
        rslex.free_arrays_buffer(result_ptr.batches, n_batches)
        rslex.free_schemas_buffer(result_ptr.schemas, n_batches)
    elif collect_results:
        batches = []
    else:
        batches = None

    return Result(result.decode('utf-8'), batches)


def create_rslex_context(engine_server_port: int,
                         engine_server_secret: str,
                         log_folder: str,
                         instrumentation_key: str,
                         verbosity: str,
                         hbi_mode: bool,
                         session_id: str,
                         caller_session_id: str,
                         run_info: str) -> RsLexContext:
    result = rslex.create_context(ctypes.c_uint64(engine_server_port),
                                  _str_to_c_char(engine_server_secret),
                                  _str_to_c_char(log_folder),
                                  _str_to_c_char(instrumentation_key),
                                  _str_to_c_char(verbosity),
                                  ctypes.c_bool(hbi_mode),
                                  _str_to_c_char(session_id),
                                  _str_to_c_char(caller_session_id),
                                  _str_to_c_char(run_info))
    message = ctypes.cast(result.message, ctypes.c_char_p).value.decode('utf-8')
    rslex.free_string(result.message)
    if len(message) != 0:
        raise Exception(message)
    return result

def _str_to_c_char(value: str) -> ctypes.c_char_p:
    return ctypes.c_char_p((value if value else '').encode('utf-8'))

def release_rslex_context(context: RsLexContext) -> None:
    if not isinstance(context, RsLexContext):
        raise ValueError("release_rslex_context only accepts RsLexContext object")
    rslex.release_context(context.context_ptr)


def create_downloader(target_path: str, rslex_context: RsLexContext) -> _CreateDownloaderOutput:
    result = rslex.create_downloader(_str_to_c_char(target_path), rslex_context.context_ptr)
    message = ctypes.cast(result.message, ctypes.c_char_p).value.decode('utf-8')
    rslex.free_string(result.message)
    if len(message) != 0:
        raise Exception(message)
    return result


def release_downloader(downloader: _CreateDownloaderOutput) -> None:
    rslex.release_downloader(downloader.downloader_ptr, downloader.target_dir_ptr)


def download(stream_info_dto_json: str,
             downloader: _CreateDownloaderOutput) -> str:
    result_ptr = rslex.download(_str_to_c_char(stream_info_dto_json),
                                downloader.downloader_ptr)
    message = ctypes.cast(result_ptr.message, ctypes.c_char_p).value.decode('utf-8')
    rslex.free_string(result_ptr.message)
    if result_ptr.has_error > 0:
        raise Exception('Download failed:\n{}'.format(message))
    return message  # message is downloaded path when there is no error
