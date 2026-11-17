# 2024 Voter FAQ Data

This is the baseline 2024 dataset from the AI for Society Research Group's [election-dataset-us](https://github.com/ai4society/election-dataset-us/) repository. I didn't collect this data, and the pipeline never modifies it. It's strictly here so we have something to compare the 2026 data against.

| File | What's in it |
| ----- | ----- |
| `<state>_qa.json` | One file per state containing its questions and answers (mostly from the state site and Vote411, plus a few other pages like county sites). Note: Delaware uses the weird filename `dl_qa.json`. |
| `manifest.json` | A cheat sheet tracking how each state stored its Vote411 records in 2024. `code/describe_dataset.py` auto-generates it, and the comparison tool reads it. |

If you ever need to restore these files to their exact original state, I recorded the specific repo version in `reference/baseline_provenance.json` along with file checksums. You can pull them back down by running:

```
python code/restore_baseline.py
```

If you end up using this 2024 data for your own work, make sure to cite their original paper. The citation block is in the main [README](../../README.md#citation).
