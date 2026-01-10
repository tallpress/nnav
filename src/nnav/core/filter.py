"""Message filtering logic for nnav."""

import re
from dataclasses import dataclass, field

from nnav.config import HideConfig
from nnav.nats_client import MessageType, NatsMessage
from nnav.utils.patterns import matches_nats_pattern


@dataclass
class FilterTerm:
    """A single filter term with optional compiled regex."""

    text: str
    regex: re.Pattern[str] | None = None
    is_exclude: bool = False


@dataclass
class FilterState:
    """Complete filter state."""

    text: str = ""
    message_type: MessageType | None = None
    include_terms: list[FilterTerm] = field(default_factory=list)
    exclude_terms: list[FilterTerm] = field(default_factory=list)
    tree_prefix: str | None = None


class MessageFilter:
    """Filters messages based on text, regex, type, and hide config."""

    def __init__(self, hide_config: HideConfig | None = None) -> None:
        self.hide_config = hide_config or HideConfig()
        self.state = FilterState()
        self._parse_errors: list[str] = []

    @property
    def parse_errors(self) -> list[str]:
        """Get any errors from the last parse operation."""
        return self._parse_errors

    def parse(self, filter_text: str) -> None:
        """Parse filter text into include and exclude terms."""
        self._parse_errors = []
        self.state.text = filter_text
        self.state.include_terms = []
        self.state.exclude_terms = []

        if not filter_text.strip():
            return

        terms = self._split_terms(filter_text)

        for term in terms:
            if term.startswith("!"):
                pattern = term[1:]
                if pattern:
                    regex = self._compile_regex(pattern)
                    self.state.exclude_terms.append(
                        FilterTerm(text=pattern, regex=regex, is_exclude=True)
                    )
            elif term:
                regex = self._compile_regex(term)
                self.state.include_terms.append(
                    FilterTerm(text=term, regex=regex, is_exclude=False)
                )

    def _split_terms(self, filter_text: str) -> list[str]:
        """Split filter text on spaces, respecting /regex/ boundaries."""
        terms: list[str] = []
        current = ""
        in_regex = False

        for char in filter_text:
            if char == "/" and not in_regex:
                in_regex = True
                current += char
            elif char == "/" and in_regex:
                in_regex = False
                current += char
            elif char == " " and not in_regex:
                if current:
                    terms.append(current)
                    current = ""
            else:
                current += char

        if current:
            terms.append(current)

        return terms

    def _compile_regex(self, term: str) -> re.Pattern[str] | None:
        """Compile a term as regex if it's in /pattern/ format."""
        if term.startswith("/") and term.endswith("/") and len(term) > 2:
            try:
                return re.compile(term[1:-1], re.IGNORECASE)
            except re.error as e:
                self._parse_errors.append(f"Invalid regex {term}: {e}")
                return None
        return None

    def should_hide(self, msg: NatsMessage) -> bool:
        """Check if message should be hidden based on hide config."""
        if self.hide_config.inbox and msg.subject.startswith("_INBOX."):
            return True
        if self.hide_config.jetstream and msg.subject.startswith("$JS."):
            return True
        if (
            self.hide_config.jetstream_ack
            and msg.reply_to
            and msg.reply_to.startswith("$JS.ACK.")
        ):
            return True
        return False

    def matches(self, msg: NatsMessage) -> bool:
        """Check if message matches current filter criteria."""
        # Type filter
        if self.state.message_type and msg.message_type != self.state.message_type:
            return False

        # Include terms - message must match ALL
        for term in self.state.include_terms:
            if not self._term_matches(term, msg):
                return False

        # Exclude terms - message must NOT match ANY
        for term in self.state.exclude_terms:
            if self._term_matches(term, msg):
                return False

        return True

    def _term_matches(self, term: FilterTerm, msg: NatsMessage) -> bool:
        """Check if a single term matches the message."""
        if term.regex:
            return bool(term.regex.search(msg.subject) or term.regex.search(msg.payload))
        elif ">" in term.text or "*" in term.text:
            return matches_nats_pattern(msg.subject, term.text)
        else:
            term_lower = term.text.lower()
            return (
                term_lower in msg.subject.lower() or term_lower in msg.payload.lower()
            )

    def clear(self) -> None:
        """Clear all filter state."""
        self.state = FilterState()
        self._parse_errors = []

    def set_type_filter(self, message_type: MessageType | None) -> None:
        """Set the message type filter."""
        self.state.message_type = message_type

    def set_tree_prefix(self, prefix: str | None) -> None:
        """Set the tree filter prefix for subject display."""
        self.state.tree_prefix = prefix

    def get_display_subject(self, subject: str) -> str:
        """Get subject for display, stripping tree filter prefix if applicable."""
        if not self.state.tree_prefix:
            return subject

        prefix = self.state.tree_prefix
        if subject.startswith(prefix + "."):
            return "..." + subject[len(prefix) + 1 :]
        elif subject == prefix:
            parts = subject.rsplit(".", 1)
            return "..." + parts[-1] if len(parts) > 1 else subject

        return subject
