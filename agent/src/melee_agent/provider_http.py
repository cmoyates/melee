"""One private HTTP exchange with an independent wall-clock alarm, then exit."""

import json
import signal
import sys
import urllib.error
import urllib.request

from .provider import ENDPOINT, MAX_BODY_BYTES, MAX_RESPONSE_BYTES


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main():
    def expired(signum, frame):
        raise TimeoutError()
    try:
        message = json.loads(sys.stdin.buffer.read(MAX_BODY_BYTES * 2))
        timeout = message["timeout"]
        if type(timeout) not in (int, float) or not 0 < timeout <= 30:
            return 1
        signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, timeout)
        payload = message["payload"].encode()
        if len(payload) > MAX_BODY_BYTES:
            return 1
        request = urllib.request.Request(ENDPOINT, data=payload,
            headers={"Authorization": "Bearer " + message["key"], "Content-Type": "application/json"})
        opener = urllib.request.build_opener(NoRedirect())
        try:
            response = opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as error:
            with error:
                report = {"status": error.code, "headers": {"Retry-After": error.headers.get("Retry-After", "1")}, "body": ""}
        else:
            with response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
                if len(body) > MAX_RESPONSE_BYTES:
                    return 1
                report = {"status": response.status, "headers": {}, "body": body.decode()}
        print(json.dumps(report, allow_nan=False))
        return 0
    except Exception:
        return 1  # No exception text: it could include credentials or request content.


if __name__ == "__main__":
    raise SystemExit(main())
