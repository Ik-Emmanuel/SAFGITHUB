import json
import os

from azureml.dataprep.api._loggerfactory import _LoggerFactory

from ._aml_helper import get_workspace_from_run, verify_workspace


logger = None

def get_logger():
    global logger
    if logger is not None:
        return logger

    logger = _LoggerFactory.get_logger("dprep._aml_auth_resolver")
    return logger


def _resolve_auth_from_workspace(request, writer, socket):
    try:
        from azureml.core import Workspace
        from azureml.data.datastore_client import _DatastoreClient
        from azureml._base_sdk_common.service_discovery import get_service_url
        from azureml.exceptions import RunEnvironmentException

        auth_type = request.get('auth_type')
        ws_name = request.get('ws_name')
        subscription = request.get('subscription')
        resource_group = request.get('resource_group')
        extra_args = json.loads(request.get('extra_args') or '{}')

        if not ws_name or not subscription or not resource_group:
            writer.write(json.dumps({'result': 'error', 'error': 'InvalidWorkspace'}))
            return

        try:
            ws = get_workspace_from_run()
        except RunEnvironmentException as e:
            writer.write(json.dumps({
                'result': 'error',
                'error': 'Exception trying to get workspace information from the run. Error: {}'.format(e.message)
            }))
            return
        if not ws:
            try:
                auth = _get_auth(extra_args, auth_type)
            except Exception as e:
                writer.write(json.dumps({'result': 'error', 'error': str(e)}))
                return

            ws = Workspace.get(ws_name, auth=auth, subscription_id=subscription, resource_group=resource_group)

        verify_workspace(ws, subscription, resource_group, ws_name)

        try:
            host = os.environ.get('AZUREML_SERVICE_ENDPOINT') or \
                   get_service_url(ws._auth, ws.service_context._get_workspace_scope(), ws._workspace_id,
                                   ws.discovery_url)
        except AttributeError:
            # This check is for backward compatibility, handling cases where azureml-core package is pre-Feb2020,
            # as ws.discovery_url was added in this PR:
            # https://msdata.visualstudio.com/Vienna/_git/AzureMlCli/pullrequest/310794
            host = get_service_url(ws._auth, ws.service_context._get_workspace_scope(), ws._workspace_id)

        writer.write(json.dumps({
            'result': 'success',
            'auth': json.dumps(ws._auth.get_authentication_header()),
            'host': host
        }))
    except Exception as e:
        writer.write(json.dumps({'result': 'error', 'error': str(e)}))


def register_datastore_resolver(requests_channel):
    requests_channel.register_handler('resolve_auth_from_workspace', _resolve_auth_from_workspace)


def _get_auth(creds, auth_type):
    from azureml.core.authentication import InteractiveLoginAuthentication, AzureCliAuthentication, \
        ServicePrincipalAuthentication
    from azureml.core import VERSION
    import azureml.dataprep as dprep

    def log_version_issues(exception):
        log.warning(
            "Failed to construct auth object. Exception : {}, AML Version: {}, DataPrep Version: {}".format(
                type(exception).__name__, VERSION, dprep.__version__
            )
        )

    log = get_logger()
    cloud = creds.get('cloudType')
    tenant_id = creds.get('tenantId')
    auth_class = creds.get('authClass')

    if auth_type == 'SP':
        if not creds or not tenant_id:
            raise ValueError("InvalidServicePrincipalCreds")
        try:
            return ServicePrincipalAuthentication(tenant_id, creds['servicePrincipalId'],
                                                  creds['password'], cloud=creds['cloudType'])
        except Exception as e:
            log_version_issues(e)
            return ServicePrincipalAuthentication(tenant_id, creds['servicePrincipalId'], creds['password'])

    if auth_class == AzureCliAuthentication.__name__:
        try:
            return AzureCliAuthentication(cloud=cloud)
        except Exception as e:
            log_version_issues(e)
            return AzureCliAuthentication()

    if auth_class != InteractiveLoginAuthentication.__name__:
        log.warning("Unrecognized authentication type: {}".format(auth_class))

    # fallback to interactive authentication which has internal authentication fallback
    try:
        return InteractiveLoginAuthentication(tenant_id=tenant_id, cloud=cloud)
    except Exception as e:
        log_version_issues(e)
        return InteractiveLoginAuthentication()
