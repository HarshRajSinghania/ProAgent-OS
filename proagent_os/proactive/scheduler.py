from __future__ import annotations

import asyncio
import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from proagent_os.proactive.monitors import MonitorService

logger = logging.getLogger("proagent.scheduler")


class ProactiveScheduler:
    def __init__(self, poll_seconds: int = 30) -> None:
        self.poll_seconds = poll_seconds
        self.scheduler = AsyncIOScheduler()
        self.monitors = MonitorService()
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self.scheduler.add_job(self._tick, "interval", seconds=self.poll_seconds, id="monitor_tick", replace_existing=True)
        self.scheduler.start()
        self._started = True
        logger.info("Proactive scheduler started (poll=%ss)", self.poll_seconds)

    def shutdown(self) -> None:
        if self._started:
            self.scheduler.shutdown(wait=False)
            self._started = False

    async def _tick(self) -> None:
        due = self.monitors.due_monitors()
        for mon in due:
            try:
                # Respect per-monitor interval via last_run_at check
                last = mon.get("last_run_at")
                interval = int(mon.get("interval_seconds") or 60)
                if last:
                    from datetime import datetime, timezone

                    try:
                        last_dt = datetime.fromisoformat(last)
                        if last_dt.tzinfo is None:
                            last_dt = last_dt.replace(tzinfo=timezone.utc)
                        age = (datetime.now(timezone.utc) - last_dt).total_seconds()
                        if age < interval:
                            continue
                    except Exception:  # noqa: BLE001
                        pass
                await self.monitors.run_once(mon["tenant_id"], mon["id"])
                logger.info("Ran monitor %s for tenant %s", mon["id"], mon["tenant_id"])
            except Exception:  # noqa: BLE001
                logger.exception("Monitor run failed: %s", mon.get("id"))


async def run_worker_forever(poll_seconds: int = 30) -> None:
    logging.basicConfig(level=logging.INFO)
    sched = ProactiveScheduler(poll_seconds=poll_seconds)
    sched.start()
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        sched.shutdown()
