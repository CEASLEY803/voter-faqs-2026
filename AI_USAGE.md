# Coding-assistance disclosure log

This is a working record for the required disclosure, not a complete conversation export or final report. Retain the chat transcript to recover all prompts, follow-ups, and available model metadata. Do not treat this file as proof of complete disclosure.

## October 22, 2026: baseline recovery and South Carolina collector

- Tool: Codex desktop coding assistant.
- Model information: session identifies the assistant as Codex based on GPT-6; exact selectable model variant and version are not exposed in the available session metadata. Verify against the app or a conversation export before final disclosure.
- Scope: project setup, recovery of a pinned upstream baseline, collector implementation, validation, and code documentation.
- Generated code: `restore_baseline.py`, `collect_sc.py`, dependency and ignore configuration.
- Validation: original upstream notebook validator, baseline hashes, source-text retention, answer boundaries, links, and Unicode checks.
- Documentation will NOT be written generatively; however the formatting did use the help of codex to create the tables seen in README.md.

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

## October 22, 2026: all-state Vote411 batch

User request, verbatim:

> ok not touching them, vote 411 seems flawless. id like to try it on all 50 now

Coding assistance: expand the explicit state-to-URL mapping to 50 states, implement sequential batch collection with per-state error isolation and a manifest, run the collector, and validate extracted records against saved HTML. Preserve the corrected parser and original text capitalization. Source review of pilot output does not establish all-state extraction completeness; automated checks and any exceptions are recorded separately. Model information is the same as recorded above.

The first attempt exposed statement headings, bold paragraph question labels, and pages with no recognized question headings (30 initial successes and 20 validation failures). Coding changes added deterministic question-label detection based on published heading/leading-bold formatting and final question marks. Sources with no identifiable questions retain supporting content with explicit review flags. All 50 saved pages were reprocessed into a separate version-3 batch; initial snapshots and outputs remain intact. Added a reusable integrity and text-token-conservation validator. New question boundaries require human review even for previously reviewed pilot states. No research interpretation was generated.

## October 22, 2026: code review and approved fixes

Review request, verbatim:

> i want to stop here and do a code review, once that's done im going to push the commits

Fix request, verbatim:

> Extract question wording without appending navigation or self-link destinations but preserve useful answer links. We can preserve paragraphs across nested contianers
>
> And definitely add the MIT license

Coding assistance: inspect collection and validation code, reproduce appended SC navigation URLs and lost nested-container paragraph boundaries, then implement separate question link handling and explicit container boundaries. Add the root MIT license with the student's copyright notice, preserve upstream licensing, and reprocess saved sources into version-4 outputs. Update validation for intentionally omitted question destinations and verify answer-link retention, formatting, source hashes, and original collection times. Model information is the same as recorded above. No push was performed.

## October 26, 2026: switch from Codex to Claude Code

From this entry on, coding assistance comes from Claude Code instead of Codex. Entries above this one used the Codex model recorded in the first entry. Entries below this one use the model recorded here unless they say otherwise.

- Tool: Claude Code, run from the Code tab of the Claude desktop app.
- Model information: Claude Opus 5.5, model ID `claude-opus-5-5`, as stated in the session's environment information. Verify against the app or a conversation export before final disclosure.
- Scope: carry on the existing coding work.

User prompts, verbatim:

Coding assistance: a read-only review of the repository (code, data folders, batch manifests, validation reports, and the original pilot folder) to summarize what is done and what remains. No code or data was changed during the review. This entry was added at the user's request.

## October 29, 2026: source URLs moved into sources.csv

User request, verbatim:

> I want to get the URL's organized first. Can we switch to using a CSV to control that?
>
> so like it has the state, the website, and the URL in a row? two rows per website for state/vote411 so that way in the future someone can just open the CSV and swap out the URL

Coding assistance: create `sources.csv` with one `state` row and one `vote411` row per state (100 rows) and a `notes` column recording where each URL came from. Vote411 URLs are the ones the existing batches used. State URLs start from the official state page that supplied the most 2024 records. Six state rows (IL, MA, NM, OH, UT, WI) are left blank because the 2024 data gives no usable official URL. Add `load_sources()` to `collect_sc.py`, and change `collect_sc.py`, `collect_vote411.py`, and `validate_vote411_batch.py` to read URLs from the CSV instead of hard-coded values. Checks: CSV Vote411 URLs match the latest batch's requested URLs, a replay of the latest batch produces byte-identical outputs and passes validation, and malformed CSV rows are rejected. A request to each state URL found six that return a 404 page (CT, DE, IN, LA, MS, SD), which are flagged in `notes`. The README was not edited. Model information is the same as the October 26 entry.

## October 29, 2026: state election site snapshots

User request, verbatim:

> we need all of the individual state websites now, elections are happening soon so id like to avoid partially updated data

Scope choice supplied by the user when asked how many pages to save per state: "All 2024 pages".

Coding assistance: allow several `state` rows per state in `sources.csv` and add every official state page the 2024 data used (excluding a county site and a League of Women Voters page). Make `load_sources()` accept CSV files saved by Excel (byte order mark). Add `snapshot_state_sites.py`, which saves exact page bytes with timestamps and checksums into one batch under `data/2026/state_sites/`, records failures (HTTP errors, redirects to 404 pages or other sites) instead of stopping, and can continue an existing batch. A Claude research subagent searched for current URLs for the 12 states with blank or dead rows; its confirmed pages, and three unconfirmed search results for IL, OH, and WI, were added to `sources.csv` with notes saying so. A test of capturing blocked sites through a browser was stopped by Claude Code's safety check as bot-check circumvention and was not used; the import option written for that test was removed before committing. A first version of the bot-check-page filter was too broad and deleted 20 real, uncommitted snapshots (CA, HI, ID, IL, MS, NJ, WA); they were downloaded again minutes later, and their recorded collection times are the times of the second download. The README was not edited. Model information is the same as the October 26 entry.

## October 29, 2026: manual saves for blocked state sites

User decision, verbatim, when asked how to capture the 15 states that refuse scripted requests:

> I'll save them myself

Coding assistance: add `--checklist` to `snapshot_state_sites.py`, which lists each blocked page with the file name to save it under, and `--import-manual`, which copies pages the user saved from their own browser into the existing batch. Imported pages are marked `manual browser save`, take their collection time from the saved file's modified time, and are rejected if they are bot-check pages or if the page's canonical address is on another site. Tested on a throwaway copy of the batch with made-up files. The user saves the pages; the code only imports them. Model information is the same as the October 26 entry.
