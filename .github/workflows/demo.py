import os
import traceback
import json

import jwt

import sys
sys.path.append('.')
from botocore_addition import (
    get_session,
    GitHubWebIdentityTokenLoader,
)

# print(json.dumps(dict(os.environ), indent=2, sort_keys=True))

try:
    print("Getting a default session")
    default_session = get_session(disable_env_vars=True)

    response = default_session.client('sts').get_caller_identity()
    print(json.dumps(response, indent=2))

    profile_name = "role-2"
    print("Getting a session for profile {}".format(profile_name))
    named_profile_session = get_session(profile_name=profile_name, disable_env_vars=True)
    response = named_profile_session.client('sts').get_caller_identity()
    print(json.dumps(response, indent=2))

    print("Getting a session from environment variables")
    env_var_session = get_session(disable_env_vars=False)
    response = env_var_session.client('sts').get_caller_identity()
    print(json.dumps(response, indent=2))

    print("Testing manual config 1")
    get_session(profile_name="manual-config-1").client('sts').get_caller_identity()
    print("Testing manual config 2")
    get_session(profile_name="manual-config-2").client('sts').get_caller_identity()
    print("Testing manual config 3")
    get_session(profile_name="manual-config-3").client('sts').get_caller_identity()

    print("Example JWT")
    print(json.dumps(jwt.decode(GitHubWebIdentityTokenLoader.EXAMPLE_JWT, options={"verify_signature": False}), indent=2))
except:
    raise

from pathlib import Path

print(Path(os.environ["AWS_CONFIG_FILE"]).resolve())
print(Path('~/.aws/config').expanduser())
