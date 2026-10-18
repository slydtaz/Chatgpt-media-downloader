from __future__ import annotations

from .config import ensure_dirs, ensure_install_id, VERSION
from .platform import detect_system, is_supported
from .gui import run
from .logging_utils import setup_logging
from .config import LOG_DIR


def main() -> None:
    ensure_dirs()
    ensure_install_id()
    system = detect_system()
    logger = setup_logging(LOG_DIR)
    logger.info("Aplicação %s iniciada em %s", VERSION, system.architecture_label)
    if not is_supported(system):
        logger.warning("Arquitetura não mapeada explicitamente: %s", system.architecture_label)
    run()


if __name__ == "__main__":
    main()
