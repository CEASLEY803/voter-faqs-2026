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

## November 4, 2026: parsing, combined dataset, comparison, analysis and pipeline

User request, verbatim:

> Finish the remaining code for the project. It should be rerunnable for a future election cycle.
>
> 1. Parse the saved state election site pages in data/2026/state_sites/20261029T220403252970Z/ into Q&A records with q, a, s and t, the same fields as the 2024 files.
>    - Use one general parser instead of one per state. On most pages a question is a short block ending in a question mark, sometimes starting with Q: or Q., and its answer is everything after it until the next question or the next heading that is not a question. This covers headings, accordion buttons, bold lead-ins and dt/dd lists.
>    - Remove navigation menus, headers, footers and sidebars first, since the menus on the NV, IA, ND and MA pages contain short question-like lines. Drop questions with empty answers so tables of contents are not turned into records.
>    - Keep parse_scvotes for South Carolina. Allow site-specific parsers to be added later through a lookup by hostname.
>    - Parse the Delaware pollbook PDF with pypdf or flag it.
>    - The Iowa FAQ, the Delaware general FAQ and the Colorado main FAQ page have no FAQ text in the saved HTML. Flag them instead of guessing.
>    - Compare each page's record count to the number of records the same URL produced in 2024 and flag pages that come out well below it.
>
> 2. Build a combined 2026 dataset with one file per state in the same format as data/2024, using the Vote411 records from the latest validated batch plus the state site records, and a manifest listing which batches it came from.
>
> 3. Compare 2024 and 2026 per state within each source, state site against state site and Vote411 against Vote411, using the s URL. Classify questions as same, reworded, new or removed, and flag changed answers for matched questions. Handle the 2024 quirks: tx_qa.json uses metadata and data instead of questions, nm_qa.json has no records, Delaware is filed as dl, and some MA records list Voting-Mass.gov or Voting411.org as the source instead of a URL.
>
> 4. Cross-state analysis and charts: counts per state for both years, change rates, and topic coverage for registration, mail and absentee voting, early voting, voter ID, polling places and deadlines, using keyword rules. Rank states by coverage and by amount of change.
>
> 5. One command that runs the whole pipeline for a given cycle, with the year as an input instead of hardcoded 2026, plus a review file for marking each state approved with a name and date. The analysis should be able to run on approved states only.
>
> Add any new libraries to requirements.txt with pinned versions.

Coding assistance: add `datasets.py` (reads yearly datasets, including the 2024 `tx` layout and the `nm` file, which holds 66 records as parallel `q`, `a` and `s` lists under the code `mx`; classifies records as state site, Vote411 or other), `parse_state_sites.py` (general parser, `SITE_PARSERS` hostname lookup with `parse_scvotes`, numbered-PDF parsing with pypdf, flags for pages with no records or under half the 2024 count for the same URL), `build_dataset.py` (writes `data/<year>/combined/` and its manifest), `compare_years.py` (same, reworded at similarity 0.8 or higher, new and removed questions; answer changes with similarity scores, ignoring lines repeated across most answers of a page), `analyze_states.py` (counts, change rates, keyword topic coverage, rankings and three matplotlib charts) and `run_pipeline.py` (one command per cycle, a review file at `data/<year>/review.csv`, and `--approved-only`). The collectors take `--year`. Parser rules were adjusted after checking the output against the saved pages and the 2024 counts for NV, TN, WY, NJ, WA, AZ, VT and WV. The thresholds (0.8 for rewording, 0.6 for repeated lines) were chosen by Claude from samples of the data and are constants in the code. Charts use a palette checked with the dataviz skill's validator. Code and data outputs only: no interpretation or report text was written. Pypdf 6.21.4 and matplotlib 3.11.2 were already installed and are now pinned. The README was not edited. Model information is the same as the October 26 entry.

## November 5, 2026: extraction methods in manifests and Vote411 comparison by section

User request, verbatim:

> Have each year’s manifest record how its data was extracted, so the code can tell when two years used different methods.
> Compare Vote411 by section when the earlier year used section titles, and question by question when both years used the same method.
> Make that choice a setting a future student can change, not something hardcoded.

Coding assistance: add `settings.toml` with `vote411_unit` (auto, section or question) and ordered keyword rules that assign a Vote411 record to a section. Add `describe_dataset.py`, which writes a manifest for a dataset this pipeline did not build and infers each state's Vote411 method from the records; it wrote `data/2024/manifest.json` (28 section_titles, 15 mixed, 4 question_headings, 3 none) with the counts behind each state and refuses to overwrite manual corrections without `--force`. `build_dataset.py` records the 2026 methods (39 question_headings, 11 sections_without_questions), extraction version and parser version. `compare_years.py` chooses the unit per state from the setting and both manifests, builds 2026 sections from the saved Vote411 pages and 2024 sections from the keyword rules, and lists records no rule matches. `per_state.csv` gains the unit, both methods, compared counts and mean answer similarity. Claude found while checking the data that the 2024 Vote411 method varies by state rather than by year, and chose the inference rule and its thresholds from the records; the keyword rules were written by Claude from the 2024 wordings and 2026 section titles. Code and data outputs only: no interpretation or report text was written. The README was not edited. Model information is the same as the October 26 entry.

## November 10, 2026: non-FAQ rules, Vote411 section records, minor and major edits, data quality report

- Model information: this request started on Claude Opus 5.5 (`claude-opus-5-5`). Partway through, the user switched the session to Claude Fable 5.2, model ID `claude-fable-5-2`, as stated in the session's environment information. The search for false positives, the threshold sampling and the first draft of the settings were done on Opus 5.5; the code changes, the data quality report, the rebuild and this entry were done on Fable 5.2. Entries below this one use Fable 5.2 unless they say otherwise. Verify against the app or a conversation export before final disclosure.

User request, verbatim:

> The parser is currently saving any short block that ends with a question mark so page elements like contact boxes are getting saved as actual records. For example Oregon's 2026 data pulled in How Can We Help You? from the bottom of their FAQ page. Please track down similar false positives across all states like questions that repeat on multiple pages or sound like calls to action. Drop them using rules that can be edited later in settings.toml and list the dropped items in the data quality report.
>
> There are also 11 states with zero Vote411 records in the combined 2026 data because their Vote411 pages use sections instead of question headings so the extractor comes up empty. To fix this just store any section without question headings as a single record. Use the section title as the question and the section text as the answer which matches the 2024 data structure. Please work from the already saved pages instead of downloading them again, note this method in the manifest and rebuild the combined dataset.
>
> Regarding Vote411 change rates a single word edit anywhere in a section currently flags it as changed resulting in 47 out of 50 states showing a 100% change rate. We need this metric to reflect meaningful changes so please set up a similarity threshold to categorize edits into minor and major and report them separately. Pick a realistic threshold based on actual section pairs and store it in settings.toml.
>
> For the new data quality report step in run_pipeline.py generate a CSV file accompanied by a brief Markdown summary per cycle. This report should centralize flagged pages, states missing records for a particular source, dropped non-FAQ questions, unusually short or long answers, duplicate questions within the same state and states where the record count falls way below the baseline cycle.
>
> Finally please move the rewording threshold and the boilerplate settings from compare_years.py into settings.toml so all comparison settings live in a single file. Once everything is set rerun the pipeline for 2026 and update the analysis output.

A later message in the same request, verbatim, after the user interrupted to switch models:

> continue

Coding assistance: add non-FAQ rules to `settings.toml` and apply them in `build_dataset.py`, which drops 11 state-site records (CT, MN, ND, OH, OR, WV) and lists them in `dropped_records.json`. Claude chose which candidates to drop and which to keep: South Carolina's "How can I help?" (a real accordion entry) and North Carolina's "Unsure if you are registered?" (also in the 2024 data) were kept, and real FAQ entries repeated on sibling pages (LA, WI, MO, UT) are reported but not dropped. `build_dataset.py` stores each Vote411 section without question headings as one record from the saved batch files (765 records; 2,360 Vote411 records in total) and records the methods in the manifest (39 mixed, 11 section_titles). `compare_years.py` reads its thresholds from `settings.toml` and labels answer changes `minor_change` or `major_change`; Claude chose the 0.85 threshold from samples of matched 2024 and 2026 Vote411 sections. A 2024 section made of one record now compares on its answer only. `analyze_states.py` reports minor, major and total change rates, ranks by major change, and stacks major and minor in the change chart. New `quality_report.py`, called by `run_pipeline.py`, writes `data/<year>/quality/quality_report.csv` and `quality_summary.md`; the Markdown is generated by code from counts and lists, with no interpretation. The 2026 pipeline was rerun and its outputs updated. The README was not edited.

## November 10, 2026: comparison unit rule, Illinois correction and per-state overrides

User answer, verbatim, when asked whether CA, GA, IL and TX should compare Vote411 question by question again:

> Yes for CA, GA and TX, but not IL
>
> For Illinois keep the comparison by section. The 2024 Vote411 records for Illinois are not real questions and instead contain dates and page fragments like By Mail Tuesday October 8 2024 and Get Registered. This means the recorded method for Illinois in 2024 is incorrect. also allow per state overrides of the comparison unit directly in settings.toml and set Illinois to use the section method

Coding assistance: the method Claude's inference had recorded for Illinois in 2024 was found to be wrong. `describe_dataset.py` now records a state as `page_fragments` when under half of its Vote411 records end in a question mark (Illinois: 0 of 103; the next lowest state is 70%), and `data/2024/manifest.json` was regenerated, with Illinois the only state that changed. The "auto" rule in `compare_years.py` now compares question by question when the baseline used question headings and the current cycle has question-heading records, which applies to CA, GA and TX. `settings.toml` gains `[comparison.vote411_unit_overrides]`, which takes priority over the setting and the manifests, with `il = "section"`. Summary rows, per-state comparison files and `per_state.csv` record what decided each state's unit. The 2026 pipeline was rerun: 46 states by section from the manifests, Illinois by section from the override, and 3 by question. Model: Claude Fable 5.2 (`claude-fable-5-2`). The README was not edited.

## November 13, 2026: pairs file for the comparison step

User request, verbatim:

> Add a pairs file to the comparison step. Right now each state's comparison lives in its own JSON file, so there is no single place to browse every 2024 and 2026 pair. Have the analysis step also write data/<year>/analysis/comparison/pairs.csv with one row per compared question or section across all states, so it gets rebuilt every cycle like the other outputs.
>
> Each row should have the state, the source (state site or Vote411), the unit, the question status, the answer status, both similarity scores, both questions, both answers and both source URLs. Add one plain-language column that combines the two labels, like "same question, major answer change" or "new question", so someone browsing the table can filter without reading the README first. Keep every status, including unassigned. Sort by state, then source.
>
> Then rerun the 2026 analysis. Apart from the new file, the existing outputs should come out unchanged, so please check that. Report the row count and file size. I'll update the README myself, so leave it alone. Commit when done but don't push.

Coding assistance: `compare_years.py` now writes `comparison/pairs.csv` from `write_comparison`, so both the analysis step and the standalone comparison produce it. Each compared item carries both answers in memory; they are written to `pairs.csv` only and left out of the per-state JSON files, which stay as they were. The plain-language `result` column and its wording (for example "same section, major text change" and "2024 record not matched to any section") were chosen by Claude. The file is saved as UTF-8 with a byte order mark so Excel reads it correctly. The 2026 analysis was rerun: `pairs.csv` has 3,824 rows, the same as the items in the 50 JSON files, and git showed no change to any existing output. Model: Claude Fable 5.2 (`claude-fable-5-2`). The README was not edited.

## November 13, 2026: no change rates when a source has no records in one year

User request, verbatim:

> States with no records for a source in one of the two years currently get a 100% major change rate. For example, Colorado and Iowa have no 2026 state-site records, so every 2024 question counts as removed, and Illinois, Ohio and Utah have no 2024 state-site records, so every 2026 question counts as new. That's missing data, not change, and it makes those states look like the ones that changed most.
>
> When a state has no records for a source in one of the two years, leave its minor, major and total change rates for that source blank instead of computing them. Leave it out of the major change ranking for that source. Add a column for each source to per_state.csv that says why, like "no 2024 records" or "no 2026 records". In change_rate_by_state.png, show those states with that short label instead of a bar, so they don't read as 0%. Keep everything else as it is, including their rows in the comparison files and pairs.csv.
>
> Then rerun the 2026 analysis. Report which states and sources this affects, and confirm that only per_state.csv, rankings.csv and change_rate_by_state.png changed. Leave the README alone. Commit when done but don't push.

Coding assistance: `analyze_states.py` leaves the three change rates and the major change rank blank for a source when the state has no records for it in one of the two years, adds `change_rate_note_state_site` and `change_rate_note_vote411` to `per_state.csv`, and draws those states at the bottom of each chart panel with the note in place of a bar. The 2026 analysis was rerun. It affects the state-site rates of CO and IA (no 2026 records) and IL, OH and UT (no 2024 records), and the Vote411 rates of MI, NM and PA (no 2024 records). Git showed changes only to `per_state.csv`, `rankings.csv` and `change_rate_by_state.png`. Model: Claude Fable 5.2 (`claude-fable-5-2`). The README was not edited.

## November 13, 2026: topic rules corrected and moved to settings.toml

User request, verbatim:

> The topic coverage numbers undercount voter ID in 2024. The voter_id rule in analyze_states.py catches phrases like "photo ID" and "voter ID" but not "What ID is needed for voting?" or "What types of ID are acceptable for voting in Alabama?". Because of that, 9 states show no voter ID question in 2024, but 8 of them (AK, AL, AR, HI, ME, NH, RI and WA) do have one. Wisconsin looked like the only real gap. This is most of the reason coverage of all six topics appears to go from 39 states to 48.
>
> Fix the voter_id rule so it catches questions asking what ID is needed or accepted, without picking up unrelated uses of "ID". Then check the other five topic rules the same way against both years' questions, looking for real questions they miss and unrelated questions they catch, and fix any you find. While you're in there, move the topic rules into settings.toml with the other rules, so a future student can change them without editing code.
>
> Then rerun the 2026 analysis. Report how many states cover all six topics and how many have a voter ID question, in 2024 and in 2026, before and after the fix. List every question that newly matches or stops matching a topic so I can spot check them. The comparison files and pairs.csv shouldn't change. Leave the README alone. Commit when done but don't push.

Coding assistance: the six topic rules moved from `analyze_states.py` to `[[topics]]` entries in `settings.toml`, each with a name, a chart label, a pattern and an optional `ignore` list of phrases that are cut out of a question before the pattern is tried. `datasets.py` validates and applies them (`topic_rules`, `question_topics`). Claude chose the new patterns and ignore phrases after listing, for both years, what each old rule matched and what looser keywords it missed. The voter ID rule now matches any mention of an ID, identification or proof of identity, and ignores the "voter ID card" that Oklahoma and Missouri mail to registered voters. The other changes: early voting also matches "early in-person voting", "in-person absentee", "advance voting" and "vote before Election Day"; polling places no longer counts poll workers, poll watchers, poll books, exit polls or precinct committee offices, and also matches "where do I go to vote", polling or voting hours and voting locations; deadlines no longer counts "due to" and also matches wordings such as "when do I need to register" and "too late"; mail and absentee no longer counts registering by mail and also matches wordings such as "return my ballot" and "when are ballots mailed"; registration no longer counts registering a business, vehicle, PAC or minor party and also matches "voter rolls". The 2026 analysis was rerun. States covering all six topics: 39 before and 49 after in 2024, 48 before and 50 after in 2026. States with a voter ID question: 41 before and 50 after in 2024, 50 before and after in 2026. Git showed changes only to `per_state.csv`, `rankings.csv`, `topics.csv` and `topic_coverage.png`; the comparison files and `pairs.csv` did not change. The 789 question and topic pairs that changed were listed in `topic_rule_changes.csv` for the user to spot check (not committed). Model: Claude Fable 5.2 (`claude-fable-5-2`). The README was not edited.

## November 14, 2026: charts and pairs.csv reworked for a first-time reader

User request, verbatim:

> The three charts and pairs.csv were checked the way a first-time visitor sees them: on the GitHub page at normal size and in the Datasette Lite table. They are hard to read at a glance. Fix the problems below, then rerun the 2026 analysis.
>
> 1. States with too few 2026 records to compare. Seven states have a 2026 state-site record count under half of their 2024 count: HI 13 (was 52), IN 3 (21), MA 13 (79), MD 6 (23), MN 22 (55), ND 5 (28), TX 27 (69). All seven have flagged pages in the quality report, so most of their removed questions are questions the collection missed. Their rates measure the collection, not the state, and they are 7 of the top 9 bars on the state-site side of the change chart. Treat them like the states with no records in one year: leave the three rates blank, write the reason in the change_rate_note column (for example "13 records in 2026, 79 in 2024"), and show that note on the chart in place of a bar. Use the existing below_baseline_ratio setting as the cutoff so this rule and the quality report always agree. Apply it to both sources and do not hard-code the states.
>
> 2. Change chart (change_rate_by_state.png).
> - Alabama and Maine have empty rows on the state-site side because nothing changed. An empty row looks like missing data. Label a row with 0% change "no change".
> - Move the legend to the top, under the title. It is now below all 50 rows.
> - Draw a line at the median major change rate on each side, and put the number in that side's title, for example "State election site: median major change 22% (38 states)". Compute it from the data.
> - The Vote411 title says "by section in 44 states, by question in 3" because it counts only states that have a bar. The rest of the project says 47 and 3. Count all states so the numbers match.
>
> 3. Questions chart (questions_per_state.png).
> - On the Vote411 side, most 2024 records are whole sections and most 2026 records are questions, so Vote411 looks like it tripled. When the manifests show the two years were built differently, say so in that side's title in plain words, and do not label the axis "Questions".
> - A state with no records for a source in one year has a missing bar and no label (state site: IL, OH and UT in 2024, CO and IA in 2026; Vote411: MI, NM and PA in 2024). Label these the same way the change chart does.
> - Say the sort order under the title. Move the legend to the top.
>
> 4. Topic chart (topic_coverage.png).
> - Almost every state covers every topic in both years, but most squares are so pale that the chart reads as "barely covered", and a square with one question looks the same as a square with none. Make an empty square unmistakable (white with an X) and give a square with one question a clearly visible color.
> - Put the finding in the title, computed from the data, for example "49 of 50 states covered all six topics in 2024, and all 50 in 2026".
> - "Ordered by coverage rank" means nothing to a reader. Say the order in plain words.
>
> 5. Size of all three charts. GitHub shows each chart about 850 pixels wide, which is about half its real size, and the change chart is then taller than a laptop screen. Make each chart fit in about 800 pixels of height at that width, with no text smaller than about 10 pixels at that width. To check, save a copy of each chart scaled to 850 pixels wide and look at it. Do not commit the copies.
>
> 6. pairs.csv. In the Datasette Lite table most filter combinations return no rows.
> - The state column holds lowercase codes, so "state = Oregon" and "state = OR" both return nothing. Write the full state name, such as Oregon.
> - unit, question_status and answer_status repeat what result already says, and combining any of them with result usually returns nothing. Remove those three columns. The per-state JSON files still have them.
> - Name the question, answer and URL columns by year instead of baseline and current, using the two years of the run: question_2024, question_2026, answer_2024, answer_2026, url_2024, url_2026.
> - Column order: state, source, result, the two questions, the two answers, the two similarity scores, the two URLs.
> Do not change the per-state JSON files or summary.csv.
>
> Then rerun the 2026 analysis and report: the new median major change rate for each source and how many states it covers, every state and source with a blank rate and its note, and the list of changed files from git. Only per_state.csv, rankings.csv, pairs.csv and the three charts should change. Also look at each finished chart at 850 pixels wide and say what a first-time reader would still find unclear. Leave the README alone, because its numbers and links will be updated separately. Commit when done but don't push.

Coding assistance: `datasets.py` gains `below_baseline`, which both `quality_report.py` and `analyze_states.py` call with the `below_baseline_ratio` setting, and `STATE_NAMES`. `analyze_states.py` leaves the three change rates and the major change rank blank for a source whose record count is under that share of the baseline count, with a note such as "13 records in 2026, 79 in 2024". This applies to the state-site rates of HI, IN, MA, MD, MN, ND and TX and to no Vote411 rates. The three chart functions were rewritten. Every chart is now drawn 8.5 by 8 inches, so it is 850 by 800 pixels at the width GitHub shows, with no text under 10 pixels at that size. Claude chose the layout, the wording on the charts, the plain-word descriptions of the Vote411 extraction methods, and the topic chart's four color steps (1, 2 to 4, 5 to 9, 10 or more), which were checked with the chart skill's palette validator. `compare_years.py` writes `pairs.csv` with full state names, year-named columns and without the unit and status columns, sorted by state name; row count (3,824) and all remaining cell values are unchanged. The 2026 analysis was rerun. Median major change: state election site 22% over 38 states (was 27% over 45), Vote411 55% over 47 states (unchanged). Git showed changes only to `per_state.csv`, `rankings.csv`, `pairs.csv` and the three charts. Each chart was viewed scaled to 850 pixels wide; the scaled copies were not committed. Model: Claude Fable 5.2 (`claude-fable-5-2`). The README was not edited.

## November 14, 2026: removed pages listed in the quality report

User request, verbatim:

> When a page in sources.csv has moved, the old address usually returns a 404 or redirects to a 404 page. snapshot_state_sites.py records these as failed with one of the errors in REMOVED_PAGE_ERRORS. It leaves them off the save-by-hand checklist, and the pipeline keeps going. That part works.
>
> The problem is where these pages show up. They only appear in the run's printed output and in the batch's batch_manifest.json. The quality report never lists them, so a moved page can go unnoticed. The 2026 batch still has four of them in sources.csv: one Connecticut page that redirects to a 404 page, two Indiana pages that return 404, and one Michigan page that returns 404. Indiana is also one of the states with under half its 2024 record count, and nothing in the report connects the two.
>
> Add a category called removed_page to quality_report.py. It gets one row for each state-site page that is still in sources.csv and whose snapshot failed with one of the REMOVED_PAGE_ERRORS. Use the state-site batch the build used, which the build manifest already names. Each row gives the state, the URL and the error. Import REMOVED_PAGE_ERRORS from snapshot_state_sites.py instead of copying the strings.
>
> Put the new category first, since it's the one to act on before rerunning. Its line in the summary table should say what to do: find each page's new address and update sources.csv. In the summary's own section for the category, list each page with its state, URL and error, the same way missing_source lists its rows.
>
> Leave pages that redirect to another site, and pages that return 403, as they are. In the 2026 batch every one of them was a bot check, and the save-by-hand checklist is the right place for those.
>
> Then regenerate only the 2026 quality report. The new category should list the four pages above. Nothing outside data/2026/quality/ should change. Leave the README alone. Commit when done but don't push.

Coding assistance: `quality_report.py` gains `removed_pages`, which reads the `batch_manifest.json` of the state-site batch named in the build manifest and returns each failed page whose error is in `REMOVED_PAGE_ERRORS` (imported from `snapshot_state_sites.py`) and whose URL is still a state row in `sources.csv`. Each one becomes a `removed_page` row with the state, the URL and the error in the detail column. The category is first in `CATEGORIES`, so it is first in both output files, and the summary lists its rows one per line. Claude wrote the category's description. Only the 2026 quality report was regenerated: 126 findings, up from 122. The four new rows are the Connecticut page (redirected to a 404 page), the two Indiana pages and the Michigan page (HTTP 404). The 122 earlier rows are unchanged and in the same order, and git showed changes only to the two files in `data/2026/quality/`. Model: Claude Fable 5.2 (`claude-fable-5-2`). The README was not edited.

## November 14, 2026: replacement candidates for removed pages

User request, verbatim:

> When a page in sources.csv is gone, snapshot_state_sites.py records it as failed with one of the errors in REMOVED_PAGE_ERRORS. The pipeline keeps going, which is right. But those pages only show up in the printed output and in batch_manifest.json. The quality report doesn't list them, and nobody is told where the page might have moved. Right now someone has to hunt for the new address by hand.
>
> Make the tool do that search.
>
> 1. Find candidates. Add an option to snapshot_state_sites.py, used with --batch, that looks for a replacement for each removed page still in sources.csv. Collect links from the removed page's parent address and from the state's other saved pages in the batch. Keep links on the same site that aren't already in sources.csv. Rank them by how close their address and link text are to the removed page's address, and keep the top three. Download each candidate with the same user agent and one-second delay as the rest of the script. Run parse_html on it and count the questions it finds. Save the candidates in the batch folder so the quality report can read them without going online. Don't save candidate pages as snapshots, and never change sources.csv automatically.
>
> 2. Report them. Add a removed_page category to quality_report.py and put it first. It gets one row per removed page still in sources.csv, from the state-site batch the build used. The summary lists each page with its state, address and error. Under each page it lists the candidates with their question counts, or says no candidate was found. Import REMOVED_PAGE_ERRORS instead of copying the strings.
>
> 3. Wire it in. run_pipeline.py --collect should run the candidate search after the snapshot step, so a new cycle gets suggestions without an extra command.
>
> Leave pages that return 403 or redirect to another site alone. In the 2026 batch those were all bot checks, and the save-by-hand checklist already covers them.
>
> Then run the candidate search on the 2026 batch and regenerate the 2026 quality report. Four removed pages are still in sources.csv: one in Connecticut, two in Indiana and one in Michigan. For Indiana's /idr/hoosiers-vote/register/ page, the search should find /idr/hoosiers-vote/register-to-vote and report 0 questions. Report what it found for all four. In the data, only the new candidates file in the batch folder and the files in data/2026/quality/ should change. Leave the README and sources.csv alone. Commit when done but don't push.

Coding assistance: this builds on the `removed_page` category from the entry above, which was already committed. `snapshot_state_sites.py` gains `--find-replacements`, used with `--batch`. For each removed page still in `sources.csv` it reads the links on the page's parent address and on the state's saved HTML pages in the batch, keeps links on the same site whose address is not in `sources.csv`, scores each one, downloads the three best with the script's user agent and one-second delay, and counts the questions `parse_html` finds. The result is written to `replacement_candidates.json` in the batch folder. Candidate pages are not saved, and `batch_manifest.json` and `sources.csv` are not written. Claude chose the score: the average of how alike the two addresses are (Python's `difflib.SequenceMatcher`) and the share of the words in the removed page's own name that appear in the link text. Claude also chose the file name, the fields saved for each candidate, a second try ten seconds later when a connection drops, and the rule that running the search for named states keeps the saved results of the others. The checks that decide whether a download is a usable page were moved out of `save_response` into `response_error`, so saved pages and candidates use the same checks. `removed_pages` now lives in `snapshot_state_sites.py`, where the search and the quality report both call it, so `quality_report.py` imports that function and not `REMOVED_PAGE_ERRORS` itself; the error strings are still written in one place. `quality_report.py` reads the candidates file, puts each page's candidates in its `removed_page` row, and lists them under the page in the summary with their question counts, link text and score. It says "No candidate found" or "Candidates not searched" when that is the case. Claude wrote the explanation at the top of that summary section. `run_pipeline.py --collect` runs the search right after the snapshot step. The search was run on the 2026 batch and the 2026 quality report was regenerated. All four removed pages got three candidates. For Indiana's `/idr/hoosiers-vote/register/` the first candidate is `/idr/hoosiers-vote/register-to-vote` with 0 questions. Git showed changes only to the new candidates file and the two files in `data/2026/quality/`; the report still has 126 findings. The score, the retry, the report wording for the two empty cases and the order of the pipeline steps were checked with a scratch script that is not in the repository. Model: Claude Fable 5.2 (`claude-fable-5-2`). The README and `sources.csv` were not edited.
