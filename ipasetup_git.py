# Copyright (C) 2026 FreeIPA Contributors see COPYING for license
"""Downstream Git-wheel fallback; configured builds use ipasetup.py instead.

This supports the four administration packages directly from a full Git
checkout. It deliberately does not configure host installation or a server.
"""

import os
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parent
DEFINES = dict(re.findall(
    r'^define\((\w+),\s*([^\n)]*)\)',
    (ROOT / 'VERSION.m4').read_text(encoding='utf-8'), re.MULTILINE,
))
RELEASE = tuple(int(DEFINES['IPA_VERSION_' + part])
                for part in ('MAJOR', 'MINOR', 'RELEASE'))
VERSION = '{}.{}.{}.dev0+transficc'.format(*RELEASE)

# Reuse upstream dependency pins, package metadata and wheel filtering.
_template = ROOT / 'ipasetup.py.in'
_namespace = {'__name__': __name__, '__file__': str(_template)}
_source = _template.read_text(encoding='utf-8').replace('@VERSION@', VERSION)
exec(compile(_source, str(_template), 'exec'), _namespace)


def ipasetup(name, doc, **kwargs):
    if name not in ('ipaclient', 'ipalib', 'ipaplatform', 'ipapython'):
        raise RuntimeError('Git-wheel fallback supports administration only')
    os.environ.setdefault('IPA_OMIT_INSTALL', '1')
    if name == 'ipapython':
        # The generated version module imports packaging at runtime.
        kwargs['install_requires'] = [*kwargs['install_requires'], 'packaging']
        krb5_config = os.environ.get('GSSAPI_KRB5CONFIG', 'krb5-config')
        krb5_version = subprocess.check_output(
            [krb5_config, '--version'], universal_newlines=True,
        ).strip()
        match = re.fullmatch(
            r'Kerberos 5 release (\d+(?:\.\d+)+)', krb5_version,
        )
        if match is None:
            raise RuntimeError('Git-wheel fallback requires MIT krb5-config')
        values = {
            'VERSION': VERSION,
            'VENDOR_SUFFIX': '',
            'NUM_VERSION': str(
                RELEASE[0] * 10000 + RELEASE[1] * 100 + RELEASE[2]
            ),
            'API_VERSION': '{}.{}'.format(
                DEFINES['IPA_API_VERSION_MAJOR'],
                DEFINES['IPA_API_VERSION_MINOR'],
            ),
            'KRB5_BUILD_VERSION': match.group(1),
            'DEFAULT_PLUGINS': '\n'.join(
                line.split()[1]
                for line in (ROOT / 'API.txt').read_text(
                    encoding='utf-8'
                ).splitlines()
                if line.startswith('default:')
            ),
        }
        version = ROOT / 'ipapython/version.py.in'
        content = version.read_text(encoding='utf-8')
        for key, value in values.items():
            content = content.replace('@{}@'.format(key), value)
        version.with_suffix('').write_text(content, encoding='utf-8')
    return _namespace['ipasetup'](name, doc, **kwargs)
