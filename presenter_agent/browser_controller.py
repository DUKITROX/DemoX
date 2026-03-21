"""BrowserController — async queue-based browser action executor.

Decouples Playwright tool execution from the LLM voice pipeline.
The LLM submits fire-and-forget tickets; this controller executes them
sequentially in a background asyncio task while the LLM continues narrating.
"""

import asyncio
import logging
from collections import OrderedDict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

MAX_RESULTS = 50


@dataclass
class BrowserTicket:
    ticket_id: str          # "step_3" or "adhoc_<hex>"
    action: str             # "click" | "scroll" | "scroll_to" | "highlight" | "hover" | "type"
    target_text: str | None = None  # element visible text (None for scroll)
    pixels: int = 400       # for scroll action
    field_label: str = ""   # for type action
    type_value: str = ""    # for type action
    step_number: int | None = None


@dataclass
class BrowserResult:
    ticket_id: str
    success: bool
    message: str
    page_changed: bool = False
    new_url: str = ""


class BrowserController:
    """Executes browser actions from an asyncio.Queue in the background."""

    def __init__(self, screen_share):
        self._screen_share = screen_share
        self._queue: asyncio.Queue[BrowserTicket] = asyncio.Queue()
        self._results: OrderedDict[str, BrowserResult] = OrderedDict()
        self._task: asyncio.Task | None = None

    def start(self):
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run_loop())
            logger.info("BrowserController started")

    async def stop(self):
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        # Drain queue
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        self._results.clear()
        logger.info("BrowserController stopped")

    def submit(self, ticket: BrowserTicket) -> str:
        self._queue.put_nowait(ticket)
        logger.info(f"Ticket submitted: {ticket.ticket_id} ({ticket.action} '{ticket.target_text}')")
        return ticket.ticket_id

    def get_result(self, ticket_id: str) -> BrowserResult | None:
        return self._results.get(ticket_id)

    async def _run_loop(self):
        try:
            while True:
                ticket = await self._queue.get()
                result = await self._execute(ticket)
                # Store result in bounded dict
                self._results[ticket.ticket_id] = result
                while len(self._results) > MAX_RESULTS:
                    self._results.popitem(last=False)
                self._queue.task_done()
        except asyncio.CancelledError:
            logger.info("BrowserController loop cancelled")

    async def _execute(self, ticket: BrowserTicket) -> BrowserResult:
        url_before = await self._screen_share.get_current_url()
        try:
            if ticket.action == "click":
                await self._screen_share.click(ticket.target_text or "")
            elif ticket.action == "scroll":
                await self._screen_share.scroll_down(ticket.pixels)
            elif ticket.action == "scroll_to":
                await self._screen_share.scroll_to_element(ticket.target_text or "")
            elif ticket.action == "highlight":
                await self._screen_share.highlight_element(ticket.target_text or "")
            elif ticket.action == "hover":
                await self._screen_share.hover(ticket.target_text or "")
            elif ticket.action == "type":
                await self._screen_share.type_in_field(ticket.field_label, ticket.type_value)
            else:
                return BrowserResult(
                    ticket_id=ticket.ticket_id,
                    success=False,
                    message=f"Unknown action: {ticket.action}",
                )

            url_after = await self._screen_share.get_current_url()
            page_changed = url_after != url_before

            msg = f"{ticket.action} '{ticket.target_text}' succeeded"
            if page_changed:
                msg += f" — navigated to {url_after}"

            logger.info(f"Ticket {ticket.ticket_id}: {msg}")
            return BrowserResult(
                ticket_id=ticket.ticket_id,
                success=True,
                message=msg,
                page_changed=page_changed,
                new_url=url_after if page_changed else "",
            )

        except Exception as e:
            msg = f"{ticket.action} '{ticket.target_text}' failed: {e}"
            logger.warning(f"Ticket {ticket.ticket_id}: {msg}")
            return BrowserResult(
                ticket_id=ticket.ticket_id,
                success=False,
                message=msg,
            )
