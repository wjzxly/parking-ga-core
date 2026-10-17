"""让 `python -m parking_ga` 直接可用。"""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
