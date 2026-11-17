#!/usr/bin/env python3
"""Apply local python-for-android patches needed to build this app.

The patches work around two host/toolchain issues in python-for-android:

1. The bootstrap venv can end up with a corrupted `pip` because the Android
   target site-packages is on PYTHONPATH while pip upgrades itself.  We clear
   PYTHONPATH, re-run ensurepip, and recreate a clean venv.
2. Kivy's recipe pulls in `requests`/`charset-normalizer`.  pip resolves an
   Android-specific `chardet`/`charset_normalizer` wheel and then refuses to
   install it with the host pip in the final step.  We substitute the
   universal `none-any` wheel when one exists.

Usage:
    python scripts/apply_p4a_patches.py [path/to/pythonforandroid/build.py]

Run it after python-for-android has been downloaded (i.e. after the first
`buildozer android debug` attempt), then re-run buildozer.
"""

from __future__ import annotations

import sys
from pathlib import Path

DEFAULT_BUILD_PY = (
    Path(__file__).resolve().parent.parent
    / ".buildozer"
    / "android"
    / "platform"
    / "python-for-android"
    / "pythonforandroid"
    / "build.py"
)

PIP_BOOTSTRAP_OLD = '''    host_python = sh.Command(ctx.hostpython)
    with current_directory(join(ctx.build_dir)):
        shprint(host_python, '-m', 'venv', 'venv')

        # Prepare base environment and upgrade pip:
        base_env = dict(copy.copy(os.environ))
        base_env["PYTHONPATH"] = ctx.get_site_packages_dir(arch)
        info('Upgrade pip to latest version')
        shprint(sh.bash, '-c', (
            "source venv/bin/activate && pip install -U pip"
        ), _env=copy.copy(base_env))

        # Install Cython in case modules need it to build:
        info('Install Cython in case one of the modules needs it to build')
        shprint(sh.bash, '-c', (
            "venv/bin/pip install Cython"
        ), _env=copy.copy(base_env))'''

PIP_BOOTSTRAP_NEW = '''    host_python = sh.Command(ctx.hostpython)
    with current_directory(join(ctx.build_dir)):
        venv_dir = join(ctx.build_dir, 'venv')
        if exists(venv_dir):
            shutil.rmtree(venv_dir)
        shprint(host_python, '-m', 'venv', 'venv')

        # Prepare base environment and upgrade pip:
        # NOTE: keep PYTHONPATH empty during bootstrap so the Android
        # target site-packages cannot shadow the venv's own pip modules
        # (that produced a corrupted mixed pip install: missing
        # `capture_logging`).
        base_env = dict(copy.copy(os.environ))
        base_env["PYTHONPATH"] = ""
        info('Upgrade pip to latest version')
        shprint(sh.bash, '-c', (
            "source venv/bin/activate && "
            "python -m ensurepip --upgrade && "
            "python -m pip install -U pip"
        ), _env=copy.copy(base_env))

        # Install Cython in case modules need it to build:
        info('Install Cython in case one of the modules needs it to build')
        shprint(sh.bash, '-c', (
            "venv/bin/python -m pip install Cython"
        ), _env=copy.copy(base_env))'''

HELPER_ANCHOR = "def is_wheel_compatible(whl_name, arch, ctx):\n"

HELPER = '''def _universal_wheel_url(package_name, version):
    """Return a pure-Python (none-any) wheel URL for a package/version, if any."""
    try:
        from urllib.request import urlopen
        api = f"https://pypi.org/pypi/{package_name}/{version}/json"
        with urlopen(api, timeout=20) as resp:
            data = json.load(resp)
        for item in data.get("urls", []):
            filename = item.get("filename", "")
            if filename.endswith(("-py3-none-any.whl", "-py2.py3-none-any.whl",
                                 "-py2-none-any.whl")):
                return item.get("url")
    except Exception as exc:
        warning(f"Could not look up universal wheel for {package_name}=={version}: {exc}")
    return None


'''

APPEND_OLD = '''        if pure_python:
            processed_modules.append(module["download_info"]["url"])'''

APPEND_NEW = '''        if pure_python:
            wheel_url = module["download_info"]["url"]
            if not wheel_url.endswith((
                    "-py3-none-any.whl",
                    "-py2.py3-none-any.whl",
                    "-py2-none-any.whl",
            )):
                universal_url = _universal_wheel_url(mname, mver)
                if universal_url:
                    info(
                        f"  {Out_Fore.GREEN}{mname}{Out_Fore.WHITE} : "
                        f"using universal wheel instead of platform wheel"
                    )
                    wheel_url = universal_url
            processed_modules.append(wheel_url)'''

REQUIREMENTS_OLD = '''            shprint(sh.bash, '-c', (
                "venv/bin/pip " +
                "install -v --target '{0}' --no-deps -r requirements.txt"
            ).format(ctx.get_site_packages_dir(arch).replace("'", "'\\"'\\"'")),
                    _env=copy.copy(env))'''

REQUIREMENTS_NEW = '''            shprint(sh.bash, '-c', (
                "venv/bin/python -m pip " +
                "install -v --target '{0}' --no-deps -r requirements.txt"
            ).format(ctx.get_site_packages_dir(arch).replace("'", "'\\"'\\"'")),
                    _env=copy.copy(env))'''

RENAMES = [
    ("clean pip bootstrap", PIP_BOOTSTRAP_OLD, PIP_BOOTSTRAP_NEW),
    ("requirements install via python -m pip", REQUIREMENTS_OLD, REQUIREMENTS_NEW),
]


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_BUILD_PY
    if not path.exists():
        print(f"python-for-android build.py not found: {path}")
        print("Run `buildozer -v android debug` once to download p4a, then rerun this script.")
        return 1

    text = path.read_text()
    changed = False

    for label, old, new in RENAMES:
        if new in text:
            print(f"already applied: {label}")
        elif old in text:
            text = text.replace(old, new, 1)
            changed = True
            print(f"applied: {label}")
        else:
            print(f"WARNING: could not locate patch target: {label}")

    if "def _universal_wheel_url" not in text:
        if HELPER_ANCHOR in text:
            text = text.replace(HELPER_ANCHOR, HELPER + HELPER_ANCHOR, 1)
            changed = True
            print("applied: universal wheel helper")
        else:
            print("WARNING: could not locate helper anchor")
    else:
        print("already applied: universal wheel helper")

    if APPEND_NEW in text:
        print("already applied: universal wheel fallback")
    elif APPEND_OLD in text:
        text = text.replace(APPEND_OLD, APPEND_NEW, 1)
        changed = True
        print("applied: universal wheel fallback")
    else:
        print("WARNING: could not locate universal wheel fallback target")

    if changed:
        path.write_text(text)
        print(f"patched {path}")
    else:
        print("no changes needed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
