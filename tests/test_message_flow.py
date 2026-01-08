"""Tests for message flow to detect duplicates."""

from datetime import datetime

from nnav.nats_client import MessageType, NatsMessage


class TestMessageDeduplication:
    """Test that messages can be identified and deduplicated."""

    def test_messages_with_same_subject_different_time_are_different(self) -> None:
        """Two messages on same subject at different times are distinct."""
        msg1 = NatsMessage(
            subject="test.subject",
            payload='{"id": 1}',
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            message_type=MessageType.PUBLISH,
        )
        msg2 = NatsMessage(
            subject="test.subject",
            payload='{"id": 1}',
            timestamp=datetime(2024, 1, 1, 12, 0, 1),
            message_type=MessageType.PUBLISH,
        )
        # Same content but different timestamps - these are different messages
        assert msg1.timestamp != msg2.timestamp

    def test_request_and_response_are_separate_messages(self) -> None:
        """A request and its response should be two distinct messages."""
        request = NatsMessage(
            subject="orders.create",
            payload='{"item": "test"}',
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            reply_to="_INBOX.abc123",
            message_type=MessageType.REQUEST,
        )
        response = NatsMessage(
            subject="_INBOX.abc123",
            payload='{"status": "ok"}',
            timestamp=datetime(2024, 1, 1, 12, 0, 1),
            message_type=MessageType.RESPONSE,
        )
        # These are TWO different messages, not duplicates
        assert request.subject != response.subject
        assert request.message_type != response.message_type

    def test_messages_list_tracks_all_messages(self) -> None:
        """Verify list properly tracks messages without duplicates."""
        messages: list[NatsMessage] = []

        # Simulate adding messages
        for i in range(10):
            msg = NatsMessage(
                subject=f"test.{i}",
                payload=f'{{"id": {i}}}',
                timestamp=datetime.now(),
                message_type=MessageType.PUBLISH,
            )
            messages.append(msg)

        assert len(messages) == 10
        subjects = [m.subject for m in messages]
        assert len(subjects) == len(set(subjects))  # All unique
