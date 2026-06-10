"""Enable ``python -m tremula`` (used by the detached distiller spawn)."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
