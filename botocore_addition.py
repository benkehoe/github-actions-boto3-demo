import os
import json

import requests
import jwt
import boto3

from botocore.credentials import (
    CredentialProvider,
    DeferredRefreshableCredentials,
    AssumeRoleWithWebIdentityCredentialFetcher,
)
from botocore.exceptions import InvalidConfigError
from botocore.utils import FileWebIdentityTokenLoader
import botocore.session, botocore.credentials

def get_session(profile_name=None, disable_env_vars=False):
    botocore_session = botocore.session.Session(profile=profile_name)

    provider = AssumeRoleWithWebIdentityProvider(
        load_config=lambda: botocore_session.full_config,
        client_creator=botocore_session.create_client,
        profile_name=profile_name or "default",
        disable_env_vars=disable_env_vars,
    )
    botocore_session.register_component(
        "credential_provider",
        botocore.credentials.CredentialResolver([provider])
    )

    session = boto3.Session(botocore_session=botocore_session)

    return session

class BearerAuth(requests.auth.AuthBase):
    def __init__(self, token):
        self.token = token
    def __call__(self, r):
        r.headers["authorization"] = "Bearer " + self.token
        return r

class GitHubWebIdentityTokenLoader(object):
    KNOWN_SERVER_CONFIGS = {
        "GitHub": ("ACTIONS_ID_TOKEN_REQUEST_URL", "ACTIONS_ID_TOKEN_REQUEST_TOKEN"),
    }
    DEFAULT_AUDIENCE = None

    EXAMPLE_JWT = None

    def __init__(self, web_identity_token_server, http_get=None):
        self._web_identity_token_server = web_identity_token_server
        if not http_get:
            http_get = requests.get
        self._http_get = http_get

    def _get_config(self):
        parts = self._web_identity_token_server.split(",", 2)
        audience = self.DEFAULT_AUDIENCE
        if len(parts) == 3:
            url_env_var_name, token_env_var_name, audience = parts
        else:
            if parts[0] in self.KNOWN_SERVER_CONFIGS:
                url_env_var_name, token_env_var_name = self.KNOWN_SERVER_CONFIGS[parts[0]]
                if len(parts) == 2:
                    audience = parts[1]
            elif len(parts) == 1:
                raise InvalidConfigError("Unknown server config name {}".format(parts[0]))
            else:
                url_env_var_name, token_env_var_name = parts
        return url_env_var_name, token_env_var_name, audience

    def __call__(self):
        url_env_var_name, token_env_var_name, audience = self._get_config()

        url = os.environ[url_env_var_name]

        params = {}
        if audience:
            params["audience"] = audience

        request_token = os.environ[token_env_var_name]
        auth = BearerAuth(request_token)

        # print(url, params, request_token)
        response = self._http_get(url, params=params, auth=auth)
        # print(response.status_code, response.url, response.text)
        response.raise_for_status()
        token = response.json()["value"]
        # print(jwt.get_unverified_header(token))
        if not self.EXAMPLE_JWT:
            self.__class__.EXAMPLE_JWT = token
        return token

class AssumeRoleWithWebIdentityProvider(CredentialProvider):
    METHOD = 'assume-role-with-web-identity'
    CANONICAL_NAME = None
    _CONFIG_TO_ENV_VAR = {
        'web_identity_token_server': 'AWS_WEB_IDENTITY_TOKEN_SERVER',
        'role_session_name': 'AWS_ROLE_SESSION_NAME',
        'role_arn': 'AWS_ROLE_ARN',
    }

    def __init__(
            self,
            load_config,
            client_creator,
            profile_name,
            cache=None,
            disable_env_vars=False,
            token_loader_cls=None,
    ):
        self.cache = cache
        self._load_config = load_config
        self._client_creator = client_creator
        self._profile_name = profile_name
        self._profile_config = None
        self._disable_env_vars = disable_env_vars
        if token_loader_cls is None:
            token_loader_cls = GitHubWebIdentityTokenLoader
        self._token_loader_cls = token_loader_cls

    def load(self):
        # print("load() called")
        return self._assume_role_with_web_identity()

    def _get_profile_config(self, key):
        if self._profile_config is None:
            loaded_config = self._load_config()
            profiles = loaded_config.get('profiles', {})
            # print("profiles", profiles)
            self._profile_config = profiles.get(self._profile_name, {})
        return self._profile_config.get(key)

    def _get_env_config(self, key):
        if self._disable_env_vars:
            # print("not checking env")
            return None
        env_key = self._CONFIG_TO_ENV_VAR.get(key)
        # print("env key for {} is {}".format(key, env_key))
        if env_key and env_key in os.environ:
            # print("Got value", os.environ[env_key])
            return os.environ[env_key]
        return None

    def _get_config(self, key):
        # print("checking key", key)
        env_value = self._get_env_config(key)
        if env_value is not None:
            # print("Got env value")
            return env_value
        return self._get_profile_config(key)

    def _assume_role_with_web_identity(self):
        token_server = self._get_config('web_identity_token_server')
        if not token_server:
            return None
        token_loader = self._token_loader_cls(token_server)

        role_arn = self._get_config('role_arn')
        if not role_arn:
            error_msg = (
                'The provided profile or the current environment is '
                'configured to assume role with web identity but has no '
                'role ARN configured. Ensure that the profile has the role_arn'
                'configuration set or the AWS_ROLE_ARN env var is set.'
            )
            raise InvalidConfigError(error_msg=error_msg)

        extra_args = {}
        role_session_name = self._get_config('role_session_name')
        if role_session_name is not None:
            extra_args['RoleSessionName'] = role_session_name

        fetcher = AssumeRoleWithWebIdentityCredentialFetcher(
            client_creator=self._client_creator,
            web_identity_token_loader=token_loader,
            role_arn=role_arn,
            extra_args=extra_args,
            cache=self.cache,
        )
        # The initial credentials are empty and the expiration time is set
        # to now so that we can delay the call to assume role until it is
        # strictly needed.
        return DeferredRefreshableCredentials(
            method=self.METHOD,
            refresh_using=fetcher.fetch_credentials,
        )
