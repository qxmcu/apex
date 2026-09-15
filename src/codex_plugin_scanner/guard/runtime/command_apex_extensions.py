"""
HOL Guard Command Extension for ApexCompress (apex / apexcompress).
Classifies CLI invocations into policy decisions:
- REVIEW: Mutating operations (compress, decompress/extract, repair)
- ALLOW: Safe / Read-only inspection operations (list, test, diff, info, completions, --help, --version)
"""

import shlex
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Sequence, Union


class DecisionLevel(str, Enum):
    ALLOW = "allow"
    REVIEW = "review"
    DENY = "deny"


@dataclass(frozen=True)
class ExtensionDecision:
    level: DecisionLevel
    command: str
    subcommand: Optional[str]
    reason: str

    @property
    def requires_review(self) -> bool:
        return self.level == DecisionLevel.REVIEW

    @property
    def is_safe(self) -> bool:
        return self.level == DecisionLevel.ALLOW


APEX_BINARY_NAMES = {"apex", "apexcompress"}

# Mutating commands that touch or modify filesystem state
REVIEW_SUBCOMMANDS = {
    "compress", "c",
    "decompress", "extract", "x",
    "repair", "fix", "heal",
}

# Safe inspection commands that perform zero state mutation
SAFE_SUBCOMMANDS = {
    "list", "l",
    "test", "t",
    "diff", "d",
    "info", "i",
    "completions",
    "benchmark", "b",
}


def is_apex_command(cmd_tokens: Sequence[str]) -> bool:
    """Checks if the argv / token sequence starts with apex or apexcompress."""
    if not cmd_tokens:
        return False
    binary = cmd_tokens[0].rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()
    if binary.endswith(".exe"):
        binary = binary[:-4]
    return binary in APEX_BINARY_NAMES


def classify_apex_command(tokens_or_str: Union[str, Sequence[str]]) -> Optional[ExtensionDecision]:
    """
    Evaluates an apex or apexcompress command and returns the guard decision.
    Returns None if the command is not recognized as an Apex command.
    """
    if isinstance(tokens_or_str, str):
        try:
            tokens = shlex.split(tokens_or_str)
        except ValueError:
            tokens = tokens_or_str.split()
    else:
        tokens = list(tokens_or_str)

    if not is_apex_command(tokens):
        return None

    binary = tokens[0].rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()
    if binary.endswith(".exe"):
        binary = binary[:-4]
    subcommand = None

    # Scan for first non-flag token after binary
    for tok in tokens[1:]:
        if not tok.startswith("-"):
            subcommand = tok.lower()
            break
        if tok in ("-h", "--help", "-V", "--version"):
            return ExtensionDecision(
                level=DecisionLevel.ALLOW,
                command=binary,
                subcommand=tok,
                reason="Informational flag is safe",
            )

    if subcommand is None:
        # Default with no subcommand or only flags like --help
        return ExtensionDecision(
            level=DecisionLevel.ALLOW,
            command=binary,
            subcommand=None,
            reason="Root invocation / help is safe",
        )

    if subcommand in REVIEW_SUBCOMMANDS:
        return ExtensionDecision(
            level=DecisionLevel.REVIEW,
            command=binary,
            subcommand=subcommand,
            reason=f"Mutating filesystem operation '{subcommand}' requires review",
        )

    if subcommand in SAFE_SUBCOMMANDS:
        return ExtensionDecision(
            level=DecisionLevel.ALLOW,
            command=binary,
            subcommand=subcommand,
            reason=f"Read-only inspection command '{subcommand}' is automatically permitted",
        )

    # Unknown subcommand - default to REVIEW for safety
    return ExtensionDecision(
        level=DecisionLevel.REVIEW,
        command=binary,
        subcommand=subcommand,
        reason=f"Unrecognized subcommand '{subcommand}' requires review",
    )
