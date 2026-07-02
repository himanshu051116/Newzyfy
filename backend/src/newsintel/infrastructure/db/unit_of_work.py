from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from newsintel.application.acquisition.ports import AcquisitionUnitOfWork
from newsintel.infrastructure.db.acquisition_repositories import (
    SqlAlchemyChannelRepository,
    SqlAlchemyFrontierRepository,
    SqlAlchemyOutboxRepository,
    SqlAlchemyPublisherRepository,
)


class SqlAlchemyAcquisitionUnitOfWork(AcquisitionUnitOfWork):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> "SqlAlchemyAcquisitionUnitOfWork":
        self._session = self._session_factory()
        self.publishers = SqlAlchemyPublisherRepository(self._session)
        self.channels = SqlAlchemyChannelRepository(self._session)
        self.frontier = SqlAlchemyFrontierRepository(self._session)
        self.outbox = SqlAlchemyOutboxRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if not self._session:
            return
        if exc:
            await self._session.rollback()
        await self._session.close()
        self._session = None

    async def commit(self) -> None:
        if not self._session:
            raise RuntimeError("unit of work is not active")
        await self._session.commit()

    async def rollback(self) -> None:
        if not self._session:
            raise RuntimeError("unit of work is not active")
        await self._session.rollback()

