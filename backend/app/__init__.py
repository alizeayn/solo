"""Solo — backend application package."""

from .version import read_version

__version__ = read_version()

__all__ = ["__version__", "read_version"]
