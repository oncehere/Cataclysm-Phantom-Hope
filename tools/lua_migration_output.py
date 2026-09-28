"""Result records, reports and transactional output for Lua-first migration.

Semantic translation stays in migrate_lua_first.py.  This module only formats
its structured result and installs the generated files, including the existing
non-mutating check mode and rollback on a failed replacement.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

try:
    from agent.migration_todo import (
        MigrationBoundary,
        MigrationTodo,
        TODO_CATEGORIES,
        TodoCategory,
        validate_todo_category,
    )
except ModuleNotFoundError:
    from tools.agent.migration_todo import (
        MigrationBoundary,
        MigrationTodo,
        TODO_CATEGORIES,
        TodoCategory,
        validate_todo_category,
    )


@dataclass
class MigrationResult:
    files: dict[Path, str] = field(default_factory=dict)
    converted: list[str] = field(default_factory=list)
    partial: list[str] = field(default_factory=list)
    todos: list[MigrationTodo] = field(default_factory=list)
    boundaries: list[MigrationBoundary] = field(default_factory=list)

    def __post_init__(self) -> None:
        if any(not isinstance(todo, MigrationTodo) for todo in self.todos):
            raise TypeError(
                "migration result TODOs must be MigrationTodo records"
            )
        if any(
            not isinstance(boundary, MigrationBoundary)
            for boundary in self.boundaries
        ):
            raise TypeError(
                "migration result boundaries must be MigrationBoundary records"
            )

    def add_todo(self, category: TodoCategory, rendered: str) -> None:
        """Append one explicitly classified TODO from legacy report text.

        ``rendered`` remains accepted at the producer boundary so the large
        family of existing renderers can keep their precise source wording.
        Classification is required by the caller and is never inferred from
        that wording.
        """
        validate_todo_category(category)
        self.todos.append(MigrationTodo.from_rendered(category, rendered))


def render_report(result: MigrationResult, mod_id: str) -> str:
    if any(not isinstance(todo, MigrationTodo) for todo in result.todos):
        raise TypeError("migration result contains an unstructured TODO")
    todo_counts = {
        category: sum(todo.category == category for todo in result.todos)
        for category in TODO_CATEGORIES
    }
    lines = [
        f"# Lua-first migration report: `{mod_id}`",
        "",
        "This report is generated from source structure, "
        "not proof of gameplay equivalence.",
        "No JSON loader, EOC runner, or raw legacy object was emitted.",
        "TODO categories are boundary records, not completion metrics.",
        "",
        f"- Fully translated skeletons: {len(result.converted)}",
        f"- Partial skeletons: {len(result.partial)}",
        f"- Explicit TODO records: {len(result.todos)}",
        f"- Classified source/safety boundaries: {len(result.boundaries)}",
        "",
        "## Fully translated skeletons",
        "",
    ]
    lines.extend(f"- {entry}" for entry in result.converted)
    if not result.converted:
        lines.append("- None")
    lines.extend(("", "## Partial skeletons", ""))
    lines.extend(f"- {entry}" for entry in result.partial)
    if not result.partial:
        lines.append("- None")
    lines.extend(("", "## Classified migration TODOs", ""))
    for category in TODO_CATEGORIES:
        lines.extend((f"### `{category}` ({todo_counts[category]})", ""))
        category_todos = (
            todo for todo in result.todos if todo.category == category
        )
        lines.extend(
            f"- [ ] {todo.location}: {todo.message}"
            for todo in category_todos
        )
        if todo_counts[category] == 0:
            lines.append("- None")
    lines.extend(("", "## Classified source and safety boundaries", ""))
    lines.extend(
        f"- {entry.location}: {entry.message}" for entry in result.boundaries
    )
    if not result.boundaries:
        lines.append("- None")
    lines.append("")
    return "\n".join(lines)


def _exists_or_symlink(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _install_staged_file(source: Path, destination: Path) -> None:
    source.replace(destination)


def write_result(
    result: MigrationResult, output: Path, force: bool, check: bool
) -> bool:
    if output.is_symlink() or (output.exists() and not output.is_dir()):
        raise ValueError(f"output is not a directory: {output}")
    for relative in result.files:
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"unsafe migration output path: {relative}")

    stale: list[Path] = []
    existing = [
        output / relative
        for relative in sorted(result.files)
        if _exists_or_symlink(output / relative)
    ]
    if not check and not force and existing:
        raise ValueError(f"refusing to overwrite {existing[0]}; pass --force")

    for relative, contents in sorted(result.files.items()):
        destination = output / relative
        if check:
            try:
                current = destination.read_text(encoding="utf-8")
            except OSError:
                stale.append(relative)
            else:
                if current != contents:
                    stale.append(relative)
            continue
    if check and stale:
        print("stale Lua-first migration output:", file=sys.stderr)
        for relative in stale:
            print(f"  {relative.as_posix()}", file=sys.stderr)
        return False
    if check:
        return True

    output.parent.mkdir(parents=True, exist_ok=True)
    for relative in sorted(result.files):
        destination = output / relative
        if destination.exists() and destination.is_dir():
            raise ValueError(
                f"migration output path is a directory: {destination}"
            )
        parent = destination.parent
        while parent != output:
            if parent.is_symlink() or (
                parent.exists() and not parent.is_dir()
            ):
                raise ValueError(
                    f"migration output parent is not a directory: {parent}"
                )
            parent = parent.parent

    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{output.name}.lua-first-", dir=output.parent
        )
    )
    staged_root = temporary / "generated"
    backup_root = temporary / "backup"
    try:
        for relative, contents in sorted(result.files.items()):
            staged = staged_root / relative
            staged.parent.mkdir(parents=True, exist_ok=True)
            staged.write_text(contents, encoding="utf-8")

        if not output.exists():
            staged_root.replace(output)
            return True

        created_directories: list[Path] = []
        backups: list[tuple[Path, Path]] = []
        installed: list[Path] = []
        try:
            for relative in sorted(result.files):
                destination = output / relative
                missing: list[Path] = []
                parent = destination.parent
                while parent != output and not parent.exists():
                    missing.append(parent)
                    parent = parent.parent
                for directory in reversed(missing):
                    directory.mkdir()
                    created_directories.append(directory)

            for relative in sorted(result.files):
                destination = output / relative
                if not _exists_or_symlink(destination):
                    continue
                backup = backup_root / relative
                backup.parent.mkdir(parents=True, exist_ok=True)
                destination.replace(backup)
                backups.append((destination, backup))

            for relative in sorted(result.files):
                destination = output / relative
                _install_staged_file(staged_root / relative, destination)
                installed.append(destination)
        except Exception:
            for destination in reversed(installed):
                if _exists_or_symlink(destination):
                    destination.unlink()
            for destination, backup in reversed(backups):
                if _exists_or_symlink(backup):
                    backup.replace(destination)
            for directory in reversed(created_directories):
                try:
                    directory.rmdir()
                except OSError:
                    pass
            raise
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    return True
