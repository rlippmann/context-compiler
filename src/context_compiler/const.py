"""Schema key constants used by the context compiler state model."""

from typing import Final

# State schema
STATE_PREMISE: Final = "premise"
STATE_POLICIES: Final = "policies"
STATE_VERSION: Final = "version"

# Policy values
POLICY_USE: Final = "use"
POLICY_PROHIBIT: Final = "prohibit"

# Schema version
SCHEMA_VERSION: Final = 2
