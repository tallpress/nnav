#!/usr/bin/env python3
"""
Demo script that publishes NATS traffic to showcase nnav features.

Features demonstrated:
- Hierarchical subjects (for subject tree view)
- Request/Response RPC patterns (for latency tracking)
- Various JSON payloads (for syntax highlighting and path queries)
- Similar messages (for diff feature)
- Different message types (REQ/RES/PUB for filtering)

Usage:
    uv run python scripts/demo_traffic.py

Then in another terminal:
    uv run nnav -S ">"
"""

import asyncio
import json
import random
import sys
import uuid
from datetime import datetime
from pathlib import Path

import nats
from nats.aio.client import Client

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from nnav.config import load_config


async def publish_orders(nc: Client) -> None:
    """Publish order lifecycle events."""
    order_id = str(uuid.uuid4())[:8]
    customer_id = random.randint(1000, 9999)

    # Order created
    await nc.publish(
        "orders.created",
        json.dumps({
            "order_id": order_id,
            "customer_id": customer_id,
            "items": [
                {"sku": "WIDGET-001", "quantity": 2, "price": 29.99},
                {"sku": "GADGET-042", "quantity": 1, "price": 149.99},
            ],
            "total": 209.97,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
        }).encode(),
    )

    await asyncio.sleep(0.3)

    # Order payment processed
    await nc.publish(
        "orders.payment.processed",
        json.dumps({
            "order_id": order_id,
            "payment_method": "credit_card",
            "amount": 209.97,
            "transaction_id": str(uuid.uuid4())[:12],
            "status": "success",
        }).encode(),
    )

    await asyncio.sleep(0.2)

    # Order shipped
    await nc.publish(
        "orders.shipped",
        json.dumps({
            "order_id": order_id,
            "carrier": "FedEx",
            "tracking_number": f"FX{random.randint(100000000, 999999999)}",
            "estimated_delivery": "2024-12-20",
        }).encode(),
    )


async def publish_user_events(nc: Client) -> None:
    """Publish user activity events."""
    user_id = random.randint(1, 100)

    events = [
        ("users.login", {"user_id": user_id, "ip": "192.168.1.42", "user_agent": "Mozilla/5.0"}),
        ("users.profile.viewed", {"user_id": user_id, "viewer_id": random.randint(1, 100)}),
        ("users.settings.updated", {"user_id": user_id, "changes": {"theme": "dark", "notifications": True}}),
    ]

    for subject, payload in events:
        await nc.publish(subject, json.dumps(payload).encode())
        await asyncio.sleep(0.15)


async def publish_metrics(nc: Client) -> None:
    """Publish system metrics."""
    services = ["api-gateway", "auth-service", "order-service", "inventory-service"]

    for service in services:
        await nc.publish(
            f"metrics.{service}",
            json.dumps({
                "service": service,
                "cpu_percent": round(random.uniform(10, 80), 1),
                "memory_mb": random.randint(256, 2048),
                "requests_per_sec": random.randint(100, 5000),
                "error_rate": round(random.uniform(0, 0.05), 4),
                "timestamp": datetime.now().isoformat(),
            }).encode(),
        )
        await asyncio.sleep(0.1)


async def do_rpc_calls(nc: Client) -> None:
    """Demonstrate request/response RPC pattern."""

    # User lookup RPC
    try:
        response = await nc.request(
            "rpc.users.get",
            json.dumps({"user_id": 42}).encode(),
            timeout=2,
        )
        print(f"  RPC users.get response: {response.data.decode()[:50]}...")
    except Exception as e:
        print(f"  RPC users.get: no responder ({e})")

    await asyncio.sleep(0.2)

    # Inventory check RPC
    try:
        response = await nc.request(
            "rpc.inventory.check",
            json.dumps({"sku": "WIDGET-001", "quantity": 5}).encode(),
            timeout=2,
        )
        print(f"  RPC inventory.check response: {response.data.decode()[:50]}...")
    except Exception as e:
        print(f"  RPC inventory.check: no responder ({e})")


async def run_rpc_responder(nc: Client, stop_event: asyncio.Event) -> None:
    """Run RPC responders to demonstrate request/response matching."""

    async def handle_user_get(msg: nats.aio.msg.Msg) -> None:
        request = json.loads(msg.data.decode())
        await asyncio.sleep(random.uniform(0.01, 0.05))  # Simulate work
        response = {
            "user_id": request.get("user_id"),
            "name": "Alice Johnson",
            "email": "alice@example.com",
            "role": "admin",
            "created_at": "2024-01-15T10:30:00Z",
        }
        await nc.publish(msg.reply, json.dumps(response).encode())

    async def handle_inventory_check(msg: nats.aio.msg.Msg) -> None:
        request = json.loads(msg.data.decode())
        await asyncio.sleep(random.uniform(0.02, 0.08))  # Simulate DB lookup
        response = {
            "sku": request.get("sku"),
            "available": random.randint(0, 100),
            "reserved": random.randint(0, 10),
            "warehouse": random.choice(["US-EAST", "US-WEST", "EU-CENTRAL"]),
        }
        await nc.publish(msg.reply, json.dumps(response).encode())

    sub1 = await nc.subscribe("rpc.users.get", cb=handle_user_get)
    sub2 = await nc.subscribe("rpc.inventory.check", cb=handle_inventory_check)

    await stop_event.wait()

    await sub1.unsubscribe()
    await sub2.unsubscribe()


async def publish_errors(nc: Client) -> None:
    """Publish some error events for filtering demo."""
    errors = [
        ("errors.api", {"code": 500, "message": "Internal server error", "path": "/api/orders"}),
        ("errors.database", {"code": "CONN_TIMEOUT", "message": "Connection timeout", "db": "postgres"}),
        ("errors.validation", {"field": "email", "message": "Invalid email format", "value": "not-an-email"}),
    ]

    error = random.choice(errors)
    await nc.publish(
        error[0],
        json.dumps({**error[1], "timestamp": datetime.now().isoformat()}).encode(),
    )


async def publish_similar_messages(nc: Client) -> None:
    """Publish similar messages to demonstrate diff feature."""
    base_config = {
        "version": "1.2.3",
        "features": {
            "dark_mode": True,
            "notifications": True,
            "auto_save": False,
        },
        "limits": {
            "max_connections": 100,
            "timeout_seconds": 30,
        },
    }

    await nc.publish("config.current", json.dumps(base_config).encode())

    await asyncio.sleep(0.5)

    # Updated config with some changes
    updated_config = {
        "version": "1.2.4",
        "features": {
            "dark_mode": True,
            "notifications": False,  # Changed
            "auto_save": True,       # Changed
        },
        "limits": {
            "max_connections": 150,  # Changed
            "timeout_seconds": 30,
        },
    }

    await nc.publish("config.updated", json.dumps(updated_config).encode())


async def main() -> None:
    config = load_config()
    url = config.connection.url or "nats://localhost:4222"

    print("Connecting to NATS...")
    connect_opts: dict[str, object] = {"servers": url}
    if config.connection.user:
        connect_opts["user"] = config.connection.user
    if config.connection.password:
        connect_opts["password"] = config.connection.password

    nc = await nats.connect(**connect_opts)  # type: ignore[arg-type]
    print(f"Connected to {url}")

    stop_event = asyncio.Event()
    responder_task = asyncio.create_task(run_rpc_responder(nc, stop_event))

    print("\nPublishing demo traffic (Ctrl+C to stop)...")
    print("Run 'uv run nnav -S \">\"' in another terminal to view\n")

    try:
        cycle = 0
        while True:
            cycle += 1
            print(f"--- Cycle {cycle} ---")

            print("  Publishing orders...")
            await publish_orders(nc)

            print("  Publishing user events...")
            await publish_user_events(nc)

            print("  Publishing metrics...")
            await publish_metrics(nc)

            print("  Making RPC calls...")
            await do_rpc_calls(nc)

            if random.random() < 0.3:
                print("  Publishing error event...")
                await publish_errors(nc)

            if cycle % 3 == 0:
                print("  Publishing config messages (for diff demo)...")
                await publish_similar_messages(nc)

            print(f"  Sleeping 2s...\n")
            await asyncio.sleep(2)

    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        stop_event.set()
        await responder_task
        await nc.close()
        print("Disconnected")


if __name__ == "__main__":
    asyncio.run(main())
