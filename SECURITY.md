# Security and data-safety policy

AHAS is experimental archiving/optimization software, not a complete backup or hostile-input sandbox.

## Report a problem

Once this source is published to GitHub, use the repository's private vulnerability-reporting/security-advisory mechanism if the owner enables it. Do not post credentials, private media, personal paths, or confidential archives in public issues. A dedicated private contact address has not been configured in this source package.

## Important boundaries

- Open/extract archives only from sources you trust. Content hashes do not authenticate an archive creator.
- Keep independent backups and test extraction. Resource forks, ACLs, extended metadata, and other Mac-specific properties are not preserved.
- Lossless archive output is not encrypted. Filenames and contents are recoverable by anyone who can read it.
- Media Optimizer is irreversible and explicitly opt-in. Never substitute converted output for your only copy of an original.
- The local UI requires a per-process token and validates Host/Origin, but is not a multi-user login system or protection from someone controlling your account.
- Normal mode binds loopback only. Never run `--preview` on an untrusted network.
- Source files should not change during processing. No filesystem snapshot is taken and checks cannot prevent every hostile same-user filesystem race.
- Controlled cancellation removes partial output. A forced kill, power loss, or filesystem error may leave partial files/folders.
- The distributed development app is ad-hoc signed, not Apple Developer ID signed or notarized. Do not disable Gatekeeper globally to run it. Check signatures/checksums and prefer a successful native-Mac build before trusting a release.
- Build/publishing scripts require review. GitHub authentication happens through GitHub CLI on your computer; never send tokens/passwords in chat. Private repositories are the publishing script's default.

## Defensive implementation

The archive reader rejects path traversal, normalized name conflicts, missing/non-directory parents, bad framing/digests, invalid dedup references, oversized records, excessive output size, and trailing data. Decoder memory is capped. Extraction uses a new root and does not create stored symbolic links. New archives are published without overwriting an existing file. Media tools run as argument lists without a shell; source files are not their output targets.

These measures do not guarantee protection against every malicious archive, database, codec, or local process. Keep macOS/Python updated and use reasonable extraction size limits.
