# Copyright 2017-2018 Amazon.com, Inc. and its affiliates. All Rights Reserved.
#
# Licensed under the MIT License. See the LICENSE accompanying this file
# for the specific language governing permissions and limitations under
# the License.
from unittest.mock import MagicMock

import efs_utils_common.proxy as proxy
from efs_utils_common.constants import WATCHDOG_SERVICE, WATCHDOG_SERVICE_PLIST_PATH

from .. import utils

FS_ID = "fs-deadbeef"


def test_upstart_system(mocker):
    process_mock = MagicMock()
    process_mock.communicate.return_value = (
        "stop",
        "",
    )
    process_mock.returncode = 0
    popen_mock = mocker.patch("subprocess.Popen", return_value=process_mock)

    proxy.start_watchdog("init")

    assert 2 == popen_mock.call_count
    assert "/sbin/start" in popen_mock.call_args[0][0]


def test_systemd_system(mocker):
    call_mock = mocker.patch("subprocess.call", return_value=1)
    popen_mock = mocker.patch("subprocess.Popen")

    proxy.start_watchdog("systemd")

    utils.assert_called_once(call_mock)
    assert "systemctl" in call_mock.call_args[0][0]
    assert "is-active" in call_mock.call_args[0][0]
    utils.assert_called_once(popen_mock)
    assert "systemctl" in popen_mock.call_args[0][0]
    assert "start" in popen_mock.call_args[0][0]


def test_launchd_canonical_label_loaded(mocker):
    call_mock = mocker.patch("subprocess.call", side_effect=[0])

    proxy.start_watchdog("launchd")

    utils.assert_called_once(call_mock)
    assert call_mock.call_args_list[0][0][0] == [
        "launchctl",
        "list",
        WATCHDOG_SERVICE,
    ]


def test_launchd_loads_canonical_plist(mocker):
    call_mock = mocker.patch("subprocess.call", side_effect=[1, 0])
    mocker.patch("os.path.exists", return_value=True)

    proxy.start_watchdog("launchd")

    assert call_mock.call_args_list[-1][0][0] == [
        "launchctl",
        "load",
        WATCHDOG_SERVICE_PLIST_PATH,
    ]


def test_launchd_missing_plists_is_fatal(mocker):
    call_mock = mocker.patch("subprocess.call", side_effect=[1])
    mocker.patch("os.path.exists", return_value=False)
    fatal_mock = mocker.patch("efs_utils_common.proxy.fatal_error")

    proxy.start_watchdog("launchd")

    utils.assert_called_once(call_mock)
    utils.assert_called_once(fatal_mock)
    assert "plist" in fatal_mock.call_args[0][0].lower()


def test_launchd_load_failure_is_fatal(mocker):
    call_mock = mocker.patch("subprocess.call", side_effect=[1, 23])
    mocker.patch("os.path.exists", return_value=True)
    fatal_mock = mocker.patch("efs_utils_common.proxy.fatal_error")

    proxy.start_watchdog("launchd")

    assert call_mock.call_args_list[-1][0][0] == [
        "launchctl",
        "load",
        WATCHDOG_SERVICE_PLIST_PATH,
    ]
    utils.assert_called_once(fatal_mock)
    assert "exit code 23" in fatal_mock.call_args[0][0]


def test_unknown_system(mocker):
    popen_mock = mocker.patch("subprocess.Popen")

    proxy.start_watchdog("unknown")

    utils.assert_not_called(popen_mock)
