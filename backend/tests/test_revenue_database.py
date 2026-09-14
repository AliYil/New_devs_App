import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database_pool import DatabasePool
from app.services.cache import get_revenue_summary
from app.services.reservations import calculate_total_revenue


class RevenueDatabaseTest(unittest.IsolatedAsyncioTestCase):
    async def test_configured_async_pool_is_reused_and_sessions_open(self):
        pool = DatabasePool()
        with patch("app.core.database_pool.settings.database_url",
                   "postgresql://postgres:postgres@localhost:5433/propertyflow"):
            try:
                await pool.initialize()
                engine = pool.engine
                self.assertEqual(engine.url.drivername, "postgresql+asyncpg")
                self.assertEqual(engine.url.port, 5433)
                self.assertEqual(engine.url.database, "propertyflow")
                await pool.initialize()
                self.assertIs(pool.engine, engine)
                async with pool.get_session() as session:
                    self.assertIsInstance(session, AsyncSession)
            finally:
                await pool.close()
        self.assertIsNone(pool.session_factory)

    async def test_database_rows_and_failures_reach_the_caller(self):
        pool = DatabasePool()
        session = AsyncMock()
        session.__aenter__.return_value = session
        pool.session_factory = Mock(return_value=session)
        with patch("app.core.database_pool.db_pool", pool):
            for amount, count, total in [(Decimal("2250.000"), 4, "2250.000"),
                                         (None, 0, "0.00")]:
                session.execute.return_value = Mock(one=Mock(return_value=SimpleNamespace(
                    total_revenue=amount, reservation_count=count
                )))
                result = await calculate_total_revenue("prop-001", "tenant-a")
                self.assertEqual(result["total"], total)
                self.assertEqual(result["count"], count)
                self.assertEqual(session.execute.call_args.args[1], {
                    "property_id": "prop-001", "tenant_id": "tenant-a"
                })

            session.execute.side_effect = ConnectionError("database unavailable")
            redis = AsyncMock()
            redis.get.return_value = None
            with patch("app.services.cache.redis_client", redis):
                with self.assertRaisesRegex(ConnectionError, "database unavailable"):
                    await get_revenue_summary("prop-001", "tenant-a")
                redis.setex.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
