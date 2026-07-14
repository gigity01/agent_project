# app/db/uow/sqlalchemy.py


from collections.abc import Callable

from sqlalchemy.orm import Session

session_factory = Callable[[], Session]