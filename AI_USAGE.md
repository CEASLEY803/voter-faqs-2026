# Coding-assistance disclosure log

This is a working record for the required disclosure, not a complete conversation export or final report. Retain the chat transcript to recover all prompts, follow-ups, and available model metadata. Do not treat this file as proof of complete disclosure.

## October 22, 2026: baseline recovery and South Carolina collector

- Tool: Codex desktop coding assistant.
- Model information: session identifies the assistant as Codex based on GPT-6; exact selectable model variant and version are not exposed in the available session metadata. Verify against the app or a conversation export before final disclosure.
- Scope: project setup, recovery of a pinned upstream baseline, collector implementation, validation, and code documentation.
- Generated code: `restore_baseline.py`, `collect_sc.py`, dependency and ignore configuration.
- Supporting documentation: `README.md` and this log.
- Validation: original upstream notebook validator, baseline hashes, source-text retention, answer boundaries, links, and Unicode checks.

User instructions initiating this coding work, verbatim:

> maybe write a note for yourself, but i'd like you to explain all of your coding decisions as you go: why you chose a function, etc

Standing project policy supplied by the user, verbatim:

> No generative AI will be used except for coding. If used, all prompts and model information will be disclosed in the report

## October 22, 2026: local commit logging

User instruction, verbatim:

> Id like to keep the commits very frequent for logging purposes.

Commit author information supplied by the user, verbatim:

> CEASLEY803 is the github account name, [email removed] is the email

Coding assistance: save the frequent-commit preference, configure Git author information for this repository, and create retrospective local checkpoints for existing setup, baseline recovery, and collection work. Commit timestamps reflect actual creation time. Model information is the same as recorded above.

## October 22, 2026: source-review corrections

User request, verbatim:

> I compared the jsons with the actual website and came across a few things to fix:
>
> The script removes paragraph breaks when it shouldn't
> on voter411, the script is pulling section headers and their descriptions as Q&A when it shouldn't
>
> Preserve paragraph breaks and list structure
> Use actual question headings for FAQ records
> Keep topic introductions and sections without questions separately, that way the information survives without labeling a category as a question
> Keep the topic title alongside the supporting content so we know where it belongs

Coding assistance: implement block-aware text rendering and nested list formatting, separate supporting content from question-heading records, add checksum-verified replay of source snapshots, and update code documentation. Validate formatting and extraction boundaries with small HTML fixtures and the saved source pages. Model information is the same as recorded above. The user supplied the source-review findings and extraction requirements.

## October 22, 2026: Georgia and Ohio Vote411 portability check

User request, verbatim:

> Everything looks correct from that extraction, i think we can try running it against maybe Georgia and Ohio next

Coding assistance: add a small state-selectable Vote411 runner that reuses the corrected SC parser, text renderer, and validators. Run it for Georgia and Ohio, retain source snapshots and supporting-content sidecars, and check extraction completeness against saved page structure. These runs cover Vote411 only. The user approved the corrected SC extraction; Georgia and Ohio require their own human source review. Model information is the same as recorded above.
