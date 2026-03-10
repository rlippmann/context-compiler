"""Schema key constants used by the context compiler state model."""

from typing import Final

# State schema
STATE_FACTS: Final = "facts"
STATE_POLICIES: Final = "policies"
STATE_VERSION: Final = "version"

# Fact keys
FOCUS_PRIMARY: Final = "focus.primary"

# Policy keys
POLICY_PROHIBIT: Final = "prohibit"

# Event kinds
EVENT_RESET_POLICIES: Final = "reset_policies"
EVENT_CLEAR_STATE: Final = "clear_state"
