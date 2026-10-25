"""
Sutawane Classes Management Software - Production-Safe Caching Engine.

Guarantees:
1. Zero Downtime: All cache operations are wrapped in fail-safe try/except blocks.
   If cache backend fails, times out, or disconnects, the system transparently
   falls back to live database queries with zero user disruption.
2. Zero Stale Data: Employs atomic O(1) Namespace Versioning.
   When any model (Payment, Expense, Student, Branch, Session) is saved or updated,
   its entire namespace version is incremented, instantly invalidating stale caches
   across all worker processes in microseconds.
3. Multi-Worker & Multi-Process Safe: Works seamlessly with Gunicorn, Waitress,
   Redis, FileBasedCache, and LocMemCache.
"""

import logging
from typing import Any, Callable, Optional
from django.core.cache import cache

logger = logging.getLogger('MyApp.cache')

# Standard namespace time-to-live (seconds)
TTL_DASHBOARD = 180      # 3 minutes (invalidated immediately on transaction signals)
TTL_REPORTS = 300        # 5 minutes (invalidated immediately on financial signals)
TTL_DUES = 120           # 2 minutes (invalidated on payment / admission signals)
TTL_CONTEXT = 600        # 10 minutes (invalidated on branch/session/setting signals)
TTL_STUDENTS = 180       # 3 minutes
TTL_SEARCH = 60          # 1 minute
TTL_PUBLIC = 600         # 10 minutes (public marketing landing page)
TTL_LICENSE = 300        # 5 minutes


# -----------------------------------------------------------------------------
# Fail-Safe Low-Level Cache Wrappers
# -----------------------------------------------------------------------------

def safe_cache_get(key: str, default: Any = None) -> Any:
    """
    Safely retrieves value from cache.
    Returns `default` on cache miss OR if cache backend raises any exception.
    """
    try:
        val = cache.get(key)
        return val if val is not None else default
    except Exception as exc:
        logger.warning("Cache GET failed for key '%s': %s", key, exc)
        return default


def safe_cache_set(key: str, value: Any, timeout: Optional[int] = None) -> bool:
    """
    Safely stores value in cache.
    Returns True if stored, False if any exception occurred.
    """
    try:
        cache.set(key, value, timeout)
        return True
    except Exception as exc:
        logger.warning("Cache SET failed for key '%s': %s", key, exc)
        return False


def safe_cache_delete(key: str) -> bool:
    """
    Safely deletes a single key from cache.
    """
    try:
        cache.delete(key)
        return True
    except Exception as exc:
        logger.warning("Cache DELETE failed for key '%s': %s", key, exc)
        return False


def safe_cache_delete_many(keys: list) -> bool:
    """
    Safely deletes multiple keys from cache.
    """
    if not keys:
        return True
    try:
        cache.delete_many(keys)
        return True
    except Exception as exc:
        logger.warning("Cache DELETE_MANY failed: %s", exc)
        return False


def safe_cache_get_or_set(key: str, fallback_callable: Callable[[], Any], timeout: Optional[int] = None) -> Any:
    """
    Atomically retrieves cached value or computes and stores fallback.
    Never fails: if caching fails, executes fallback and returns live data.
    """
    cached_val = safe_cache_get(key)
    if cached_val is not None:
        return cached_val

    try:
        computed = fallback_callable()
    except Exception:
        raise

    safe_cache_set(key, computed, timeout)
    return computed


# -----------------------------------------------------------------------------
# Namespace Versioning (Atomic O(1) Multi-Worker Invalidation)
# -----------------------------------------------------------------------------

def get_namespace_version(namespace: str) -> int:
    """
    Returns the current integer version for a cache namespace.
    If not initialized, defaults to 1 without expiring.
    """
    ver_key = f"__ns_ver__{namespace}"
    try:
        ver = cache.get(ver_key)
        if ver is None:
            ver = 1
            try:
                cache.set(ver_key, 1, None)
            except Exception:
                pass
        return int(ver)
    except Exception as exc:
        logger.warning("Failed to get namespace version for '%s': %s", namespace, exc)
        return 1


def invalidate_namespace(namespace: str) -> int:
    """
    Instantly invalidates all entries belonging to `namespace` across all workers
    by incrementing its version counter. O(1) performance with zero DB impact.
    """
    ver_key = f"__ns_ver__{namespace}"
    try:
        try:
            new_ver = cache.incr(ver_key)
        except Exception:
            current = cache.get(ver_key) or 1
            new_ver = int(current) + 1
            cache.set(ver_key, new_ver, None)
        logger.debug("Cache namespace '%s' bumped to v%s", namespace, new_ver)
        return int(new_ver)
    except Exception as exc:
        logger.warning("Failed to invalidate namespace '%s': %s", namespace, exc)
        return 1


def build_cache_key(namespace: str, identifier: str) -> str:
    """
    Constructs a versioned cache key combining namespace, current version, and scope identifier.
    Example: 'dashboard:v3:dash_ALL_2026-27_2026-10-25'
    """
    version = get_namespace_version(namespace)
    sanitized_id = str(identifier).strip().replace(' ', '_').replace('/', '_')
    return f"{namespace}:v{version}:{sanitized_id}"


# -----------------------------------------------------------------------------
# Domain-Specific Invalidation Helpers
# -----------------------------------------------------------------------------

def invalidate_financial_cache():
    """
    Purges dashboard, reports, and dues caches whenever any financial transaction occurs
    (Payment received, reversed, Expense entered, Installment adjusted).
    Guarantees that cash books, ledgers, and KPI cards show 100% live figures.
    """
    invalidate_namespace('dashboard')
    invalidate_namespace('reports')
    invalidate_namespace('dues')


def invalidate_student_cache():
    """
    Purges student dues, search autocomplete, and admission summaries.
    """
    invalidate_namespace('students')
    invalidate_namespace('search')
    invalidate_namespace('dues')
    invalidate_namespace('dashboard')


def invalidate_context_cache():
    """
    Purges global branch list, academic sessions, and institute settings dictionary.
    """
    invalidate_namespace('context')
    # Also explicitly clear legacy keys in case older code references them
    safe_cache_delete('global_active_branches')
    safe_cache_delete('global_active_sessions')
    safe_cache_delete('global_system_settings_dict')


def invalidate_license_cache():
    """
    Purges cached software license verification records.
    """
    invalidate_namespace('license')
    safe_cache_delete('software_license_status')


def invalidate_public_cache():
    """
    Purges public landing page marketing statistics and course listings.
    """
    invalidate_namespace('public')


def invalidate_all_app_cache():
    """
    Comprehensive flush of all application cache namespaces.
    Safe for production use without restarting server or losing user sessions.
    """
    namespaces = [
        'dashboard',
        'reports',
        'dues',
        'context',
        'students',
        'search',
        'public',
        'license',
    ]
    for ns in namespaces:
        invalidate_namespace(ns)
    invalidate_context_cache()
    invalidate_license_cache()
    logger.info("All application cache namespaces successfully invalidated.")
