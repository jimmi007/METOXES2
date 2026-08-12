import logging
from logging.config import dictConfig

from metoxes.config import DevConfig, ProdConfig, config


def obfuscated(email: str, obfuscated_length: int) -> str:
    if not isinstance(email, str) or "@" not in email:
        return str(email)

    first, last = email.split("@", 1)
    visible = first[:obfuscated_length]

    return (
        visible
        + ("*" * max(len(first) - obfuscated_length, 0))
        + "@"
        + last
    )


class EmailObfuscationFilter(logging.Filter):
    def __init__(
        self,
        name: str = "",
        obfuscated_length: int = 2,
    ) -> None:
        super().__init__(name)
        self.obfuscated_length = obfuscated_length

    def filter(self, record: logging.LogRecord) -> bool:
        if hasattr(record, "email"):
            record.email = obfuscated(
                record.email,
                self.obfuscated_length,
            )

        return True


def configure_logging() -> None:
    is_dev = isinstance(config, DevConfig)
    is_prod = isinstance(config, ProdConfig)

    metoxes_handlers = ["console"]

    if is_dev:
        metoxes_handlers.append("rotating_file")

    if is_prod and config.LOGTAIL_API_KEY:
        metoxes_handlers.append("logtail")

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,

            "filters": {
                "correlation_id": {
                    "()": "asgi_correlation_id.CorrelationIdFilter",
                    "uuid_length": 8 if is_dev else 32,
                    "default_value": "-",
                },
                "email_obfuscation": {
                    "()": EmailObfuscationFilter,
                    "obfuscated_length": 2 if is_dev else 0,
                },
            },

            "formatters": {
                "console": {
                    "class": "logging.Formatter",
                    "datefmt": "%Y-%m-%d %H:%M:%S",
                    "format": (
                        "%(asctime)s | %(levelname)s | "
                        "%(correlation_id)s | %(name)s:%(lineno)d | "
                        "%(message)s"
                    ),
                },
                "json": {
                    "class": "pythonjsonlogger.jsonlogger.JsonFormatter",
                    "format": (
                        "%(asctime)s %(levelname)s "
                        "%(correlation_id)s %(name)s "
                        "%(lineno)d %(message)s"
                    ),
                },
            },

            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "level": "DEBUG" if is_dev else "INFO",
                    "formatter": "console",
                    "filters": [
                        "correlation_id",
                        "email_obfuscation",
                    ],
                    "stream": "ext://sys.stdout",
                },

                "rotating_file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "level": "DEBUG",
                    "formatter": "json",
                    "filename": "metoxes.log",
                    "maxBytes": 1024 * 1024,
                    "backupCount": 5,
                    "encoding": "utf8",
                    "filters": [
                        "correlation_id",
                        "email_obfuscation",
                    ],
                },

                "logtail": {
                    "class": "logtail.LogtailHandler",
                    "level": "INFO",
                    "formatter": "console",
                    "filters": [
                        "correlation_id",
                        "email_obfuscation",
                    ],
                    "source_token": config.LOGTAIL_API_KEY,
                },
            },

            "root": {
                "handlers": ["console"],
                "level": "INFO",
            },

            "loggers": {
                "uvicorn": {
                    "handlers": ["console"],
                    "level": "INFO",
                    "propagate": False,
                },

                "uvicorn.error": {
                    "handlers": ["console"],
                    "level": "INFO",
                    "propagate": False,
                },

                "uvicorn.access": {
                    "handlers": ["console"],
                    "level": "INFO",
                    "propagate": False,
                },

                "metoxes": {
                    "handlers": metoxes_handlers,
                    "level": "DEBUG" if is_dev else "INFO",
                    "propagate": False,
                },

                "databases": {
                    "handlers": ["console"],
                    "level": "WARNING",
                    "propagate": False,
                },

                "aiosqlite": {
                    "handlers": ["console"],
                    "level": "WARNING",
                    "propagate": False,
                },

                "sqlalchemy.engine": {
                    "handlers": ["console"],
                    "level": "WARNING",
                    "propagate": False,
                },
            },
        }
    )