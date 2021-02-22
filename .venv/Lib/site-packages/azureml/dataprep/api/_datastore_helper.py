# Copyright (c) Microsoft Corporation. All rights reserved.
from .datasources import DataLakeDataSource
from ... import dataprep
from typing import TypeVar, List
import json

DEFAULT_SAS_DURATION = 30  # this aligns with our SAS generation in the UI BlobStorageManager.ts
Datastore = TypeVar('Datastore', 'AbstractDatastore', 'DataReference', 'DataPath')
Datastores = TypeVar('Datastores', Datastore, List[Datastore])


def datastore_to_dataflow(data_source: Datastores, query_timeout: int = -1) -> 'dataprep.Dataflow':
    from .dataflow import Dataflow
    from .engineapi.api import get_engine_api

    def construct_df(datastore_values):
        if type(datastore_values) is not list:
            datastore_values = [datastore_values]
        df = Dataflow(get_engine_api())
        return df.add_step('Microsoft.DPrep.GetDatastoreFilesBlock', {
                               'datastores': [datastore_value._to_pod() for datastore_value in datastore_values]
                           })

    if type(data_source) is list:
        datastore_values = []
        for source in data_source:
            datastore, datastore_value = get_datastore_value(source)
            if not _is_fs_datastore(datastore):
                raise NotSupportedDatastoreTypeError(datastore)
            datastore_values.append(datastore_value)
        return construct_df(datastore_values)

    datastore, datastore_value = get_datastore_value(data_source)
    if _is_fs_datastore(datastore):
        return construct_df(datastore_value)

    try:
        from azureml.data.azure_sql_database_datastore import AzureSqlDatabaseDatastore
        from azureml.data.azure_postgre_sql_datastore import AzurePostgreSqlDatastore
    except ImportError as e:
        raise _decorate_import_error(e)

    if isinstance(datastore, AzureSqlDatabaseDatastore) or isinstance(datastore, AzurePostgreSqlDatastore):
        if query_timeout == -1:
            query_timeout = 30 if isinstance(datastore, AzureSqlDatabaseDatastore) else 20
        df = Dataflow(get_engine_api())
        return df.add_step('Microsoft.DPrep.ReadDatastoreSqlBlock', {
                               'datastore': datastore_value._to_pod(),
                               'queryTimeout': query_timeout
                           })

    raise NotSupportedDatastoreTypeError(datastore)


def get_datastore_value(data_source: Datastore) -> ('AbstractDatastore', 'dataprep.api.dataflow.DatastoreValue'):
    from .dataflow import DatastoreValue
    try:
        from azureml.data.abstract_datastore import AbstractDatastore
        from azureml.data.data_reference import DataReference
        from azureml.data.datapath import DataPath
    except ImportError as e:
        raise _decorate_import_error(e)

    datastore = None
    path_on_storage = ''

    if isinstance(data_source, AbstractDatastore):
        datastore = data_source
    elif isinstance(data_source, DataReference):
        datastore = data_source.datastore
        path_on_storage = data_source.path_on_datastore or path_on_storage
    elif isinstance(data_source, DataPath):
        datastore = data_source._datastore
        path_on_storage = data_source.path_on_datastore or path_on_storage

    _ensure_supported(datastore)
    path_on_storage = path_on_storage.lstrip('/')

    workspace = datastore.workspace
    _set_auth_type(workspace)
    return (datastore, DatastoreValue(
        subscription=workspace.subscription_id,
        resource_group=workspace.resource_group,
        workspace_name=workspace.name,
        datastore_name=datastore.name,
        path=path_on_storage
    ))


def login():
    try:
        from azureml.core.authentication import InteractiveLoginAuthentication
    except ImportError as e:
        raise _decorate_import_error(e)

    auth = InteractiveLoginAuthentication()
    auth.get_authentication_header()


def _ensure_supported(datastore: 'AbstractDatastore'):
    try:
        from azureml.data.azure_sql_database_datastore import AzureSqlDatabaseDatastore
        from azureml.data.azure_postgre_sql_datastore import AzurePostgreSqlDatastore
    except ImportError as e:
        raise _decorate_import_error(e)

    if _is_fs_datastore(datastore) or isinstance(datastore, AzureSqlDatabaseDatastore) \
            or isinstance(datastore, AzurePostgreSqlDatastore):
        return
    raise NotSupportedDatastoreTypeError(datastore)


def _set_auth_type(workspace: 'Workspace'):
    from .engineapi.api import get_engine_api
    from .engineapi.typedefinitions import SetAmlAuthMessageArgument, AuthType
    try:
        from azureml.core.authentication import ServicePrincipalAuthentication
    except ImportError as e:
        raise _decorate_import_error(e)

    def try_update_auth(attr_getter, auth_dict, key):
        try:
            auth_dict[key] = attr_getter()
        except AttributeError:
            # this happens when the azureml-core SDK is old (prior to sovereign cloud changes)
            return

    auth = {}
    try_update_auth(lambda: workspace._auth._cloud_type.name, auth, 'cloudType')
    try_update_auth(lambda: workspace._auth._tenant_id, auth, 'tenantId')
    try_update_auth(lambda: type(workspace._auth).__name__, auth, 'authClass')
    if isinstance(workspace._auth, ServicePrincipalAuthentication):
        auth = {
            **auth,
            'servicePrincipalId': workspace._auth._service_principal_id,
            'password': workspace._auth._service_principal_password
        }
        get_engine_api().set_aml_auth(SetAmlAuthMessageArgument(AuthType.SERVICEPRINCIPAL, json.dumps(auth)))
    else:
        get_engine_api().set_aml_auth(SetAmlAuthMessageArgument(AuthType.DERIVED, json.dumps(auth)))


def _all(items, predicate):
    return len(list(filter(lambda ds: not predicate(ds), items))) == 0


def _is_datapath(data_path) -> bool:
    try:
        from azureml.data.data_reference import DataReference
        from azureml.data.abstract_datastore import AbstractDatastore
        from azureml.data.datapath import DataPath
    except ImportError as e:
        raise _decorate_import_error(e)

    return isinstance(data_path, DataReference) or \
            isinstance(data_path, AbstractDatastore) or \
            isinstance(data_path, DataPath)


def _is_datapaths(data_paths) -> bool:
    return type(data_paths) is list and _all(data_paths, _is_datapath)


def _is_fs_datastore(datastore: 'AbstractDatastore') -> bool:
    try:
        from azureml.data.azure_storage_datastore import AzureBlobDatastore
        from azureml.data.azure_storage_datastore import AzureFileDatastore
        from azureml.data.azure_data_lake_datastore import AzureDataLakeDatastore
        from azureml.data.azure_data_lake_datastore import AzureDataLakeGen2Datastore
    except ImportError as e:
        raise _decorate_import_error(e)

    return isinstance(datastore, AzureBlobDatastore) or \
            isinstance(datastore, AzureFileDatastore) or \
            isinstance(datastore, AzureDataLakeDatastore) or \
            isinstance(datastore, AzureDataLakeGen2Datastore)


def _to_stream_info_value(datastore: 'AbstractDatastore', path_in_datastore: str = '') -> dict:
    def to_value(value):
        return {'string': value}

    return {
        'streaminfo': {
            'handler': 'AmlDatastore',
            'resourceidentifier': path_in_datastore,
            'arguments': {
                'subscription': to_value(datastore.workspace.subscription_id),
                'resourceGroup': to_value(datastore.workspace.resource_group),
                'workspaceName': to_value(datastore.workspace.name),
                'datastoreName': to_value(datastore.name)
            }
        }
    }


def _serialize_datastore(datastore):
    return {
        'workspace': datastore.workspace.name,
        'subscription_id': datastore.workspace.subscription_id,
        'resource_group': datastore.workspace.resource_group,
        'datastore': datastore.name
    }


def _deserialize_datastore(datastore_dict):
    try:
        from azureml.core import Workspace, Run, Datastore as DatastoreClient
    except ImportError as e:
        raise _decorate_import_error(e)

    try:
        workspace = Run.get_context().experiment.workspace
    except AttributeError:
        workspace = Workspace.get(
            name=datastore_dict['workspace'], subscription_id=datastore_dict['subscription_id'],
            resource_group=datastore_dict['resource_group']
        )
    return DatastoreClient(workspace, datastore_dict['datastore'])


def _decorate_import_error(e: ImportError) -> ImportError:
    return ImportError('Unable to import Azure Machine Learning SDK. In order to use datastore, please make '\
                       + 'sure the Azure Machine Learning SDK is installed.\n{}'.format(e))


class NotSupportedDatastoreTypeError(Exception):
    def __init__(self, datastore: 'AbstractDatastore'):
        super().__init__('Datastore "{}"\'s type "{}" is not supported.'.format(datastore.name, datastore.datastore_type))
        self.datastore = datastore
