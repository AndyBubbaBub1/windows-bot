"""Entry point to start the APScheduler for recurring tasks.

This script reads the ``schedule`` section of ``config.yaml`` to
register jobs with the APScheduler.  Each job is defined by a dotted
function path and a cron schedule.  After configuring the scheduler
the script starts it and waits indefinitely.  Use Ctrl+C to stop the
scheduler.
"""

from __future__ import annotations

import time
import logging

# Note: The moex_bot package must be installed (e.g. via ``pip install -e .``)
# for these imports to resolve without modifying sys.path.  See ``setup.py``
# and ``pyproject.toml`` for packaging details.
from moex_bot.core.logging_config import configure_logging
from moex_bot.core.config import load_config
from moex_bot.core.scheduler import create_scheduler


def main() -> None:
    """Run the APScheduler based on the schedule defined in the config."""
    # Configure consistent logging
    configure_logging()
    logger = logging.getLogger(__name__)
    cfg = load_config()
    logger.info("Loaded config.yaml for scheduler")

    sched = create_scheduler(cfg)
    if not sched.get_jobs():
        logger.warning("No jobs defined in config 'schedule'. Exiting.")
        return

    logger.info("Starting scheduler... (Ctrl+C to exit)")
    sched.start()
    try:
        # Keep the main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping scheduler...")
        sched.shutdown()



if __name__ == '__main__':
    main()