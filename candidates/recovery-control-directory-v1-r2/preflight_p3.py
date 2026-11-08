"""Verify the revision inventory before loading the review-only P3 preflight."""
from pathlib import Path
import sys

if not sys.flags.isolated or not sys.flags.dont_write_bytecode:
    raise RuntimeError('Use python -I -B')

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from run_local import verify_inputs

verify_inputs()
sys.path.insert(0, str(ROOT / 'source'))
from tools.preflight_recovery_compose import main

sys.exit(main())
