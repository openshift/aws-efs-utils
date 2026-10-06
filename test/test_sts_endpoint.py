# Licensed under the MIT License. See the LICENSE accompanying this file
# for the specific language governing permissions and limitations under
# the License.

import os

import pytest

import mount_efs
import watchdog

try:
    from ConfigParser import ConfigParser
except ImportError:
    from configparser import ConfigParser

try:
    from urlparse import parse_qs, urlparse
except ImportError:
    from urllib.parse import parse_qs, urlparse


@pytest.mark.parametrize("credential_path", ["mount-env", "mount-options", "watchdog"])
@pytest.mark.parametrize(
    "region,suffix,expected_endpoint",
    [
        ("us-east-1", None, "https://sts.us-east-1.amazonaws.com/"),
        ("us-gov-west-1", None, "https://sts.us-gov-west-1.amazonaws.com/"),
        ("cn-north-1", "amazonaws.com.cn", "https://sts.cn-north-1.amazonaws.com.cn/"),
        ("us-iso-east-1", "c2s.ic.gov", "https://sts.us-iso-east-1.c2s.ic.gov/"),
        ("us-isob-east-1", "sc2s.sgov.gov", "https://sts.us-isob-east-1.sc2s.sgov.gov/"),
        ("us-isof-south-1", "csp.hci.ic.gov", "https://sts.us-isof-south-1.csp.hci.ic.gov/"),
        ("eu-isoe-west-1", "cloud.adc-e.uk", "https://sts.eu-isoe-west-1.cloud.adc-e.uk/"),
    ],
)
def test_webidentity_uses_partition_sts_endpoint(
    mocker, tmpdir, credential_path, region, suffix, expected_endpoint
):
    config = ConfigParser()
    config.add_section("mount")
    config.set("mount", "dns_name_suffix", "amazonaws.com")
    config.add_section("mount." + region)
    # A regional section without a suffix must inherit the base mount setting.
    config.set("mount." + region, "stunnel_debug_enabled", "false")
    if suffix:
        config.set("mount." + region, "dns_name_suffix", suffix)

    token_file = tmpdir.join("web-identity-token")
    token_file.write("test-token")
    role_arn = "arn:aws-iso-b:iam::123456789012:role/efs-test"
    credentials = {
        "AccessKeyId": "test-access-key",
        "SecretAccessKey": "test-secret-key",
        "Token": "test-session-token",
    }
    response = {
        "AssumeRoleWithWebIdentityResponse": {
            "AssumeRoleWithWebIdentityResult": {
                "Credentials": {
                    "AccessKeyId": credentials["AccessKeyId"],
                    "SecretAccessKey": credentials["SecretAccessKey"],
                    "SessionToken": credentials["Token"],
                }
            }
        }
    }
    module = watchdog if credential_path == "watchdog" else mount_efs
    request = mocker.patch.object(module, "url_request_helper", return_value=response)
    mocker.patch.dict(os.environ, {}, clear=True)
    mocker.patch.object(
        module,
        "get_aws_security_credentials_from_instance_metadata",
        side_effect=AssertionError("web identity must not fall back to instance metadata"),
    )

    expected_source = "webidentity:%s,%s" % (role_arn, token_file)
    if credential_path == "watchdog":
        actual = watchdog.get_aws_security_credentials(config, expected_source, region)
    else:
        mocker.patch.object(
            mount_efs,
            "get_iam_role_name",
            side_effect=AssertionError("web identity must not query instance metadata"),
        )
        options = {}
        if credential_path == "mount-env":
            mocker.patch.dict(
                os.environ,
                {
                    "AWS_ROLE_ARN": role_arn,
                    "AWS_WEB_IDENTITY_TOKEN_FILE": str(token_file),
                },
            )
        else:
            options = {"role_arn": role_arn, "jwt_path": str(token_file)}
        actual, source = mount_efs.get_aws_security_credentials(
            config, True, region, **options
        )
        assert source == expected_source

    assert actual == credentials
    assert request.call_count == 1
    parsed = urlparse(request.call_args[0][1])
    assert "%s://%s%s" % (parsed.scheme, parsed.netloc, parsed.path) == expected_endpoint
    params = parse_qs(parsed.query)
    assert params["Action"] == ["AssumeRoleWithWebIdentity"]
    assert params["RoleArn"] == [role_arn]
    assert params["WebIdentityToken"] == ["test-token"]
