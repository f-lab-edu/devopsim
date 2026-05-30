import logging
import sys

from detector.config import Config

logger = logging.getLogger("detector")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    config = Config.from_env()
    logger.info(
        "detector starting model=%s namespaces=%s dry_run=%s max_steps=%d",
        config.model,
        config.allowed_namespaces,
        config.dry_run,
        config.max_steps,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
