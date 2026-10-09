"""Conservative dependency boundary for the first self-contained Ground export."""
from pathlib import Path
import re


def GroundDependencyDirectives_Validate(root: Path) -> None:
    virtual_headers = {"CMSIS_NVIC_VIRTUAL_HEADER_FILE", "CMSIS_VECTAB_VIRTUAL_HEADER_FILE"}
    for path in root.rglob("*"):
        if any(part.lower() in {"build", ".git", "debug", "release"} for part in path.relative_to(root).parts):
            continue
        if not path.is_file() or path.suffix.lower() not in {".c", ".h", ".s", ".ld"}:
            continue
        if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
            raise ValueError("Ground dependency escapes the copied project: " + str(path))
        text = path.read_text(encoding="utf-8-sig")
        # C11 translates trigraphs before splicing and removing comments. Do
        # not let an alternate '#' or backslash evade this conservative profile.
        # Reject these spellings explicitly, including in comments/strings,
        # rather than approximate another C preprocessing implementation.
        if "%:" in text or re.search(r"\?\?[=/'()!<>-]", text):
            raise ValueError("Ground alternate preprocessing tokens are unsupported: " + str(path))
        text = re.sub(r"\\\r?\n", "", text)
        if "%:" in text:
            raise ValueError("Ground alternate preprocessing tokens are unsupported: " + str(path))
        text = re.sub(r"/\*.*?\*/|//[^\r\n]*", "", text, flags=re.S)
        if re.search(r"(?m)^\s*#\s*(include_next|import|embed)\b|\.incbin\b|\.include\b", text):
            raise ValueError("Ground indirect/assembler file dependency is unsupported: " + str(path))
        if path.suffix.lower() == ".ld" and re.search(r"\b(?:INCLUDE|INPUT|GROUP|STARTUP|SEARCH_DIR|OUTPUT)\b", text):
            raise ValueError("Ground linker file dependencies are unsupported; use one self-contained script: " + str(path))
        if re.search(r"(?m)^\s*#\s*define\s+(?:CMSIS_NVIC_VIRTUAL|CMSIS_VECTAB_VIRTUAL)\b", text):
            raise ValueError("Ground CMSIS virtual header dependencies are unsupported")
        for expression in re.findall(r"(?m)^\s*#\s*include\s+([^\r\n]+)", text):
            match = re.fullmatch(r'\s*[<"]([A-Za-z0-9_./-]+)[>"]\s*', expression)
            if match is None:
                # These stock CMSIS branches remain inactive in the supported
                # GCC profile; enabling either feature is rejected above and
                # extra command-line definitions are rejected by the importer.
                if expression.strip() in virtual_headers and path.as_posix().find("/Drivers/CMSIS/") >= 0:
                    continue
                raise ValueError("Ground include must be a literal project/toolchain header: " + str(path))
            name = match[1]
            if name.startswith("/") or ".." in name.split("/"):
                raise ValueError("Ground include escapes the copied project: " + name)
            if not name.endswith(".h"):
                raise ValueError("Ground include requires a frozen C .h header: " + name)
    # All project files are frozen, including potential shadowing headers.
    # Quoted/angle relative names search only the copied -I tree or the selected
    # compiler's own headers. Imported include paths/flags cannot add tree-external
    # search roots; emitted make also removes inherited compiler include env vars.
