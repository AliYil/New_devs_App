import json
import unittest
from unittest.mock import AsyncMock, patch

from app.services.cache import get_revenue_summary


class RevenueCacheTest(unittest.IsolatedAsyncioTestCase):
    async def test_shared_property_is_isolated_on_cache_misses_and_hits(self):
        for tenants in [("tenant-a", "tenant-b"), ("tenant-b", "tenant-a")]:
            with self.subTest(request_order=tenants):
                expected = {
                    "tenant-a": {"total": "2250.000", "count": 4},
                    "tenant-b": {"total": "0.00", "count": 0},
                }
                # Old unscoped entries must not be reused after the fix.
                entries = {"revenue:prop-001": json.dumps(expected["tenant-a"])}

                async def store(key, ttl, value):
                    self.assertEqual(ttl, 300)
                    entries[key] = value

                async def calculate(property_id, tenant_id):
                    self.assertEqual(property_id, "prop-001")
                    return expected[tenant_id]

                redis = AsyncMock()
                redis.get.side_effect = entries.get
                redis.setex.side_effect = store
                with patch("app.services.cache.redis_client", redis), patch(
                    "app.services.reservations.calculate_total_revenue",
                    new_callable=AsyncMock,
                    side_effect=calculate,
                ) as aggregate:
                    for tenant in tenants + tenants:
                        result = await get_revenue_summary("prop-001", tenant)
                        self.assertEqual(result, expected[tenant])

                    self.assertEqual(aggregate.await_count, 2)
                    self.assertEqual(redis.setex.await_count, 2)


if __name__ == "__main__":
    unittest.main()
