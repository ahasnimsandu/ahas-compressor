# AHAS archive format v2

Extension: `.ahas`. This is a new framed format, not a renamed legacy SQLite/CLA file.

## Envelope

Eight magic bytes: `41 48 41 53 02 0D 0A 1A` (`AHAS`, version 2, CR LF, SUB). These are followed by exactly one XZ stream, created with Python's LZMA/XZ writer. Concatenated streams or trailing bytes are rejected. The stream is solid: a single compression dictionary spans all records.

The XZ decoder is limited to 256 MiB of dictionary/decoder memory. Standard encoding profiles: preset 1, 6, or 9|EXTREME. New archives use 4 MiB maximum data records; payload is streamed, not loaded as one giant string.

## Framing

A JSON record consists of a one-byte tag, a four-byte unsigned big-endian JSON length, and that many UTF-8 JSON bytes. JSON is encoded compactly with ASCII escapes; individual metadata records are capped at 1 MiB. This format has no pickle, executable scripts, or stored symlinks.

1. `H` JSON header: `{version:2,total:<logical file bytes>,entries:<file+directory count>}`.
2. Exactly `entries` entries in parent-before-child order:
   - `D` JSON directory: `{path,size:0,mode,mtime_ns}`.
   - `F` JSON file: `{path,size,mode,mtime_ns,digest:<64 lowercase hex BLAKE2b-256 characters>}`, followed by data records and an end record.
   - `R` JSON duplicate file: the same fields plus `source:<path of an earlier validated file>`. No payload. Size and digest must exactly match the referenced prior file. References restore as independent ordinary file copies, not filesystem hard links.
3. `Q` JSON footer: `{total:<logical bytes>,files:<regular-file count including references>,entries:<all entries>}`. Totals must match the parsed stream/header. No extra decoded data may follow.

Within an `F` payload:

- `B`: four-byte unsigned big-endian length (1…4,194,304), then that many raw file bytes.
- `Z`: four-byte unsigned big-endian length (same range), representing that many zero bytes. No raw zero payload is stored.
- `E`: exactly 32 bytes of BLAKE2b-256 over the entire reconstructed file. Must match the file metadata digest. The sum of B/Z lengths must equal the declared file size.

All B/Z data are inside the one XZ stream, not separately compressed chunks. Empty files have no B/Z records and still require E with the empty-file hash. Directories have no content digest. Shared file payload is verified once and duplicate references must match the verified source size/hash.

## Safety checks and limitations

Paths must be nonempty relative POSIX-style paths without `.`/`..`, backslashes, or NUL bytes. Duplicate case-folded NFC names, non-directory/missing parents, invalid lengths/encodings, excessive logical sizes, invalid references, incomplete framing, and content hash mismatches are rejected. New extraction roots are created exclusively and removed on controlled failure. Symlinks/special files are not encoded. Restrictive permissions are applied only after all duplicate copies are complete.

Default restored-size limit: 1,024 GiB; editable in UI/CLI. Entry-count limit: ten million, not a promise that such a large manifest is practical. Manifests scale with entry count. This is not an authenticated or encrypted format; hashes/XZ checks detect accidental corruption, not an attacker able to rewrite the archive.

## Legacy CLA support

The reader detects the SQLite file signature and delegates to the legacy engine (`compactlocal/archive.py`). New writes always use AHAS v2. Legacy CLA preserves its original 4 MiB chunk deduplication design. V2 instead performs whole-file deduplication plus solid dictionary compression, so it can be worse for some partial-duplicate datasets. File-content losslessness is independent of the extension.
