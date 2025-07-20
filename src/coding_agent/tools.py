import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List

import pathspec


def schema(props: Dict[str, Any], required: List[str]) -> Dict[str, Any]:
    """Creates a JSON schema object for tool input validation.

    Args:
        props: Dictionary containing property definitions for the schema.
        required: List of property names that are required.

    Returns:
        Dict[str, Any]: A JSON schema object with properties and requirements defined.
    """
    return {
        "type": "object",
        "properties": props,
        "required": required,
        "additionalProperties": False,
    }


def _get_gitignore(root: Path) -> pathspec.PathSpec:
    """Collects and compiles gitignore patterns from multiple sources.

    Collects ignore patterns from .gitignore, .git/info/exclude, and the
    global .gitignore file.

    Args:
        root: The root directory path to search for gitignore files.

    Returns:
        pathspec.PathSpec: A PathSpec object that can be used to match files against
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


def _resolve_relative(path_str: str) -> Path:
    """Resolves a relative path safely within project boundaries.

    Resolves path_str against project root, ensuring it is
    not absolute and does not escape the repo via "..".

    Args:
        path_str: The path string to resolve.

    Returns:
        Path: The resolved absolute path.

    Raises:
        ValueError: If path is empty, absolute, or escapes project root.
    """
    if not path_str:
        raise ValueError("`path` is required")

    rel_path = Path(path_str)

    if rel_path.is_absolute():
        raise ValueError("Absolute paths are not allowed")

    base_dir = Path(".").resolve()
    abs_path = (base_dir / rel_path).resolve()

    if base_dir not in abs_path.parents and abs_path != base_dir:
        raise ValueError("Path escapes project root")

    return abs_path


def list_files(inp: Dict[str, str]) -> str:
    """Recursively lists files under a given path, respecting .gitignore rules.

    Args:
        inp: Dictionary containing input parameters.
            path: Optional base directory path. Defaults to current directory.

    Returns:
        str: A JSON string containing an array of relative file paths.

    Raises:
        FileNotFoundError: If the specified path does not exist.
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


def read_file(inp: Dict[str, str]) -> str:
    """Returns the textual contents of a file.

    Args:
        inp: Dictionary containing input parameters.
            path: The relative path to the file to read.

    Returns:
        str: The text content of the file.

    Raises:
        FileNotFoundError: If the file does not exist.
        IsADirectoryError: If the path points to a directory instead of a file.
        ValueError: If the path is invalid.
    """
    path = _resolve_relative(inp["path"])

    if not path.exists():
        raise FileNotFoundError(f"No such file: {path}")
    if path.is_dir():
        raise IsADirectoryError(f"Expected a file, found a directory: {inp['path']}")

    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def edit_file(inp: Dict[str, str]) -> str:
    """Edits the content of a file by replacing text or creating a new file.

    Replaces all occurrences of old_str with new_str in the specified file.
    If the file does not exist and old_str is empty, creates a new file with
    new_str as its content.

    Args:
        inp: Dictionary containing input parameters.
            path: The relative path to the file to edit.
            old_str: The string to be replaced. If empty and file doesn't exist,
                     a new file will be created.
            new_str: The string to replace old_str with, or the content for a new file.

    Returns:
        str: A success message indicating the file was edited or created.

    Raises:
        FileNotFoundError: If the file does not exist and old_str is not empty.
        IsADirectoryError: If the path points to a directory instead of a file.
        ValueError: If the path is invalid.
    """
    path = _resolve_relative(inp["path"])
    old_str = inp["old_str"]
    new_str = inp["new_str"]

    # Check if we're creating a new file.
    if not path.exists() and old_str == "":
        # Create parent directories if they don't exist.
        if not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)

        # Create new file with new_str as content.
        path.write_text(new_str, encoding="utf-8")
        return f"Created new file: {inp['path']}"

    # For existing files.
    if not path.exists():
        raise FileNotFoundError(f"No such file: {path}")
    if path.is_dir():
        raise IsADirectoryError(f"Expected a file, found a directory: {inp['path']}")

    # Read the file content.
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = path.read_text(encoding="latin-1")

    # Replace old_str with new_str.
    new_content = content.replace(old_str, new_str)

    # Write the modified content back to the file.
    path.write_text(new_content, encoding="utf-8")

    return f"Successfully edited file: {inp['path']}"


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


ALL_TOOLS = [LIST_FILES, READ_FILE, EDIT_FILE]
TOOL_MAP = {t["name"]: t for t in ALL_TOOLS}
