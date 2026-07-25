#!/usr/bin/env python3
"""Discord REST client for the Timbz Loop.

Deliberately REST-only — no gateway, no websocket, no persistent process. The
loop posts a message and later *polls* its reactions, which means the whole
approval path survives the Mac being asleep and costs nothing to run.

Used from two places:
  * the local Claude Code loop (timbz-ideate / timbz-ship) to post
  * .github/workflows/timbz-gate.yml to read reactions back

Auth: DISCORD_BOT_TOKEN in the environment. Bot needs Send Messages,
Attach Files, Read Message History and Add Reactions in the target channel.

CLI:
    python scripts/timbz_discord.py post --kind ship --body-file post.md \
        --image before.png --image after.png
    python scripts/timbz_discord.py reactions --message-id 123
    python scripts/timbz_discord.py reply --message-id 123 --text "Merged."
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

import httpx

API = "https://discord.com/api/v10"
REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / ".timbz" / "config.json"

# Discord hard-caps message content at 2000 characters.
MAX_CONTENT = 2000


class DiscordError(RuntimeError):
    pass


def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path) as fh:
        return json.load(fh)


def _load_dotenv(path: Path = REPO_ROOT / ".env") -> None:
    """Pick up DISCORD_BOT_TOKEN from .env when running locally.

    The environment always wins — in GitHub Actions the token comes from a
    repository secret and there is no .env at all. Only the keys we need are
    read; this is not a general dotenv loader.
    """
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key in ("DISCORD_BOT_TOKEN", "GITHUB_TOKEN") and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def _token() -> str:
    _load_dotenv()
    tok = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not tok:
        raise DiscordError(
            "DISCORD_BOT_TOKEN is not set. Locally: put it in .env. "
            "In CI: add it as a GitHub Actions repository secret.")
    return tok


class Discord:
    """Minimal Discord REST wrapper with rate-limit handling."""

    def __init__(self, token: Optional[str] = None, timeout: float = 20.0):
        self._headers = {
            "Authorization": f"Bot {token or _token()}",
            "User-Agent": "TimbzLoop (https://github.com/timspiller/timbz-loop, 1.0)",
        }
        self._client = httpx.Client(timeout=timeout)

    def __enter__(self) -> "Discord":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # -- transport ---------------------------------------------------------

    def _request(self, method: str, path: str, *, attempts: int = 4,
                 **kw: Any) -> Any:
        """One API call, retrying on 429 and 5xx.

        Discord returns retry_after in seconds on 429; respecting it is the
        difference between a working bot and a temporarily banned one.
        """
        url = f"{API}{path}"
        last_error = ""
        for attempt in range(attempts):
            resp = self._client.request(method, url, headers=self._headers, **kw)

            if resp.status_code == 429:
                body = _safe_json(resp)
                wait = float(body.get("retry_after", 1.0)) if body else 1.0
                time.sleep(min(wait, 30.0))
                last_error = "rate limited"
                continue

            if resp.status_code >= 500:
                time.sleep(2 ** attempt)
                last_error = f"{resp.status_code} from Discord"
                continue

            if resp.status_code >= 400:
                raise DiscordError(
                    f"{method} {path} failed: {resp.status_code} {resp.text[:400]}")

            if resp.status_code == 204 or not resp.content:
                return None
            return resp.json()

        raise DiscordError(f"{method} {path} gave up after {attempts} attempts: {last_error}")

    # -- messages ----------------------------------------------------------

    def post_message(self, channel_id: str, content: str,
                     images: Optional[list[Path]] = None) -> dict:
        """Post to a channel, optionally with image attachments.

        Content over Discord's 2000-char limit is truncated with a marker
        rather than silently dropped — a half-posted approval request that
        looks complete is a way to get a ✅ on something unread.
        """
        content = _truncate(content, MAX_CONTENT)
        payload: dict[str, Any] = {"content": content,
                                   "allowed_mentions": {"parse": []}}

        if not images:
            return self._request("POST", f"/channels/{channel_id}/messages",
                                 json=payload)

        files = []
        attachments = []
        for i, img in enumerate(images):
            img = Path(img)
            if not img.exists():
                raise DiscordError(f"attachment not found: {img}")
            ctype = mimetypes.guess_type(img.name)[0] or "application/octet-stream"
            files.append((f"files[{i}]", (img.name, img.read_bytes(), ctype)))
            attachments.append({"id": i, "filename": img.name})
        payload["attachments"] = attachments

        return self._request(
            "POST", f"/channels/{channel_id}/messages",
            data={"payload_json": json.dumps(payload)}, files=files)

    def reply(self, channel_id: str, message_id: str, text: str) -> dict:
        """Reply in-line to a message, so outcomes thread under the request."""
        return self._request(
            "POST", f"/channels/{channel_id}/messages",
            json={
                "content": _truncate(text, MAX_CONTENT),
                "message_reference": {"message_id": str(message_id),
                                      "fail_if_not_exists": False},
                "allowed_mentions": {"parse": []},
            })

    def get_message(self, channel_id: str, message_id: str) -> dict:
        return self._request(
            "GET", f"/channels/{channel_id}/messages/{message_id}")

    # -- reactions ---------------------------------------------------------

    def add_reaction(self, channel_id: str, message_id: str, emoji: str) -> None:
        """Pre-seed a reaction so approving is one tap, not a search."""
        self._request(
            "PUT",
            f"/channels/{channel_id}/messages/{message_id}"
            f"/reactions/{quote(emoji)}/@me")

    def reaction_users(self, channel_id: str, message_id: str,
                       emoji: str) -> list[str]:
        """User ids who reacted with `emoji`. Empty list if nobody did."""
        users = self._request(
            "GET",
            f"/channels/{channel_id}/messages/{message_id}"
            f"/reactions/{quote(emoji)}?limit=100")
        return [str(u["id"]) for u in (users or [])]

    def all_reactions(self, channel_id: str, message_id: str,
                      emojis: list[str]) -> dict[str, list[str]]:
        """{emoji: [user_id, ...]} for the emoji we actually care about.

        Only the configured emoji are queried — a random 🎉 from someone in the
        channel is not a signal and should not cost an API call.
        """
        out: dict[str, list[str]] = {}
        summary = self.get_message(channel_id, message_id).get("reactions") or []
        present = {r["emoji"]["name"] for r in summary if r["emoji"].get("name")}
        for emoji in emojis:
            if emoji in present:
                out[emoji] = self.reaction_users(channel_id, message_id, emoji)
        return out


def _safe_json(resp: httpx.Response) -> dict:
    try:
        return resp.json()
    except ValueError:
        return {}


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    marker = "\n… (truncated — read the PR)"
    return text[: limit - len(marker)] + marker


# -- CLI -------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Timbz Loop Discord client")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_post = sub.add_parser("post", help="post a message to the loop channel")
    p_post.add_argument("--body-file", required=True, type=Path)
    p_post.add_argument("--kind", choices=["idea", "ship", "plain"],
                        default="plain",
                        help="pre-seeds that kind's emoji on the message")
    p_post.add_argument("--image", action="append", type=Path, default=[])

    p_react = sub.add_parser("reactions", help="dump reactions on a message")
    p_react.add_argument("--message-id", required=True)
    p_react.add_argument("--kind", choices=["idea", "ship"], default="ship")

    p_reply = sub.add_parser("reply", help="reply to a message")
    p_reply.add_argument("--message-id", required=True)
    p_reply.add_argument("--text", required=True)

    args = ap.parse_args(argv)
    cfg = load_config()
    channel = cfg["discord"]["channel_id"]
    if not channel:
        print("discord.channel_id is empty in .timbz/config.json — "
              "see .timbz/SETUP.md", file=sys.stderr)
        return 2

    with Discord() as dc:
        if args.cmd == "post":
            msg = dc.post_message(channel, args.body_file.read_text(),
                                  images=args.image)
            if args.kind in ("idea", "ship"):
                for emoji in cfg["emoji"][args.kind]:
                    dc.add_reaction(channel, msg["id"], emoji)
            print(json.dumps({"message_id": msg["id"]}))

        elif args.cmd == "reactions":
            emojis = list(cfg["emoji"][args.kind])
            print(json.dumps(
                dc.all_reactions(channel, args.message_id, emojis), indent=2))

        elif args.cmd == "reply":
            dc.reply(channel, args.message_id, args.text)
            print("ok")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
