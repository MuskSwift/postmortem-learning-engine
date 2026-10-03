"""Postmortem learning slice for a closed incident."""

__version__ = "0.1.0"

from postmortem_learning_engine.validate import (
    REQUIRED_HEADINGS,
    REQUIRED_NO_BLAME_PHRASE,
    validate_or_errors,
)

# Import runs the prompt self-check. It does not call the network.
from postmortem_learning_engine import generate as _generate

__all__ = [
    "REQUIRED_HEADINGS",
    "REQUIRED_NO_BLAME_PHRASE",
    "validate_or_errors",
    "__version__",
]

del _generate
