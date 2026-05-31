import json
from pathlib import Path

_DEFAULT_RUNBOOK_FILENAME = "_default.md"
_CATALOG_FILENAME = "catalog.json"


class RunbookFilesystemAdapter:
    def __init__(self, root_dir: Path) -> None:
        self._root = Path(root_dir)

    async def fetch(self, name: str) -> str:
        target = self._root / f"{name}.md"
        if not target.is_file():
            target = self._root / _DEFAULT_RUNBOOK_FILENAME
        return target.read_text()

    async def list_runbooks(self) -> str:
        catalog_path = self._root / _CATALOG_FILENAME
        entries = json.loads(catalog_path.read_text())
        lines = [f"- {entry['name']}: {entry['description']}" for entry in entries]
        return "\n".join(lines)
