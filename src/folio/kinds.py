"""File kinds: extensions grouped by what a person calls them."""

from __future__ import annotations

KINDS: dict[str, set[str]] = {
    "pdf": {"pdf"},
    "document": {"doc", "docx", "odt", "rtf", "pages"},
    "spreadsheet": {"xls", "xlsx", "xlsm", "ods", "csv", "tsv", "numbers"},
    "presentation": {"ppt", "pptx", "odp", "key"},
    "text": {"txt", "md", "markdown", "rst", "org", "tex", "log"},
    "code": {
        "py",
        "ipynb",
        "js",
        "mjs",
        "ts",
        "tsx",
        "jsx",
        "java",
        "c",
        "h",
        "cpp",
        "hpp",
        "cs",
        "go",
        "rs",
        "rb",
        "php",
        "swift",
        "kt",
        "scala",
        "r",
        "m",
        "sql",
        "sh",
        "zsh",
        "bash",
        "lua",
        "pl",
        "f90",
        "jl",
        "html",
        "htm",
        "css",
        "scss",
        "vue",
        "svelte",
        "json",
        "yaml",
        "yml",
        "toml",
        "xml",
        "ini",
        "cfg",
        "conf",
        "mat",
    },
    "email": {"eml", "emlx", "msg"},
    "image": {"png", "jpg", "jpeg", "gif", "heic", "heif", "webp", "tiff", "tif", "bmp", "svg", "raw", "cr2", "nef", "psd", "ai"},
    "video": {"mp4", "mov", "avi", "mkv", "webm", "m4v"},
    "audio": {"mp3", "wav", "m4a", "aac", "flac", "ogg", "aiff", "aif", "flp", "mid", "midi"},
    "archive": {"zip", "rar", "7z", "tar", "gz", "tgz", "bz2", "xz", "dmg", "iso", "pkg"},
    "ebook": {"epub", "mobi", "azw3"},
}

EXT_KIND = {ext: kind for kind, exts in KINDS.items() for ext in exts}

# Kinds whose text is extracted.
TEXT_EXTS = KINDS["text"] | (KINDS["code"] - {"mat"}) | {"csv", "tsv"}
EXTRACTABLE = TEXT_EXTS | {"pdf", "docx", "pptx", "xlsx", "xlsm", "ods", "odt", "odp", "eml", "emlx", "rtf", "epub"}


def kind_of(ext: str) -> str:
    return EXT_KIND.get(ext, "other")
