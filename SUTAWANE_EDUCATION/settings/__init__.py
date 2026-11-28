"""
Settings selector for SUTAWANE_EDUCATION.
Loads production settings when DJANGO_ENV=production (or prod),
otherwise loads development settings by default.
"""

import os
from pathlib import Path
import dotenv

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
dotenv.load_dotenv(_BASE_DIR / '.env')

_ACTIVE_ENV = os.getenv('DJANGO_ENV', 'development').strip().lower()

if _ACTIVE_ENV in ('production', 'prod'):
    from .production import *  # noqa: F401, F403
else:
    from .development import *  # noqa: F401, F403
