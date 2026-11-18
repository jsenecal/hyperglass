"""Render data into shell words without letting data become shell syntax."""

# Standard Library
import re
import shlex
import typing as t

# Project
from hyperglass.exceptions.public import InputInvalid
from hyperglass.exceptions.private import ConfigError

# Keep trusted operators and whitespace separate from complete shell words. Unlike
# shlex.split(command), this retains pipelines and distinguishes | from quoted '|'.
_TOKENS = re.compile(
    r"\s+|[|&;()<>]+|(?:[^\s'\"\\|&;()<>]+|'[^']*'|\"(?:\\[\s\S]|[^\"\\])*\"|\\[\s\S])+"
)


def format_shell(command: str, values: t.Mapping[str, t.Any]) -> str:
    """Split the trusted template, substitute data, then quote each complete word.

    This protects one shell parsing layer. A configured command must not evaluate
    its arguments as another shell program (for example, sh -c or eval).
    """
    result = []
    position = 0
    for match in _TOKENS.finditer(command):
        if match.start() != position:
            raise ConfigError("Custom shell command has invalid quoting")
        position = match.end()
        token = match.group()
        if token.isspace() or token[0] in "|&;()<>":
            # Here-document bodies do not use ordinary shell argument quoting.
            if "<<" in token:
                raise ConfigError("Custom shell commands cannot use here-documents")
            result.append(token)
            continue
        try:
            words = shlex.split(token)
            if len(words) != 1:
                raise ValueError("Expected one shell word")
            word = words[0].format_map(values)
        except (ValueError, KeyError, IndexError, AttributeError) as exc:
            raise ConfigError("Custom shell command has invalid placeholders or quoting") from exc
        if any(char in word for char in "\r\n\x00"):
            raise InputInvalid(
                target=values.get("target", ""),
                error="Shell command arguments cannot contain control characters",
            )
        quoted = shlex.quote(word)
        # A substituted digit immediately before a redirection must stay an argument,
        # not become a file descriptor. Static 2>/dev/null remains unchanged.
        if word.isdecimal() and "{" in token and command[position : position + 1] in ("<", ">"):
            quoted = f"'{word}'"
        result.append(quoted)
    if position != len(command):
        raise ConfigError("Custom shell command has invalid quoting")
    return "".join(result)
