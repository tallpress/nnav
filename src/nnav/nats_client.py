"""NATS client for subscribing to messages."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

import nats
from nats.aio.client import Client
from nats.aio.msg import Msg
from nats.js.api import ConsumerConfig, DeliverPolicy


class MessageType(Enum):
    """Type of NATS message."""

    PUBLISH = "PUB"
    REQUEST = "REQ"
    RESPONSE = "RES"


class JetStreamDeliverPolicy(Enum):
    """Starting position for JetStream subscription."""

    NEW = "new"  # Only new messages
    ALL = "all"  # From beginning
    LAST = "last"  # Last message only
    BY_START_SEQ = "by_start_seq"  # From specific sequence


@dataclass
class JetStreamConfig:
    """Configuration for JetStream subscription."""

    stream: str
    deliver_policy: JetStreamDeliverPolicy = JetStreamDeliverPolicy.NEW
    start_sequence: int | None = None  # For BY_START_SEQ


@dataclass
class NatsMessage:
    """A NATS message with metadata."""

    subject: str
    payload: str
    timestamp: datetime
    reply_to: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    message_type: MessageType = MessageType.PUBLISH
    correlation_id: str | None = None
    latency_ms: float | None = None
    request_subject: str | None = None
    # JetStream metadata
    js_sequence: int | None = None
    js_stream: str | None = None


class RpcTracker:
    """Tracks request/response pairs for RPC correlation."""

    def __init__(self, timeout_seconds: float = 30.0) -> None:
        self.timeout_seconds = timeout_seconds
        self._pending_requests: dict[str, tuple[NatsMessage, datetime]] = {}

    def track_request(self, msg: NatsMessage) -> None:
        """Track a request message for later correlation."""
        if msg.reply_to:
            self._pending_requests[msg.reply_to] = (msg, datetime.now())

    def match_response(self, msg: NatsMessage) -> NatsMessage | None:
        """Try to match a response to a pending request."""
        if msg.subject in self._pending_requests:
            request, request_time = self._pending_requests.pop(msg.subject)
            msg.correlation_id = request.subject
            msg.request_subject = request.subject
            msg.latency_ms = (msg.timestamp - request_time).total_seconds() * 1000
            msg.message_type = MessageType.RESPONSE
            return request
        return None

    def get_timed_out_requests(self) -> list[NatsMessage]:
        """Get requests that have timed out without a response."""
        now = datetime.now()
        timed_out: list[NatsMessage] = []
        to_remove: list[str] = []

        for reply_to, (request, request_time) in self._pending_requests.items():
            if (now - request_time).total_seconds() > self.timeout_seconds:
                timed_out.append(request)
                to_remove.append(reply_to)

        for reply_to in to_remove:
            del self._pending_requests[reply_to]

        return timed_out

    @property
    def pending_count(self) -> int:
        """Number of pending requests."""
        return len(self._pending_requests)


class NatsSubscriber:
    """Subscribes to NATS subjects and yields messages with RPC tracking."""

    def __init__(
        self,
        server_url: str,
        user: str | None = None,
        password: str | None = None,
        subject: str = ">",
        rpc_timeout: float = 30.0,
    ) -> None:
        self.server_url = server_url
        self.user = user
        self.password = password
        self.subject = subject
        self._client: Client | None = None
        self.rpc_tracker = RpcTracker(timeout_seconds=rpc_timeout)

    async def connect(self) -> None:
        """Connect to the NATS server."""
        self._client = await nats.connect(
            self.server_url,
            user=self.user,
            password=self.password,
        )

    async def disconnect(self) -> None:
        """Disconnect from the NATS server."""
        if self._client:
            await self._client.drain()
            self._client = None

    @property
    def is_connected(self) -> bool:
        """Check if connected to NATS."""
        return self._client is not None and self._client.is_connected

    async def publish(
        self,
        subject: str,
        payload: bytes,
        reply_to: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Publish a message to a subject."""
        if not self._client:
            raise RuntimeError("Not connected to NATS server")
        await self._client.publish(subject, payload, reply=reply_to or "", headers=headers)

    async def subscribe_all(self) -> AsyncIterator[NatsMessage]:
        """Subscribe to subjects and yield messages with RPC tracking."""
        if not self._client:
            raise RuntimeError("Not connected to NATS server")

        queue: list[Msg] = []

        async def message_handler(msg: Msg) -> None:
            queue.append(msg)

        sub = await self._client.subscribe(self.subject, cb=message_handler)

        try:
            while True:
                if queue:
                    raw_msg = queue.pop(0)
                    msg = self._process_message(raw_msg)

                    # Check if this is a response to a tracked request
                    self.rpc_tracker.match_response(msg)

                    # Track if this is a request (has reply_to)
                    if msg.reply_to:
                        self.rpc_tracker.track_request(msg)

                    yield msg
                else:
                    await self._client.flush()
                    await asyncio.sleep(0.01)
        finally:
            await sub.unsubscribe()

    def _process_message(self, raw_msg: Msg) -> NatsMessage:
        """Process a raw NATS message into our format."""
        try:
            payload = raw_msg.data.decode("utf-8")
        except UnicodeDecodeError:
            payload = raw_msg.data.hex()

        # Extract headers
        headers: dict[str, str] = {}
        if raw_msg.headers:
            for key, value in raw_msg.headers.items():
                headers[key] = value if isinstance(value, str) else str(value)

        # Determine message type
        reply_to = raw_msg.reply if raw_msg.reply else None
        if reply_to:
            msg_type = MessageType.REQUEST
        elif raw_msg.subject.startswith("_INBOX."):
            msg_type = MessageType.RESPONSE
        else:
            msg_type = MessageType.PUBLISH

        return NatsMessage(
            subject=raw_msg.subject,
            payload=payload,
            timestamp=datetime.now(),
            reply_to=reply_to,
            headers=headers,
            message_type=msg_type,
        )

    async def subscribe_jetstream(
        self, config: JetStreamConfig
    ) -> AsyncIterator[NatsMessage]:
        """Subscribe to a JetStream stream and yield messages."""
        if not self._client:
            raise RuntimeError("Not connected to NATS server")

        js = self._client.jetstream()

        # Map our policy to nats-py DeliverPolicy
        if config.deliver_policy == JetStreamDeliverPolicy.NEW:
            deliver_policy = DeliverPolicy.NEW
            opt_start_seq = None
        elif config.deliver_policy == JetStreamDeliverPolicy.ALL:
            deliver_policy = DeliverPolicy.ALL
            opt_start_seq = None
        elif config.deliver_policy == JetStreamDeliverPolicy.LAST:
            deliver_policy = DeliverPolicy.LAST
            opt_start_seq = None
        elif config.deliver_policy == JetStreamDeliverPolicy.BY_START_SEQ:
            deliver_policy = DeliverPolicy.BY_START_SEQUENCE
            opt_start_seq = config.start_sequence
        else:
            deliver_policy = DeliverPolicy.NEW
            opt_start_seq = None

        # Create consumer config
        consumer_config = ConsumerConfig(
            deliver_policy=deliver_policy,
            opt_start_seq=opt_start_seq,
        )

        # Subscribe using push consumer for real-time delivery
        sub = await js.subscribe(
            subject=">",
            stream=config.stream,
            config=consumer_config,
        )

        try:
            async for raw_msg in sub.messages:
                msg = self._process_jetstream_message(raw_msg, config.stream)
                yield msg
        finally:
            await sub.unsubscribe()

    def _process_jetstream_message(self, raw_msg: Msg, stream: str) -> NatsMessage:
        """Process a JetStream message into our format."""
        try:
            payload = raw_msg.data.decode("utf-8")
        except UnicodeDecodeError:
            payload = raw_msg.data.hex()

        # Extract headers
        headers: dict[str, str] = {}
        if raw_msg.headers:
            for key, value in raw_msg.headers.items():
                headers[key] = value if isinstance(value, str) else str(value)

        # Get JetStream metadata
        js_sequence: int | None = None
        if raw_msg.metadata:
            js_sequence = raw_msg.metadata.sequence.stream

        return NatsMessage(
            subject=raw_msg.subject,
            payload=payload,
            timestamp=datetime.now(),
            reply_to=None,
            headers=headers,
            message_type=MessageType.PUBLISH,
            js_sequence=js_sequence,
            js_stream=stream,
        )
