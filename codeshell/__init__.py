
from importlib.metadata import PackageNotFoundError, version as package_version


def _resolve_version() -> str:
    try:
        return package_version("codeshell")
    except PackageNotFoundError:
        return "0.2.0"


__version__ = _resolve_version()

