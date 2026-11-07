"""Publish one caller-persisted report or batch from JSON stdin.

Usage: python observation-client-example.py --origin https://nexus.example \
           --token-env MY_OBSERVATION_PUBLISH_TOKEN < saved-report.json

The named environment variable contains an already authorized publish token.
Never pass the token as an argument or put it in saved-report.json. Tokens expire
after 15 minutes; obtain replacements through canonical authenticated source
management, outside this helper. A publish token cannot renew itself.

Persist the complete report, including its generation, sequence and observed_at,
BEFORE sending. After outcome_unknown, retain and explicitly resend the same
payload; do not regenerate timestamps or increment sequence to conceal a lost
response. A new observation needs a new caller-persisted sequence. This example
does not infer external activity, qualify Herdr or start a polling daemon.
"""
import argparse
import json
import os
import re
import sys

from okto_nexus.observation_client import ObservationClient, ObservationClientError


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", required=True, help="HTTPS Server origin, or loopback HTTP.")
    parser.add_argument("--token-env", required=True, help="Name of the environment variable holding the publish token.")
    args = parser.parse_args()
    try:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", args.token_env):
            raise ValueError
        raw = sys.stdin.buffer.read(100 * 4096 + 2049)
        if len(raw) > 100 * 4096 + 2048:
            raise ValueError
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_object)
        client = ObservationClient(args.origin, token=os.environ.get(args.token_env))
        result = client.publish(payload)
    except ObservationClientError as error:
        # Error attributes are closed/sanitized. Never echo stdin, the environment
        # value or a raw urllib exception; stdout is reserved for valid receipts.
        print(json.dumps({"code": error.code, "status": error.status,
            "outcome_unknown": error.outcome_unknown,
            "retry_after_seconds": error.retry_after_seconds}), file=sys.stderr)
        return 2
    except (ValueError, UnicodeError, RecursionError):
        print('{"code":"INPUT_INVALID","outcome_unknown":false}', file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
