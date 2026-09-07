#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 ARTIFACT EXPECTED_VERSION" >&2
  exit 2
fi

artifact_path="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
expected_version="$2"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
smoke_root="$(mktemp -d)"
trap 'rm -rf "$smoke_root"' EXIT

venv_path="$smoke_root/venv"
python3 -m venv "$venv_path"
"$venv_path/bin/python" -m pip install --disable-pip-version-check --no-deps "$artifact_path"

(
  cd "$smoke_root"
  PATH="$venv_path/bin:$PATH" "$venv_path/bin/python" - "$repo_root" "$expected_version" <<'PY'
import json
import sys
from importlib.metadata import version
from pathlib import Path
from shutil import which

repo_root = Path(sys.argv[1]).resolve()
expected_version = sys.argv[2]

import context_compiler
import context_compiler.grammar as grammar

module_path = Path(context_compiler.__file__).resolve()
assert repo_root not in module_path.parents, module_path
assert context_compiler.__version__ == expected_version
assert version("context-compiler") == expected_version

from context_compiler import (
    DECISION_ERROR,
    DECISION_NO_DIRECTIVE,
    DECISION_UPDATE,
    POLICY_PROHIBIT,
    POLICY_USE,
    Decision,
    DecisionKind,
    Engine,
    NoDirectiveDecision,
    PolicyValue,
    SemanticErrorDecision,
    SemanticFailure,
    UpdateDecision,
)
from context_compiler.grammar import (
    CanonicalDirective,
    DirectiveKind,
    DirectiveMetadata,
    DirectiveSyntaxFailure,
    InvalidDirectiveSyntax,
    decompose_directive,
    get_directive_metadata,
)

assert CanonicalDirective is grammar.CanonicalDirective
assert DirectiveKind is grammar.DirectiveKind
assert get_directive_metadata()
assert decompose_directive("use docker").text == "use docker"

engine = Engine()
decision = engine.step("set premise package smoke")
assert decision.kind.value == "update"
assert decision.changed is True

payload = engine.export_json()
restored = Engine()
restored.import_json(payload)
assert restored.premise == "package smoke"
assert json.loads(restored.export_json()) == json.loads(payload)

cli_path = which("context-compiler")
assert cli_path is not None
assert Path(cli_path).resolve().is_relative_to(Path(sys.prefix).resolve())
PY
  cli_version="$(PATH="$venv_path/bin:$PATH" "$venv_path/bin/context-compiler" --version)"
  [[ "$cli_version" == "$expected_version" ]]
)

echo "Package smoke passed: $(basename "$artifact_path")"
