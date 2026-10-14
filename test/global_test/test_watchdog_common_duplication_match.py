#
# Copyright 2017-2018 Amazon.com, Inc. and its affiliates. All Rights Reserved.
#
# Licensed under the MIT License. See the LICENSE accompanying this file
# for the specific language governing permissions and limitations under
# the License.
#
# The standalone watchdog cannot import from efs_utils_common (its install location has no access
# to the shared package), so the credential "Expiration" format is deliberately duplicated in both
# src/watchdog/__init__.py and src/efs_utils_common.aws_credentials. This test imports both copies
# and asserts they are equal, so the duplication cannot drift silently.

import efs_utils_common.aws_credentials as aws_credentials
import watchdog


def test_credentials_expiration_datetime_format_match():
    assert (
        watchdog.CREDENTIALS_EXPIRATION_DATETIME_FORMAT
        == aws_credentials.CREDENTIALS_EXPIRATION_DATETIME_FORMAT
    ), "watchdog and efs_utils_common.aws_credentials disagree on the credential Expiration format"
