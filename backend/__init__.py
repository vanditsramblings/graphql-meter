# GraphQL Meter Backend

try:
    from importlib.metadata import version as _pkg_version
    __version__ = _pkg_version("graphql-meter")
except Exception:
    __version__ = "0.1.0"
