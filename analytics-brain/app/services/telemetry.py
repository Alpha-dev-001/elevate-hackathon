import time
from app.core.redis import get_redis, Keys, TTL
from app.models.schemas import CustomerEvent, TelemetrySnapshot, Anomaly, AnomalyType


async def record_event(merchant_id: str, event: CustomerEvent) -> None:
    redis = await get_redis()

    if event.event_type.value == "view":
        await redis.zincrby(Keys.product_velocity(merchant_id), 1, event.product_id)
        await redis.expire(Keys.product_velocity(merchant_id), TTL.SNAPSHOT)

    await redis.sadd(Keys.active_sessions(merchant_id), event.session_id)
    await redis.expire(Keys.active_sessions(merchant_id), TTL.SNAPSHOT)

    await redis.lpush(
        Keys.session_events(event.session_id),
        event.model_dump_json(),
    )
    await redis.expire(Keys.session_events(event.session_id), TTL.SESSION)


async def capture_snapshot(merchant_id: str) -> TelemetrySnapshot:
    redis = await get_redis()

    active_sessions = await redis.scard(Keys.active_sessions(merchant_id))

    velocity_data = await redis.zrevrange(
        Keys.product_velocity(merchant_id), 0, -1, withscores=True
    )

    product_velocity: dict[str, float] = {
        product_id: score for product_id, score in velocity_data
    }
    hot_products = [pid for pid, _ in velocity_data[:5]]
    anomalies = _detect_anomalies(product_velocity, active_sessions)

    snapshot = TelemetrySnapshot(
        captured_at=int(time.time() * 1000),
        active_session_count=active_sessions,
        product_velocity=product_velocity,
        hot_products=hot_products,
        anomalies=anomalies,
    )

    await redis.set(
        Keys.snapshot(merchant_id),
        snapshot.model_dump_json(),
        ex=TTL.SNAPSHOT,
    )

    return snapshot


def _detect_anomalies(
    product_velocity: dict[str, float],
    active_sessions: int,
) -> list[Anomaly]:
    anomalies: list[Anomaly] = []
    velocities = list(product_velocity.values())
    if not velocities:
        return anomalies

    avg = sum(velocities) / len(velocities)
    now = int(time.time() * 1000)

    for product_id, velocity in product_velocity.items():
        if velocity > avg * 3:
            anomalies.append(Anomaly(
                type=AnomalyType.VELOCITY_SPIKE,
                product_id=product_id,
                severity="high" if velocity > avg * 5 else "medium",
                detected_at=now,
                context={"velocity": velocity, "avg": avg, "ratio": round(velocity / avg, 2)},
            ))
        if velocity == 0 and active_sessions > 5:
            anomalies.append(Anomaly(
                type=AnomalyType.DEAD_PRODUCT,
                product_id=product_id,
                severity="low",
                detected_at=now,
                context={"active_sessions": active_sessions},
            ))

    return anomalies
