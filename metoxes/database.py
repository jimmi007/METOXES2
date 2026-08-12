import databases
import sqlalchemy

from metoxes.config import config


metadata = sqlalchemy.MetaData()


stock_table = sqlalchemy.Table(
    "stocks",
    metadata,

    sqlalchemy.Column(
        "id",
        sqlalchemy.Integer,
        primary_key=True,
    ),

    sqlalchemy.Column(
        "purchase_date",
        sqlalchemy.Date,
        nullable=False,
    ),

    sqlalchemy.Column(
        "sector",
        sqlalchemy.String,
        nullable=False,
    ),

    sqlalchemy.Column(
        "symbol",
        sqlalchemy.String,
        nullable=False,
    ),

    sqlalchemy.Column(
        "platform",
        sqlalchemy.String,
        nullable=False,
    ),

    sqlalchemy.Column(
        "purchase_price",
        sqlalchemy.Float,
        nullable=False,
    ),

    sqlalchemy.Column(
        "quantity",
        sqlalchemy.Float,
        nullable=False,
    ),

    sqlalchemy.Column(
        "current_price",
        sqlalchemy.Float,
        nullable=True,
    ),

    sqlalchemy.Column(
        "profit_loss",
        sqlalchemy.Float,
        nullable=True,
    ),
)


if not config.DATABASE_URL:
    raise RuntimeError("DATABASE_URL is missing")

if not config.SYNC_DATABASE_URL:
    raise RuntimeError("SYNC_DATABASE_URL is missing")


engine = sqlalchemy.create_engine(
    config.SYNC_DATABASE_URL
)


metadata.create_all(engine)


database = databases.Database(
    config.DATABASE_URL,
    force_rollback=config.DB_FORCE_ROLL_BACK,
)