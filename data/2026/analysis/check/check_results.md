# Cross-check of the 2026 results

1,601 numbers recounted, all match.

Written by `code/check_results.py`. It works the published numbers out a second time from the dataset files, `comparison/pairs.csv`, `topics.csv` and `settings.toml`, without the code that produced them, and compares them with `per_state.csv` and the per-state comparison files.

## Mismatches

None.

## Numbers to compare with the README and the chart titles

| Records | 2024 | 2026 |
| --- | --- | --- |
| State election sites | 2,020 | 2,028 |
| Vote411 | 1,163 | 2,360 |
| Other pages, not compared | 104 | 0 |
| All | 3,287 | 4,388 |

- Median major change, state election site: 21% over 37 states
- Median major change, Vote411: 52% over 44 states
- States with a question on all 6 topics in 2024: 49 of 50
- States with a question on all 6 topics in 2026: 50 of 50
- Rows in pairs.csv: 3,949

States the change chart leaves out, and why:

- State election site, fewer than 0.5 times the 2024 count: Hawaii, Indiana, Iowa, Maryland, Massachusetts, Minnesota, North Dakota, Texas
- State election site, more than 2 times the 2024 count: Colorado, Wisconsin
- State election site, none in 2024 to compare with: Illinois, Ohio, Utah
- Vote411, more than 2 times the 2024 count: California, Georgia, Wisconsin
- Vote411, none in 2024 to compare with: Michigan, New Mexico, Pennsylvania

## Five states to read off the change chart

Picked with a fixed seed, so they are the same on every run. Find each state's bar on `charts/change_rate_by_state.png` and see that it matches.

- Kansas, state election site: 5 of 24 major (21%), 5 of 24 minor (21%)
- Kansas, Vote411: 9 of 22 major (41%), 2 of 22 minor (9%)
- Missouri, state election site: 7 of 24 major (29%), 17 of 24 minor (71%)
- Missouri, Vote411: 15 of 22 major (68%), 0 of 22 minor (0%)
- New Jersey, state election site: 6 of 33 major (18%), 5 of 33 minor (15%)
- New Jersey, Vote411: 8 of 23 major (35%), 1 of 23 minor (4%)
- North Carolina, state election site: 14 of 96 major (15%), 14 of 96 minor (15%)
- North Carolina, Vote411: 16 of 23 major (70%), 1 of 23 minor (4%)
- South Carolina, state election site: 18 of 34 major (53%), 4 of 34 minor (12%)
- South Carolina, Vote411: 15 of 22 major (68%), 1 of 22 minor (5%)

## Spot check by a person

`spot_check.csv` holds 41 rows of `pairs.csv`, 2 for each source and result that occurs. Open the two addresses of a row, see whether the result is right, and write yes or no in the agree column, with your name and the date. A row that is filled in is never changed by a later run.

- Filled in: 0 of 41
- Say yes: 0
- Say no: 0
