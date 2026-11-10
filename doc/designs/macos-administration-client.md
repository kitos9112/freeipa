# macOS administration client (experimental)

This provider is intended for a native Python administration process on macOS
using explicit IPA configuration and existing Kerberos credentials. It does not
implement host enrolment, service management, SSSD, PAM, login integration or
server operation. Adding a provider does not establish general macOS support.

## Implementation boundary

Darwin already maps to `macos` in `ipaplatform.osinfo`. The provider supplies the
existing paths/constants/tasks/services interfaces and is included in the
explicit setuptools package list. It reuses base IPA configuration paths;
`IPA_CONFDIR` selects an application-specific directory. Unsupported service
management raises `NotImplementedError`. Host configuration tasks retain the
base unsupported behavior, with explicit errors for base installation hooks
that otherwise do nothing, and for resolver/NSS/automount mutations.

A generic remote-administration provider could eventually remove more host
assumptions, but would require a new platform-selection and support contract.
The dedicated provider fits the current Darwin detection without changing Linux
selection. A Linux override is not a supported macOS installation strategy.

The session-storage fix is independent: `krb5_build_principal` is variadic, and
its ctypes `argtypes` must list only the four fixed parameters. Apple arm64
passes variadic arguments differently from fixed arguments. Call sites already
wrap the additional arguments explicitly. See the Python
[ctypes documentation](https://docs.python.org/3/library/ctypes.html#calling-variadic-functions).

## Native environment tested

Local validation used macOS 26.7.2, Darwin 25.6.0, arm64, Homebrew Python
3.12.16 and Homebrew MIT Kerberos 1.22.2 (`1.22.2_2` formula revision), with
python-gssapi 1.12.0 compiled against that MIT installation. System-default
Python 3.15.2 was inventoried but was not the validation interpreter.
The source revision was `f82a8548811cd19e3a9e3100506a976f6d498e0b`.

This combination passed import, explicit client bootstrap and a synthetic
FILE-cache session round trip. It is a candidate for live validation, not an
authenticated support claim. Apple Kerberos, API finalisation with a real
server, authenticated RPC, expired tickets, DNS module execution and vault
operations remain unverified.

## Dependency and configuration setup

### Downstream Git builds

The experimental fork also supports wheel builds from the four package
subdirectories of a complete Git checkout. If the configured `ipasetup.py`
is absent, setup falls back to `ipasetup_git.py`, which reuses the original
setup template and derives development version/API/plugin metadata from
`VERSION.m4` and `API.txt`. It records the local MIT Kerberos build version
using `GSSAPI_KRB5CONFIG` (or `krb5-config` from PATH). Installer modules and
platform overrides are omitted by default, as for administration-only wheels.

These builds use a downstream `+transficc` development version. All four
distributions must use the same Git revision; installing just `ipaclient`
from Git would leave its exact-version dependencies unavailable on PyPI.
Configured upstream builds continue to use their generated `ipasetup.py`.
This fallback targets direct Git wheel builds, not standalone subdirectory
source archives or editable installation. It is a downstream integration
change, separate from the proposed ABI and platform contributions.

With uv, declare all four distributions and supply Git sources with their
respective `subdirectory` values (`ipaclient`, `ipalib`, `ipaplatform`,
`ipapython`). A `sys_platform == 'darwin'` source marker limits the fork to
macOS, and `uv.lock` records the commit resolved from the fork's `master`.
Other platforms can retain their registry packages. The MIT build/linkage
requirements below still apply; a Git source entry does not configure GSSAPI.

### Native prerequisites

Use a virtual environment. Native dependencies include Kerberos, OpenLDAP
(the DN implementation uses libldap even without LDAP administration), and
the dependencies declared by the four Python packages. This procedure assumes
Homebrew dependencies are already installed; installing them is a separate
machine setup step. Intel Homebrew paths differ and have not been tested.

```sh
/opt/homebrew/opt/python@3.12/bin/python3.12 -m venv /tmp/ipa-client-venv
source /tmp/ipa-client-venv/bin/activate
export GSSAPI_KRB5CONFIG=/opt/homebrew/opt/krb5/bin/krb5-config
export GSSAPI_COMPILER_ARGS="$(/opt/homebrew/opt/krb5/bin/krb5-config --cflags gssapi)"
export GSSAPI_LINKER_ARGS="$(/opt/homebrew/opt/krb5/bin/krb5-config --libs gssapi)"
python -m pip install --no-binary=gssapi --no-cache-dir gssapi==1.12.0
```

Specifying `krb5-config` alone does not override python-gssapi's default Apple
framework linkage. Verify linkage with `otool -L` on its native extensions.
Use matching versions of the patched `ipapython`, `ipaplatform`, `ipalib` and
`ipaclient` wheels, built using the project's existing build process. During
local validation, generated metadata was substituted from source templates
with development version `4.14.0.dev0`, API `2.258`, plugin defaults from
`API.txt` and the installed MIT build version; a complete Autoconf build on
macOS has not been validated. Do not mix these wheels with released 4.13.1
components, whose metadata requires matching package versions.

Launch the Python process with the same MIT library directory used by gssapi:

```sh
export DYLD_LIBRARY_PATH=/opt/homebrew/opt/krb5/lib
export IPA_CONFDIR=/absolute/path/to/test-ipa-config
export KRB5_CONFIG="$IPA_CONFDIR/krb5.conf"
export KRB5CCNAME="FILE:$IPA_CONFDIR/test.ccache"
```

The session-storage loader still uses `libkrb5.dylib`. Verify its actual
resolved library as well as gssapi linkage. Local checks confirmed MIT via
`dladdr`; the environment variable alone is not proof. Framework Python or
protected launchers may handle dynamic-loader variables differently.

Create `default.conf` in that directory, replacing only the example test-server
configuration with the isolated realm's values:

```ini
[global]
host = controller.ipa.test
domain = ipa.test
realm = IPA.TEST
server = ipa.ipa.test
xmlrpc_uri = https://ipa.ipa.test/ipa/xml
jsonrpc_uri = https://ipa.ipa.test/ipa/json
basedn = dc=ipa,dc=test
enable_ra = True
```

Copy the isolated server's public IPA CA certificate to `ca.crt` through a
trusted channel. Do not disable TLS verification. Create a private `krb5.conf`
pointing at that KDC and acquire credentials with the same Homebrew MIT `kinit`,
using the explicit FILE cache. Do not change global macOS authentication
configuration or assume that an Apple API cache is interchangeable.

```python
from ipalib import api

api.bootstrap(context="client", in_server=False, in_tree=False, log=None)
api.finalize()
api.Backend.rpcclient.connect()
try:
    api.Command.ping()
finally:
    if api.Backend.rpcclient.isconnected():
        api.Backend.rpcclient.disconnect()
```

Finalisation normally discovers the remote command schema and can contact the
server before an explicit backend connection. A missing CA is rejected before
that connection. Offline bootstrap does not prove successful finalisation.
Client plugins, notably vault, perform local processing; vault support must be
assessed separately using synthetic secrets in a disposable vault.

## Validation and limitations

Run the new Darwin/import-hook and session-storage tests with the upstream
pytest harness. The session-storage regression creates its own FILE cache and
synthetic principal without contacting a KDC or reading the user's cache.
The macOS bootstrap smoke test explicitly disables source-tree/server mode.

Linux CI must run the relevant platform and session-storage tests, plus
`make fasttest` and `make fastlint` in a configured build. Those checks have
not been completed on Linux. Existing platform tests assume Linux accounts,
RPM version handling and Linux container detection; their behavior on macOS
needs separate test-harness work. Do not interpret mocked discovery or Linux
provider imports on a Mac as Linux runtime validation.

Ansible validation used ansible-core 2.21.6 and
`freeipa.ansible_freeipa` 1.17.0: `ipadnsrecord` and its common bindings imported
with no recorded bindings import error. Execution against IPA is pending.
Set `ipaapi_context: client`, use the native virtual-environment interpreter,
and pass `IPA_CONFDIR`, `KRB5_CONFIG`, `KRB5CCNAME` and the MIT loader directory
to the delegated localhost task. The collection maps client context to IPA's
CLI context, so its finalisation path is distinct from the bootstrap smoke
test. Check mode, creation, idempotence and removal require the isolated server.
