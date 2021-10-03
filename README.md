# boto3 should add direct support for AssumeRoleWithWebIdentity for GitHub Actions

There is a [`aws-actions/configure-aws-credentials`](https://github.com/aws-actions/configure-aws-credentials) action that will get AWS credentials for you based on [`STS.AssumeRoleWithWebIdentity`](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRoleWithWebIdentity.html), and put the credentials in environment variables.
I see two problems with this:
* You need to put a whole step in your job definition. Why can't it just be environment variables? Or a config file in the repo, just like the `~/.aws/config` file you use elsewhere?
* You can't use more than one role at a time. At best, you would need to serialize your use of multiple roles, separated by steps to assume those different roles.

This repo demonstrates how we can solve both problems in `botocore`.
`botocore` would add a new [`CredentialProvider`](https://github.com/boto/botocore/blob/6155f328adb44bc33c7bb2a9c85ce695a48be133/botocore/credentials.py#L903).
See the [demo action](.github/workflows/demo.yaml) and the [demo code](.github/workflows/demo.py), the [changes for `botocore`](botocore_addition.py), and [the logs for a run](https://github.com/benkehoe/github-actions-boto3-demo/runs/3779665903?check_suite_focus=true#step:5:11).

This implementation would give you two options:

## Environment variables
This is the simplest method.
You would set `AWS_ROLE_ARN=arn:aws:iam::123456789012:role/MyRole` (using your role ARN, of course) and `AWS_WEB_IDENTITY_TOKEN_SERVER=GitHub` in the environment, and it would get picked up. You can optionally set `AWS_ROLE_SESSION_NAME` as well.

Note you can do this today for web identity, except that it only works with token files and the `AWS_WEB_IDENTITY_TOKEN_FILE` environment variable.
Indeed, [Aidan Steele](https://github.com/aidansteele) used this method [a blog post](https://awsteele.com/blog/2021/09/15/aws-federation-comes-to-github-actions.html) to make GitHub actions work, before the AWS-created action was available.

## Config file
An alternative, which would also support multiple roles, is a config file.
The format for profiles would look like this:

```ini
[default]
role_arn = arn:aws:iam::123456789012:role/MyRole
web_identity_token_server = GitHub
region = us-east-2
```
(Note: `role_session_name` is optional in these profiles, but I set it in [the config file](.github/workflows/aws_config) to help differentiate which profile is being used).

Unfortunately, this requires one additional piece of configuration.
The root of the checked-out repository is `/home/runner/work/github-actions-boto3-demo/github-actions-boto3-demo` while `~/.aws/config` resolves to `/home/runner/.aws/config`.
This means you need to set `AWS_CONFIG_FILE=.github/workflows/aws_config` (or whatever the path for the config file in the repo is) in the environment.

See the [config file](.github/workflows/aws_config) for examples.

## Audience
The default audience for the OIDC token is the repo URL, which is a little weird.
The audience is who should be receiving the token, which for us is the role(s) we're assuming.
On the AWS side, the [OIDC provider](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-iam-oidcprovider.html#cfn-iam-oidcprovider-clientidlist) can have a list of audiences it will accept.

It should be something like the application on the destination side of the role assumption, ideally like the CloudFormation stack name that the role is in.
But absent that I'd say it should be the STS service principal, `sts.amazonaws.com`.

But as far as I can tell, any value provided to the GitHub OIDC token vendor other than `sigstore` (no idea what that's for) returns an error, _including_ the default audience value of the repo URL.

But I've provided the ability to set the audience manually, by adding a comma-separated value at the end of the token server config value (either `web_identity_token_server` in the config file or `AWS_WEB_IDENTITY_TOKEN_SERVER` in the enviornment).
See the [config file](.github/workflows/aws_config) for examples of this (using `sigstore`).

## Manual config
AWS might object to baking in knowledge of a 3rd party provider, so I also allowed for this to be generic.
Instead of a convenient "GitHub" value for `web_identity_token_server`, you provide a comma-separated list of the environment variables for the URL and for the token.
The code then parses the configuration from this, rather than storing direct knowledge of GitHub in the code.
It's then generic, rather than GitHub-specific, but requires basically a magic incantation that people would have to copy and paste.
You could even take that further and make it a base64-encoded JSON object if it needed to be more complicated, a proper opaque config value.

See the [config file](.github/workflows/aws_config) for examples of the manual configuration.
