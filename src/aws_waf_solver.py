"""AWS WAF Captcha solver via CapSolver.

Used by `ecourts_scraper.py` to bypass the "Human Verification" gate on
portal-nc.tylertech.cloud (the NC eCourts Smart Search portal).

The WAF page exposes a `window.gokuProps` object with three values needed
by any AWS WAF solver:
  - key     (the WAF API key)
  - iv      (initialization vector)
  - context (encrypted state token)

CapSolver's `AntiAwsWafTaskProxyLess` task takes these + the page URL and
returns a voucher token. The voucher is fed to the page's own
`ChallengeScript.submitCaptcha(voucher)` handler, which sets the
`aws-waf-token` cookie and reloads. Cookie typically lives 1-24 hours, so
one solve per browser session is plenty.

Why CapSolver instead of 2Captcha (the existing service for reCAPTCHA v2):
2Captcha workers returned ERROR_CAPTCHA_UNSOLVABLE on two consecutive
fresh challenges from this specific portal — their pool doesn't reliably
handle the WAF puzzle variant deployed here. CapSolver advertises AWS WAF
as a specialty service and uses a different solver pool.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)


CAPSOLVER_BASE = "https://api.capsolver.com"


class WAFSolveError(RuntimeError):
    """CapSolver failed to solve the AWS WAF challenge."""


def solve_aws_waf(
    *,
    api_key: str,
    site_url: str,
    aws_key: str,
    aws_iv: str,
    aws_context: str,
    timeout: float = 180.0,
    poll_interval: float = 3.0,
) -> dict:
    """Solve an AWS WAF challenge via CapSolver.

    Returns a dict: {voucher, userAgent, headers, raw}.
    The voucher is the aws-waf-token cookie value. The userAgent is what
    CapSolver used to solve it — the caller MUST use the same UA on the
    browser context, otherwise the WAF rejects the cookie.

    Args:
        api_key:    CapSolver API key (CAP-...)
        site_url:   Full URL of the page where the WAF gate appears
        aws_key:    Value of window.gokuProps.key
        aws_iv:     Value of window.gokuProps.iv
        aws_context: Value of window.gokuProps.context
        timeout:    Seconds to wait for solve (typical 5-60s)
        poll_interval: Seconds between status checks

    Raises:
        WAFSolveError on any failure (network, timeout, solver error).
    """
    if not api_key:
        raise WAFSolveError("CAPSOLVER_API_KEY not set")

    # Step 1 — create task
    create_body: dict[str, Any] = {
        "clientKey": api_key,
        "task": {
            "type": "AntiAwsWafTaskProxyLess",
            "websiteURL": site_url,
            "awsKey": aws_key,
            "awsIv": aws_iv,
            "awsContext": aws_context,
        },
    }
    logger.info("CapSolver: creating AWS WAF task for %s", site_url)
    try:
        r = requests.post(f"{CAPSOLVER_BASE}/createTask", json=create_body, timeout=30)
    except Exception as e:
        raise WAFSolveError(f"createTask network error: {e}") from e
    if r.status_code != 200:
        raise WAFSolveError(f"createTask HTTP {r.status_code}: {r.text[:200]}")
    payload = r.json()
    if payload.get("errorId"):
        raise WAFSolveError(
            f"createTask errorId={payload.get('errorId')} code={payload.get('errorCode')} "
            f"desc={payload.get('errorDescription')}"
        )
    task_id = payload.get("taskId")
    if not task_id:
        raise WAFSolveError(f"createTask returned no taskId: {payload}")
    logger.info("CapSolver: taskId=%s", task_id)

    # Step 2 — poll for result
    deadline = time.monotonic() + timeout
    last_status = ""
    while time.monotonic() < deadline:
        time.sleep(poll_interval)
        try:
            rr = requests.post(
                f"{CAPSOLVER_BASE}/getTaskResult",
                json={"clientKey": api_key, "taskId": task_id},
                timeout=30,
            )
        except Exception as e:
            logger.warning("CapSolver: getTaskResult network err: %s (retrying)", e)
            continue
        if rr.status_code != 200:
            logger.warning(
                "CapSolver: getTaskResult HTTP %d: %s (retrying)",
                rr.status_code, rr.text[:200],
            )
            continue
        rpayload = rr.json()
        if rpayload.get("errorId"):
            raise WAFSolveError(
                f"getTaskResult errorId={rpayload.get('errorId')} "
                f"code={rpayload.get('errorCode')} desc={rpayload.get('errorDescription')}"
            )
        status = rpayload.get("status", "")
        if status != last_status:
            logger.info("CapSolver: task %s status=%s", task_id, status)
            last_status = status
        if status == "ready":
            solution = rpayload.get("solution", {}) or {}
            # CapSolver's WAF solution shape: {cookie, headers?, userAgent?}.
            # The voucher cookie is bound to the userAgent / proxy that solved
            # the puzzle, so callers MUST use the returned userAgent.
            voucher = (
                solution.get("cookie")
                or solution.get("token")
                or solution.get("captcha_voucher")
                or solution.get("verifiedToken")
            )
            if not voucher:
                raise WAFSolveError(f"task ready but no voucher in solution: {solution}")
            logger.info("CapSolver: solved (voucher %d chars, ua=%s)",
                        len(voucher), (solution.get("userAgent") or "")[:60])
            return {
                "voucher": voucher,
                "userAgent": solution.get("userAgent", ""),
                "headers": solution.get("headers", {}) or {},
                "raw": solution,
            }
        # status == "processing" — keep polling

    raise WAFSolveError(f"timed out after {timeout}s (last status={last_status!r})")
