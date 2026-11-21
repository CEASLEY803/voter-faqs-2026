# VOICE: U.S. Voter FAQs Collection and Analysis Engine

This project scrapes voter frequently asked questions (FAQs) from official state election websites and Vote411.org for the 2026 election. It formats that data to match the AI for Society Research Group's 2024 dataset, and then runs a comparison to see exactly how each state's voter information changed between the two elections.

**Read more:** the [writeup](docs/Writeup.pdf), the [slides](docs/Presentation.pdf), and the [technical description](docs/TechnicalDescription.md).

## Why

Voter FAQs answer the biggest questions voters have, like how to register, where to vote, and what ID to bring. When an answer changes and the old version is still in use, voters can act on outdated rules.

## What it found

The 2026 dataset pulled 4,388 records across all 50 states (2,028 from state sites, 2,360 from Vote411). I saved these pages in the weeks leading up to the November 3 election.

A **major change** means a question was added, a question was removed, or an answer was rewritten (less than 85% similar to the 2024 answer).

- **State election sites:** in the median state, 21% of questions had a major change (out of 37 states with enough data to compare). States ranged from 0% to 94%.
- **Vote411:** the median is 52% (44 states). Vote411 is compared by whole section rather than by question, so this number can't be compared directly with the 21%.
- **Topics:** all 50 states now cover six core topics (registration, mail voting, early voting, voter ID, polling places, and deadlines), up from 49 states in 2024.

**So what:** the 2024 answers can't be assumed to still be current. Some states barely changed their FAQs, while others rewrote almost all of them. Because the whole comparison runs with one command, it can be repeated for 2028 under the same rules.

These numbers are preliminary, because no state's data has been reviewed by hand yet.

![How much each state's voter FAQ changed from 2024 to 2026](data/2026/analysis/charts/change_rate_by_state.png)

You can [browse all 3,949 compared questions](https://lite.datasette.io/?csv=https://github.com/CEASLEY803/voter-faqs-2026/blob/master/data/2026/analysis/comparison/pairs.csv&metadata=https://raw.githubusercontent.com/CEASLEY803/voter-faqs-2026/master/data/2026/analysis/comparison/pairs_metadata.json#/data/pairs?_col=state&_col=source&_col=result&_col=question_2024&_col=question_2026&_facet=result&_facet=source&_size=20) in your browser, filtered by state, source, or result.

## How to run it

One command handles the whole pipeline. It scrapes the pages, builds the JSON records, checks for data problems, compares it against the baseline year, and generates the charts. To collect 2028 and compare it to 2026:

```
python code/run_pipeline.py --year 2028 --baseline-year 2026 --collect
```

You shouldn't need to touch the Python code for a new cycle. Update `sources.csv` with the new URLs, and adjust the thresholds in `settings.toml` if needed. Setup and every option are in the [technical description](docs/TechnicalDescription.md#getting-started--how-to-run).

## Where things are

| Folder or file | What's in it |
| ----- | ----- |
| [`docs/`](docs/) | The writeup, the slides, and the technical description. |
| [`code/`](code/) | The Python scripts. `run_pipeline.py` runs everything. |
| [`data/2024/`](data/2024/) | The 2024 dataset, unchanged. |
| [`data/2026/`](data/2026/) | The saved pages, the dataset, quality reports, and charts. |
| `sources.csv`, `settings.toml` | The URLs to scrape, plus the rules and thresholds. |
| [`reference/`](reference/) | Files kept unchanged from the 2024 project (its README, license, and a notebook), plus a record of the exact version used. |
| [`AI_USAGE.md`](AI_USAGE.md) | Log of the prompts and AI models I used. |

## Credits

I (Cole Easley) built this for a CSCE 498 independent study at the University of South Carolina in Fall 2026, mentored by [Dr. Biplav Srivastava](https://github.com/biplav-s) of the [AI for Society Research Group](https://github.com/ai4society).

**Data:** The 2024 baseline data comes from the group's [election-dataset-us](https://github.com/ai4society/election-dataset-us/) repository. I pulled the 2026 data from the 50 state election websites listed in `sources.csv` and from [Vote411](https://www.vote411.org/).

**Software:** Python with [Requests](https://requests.readthedocs.io/), [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/), [pypdf](https://pypdf.readthedocs.io/), and [Matplotlib](https://matplotlib.org/). [Datasette Lite](https://lite.datasette.io/) is what displays the CSV in the browser. I used the [Internet Archive](https://web.archive.org/) as a fallback for state sites that blocked the scraper.

**Generative AI:** I used generative AI for a large portion of the coding work: OpenAI Codex (GPT-6) and Claude Code (Claude Opus 5.5 and Claude Fable 5.2). The prompts and models are logged in [`AI_USAGE.md`](AI_USAGE.md). Claude also helped organize and improve formatting of README, as well as updating outdated links/filepaths when architecture changed over the course of development.

### Citation

If you find this work useful, please cite the paper behind the 2024 dataset:

```
@inproceedings{ai4s2024-voterfaqsUS,
  title={Do Voters Get the Information They Want? Understanding Authentic Voter FAQs in the US and How to Improve for Informed Electoral Participation},
  author={Vipula Rawte and Deja N Scott and Gaurav Kumar and Aishneet Juneja and Bharat Sowrya Yaddanapalli and Biplav Srivastava},
  booktitle={TrustNLP: Fifth Workshop on Trustworthy Natural Language Processing, 2025 Annual Conference of the North American Chapter of the Association for Computational Linguistics (NAACL 2025), https://2025.naacl.org/},
  year={2025}
}
```

### Related data

- [election-dataset-us](https://github.com/ai4society/election-dataset-us/): the 2024 U.S. voter FAQs this project compares against.
- [election-dataset](https://github.com/ai4society/election-dataset/): voter FAQs from leading global democracies.

### License

New code and documentation in this project use the MIT license in `LICENSE`, copyright 2026 Cole Easley.

Material included from the 2024 project keeps its MIT license and copyright notice in `reference/LICENSE`, copyright 2024 AI for Society Research Group. (Note: The state web pages themselves might have their own copyright rules that the MIT license doesn't override).
