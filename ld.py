"""LaunchDarkly server-side SDK setup for ABC Pulse.

There is one SDK client per process (the SDK enforces a singleton through
ldclient.get()). It connects once at startup and receives flag updates over
a streaming connection, so later evaluations are local and fast.

If LD_SDK_KEY isn't set, the client runs in offline mode: every evaluation
returns its fallback value, so the app still works without LaunchDarkly.
"""

import atexit
import logging
import os

import ldclient
from ldclient import Context
from ldclient.config import Config
from ldclient.interfaces import DataSourceState

from flags import FALLBACKS

log = logging.getLogger("abc_pulse.ld")

# Seconds to wait for the first flag data at startup before serving fallbacks.
STARTUP_TIMEOUT_SECONDS = 5


def init_ld():
    """Start the LaunchDarkly client once, at app startup."""
    # LD SETUP: Set LD_SDK_KEY in .env to your environment's server-side SDK key
    # (Project settings > Environments > your environment > SDK key).
    sdk_key = os.environ.get("LD_SDK_KEY", "").strip()

    if sdk_key:
        ldclient.set_config(Config(sdk_key))
    else:
        log.warning("LD_SDK_KEY is not set: LaunchDarkly is offline and all flags use fallback values.")
        ldclient.set_config(Config("", offline=True))

    # ldclient.get() creates the client and waits up to STARTUP_TIMEOUT_SECONDS
    # for flag data. If LaunchDarkly is unreachable, it returns anyway and
    # evaluations use their fallback values until a connection succeeds.
    client = ldclient.get()
    if sdk_key and not client.is_initialized():
        log.warning("LaunchDarkly did not initialize within %ss; serving fallback values.",
                    STARTUP_TIMEOUT_SECONDS)

    # Flush pending analytics events and close the stream when the process exits.
    atexit.register(close)
    return client


def evaluate(flag_key, context: Context):
    """Evaluate a flag for a context, using the fallback defined in flags.FALLBACKS.

    Always go through this helper, never ldclient.get().variation() directly,
    so every evaluation in the app has the same safe fallback value.
    """
    return ldclient.get().variation(flag_key, context, FALLBACKS[flag_key])


def status():
    """Describe the server SDK's connection, for the demo panel and troubleshooting."""
    client = ldclient.get()
    if client.is_offline():
        return {"state": "not-configured", "detail": "LD_SDK_KEY not set; using fallback values"}

    ds = client.data_source_status_provider.status
    if ds.state == DataSourceState.VALID:
        return {"state": "connected", "detail": "Streaming flag updates"}

    # The SDK keeps retrying, so a rejected key (e.g. HTTP 401) still reads as
    # "initializing". Report the last error so a bad key is easy to spot.
    if ds.error is not None:
        reason = f"HTTP {ds.error.status_code}" if ds.error.status_code else ds.error.kind.value
        if ds.error.status_code in (401, 403):
            reason += " (check LD_SDK_KEY)"
        return {"state": "error", "detail": f"{reason}; using last known or fallback values"}
    if ds.state == DataSourceState.INITIALIZING:
        return {"state": "connecting", "detail": "Waiting for first flag data"}
    return {"state": "error", "detail": f"Data source is {ds.state.value}; using last known or fallback values"}


def close():
    """Flush events and shut the client down."""
    ldclient.get().close()
