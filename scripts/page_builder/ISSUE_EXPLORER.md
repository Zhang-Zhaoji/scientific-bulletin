# Single-issue reading explorer

Regular report pages include an interactive reading navigator when the Markdown article titles can be matched unambiguously to one local evaluation corpus. Special issues retain their existing presentation. An unmatched or ambiguous corpus retains the existing PNG fallback.

- Both charts exclude `域外局限` and count each evaluation once by `primary_category`. Missing categories and scores are explicit groups.
- The default population includes all non-excluded evaluations; the alternate population includes only articles actually expanded in the Markdown body. The article index identifies entries available only at their source URL.
- Score histogram bins are `[0,1)` through `[9,10]`. Field-chart score bands are `<=7`, `>7 and <=9`, `>9`, and missing. These are score bands, not recommendation tiers.
- Cross-tags count once per article. The 26 most frequent tags form a deterministic, keyboard-accessible text cloud. Charts and tags follow the selected population; clicks and dropdowns filter the article index while leaving the charts visible as reference.
- All script assets are local. The payload contains only public reading metadata; author/affiliation records and model internals are not embedded. The source filename and exact count tables are inspectable under “统计明细与来源”.

Normal `scripts/build_pages.py` builds use this feature automatically. To preview regular issues without rebuilding special issues or the database:

```powershell
python -B scripts/preview_issue_explorer.py --report report_20261107.md
# Omit --report to render all identity-aligned regular issues.
python -B -m unittest discover -s tests -p test_issue_explorer.py -v
python -B scripts/check_issue_explorer_browser.py --driver <local-chromedriver.exe>
```

Preview HTML, the per-issue audit, browser checks and screenshots are written to `tmps/issue_explorer_preview/`. Browser verification uses the actual local evaluation corpus to independently reconcile both charts, exercises filtering, pagination and body navigation, and checks a 390px viewport. It never writes to input Markdown, evaluation JSON or the database.
