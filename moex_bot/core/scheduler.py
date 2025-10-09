"""Task scheduler for recurring operations.

This module wraps APScheduler to schedule recurring jobs such as
daily backtests and report generation.  The schedule is specified
via the configuration file under the ``schedule`` key.  Each job can
define a cron expression, a list of weekdays or a fixed interval.

Note: In this code example the scheduler is configured but not started
automatically.  Users can import ``create_scheduler`` in their
``run_scheduler.py`` script and start it explicitly.
"""

from __future__ import annotations

from typing import Callable, Dict, Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import structlog


logger = structlog.get_logger(__name__)


def create_scheduler(cfg: Dict[str, Any]) -> BackgroundScheduler:
    """Create and configure an APScheduler from a configuration.

    The configuration should contain a ``schedule`` dictionary where
    each key is a job name and each value is a mapping with keys:

    * ``func``: dotted path to the function to run.
    * ``cron``: cron expression string (e.g. ``'0 8 * * *'``) or
      dict (e.g. ``{'hour': 8}``).
    * ``args``: optional tuple of positional arguments.
    * ``kwargs``: optional dict of keyword arguments.

    Returns:
        A configured ``BackgroundScheduler`` instance.
    """
    sched = BackgroundScheduler()
    for name, job_cfg in (cfg.get('schedule') or {}).items():
        func_path = job_cfg.get('func')
        cron = job_cfg.get('cron', {})
        args = job_cfg.get('args', [])
        kwargs = job_cfg.get('kwargs', {})
        try:
            module_name, func_name = func_path.rsplit('.', 1)
            mod = __import__(module_name, fromlist=[func_name])
            func: Callable = getattr(mod, func_name)
        except Exception as e:
            logger.error("failed to import scheduled function", func=func_path, error=str(e))
            continue
        try:
            trigger = CronTrigger(**cron) if isinstance(cron, dict) else CronTrigger.from_crontab(cron)
        except Exception as e:
            logger.error("invalid cron definition", job=name, error=str(e))
            continue
        sched.add_job(func, trigger, args=args, kwargs=kwargs, id=name, name=name)
    return sched

__all__ = ['create_scheduler']