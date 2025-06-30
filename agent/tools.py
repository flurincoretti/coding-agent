import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List

import pathspec


def schema(props: Dict[str, Any], required: List[str]) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": props,
        "required": required,
        "additionalProperties": False,
    }


def _get_gitignore(root: Path) -> pathspec.PathSpec:
    """
    Collect ignore patterns from .gitignore, .git/info/exclude, and the
    global .gitignore file configured via core.excludesFile.
    Return a PathSpec object that can be used to match files against
    all collected ignore patterns.
    """

    patterns: List[str] = []

    # Load repository-specific ignore files
    local_ignore_files = [".gitignore", ".git/info/exclude"]
    for filename in local_ignore_files:
        path = root / filename
        if path.is_file():
            patterns.extend(path.read_text().splitlines())

    # Load the global .gitignore file (if it exists)
    try:
        result = subprocess.run(
            ["git", "config", "--get", "core.excludesFile"],
            capture_output=True,
            text=True,
            check=True,
        )
        global_ignore_path = Path(result.stdout.strip()).expanduser()
        if global_ignore_path.is_file():
            patterns.extend(global_ignore_path.read_text().splitlines())
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    return pathspec.PathSpec.from_lines("gitwildmatch", patterns)


def list_files(inp: Dict[str, str]) -> str:
    """
    Recursively list files under a given path, respecting .gitignore rules.
    """

    base_dir_str = inp.get("path", ".")
    base_dir = Path(base_dir_str).resolve()

    if not base_dir.exists():
        raise FileNotFoundError(f"'{base_dir}' does not exist")

    if not base_dir.is_dir():
        return json.dumps([])

    ignore = _get_gitignore(base_dir)
    results: List[str] = []

    for root, dirs, files in os.walk(base_dir, topdown=True):
        root_path = Path(root)

        # Remove ignored directories from the `dirs` list in-place.
        for d in list(dirs):
            rel_dir_path = (root_path / d).relative_to(base_dir).as_posix() + "/"
            if ignore.match_file(rel_dir_path):
                dirs.remove(d)

        # Process all files and the remaining directories.
        for name in files + dirs:
            rel_path_str = (root_path / name).relative_to(base_dir).as_posix()

            # Check if the individual file or directory is ignored.
            if ignore.match_file(rel_path_str):
                continue

            # Add trailing slash for directories.
            if (root_path / name).is_dir():
                results.append(rel_path_str + "/")
            else:
                results.append(rel_path_str)

    return json.dumps(sorted(results))


def read_file() -> str:
    raise NotImplementedError


def edit_file() -> str:
    raise NotImplementedError


READ_FILE = {
    "name": "read_file",
    "description": ("Read the text contents of a relative file path. "),
    "input_schema": schema(
        {"path": {"type": "string", "description": "Relative file path"}}, ["path"]
    ),
    "fn": read_file,
}


LIST_FILES = {
    "name": "list_files",
    "description": (
        "Recursively list files/directories under a path. "
        "Returns JSON array of relative paths; directories end with '/'. "
        "If no path is given, the current directory is used."
    ),
    "input_schema": schema(
        {"path": {"type": "string", "description": "Optional base dir"}}, []
    ),
    "fn": list_files,
}


EDIT_FILE = {
    "name": "edit_file",
    "description": (
        "Replace old_str with new_str in the given file. "
        "If the file does not exist and old_str is empty, create the file."
    ),
    "input_schema": schema(
        {
            "path": {"type": "string"},
            "old_str": {"type": "string"},
            "new_str": {"type": "string"},
        },
        ["path", "old_str", "new_str"],
    ),
    "fn": edit_file,
}


ALL_TOOLS = [LIST_FILES]
TOOL_MAP = {t["name"]: t for t in ALL_TOOLS}
