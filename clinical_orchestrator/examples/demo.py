"""Runnable end-to-end demo.

Run from the repo root:

    python -m clinical_orchestrator.cli demo
"""

from clinical_orchestrator.cli import _demo

if __name__ == "__main__":
    import json
    print(json.dumps(_demo(), indent=2, default=str))
