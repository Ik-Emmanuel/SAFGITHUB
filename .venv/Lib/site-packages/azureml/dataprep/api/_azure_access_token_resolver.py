import json
import os
from enum import Enum

from azureml.dataprep.api._loggerfactory import _LoggerFactory

from ._constants import AZURE_CLIENT_ID, IDENTITY_CLIENT_ID_ENV_NAME


_logger = None

def _get_logger():
    global _logger
    _logger = _logger or _LoggerFactory.get_logger("dprep._azure_access_token_resolver")
    return _logger


def _print_and_log(message, is_error=False):
    print(message)
    if is_error:
        _get_logger().error(message)
    else:
        _get_logger().info(message)


class _IdentityType(Enum):
    MANAGED = 0
    SP = 1
    USER = 2


def _get_identity_type(sp):
    if sp is not None:
        return _IdentityType.SP  # Service Principal is in context ==> use SP identity

    try:
        from azureml.core.run import Run
        from azureml.exceptions import RunEnvironmentException
    except ModuleNotFoundError:
        return _IdentityType.USER  # There is no AzureML SDK presenting ==> Not in AzureML run context ==> use USER identity

    try:
        Run.get_context(allow_offline=False)
        return _IdentityType.MANAGED  # In AzureML run context ==> use MANAGED identity
    except RunEnvironmentException:
        pass
    except Exception as e:
        _print_and_log('Cannot determine which identity to use for data access due to exception {}. Fall back to use interactive login.'.format(e.__class__.__name__), is_error=True)

    return _IdentityType.USER  # Not in AzureML run context ==> use USER identity


def _resolve_azure_access_token(request, writer, socket):
    """
    data access identity resolution:
    - if Workspace is signed in with a SP, then use SP identity for data access
    - else if in submitted run:
        - if env var "DEFAULT_IDENTITY_CLIENT_ID" is there (contract with AmlCompute), use UAI (User Assigned Identity)
        - else use SAI (System Assigned Identity)
    - else use user identity: browser login if possible otherwise device code login
    """
    try:
        logger = _get_logger()
        scope = request.get('scope')
        sp = request.get('sp')
        identity_type = _get_identity_type(sp)
        logger.info('Resolving access token for scope "{}" using identity of type "{}".'.format(scope, identity_type.name))

        credential = None
        if identity_type == _IdentityType.MANAGED:
            from azure.identity import ManagedIdentityCredential
            # AML Compute will set IDENTITY_CLIENT_ID_ENV_NAME as environment variable to indicate which UAI to use.
            # When it is not set, SAI should be used
            client_id = os.environ.get(IDENTITY_CLIENT_ID_ENV_NAME, None)
            _print_and_log('Getting data access token with {}.'.format('User Assigned Identity (client_id={})'.format(client_id) if client_id else 'System Assigned Identity'))
            credential = ManagedIdentityCredential(client_id=client_id)
        elif identity_type == _IdentityType.SP:
            from azure.identity import ClientSecretCredential
            sp_cred = json.loads(sp)
            sp_id = sp_cred['servicePrincipalId']
            _print_and_log('Getting data access token with Service Principal (id={}).'.format(sp_id))
            credential = ClientSecretCredential(sp_cred['tenantId'], sp_id, sp_cred['password'])
        elif identity_type == _IdentityType.USER:
            from azure.identity import ChainedTokenCredential, InteractiveBrowserCredential, DeviceCodeCredential
            _print_and_log('Credentials are not provided to access data from the source. Please sign in using identity with required permission granted.')
            credential = ChainedTokenCredential(InteractiveBrowserCredential(), DeviceCodeCredential(AZURE_CLIENT_ID))
        else:
            logger.error('Unknown identity type "{}"'.format(identity_type.name))
            raise ValueError('Unknown identity type "{}"'.format(identity_type.name))

        access_token = credential.get_token(scope)
        logger.info('Succeeded to resolve access token for scope "{}" using identity of type "{}".'.format(scope, identity_type.name))

        writer.write(json.dumps({
            'result': 'success',
            'token': access_token.token,
            'seconds': access_token.expires_on
        }))
    except Exception as e:
        print('Failed to get data access token for scope "{}" due to exception:\n{}.'.format(scope, e))
        logger.error('Failed to get data access token for scope "{}" using identity of type "{}" due to exception {}.'.format(scope, identity_type.name, e.__class__.__name__))
        writer.write(json.dumps({'result': 'error', 'error': str(e)}))


def register_access_token_resolver(requests_channel):
    requests_channel.register_handler('resolve_azure_access_token', _resolve_azure_access_token)
