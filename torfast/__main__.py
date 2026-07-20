from __future__ import annotations

import sys

from .fast_runtime import try_fast_action
from .term import human_output_enabled


def main(argv: list[str] | None = None) -> int:
    resolved_argv = list(sys.argv[1:] if argv is None else argv)
    if human_output_enabled() and "--json" not in resolved_argv:
        from .cli import run_fast_action_human

        fast_exit_code = run_fast_action_human(resolved_argv)
    else:
        fast_exit_code = try_fast_action(resolved_argv)
    if fast_exit_code is not None:
        return fast_exit_code

    from .cli import main as cli_main

    return cli_main(resolved_argv)


if __name__ == "__main__":
    raise SystemExit(main())
