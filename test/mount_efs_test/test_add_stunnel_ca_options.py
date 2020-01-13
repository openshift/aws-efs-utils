#
# Copyright 2017-2018 Amazon.com, Inc. and its affiliates. All Rights Reserved.
#
# Licensed under the MIT License. See the LICENSE accompanying this file
# for the specific language governing permissions and limitations under
# the License.
#

import mount_efs
import tempfile

import pytest

try:
    import ConfigParser
except ImportError:
    from configparser import ConfigParser

CAPATH = '/capath'
CAFILE = '/cafile.crt'


def _get_config():
    try:
        config = ConfigParser.SafeConfigParser()
    except AttributeError:
        config = ConfigParser()
    config.add_section(mount_efs.CONFIG_SECTION)
    return config


def _create_temp_file(tmpdir, content=''):
    temp_file = tmpdir.join(tempfile.mktemp())
    temp_file.write(content, ensure=True)
    return temp_file


def test_use_existing_cafile(tmpdir):
    options = {'cafile': str(_create_temp_file(tmpdir))}
    efs_config = {}

    mount_efs.add_stunnel_ca_options(efs_config, _get_config(), options)

    assert options['cafile'] == efs_config.get('CAfile')
    assert 'CApath' not in efs_config


def test_use_missing_cafile(capsys):
    options = {'cafile': '/missing1'}
    efs_config = {}

    with pytest.raises(SystemExit) as ex:
        mount_efs.add_stunnel_ca_options(efs_config, _get_config(), options)

    assert 0 != ex.value.code

    out, err = capsys.readouterr()
    assert 'Failed to find certificate authority file for verification' in err


def test_stunnel_cafile_configuration_in_option(mocker):
    options = {'cafile': CAFILE}
    efs_config = {}

    mocker.patch('os.path.exists', return_value=True)

    mount_efs.add_stunnel_ca_options(efs_config, _get_config(), options)

    assert CAFILE == efs_config.get('CAfile')


def test_stunnel_cafile_configuration_in_config(mocker):
    options = {}
    efs_config = {}

    config = _get_config()
    config.set(mount_efs.CONFIG_SECTION, 'stunnel_cafile', CAFILE)

    mocker.patch('os.path.exists', return_value=True)

    mount_efs.add_stunnel_ca_options(efs_config, config, options)

    assert CAFILE == efs_config.get('CAfile')


def test_stunnel_cafile_not_configured(mocker):
    options = {}
    efs_config = {}

    mocker.patch('os.path.exists', return_value=True)

    mount_efs.add_stunnel_ca_options(efs_config, _get_config(), options)

    assert mount_efs.DEFAULT_STUNNEL_CAFILE == efs_config.get('CAfile')
