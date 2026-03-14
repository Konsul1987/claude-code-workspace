from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any
from urllib.parse import unquote

import httpx
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Implementation

from .auth import TokenProvider, create_token_provider
from .config import ProxyConfig

_MAX_RECONNECT_ATTEMPTS = 10
_RECONNECT_BASE_DELAY = 2.0
_RECONNECT_MAX_DELAY = 60.0
_SESSION_ACQUIRE_TIMEOUT = 30.0
_HANDLER_MAX_RETRIES = 2


class _AsyncBearerAuth(httpx.Auth):
    def __init__(self, token_provider: TokenProvider) -> None:
        self._token_provider = token_provider

    async def async_auth_flow(self, request: httpx.Request) -> Any:
        token = await self._token_provider.get_token()
        request.headers["Authorization"] = f"Bearer {token}"
        yield request


class _SessionManager:
    """Manages the remote BC session with reconnect support.

    Uses a replace-on-reconnect pattern for the ready event to avoid
    race conditions between _get_session and _run_remote_loop.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._session: ClientSession | None = None
        self._ready = asyncio.Event()

    async def get_session(self) -> ClientSession:
        """Wait for and return an active session.

        Raises TimeoutError if no session becomes available within the
        configured timeout.
        """
        while True:
            async with self._lock:
                if self._session is not None:
                    return self._session
                ready = self._ready  # snapshot under lock
            await asyncio.wait_for(ready.wait(), timeout=_SESSION_ACQUIRE_TIMEOUT)

    async def set_session(self, session: ClientSession) -> None:
        async with self._lock:
            self._session = session
            self._ready.set()

    async def clear_session(self, expected: ClientSession | None = None) -> None:
        """Clear the current session and create a fresh ready event.

        If *expected* is given, only clear if the current session matches
        (compare-and-swap semantics to avoid clearing a fresh reconnect).
        """
        async with self._lock:
            if expected is not None and self._session is not expected:
                return
            self._session = None
            self._ready = asyncio.Event()


async def run_proxy(config: ProxyConfig) -> None:
    logger = logging.getLogger("bc_mcp_proxy")
    if config.enable_debug:
        logger.setLevel(logging.DEBUG)

    token_provider = create_token_provider(config, logger=logger)
    headers = _build_transport_headers(config)
    url = _build_endpoint_url(config)
    auth = _AsyncBearerAuth(token_provider)

    instructions = config.instructions or (
        "Bridge MCP stdio clients to Microsoft Dynamics 365 Business Central."
        " All tool definitions and executions are forwarded to the configured Business"
        " Central environment."
    )

    mgr = _SessionManager()

    async def _run_remote_loop() -> None:
        """Maintain the BC connection, reconnecting on failure."""
        attempt = 0
        while True:
            try:
                logger.info("Connecting to BC at %s (attempt %d)", url, attempt + 1)
                async with streamablehttp_client(
                    url=url,
                    headers=headers,
                    timeout=config.http_timeout_seconds,
                    sse_read_timeout=config.sse_timeout_seconds,
                    auth=auth,
                ) as (remote_read, remote_write, _get_session_id):
                    client_info = Implementation(
                        name=config.server_name, version=config.server_version
                    )
                    async with ClientSession(
                        remote_read, remote_write, client_info=client_info
                    ) as remote_session:
                        await remote_session.initialize()
                        logger.info("Connected to BC (attempt %d)", attempt + 1)
                        await mgr.set_session(remote_session)
                        attempt = 0

                        # Block until the remote stream ends, which signals
                        # that the BC connection has dropped.
                        async for _message in remote_read:
                            pass

                # If we exit normally the connection was closed by the server.
                logger.warning("BC connection closed by remote end.")
                await mgr.clear_session()

            except asyncio.CancelledError:
                await mgr.clear_session()
                return

            except Exception as exc:
                await mgr.clear_session()
                attempt += 1
                if attempt > _MAX_RECONNECT_ATTEMPTS:
                    logger.error(
                        "Giving up after %d attempts: %s",
                        _MAX_RECONNECT_ATTEMPTS,
                        exc,
                    )
                    return
                delay = min(
                    _RECONNECT_BASE_DELAY * (2 ** (attempt - 1)),
                    _RECONNECT_MAX_DELAY,
                )
                logger.warning(
                    "BC lost (%s). Reconnecting in %.0fs (%d/%d)...",
                    exc,
                    delay,
                    attempt,
                    _MAX_RECONNECT_ATTEMPTS,
                )
                await asyncio.sleep(delay)

        # Unreachable in normal flow, but if _run_remote_loop returns after
        # exhausting retries the stdio server should shut down too.
        logger.error("Remote loop exited – terminating proxy.")

    server = Server(
        name=config.server_name,
        version=config.server_version,
        instructions=instructions,
    )

    @server.list_tools()
    async def _list_tools() -> Any:
        last_exc: Exception | None = None
        for _ in range(_HANDLER_MAX_RETRIES):
            session = await mgr.get_session()
            try:
                result = await session.list_tools()
                return result.tools
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_exc = exc
                logger.warning("list_tools failed (%s), retrying...", exc)
                await mgr.clear_session(expected=session)
        raise ConnectionError(
            f"BC unavailable after {_HANDLER_MAX_RETRIES} retries"
        ) from last_exc

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any]) -> Any:
        last_exc: Exception | None = None
        for _ in range(_HANDLER_MAX_RETRIES):
            session = await mgr.get_session()
            try:
                return await session.call_tool(name, arguments or {})
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_exc = exc
                logger.warning("call_tool(%s) failed (%s), retrying...", name, exc)
                await mgr.clear_session(expected=session)
        raise ConnectionError(
            f"BC unavailable after {_HANDLER_MAX_RETRIES} retries"
        ) from last_exc

    init_options = server.create_initialization_options()

    async with stdio_server() as (local_read, local_write):
        remote_task = asyncio.create_task(_run_remote_loop())

        def _on_remote_done(task: asyncio.Task[None]) -> None:
            if task.cancelled():
                return
            exc = task.exception()
            if exc:
                logger.error("Remote loop crashed: %s", exc)
            else:
                logger.error("Remote loop exited – giving up.")
            # Shut down the stdio server so the process terminates
            # instead of hanging with no BC backend.
            sys.exit(1)

        remote_task.add_done_callback(_on_remote_done)

        try:
            await server.run(local_read, local_write, init_options)
        finally:
            remote_task.cancel()
            try:
                await remote_task
            except asyncio.CancelledError:
                pass


def _build_transport_headers(config: ProxyConfig) -> dict[str, str]:
    headers: dict[str, str] = {"X-Client-Application": config.server_name}
    if config.company:
        headers["Company"] = unquote(config.company)
    if config.configuration_name:
        headers["ConfigurationName"] = unquote(config.configuration_name)
    return headers


def _build_endpoint_url(config: ProxyConfig) -> str:
    base = config.base_url.rstrip("/")
    return f"{base}/v2.0/{config.environment}/mcp"


def run_sync(config: ProxyConfig) -> None:
    asyncio.run(run_proxy(config))
