from ._pandas_helper import (have_pandas, have_pyarrow, ensure_df_native_compat, PandasImportError,
                             pyarrow_and_pandas_compatible, pyarrow_supports_cdata)
from .engineapi.api import get_engine_api
from .engineapi.engine import CancellationToken
from .engineapi.typedefinitions import ExecuteAnonymousActivityMessageArguments, AnonymousActivityData
from .errorhandlers import OperationCanceled
from .step import steps_to_block_datas
from ._rslex_executor import get_rslex_executor
import io
import json
import math
import warnings
from shutil import rmtree
from threading import Event, Thread
from typing import List
from uuid import uuid4
from ._loggerfactory import _LoggerFactory, trace

logger = _LoggerFactory.get_logger("DataframeReader")
tracer = trace.get_tracer(__name__)


# 20,000 rows gives a good balance between memory requirement and throughput by requiring that only
# (20000 * CPU_CORES) rows are materialized at once while giving each core a sufficient amount of
# work.
PARTITION_SIZE = 20000


class _InconsistentSchemaError(Exception):
    def __init__(self, reason: str):
        super().__init__('Inconsistent or mixed schemas detected across partitions: ' + reason)


# noinspection PyPackageRequirements
class _PartitionIterator:
    def __init__(self, partition_id, table):
        self.id = partition_id
        self.is_canceled = False
        self._completion_event = Event()
        self._current_idx = 0
        import pandas as pd
        self._dataframe = table.to_pandas() if not isinstance(table, pd.DataFrame) else table

    def __next__(self):
        if self._current_idx == len(self._dataframe):
            self._completion_event.set()
            raise StopIteration

        value = self._dataframe.iloc[self._current_idx]
        self._current_idx = self._current_idx + 1
        return value

    def wait_for_completion(self):
        self._completion_event.wait()

    def cancel(self):
        self.is_canceled = True
        self._completion_event.set()


# noinspection PyProtectedMember
class RecordIterator:
    def __init__(self, dataflow: 'azureml.dataprep.Dataflow', cancellation_token: CancellationToken):
        self._iterator_id = str(uuid4())
        self._partition_available_event = Event()
        self._partitions = {}
        self._current_partition = None
        self._next_partition = 0
        self._done = False
        self._cancellation_token = cancellation_token
        get_dataframe_reader().register_iterator(self._iterator_id, self)
        _LoggerFactory.trace(logger, "RecordIterator_created", { 'iterator_id': self._iterator_id })

        def start_iteration():
            dataflow_to_execute = dataflow.add_step('Microsoft.DPrep.WriteFeatherToSocketBlock', {
                'dataframeId': self._iterator_id,
            })

            try:
                get_engine_api().execute_anonymous_activity(
                    ExecuteAnonymousActivityMessageArguments(anonymous_activity=AnonymousActivityData(
                        blocks=steps_to_block_datas(dataflow_to_execute._steps))),
                    cancellation_token=self._cancellation_token)
            except OperationCanceled:
                pass
            self._clean_up()

        iteration_thread = Thread(target=start_iteration, daemon=True)
        iteration_thread.start()

        cancellation_token.register(self.cancel_iteration)

    def __next__(self):
        while True:
            if self._done and self._current_partition is None and len(self._partitions) == 0:
                raise StopIteration()

            if self._current_partition is None:
                if self._next_partition not in self._partitions:
                    self._partition_available_event.wait()
                    self._partition_available_event.clear()
                    continue
                else:
                    self._current_partition = self._partitions[self._next_partition]
                    self._next_partition = self._next_partition + 1

            if self._current_partition is not None:
                try:
                    return next(self._current_partition)
                except StopIteration:
                    self._partitions.pop(self._current_partition.id)
                    self._current_partition = None

    def cancel_iteration(self):
        for partition in self._partitions.values():
            partition.cancel()
        self._clean_up()

    def process_partition(self, partition: int, table: 'pyarrow.Table'):
        if self._cancellation_token.is_canceled:
            raise RuntimeError('IteratorClosed')

        partition_iter = _PartitionIterator(partition, table)
        self._partitions[partition] = partition_iter
        self._partition_available_event.set()
        partition_iter.wait_for_completion()
        if partition_iter.is_canceled:
            raise RuntimeError('IteratorClosed')

    def _clean_up(self):
        _LoggerFactory.trace(logger, "RecordIterator_cleanup", {'iterator_id': self._iterator_id})
        get_dataframe_reader().complete_iterator(self._iterator_id)
        self._done = True
        self._partition_available_event.set()


class RecordIterable:
    def __init__(self, dataflow):
        self._dataflow = dataflow
        self._cancellation_token = CancellationToken()

    def __iter__(self) -> RecordIterator:
        return RecordIterator(self._dataflow, self._cancellation_token)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        self._cancellation_token.cancel()


# noinspection PyProtectedMember,PyPackageRequirements
class _DataFrameReader:
    def __init__(self):
        self._outgoing_dataframes = {}
        self._incoming_dataframes = {}
        self._iterators = {}
        _LoggerFactory.trace(logger, "DataframeReader_create")

    def to_pandas_dataframe(self,
                            dataflow: 'azureml.dataprep.Dataflow',
                            extended_types: bool = False,
                            nulls_as_nan: bool = True,
                            on_error: str = 'null',
                            out_of_range_datetime: str = 'null',
                            span_context: 'DPrepSpanContext' = None) -> 'pandas.DataFrame':
        def to_pandas_preppy():
            if not extended_types:
                if not pyarrow_and_pandas_compatible():
                    warnings.warn('Your pandas and pyarrow versions are incompatible. '
                                  'Please install pyarrow>=0.16.0 for improved performance of to_pandas_dataframe. '
                                  'You can ensure the correct version is installed by running: pip install '
                                  'pyarrow>=0.16.0 --upgrade')
                else:
                    warnings.warn('Please install pyarrow>=0.16.0 for improved performance of to_pandas_dataframe. '
                                  'You can ensure the correct version is installed by running: pip install '
                                  'pyarrow>=0.12.0 --upgrade')

            import tempfile
            from azureml.dataprep.native import preppy_to_ndarrays
            from collections import OrderedDict
            from pathlib import Path
            from .dataflow import Dataflow

            random_id = uuid4()
            intermediate_path = Path(os.path.join(tempfile.gettempdir(), str(random_id)))
            try:
                dataflow_to_execute = dataflow.add_step('Microsoft.DPrep.WritePreppyBlock', {
                    'outputPath': {
                        'target': 0,
                        'resourceDetails': [{'path': str(intermediate_path)}]
                    },
                    'profilingFields': ['Kinds', 'MissingAndEmpty']
                })

                dataflow._raise_if_missing_secrets()
                activity_data = Dataflow._dataflow_to_anonymous_activity_data(dataflow_to_execute)
                dataflow._engine_api.execute_anonymous_activity(
                    ExecuteAnonymousActivityMessageArguments(
                        anonymous_activity=activity_data,
                        span_context=span_context
                    )
                )

                intermediate_files = [str(p) for p in intermediate_path.glob('part-*')]
                intermediate_files.sort()
                dataset = preppy_to_ndarrays(intermediate_files, extended_types, nulls_as_nan)
                df = pandas.DataFrame.from_dict(OrderedDict(dataset))
                return df
            finally:
                rmtree(intermediate_path, ignore_errors=True)

        def to_pandas_feather():
            random_id = str(uuid4())
            self.register_incoming_dataframe(random_id)
            dataflow_to_execute = dataflow.add_step('Microsoft.DPrep.WriteFeatherToSocketBlock', {
                'dataframeId': random_id,
                'errorStrategy': dataflow._on_error_to_enum_value(on_error),
                'dateTimeSettings': dataflow._out_of_range_datetime_to_block_value(out_of_range_datetime)
            })

            dataflow._raise_if_missing_secrets()
            activity_data = dataflow_to_execute._dataflow_to_anonymous_activity_data(dataflow_to_execute)
            dataflow._engine_api.execute_anonymous_activity(
                ExecuteAnonymousActivityMessageArguments(anonymous_activity=activity_data, span_context=span_context))

            try:
                return self.complete_incoming_dataframe(random_id)
            except _InconsistentSchemaError as e:
                reason = e.args[0]
                warnings.warn('Using alternate reader. ' + reason)
                return to_pandas_preppy()

        def to_pandas_arrow():
            executor = get_rslex_executor()
            record_batches = None

            def callback(batches):
                nonlocal record_batches
                record_batches = batches

            executor.await_result(callback,
                                  fail_on_error=on_error != 'null',
                                  fail_on_mixed_types=on_error != 'null',
                                  fail_on_out_of_range_datetime=out_of_range_datetime != 'null')
            random_id = str(uuid4())
            dataflow._raise_if_missing_secrets()
            activity_data = dataflow._dataflow_to_anonymous_activity_data(dataflow)
            dataflow._engine_api.execute_anonymous_activity(
                ExecuteAnonymousActivityMessageArguments(anonymous_activity=activity_data, span_context=span_context))

            if record_batches is None:
                raise RuntimeError()

            incoming_dfs = {}
            import pyarrow
            self._incoming_dataframes[random_id] = incoming_dfs
            for i in range(0, len(record_batches)):
                incoming_dfs[i] = pyarrow.Table.from_batches([record_batches[i]])

            return self.complete_incoming_dataframe(random_id)

        if not have_pandas():
            raise PandasImportError()
        else:
            import pandas

        import os
        if '_TEST_USE_CLEX' in os.environ and os.environ['_TEST_USE_CLEX'] == 'False':
            return to_pandas_arrow()
        elif '_TEST_USE_CLEX' in os.environ and os.environ['_TEST_USE_CLEX'] == 'True':
            if not have_pyarrow() or not pyarrow_and_pandas_compatible() or extended_types:
                return to_pandas_preppy()
        else:
            if have_pyarrow() and pyarrow_and_pandas_compatible() and pyarrow_supports_cdata():
                try:
                    return to_pandas_arrow()
                except Exception:
                    pass
            if not have_pyarrow() or not pyarrow_and_pandas_compatible() or extended_types:
                return to_pandas_preppy()

        return to_pandas_feather()

    def register_outgoing_dataframe(self, dataframe: 'pandas.DataFrame', dataframe_id: str):
        _LoggerFactory.trace(logger, "register_outgoing_dataframes", {'dataframe_id': dataframe_id})
        self._outgoing_dataframes[dataframe_id] = dataframe

    def unregister_outgoing_dataframe(self, dataframe_id: str):
        self._outgoing_dataframes.pop(dataframe_id)

    def _get_partitions(self, dataframe_id: str) -> int:
        dataframe = self._outgoing_dataframes[dataframe_id]
        partition_count = math.ceil(len(dataframe) / PARTITION_SIZE)
        return partition_count

    def _get_data(self, dataframe_id: str, partition: int) -> bytes:
        from azureml.dataprep import native
        dataframe = self._outgoing_dataframes[dataframe_id]
        start = partition * PARTITION_SIZE
        end = min(len(dataframe), start + PARTITION_SIZE)
        dataframe = dataframe.iloc[start:end]

        (new_schema, new_values) = ensure_df_native_compat(dataframe)

        return native.preppy_from_ndarrays(new_values, new_schema)

    def register_incoming_dataframe(self, dataframe_id: str):
        _LoggerFactory.trace(logger, "register_incoming_dataframes", {'dataframe_id': dataframe_id})
        self._incoming_dataframes[dataframe_id] = {}

    def complete_incoming_dataframe(self, dataframe_id: str) -> 'pandas.DataFrame':
        import pyarrow
        import pandas as pd
        partitions_dfs = self._incoming_dataframes[dataframe_id]
        if any(isinstance(partitions_dfs[key], pd.DataFrame) for key in partitions_dfs):
            raise _InconsistentSchemaError('A partition has no columns.')

        partitions_dfs = \
            [partitions_dfs[key] for key in sorted(partitions_dfs.keys()) if partitions_dfs[key].num_rows > 0]
        _LoggerFactory.trace(logger, "complete_incoming_dataframes", {'dataframe_id': dataframe_id})
        self._incoming_dataframes.pop(dataframe_id)

        if len(partitions_dfs) == 0:
            return pd.DataFrame({})

        def get_column_names(partition: pyarrow.Table) -> List[str]:
            return partition.schema.names

        def verify_column_names():
            def make_schema_error(prefix, p1_cols, p2_cols):
                return _InconsistentSchemaError(
                    '{0} The first partition has {1} columns. Found partition has {2} columns.\n'.format(prefix,
                                                                                                         len(p1_cols),
                                                                                                         len(p2_cols)) +
                    'First partition columns (ordered): {0}\n'.format(p1_cols) +
                    'Found Partition has columns (ordered): {0}'.format(p2_cols))
            expected_names = get_column_names(partitions_dfs[0])
            expected_count = partitions_dfs[0].num_columns
            for partition in partitions_dfs:
                found_names = get_column_names(partition)
                if partition.num_columns != expected_count:
                    raise make_schema_error('partition had different number of columns.', expected_names, found_names)
                for (a, b) in zip(expected_names, found_names):
                    if a != b:
                        raise make_schema_error('partition column had different name than expected.',
                                                expected_names,
                                                found_names)

        def determine_column_type(index: int) -> pyarrow.DataType:
            for partition in partitions_dfs:
                column = partition.column(index)
                if column.type != pyarrow.bool_() or column.null_count != column.length():
                    return column.type
            return pyarrow.bool_()

        def apply_column_types(fields: List[pyarrow.Field]):
            for i in range(0, len(partitions_dfs)):
                partition = partitions_dfs[i]
                column_types = partition.schema.types
                for j in range(0, len(fields)):
                    column_type = column_types[j]
                    if column_type != fields[j].type:
                        if column_type == pyarrow.bool_():
                            column = partition.column(j)
                            import numpy as np

                            def gen_n_of_x(n, x):
                                k = 0
                                while k < n:
                                    yield x
                                    k = k + 1
                            if isinstance(column, pyarrow.ChunkedArray):
                                typed_chunks = []
                                for chunk in column.chunks:
                                    typed_chunks.append(
                                        pyarrow.array(gen_n_of_x(chunk.null_count, None),
                                                      fields[j].type,
                                                      mask=np.full(chunk.null_count, True)))

                                partition = partition.remove_column(j)
                                partition = partition.add_column(j, fields[j], pyarrow.chunked_array(typed_chunks))
                            else:
                                new_col = pyarrow.column(
                                    fields[j],
                                    pyarrow.array(gen_n_of_x(column.null_count, None),
                                                  fields[j].type,
                                                  mask=np.full(column.null_count, True)))
                                partition = partition.remove_column(j)
                                partition = partition.add_column(j, new_col)
                            partitions_dfs[i] = partition
                        else:
                            raise _InconsistentSchemaError(
                                'A partition has a column with a different type than expected.\nThe type of column '
                                '\'{0}\' in the first partition is {1}. Found a partition where its type is {2}.'
                                .format(partition.schema.names[j], str(fields[j].type), str(column_type)))

        with tracer.start_as_current_span('_DataFrameReader.complete_incoming_dataframe', trace.get_current_span()):
            verify_column_names()
            first_partition = partitions_dfs[0]
            column_fields = []
            names = first_partition.schema.names
            for i in range(0, first_partition.num_columns):
                f = pyarrow.field(names[i], determine_column_type(i))
                column_fields.append(f)
            apply_column_types(column_fields)

            import pyarrow
            df = pyarrow.concat_tables(partitions_dfs).to_pandas(use_threads=True)
            return df

    def register_iterator(self, iterator_id: str, iterator: RecordIterator):
        _LoggerFactory.trace(logger, "register_iterator", {'iterator_id': iterator_id})
        self._iterators[iterator_id] = iterator

    def complete_iterator(self, iterator_id: str):
        _LoggerFactory.trace(logger, "complete_iterator", {'iterator_id': iterator_id})
        if iterator_id in self._iterators:
            self._iterators.pop(iterator_id)

    def _read_incoming_partition(self, dataframe_id: str, partition: int, partition_bytes: bytes, is_from_file: bool):
        if not have_pyarrow():
            raise ImportError('PyArrow is not installed.')
        else:
            from pyarrow import feather, ArrowInvalid
        _LoggerFactory.trace(logger, "read_incoming_partition", {'dataframe_id': dataframe_id, 'partition': partition})

        if is_from_file:
            import os
            name = partition_bytes.decode('utf-8')
            try:
                table = feather.read_table(name)
            except ArrowInvalid as e:
                size = os.path.getsize(name)
                if size != 8:
                    raise e

                with open(name, 'rb') as file:
                    count_bytes = file.read(8)
                    row_count = int.from_bytes(count_bytes, 'little')
                    import pandas as pd
                    table = pd.DataFrame(index=pd.RangeIndex(row_count))
            finally:
                # noinspection PyBroadException
                try:
                    os.remove(name)
                except:
                    pass
        else:
            # Data is transferred as either Feather or just a count of rows when the partition consisted of records with
            # no columns. Feather streams are always larger than 8 bytes, so we can detect that we are dealing with only
            # a row count by checking if we received exactly 8 bytes.
            if len(partition_bytes) == 8:  # No Columns partition.
                row_count = int.from_bytes(partition_bytes, 'little')
                import pandas as pd
                table = pd.DataFrame(index=pd.RangeIndex(row_count))
            else:
                table = feather.read_table(io.BytesIO(partition_bytes))

        if dataframe_id in self._incoming_dataframes:
            partitions_dfs = self._incoming_dataframes[dataframe_id]
            partitions_dfs[partition] = table
        elif dataframe_id in self._iterators:
            self._iterators[dataframe_id].process_partition(partition, table)
        else:
            _LoggerFactory.trace(logger,
                                 "dataframe_id_not_found",
                                 {
                                     'dataframe_id': dataframe_id,
                                     'current_dataframe_ids': str([key in self._incoming_dataframes.keys()])
                                 })
            raise ValueError('Invalid dataframe_id')

    def _cancel(self, dataframe_id: str):
        if dataframe_id in self._iterators:
            self._iterators[dataframe_id].cancel_iteration()
        elif dataframe_id in self._incoming_dataframes:
            self._incoming_dataframes[dataframe_id] = {}


_dataframe_reader = None


def get_dataframe_reader():
    global _dataframe_reader
    if _dataframe_reader is None:
        _dataframe_reader = _DataFrameReader()

    return _dataframe_reader


def ensure_dataframe_reader_handlers(requests_channel):
    requests_channel.register_handler('get_dataframe_partitions', process_get_partitions)
    requests_channel.register_handler('get_dataframe_partition_data', process_get_data)
    requests_channel.register_handler('send_dataframe_partition', process_send_partition)


def process_get_partitions(request, writer, socket):
    dataframe_id = request.get('dataframe_id')
    try:
        partition_count = get_dataframe_reader()._get_partitions(dataframe_id)
        writer.write(json.dumps({'result': 'success', 'partitions': partition_count}))
    except Exception as e:
        writer.write(json.dumps({'result': 'error', 'error': repr(e)}))


def process_get_data(request, writer, socket):
    dataframe_id = request.get('dataframe_id')
    partition = request.get('partition')
    try:
        partition_bytes = get_dataframe_reader()._get_data(dataframe_id, partition)
        byte_count = len(partition_bytes)
        byte_count_bytes = byte_count.to_bytes(4, 'little')
        socket.send(byte_count_bytes)
        socket.send(partition_bytes)
    except Exception as e:
        writer.write(json.dumps({'result': 'error', 'error': repr(e)}))


def process_send_partition(request, writer, socket):
    dataframe_id = request.get('dataframe_id')
    partition = request.get('partition')
    is_from_file = request.get('is_from_file')
    try:
        writer.write(json.dumps({'result': 'success'}) + '\n')
        writer.flush()
        byte_count = int.from_bytes(socket.recv(8), 'little')
        with socket.makefile('rb') as input:
            partition_bytes = input.read(byte_count)
            get_dataframe_reader()._read_incoming_partition(dataframe_id, partition, partition_bytes, is_from_file)
            writer.write(json.dumps({'result': 'success'}) + '\n')
    except ImportError:
        get_dataframe_reader()._cancel(dataframe_id)
        writer.write(json.dumps({'result': 'error', 'error': 'PyArrowMissing'}))
    except Exception as e:
        get_dataframe_reader()._cancel(dataframe_id)
        writer.write(json.dumps({'result': 'error', 'error': repr(e)}))
