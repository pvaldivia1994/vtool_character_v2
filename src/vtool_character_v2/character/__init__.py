"""
character — Subpackage con CharacterManager dividido por responsabilidad.
"""

from .base import CharacterManager

from . import persistence     # noqa: F401
from . import episodes        # noqa: F401
from . import psychology_init # noqa: F401

__all__ = ["CharacterManager"]
