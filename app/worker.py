import argparse
import asyncio
import logging
import sys

from app.agent import run_agent
from app.config import get_settings

logger = logging.getLogger("briefly")


def main() -> int:
    parser = argparse.ArgumentParser(description="Briefly: a daily tech news digest by email.")
    parser.add_argument(
        "--send",
        action="store_true",
        help="send the digest by email and record its articles as sent (default: preview only)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    try:
        settings = get_settings()
        result = asyncio.run(run_agent(settings, should_send=args.send))
    except Exception as error:
        logger.error("Agent run failed: %s", str(error) or repr(error))
        return 1

    if result.email:
        print(result.email.text)
    return 0


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    sys.exit(main())