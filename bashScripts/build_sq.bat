@echo off
if exist data\literature.db del data\literature.db
if exist data\literature.db-journal del data\literature.db-journal
call :run python ./sql_scripts/build_sqlite.py --jsonl "./getfiles/all_papers_2026-03-14_enriched_ror_refined.jsonl" --LLM_results "./LLM_Results/LLM_results_20260315_010034.json"
call :run python ./sql_scripts/build_sqlite.py --jsonl "./getfiles/all_papers_2026-03-21_enriched_ror_refined.jsonl" --LLM_results "./LLM_Results/LLM_results_20260321_015612.json"
call :run python ./sql_scripts/build_sqlite.py --jsonl "./getfiles/all_papers_2026-03-28_enriched_ror_refined.jsonl" --LLM_results "./LLM_Results/LLM_results_20260328_004204.json"
call :run python ./sql_scripts/build_sqlite.py --jsonl "./getfiles/all_papers_2026-04-04_enriched_ror_refined.jsonl" --LLM_results "./LLM_Results/LLM_results_20260404_020849.json"
call :run python ./sql_scripts/build_sqlite.py --jsonl "./getfiles/all_papers_2026-04-11_enriched_ror_refined.jsonl" --LLM_results "./LLM_Results/LLM_results_20260411_125808.json"
call :run python ./sql_scripts/build_sqlite.py --jsonl "./getfiles/all_papers_2026-04-18_enriched_ror_refined.jsonl" --LLM_results "./LLM_Results/LLM_results_20260418_023838.json"
call :run python ./sql_scripts/build_sqlite.py --jsonl "./getfiles/all_papers_2026-04-25_enriched_ror_refined.jsonl" --LLM_results "./LLM_Results/LLM_results_20260425_022337.json"
call :run python ./sql_scripts/build_sqlite.py --jsonl "./getfiles/all_papers_2026-05-02_enriched_ror_refined.jsonl" --LLM_results "./LLM_Results/LLM_results_20260502_020545.json"
call :run python ./sql_scripts/build_sqlite.py --jsonl "./getfiles/all_papers_2026-05-10_enriched_ror_refined.jsonl" --LLM_results "./LLM_Results/LLM_results_20260510_024906.json"
call :run python ./sql_scripts/build_sqlite.py --jsonl "./getfiles/all_papers_2026-05-16_enriched_ror_refined.jsonl" --LLM_results "./LLM_Results/LLM_results_20260516_204536.json"
call :run python ./sql_scripts/build_sqlite.py --jsonl "./getfiles/all_papers_2026-05-23_enriched_ror_refined.jsonl" --LLM_results "./LLM_Results/LLM_results_20260524_023612.json"
call :run python ./sql_scripts/build_sqlite.py --jsonl "./getfiles/all_papers_2026-05-30_enriched_ror_refined.jsonl" --LLM_results "./LLM_Results/LLM_results_20260531_011244.json"
call :run python ./sql_scripts/build_sqlite.py --jsonl "./getfiles/all_papers_2026-06-07_enriched_ror_refined.jsonl" --LLM_results "./LLM_Results/LLM_results_20260608_030855.json"
call :run python ./sql_scripts/build_sqlite.py --jsonl "./getfiles/all_papers_2026-06-13_enriched_ror_refined.jsonl" --LLM_results "./LLM_Results/LLM_results_20260613_140337.json"
call :run python ./sql_scripts/build_sqlite.py --jsonl "./getfiles/all_papers_2026-06-20_enriched_ror_refined.jsonl" --LLM_results "./LLM_Results/LLM_results_20260620_181803.json"
call :run python ./sql_scripts/build_sqlite.py --jsonl "./getfiles/all_papers_2026-06-27_enriched_ror_refined.jsonl" --LLM_results "./LLM_Results/LLM_results_20260627_023238.json"
call :run python ./sql_scripts/build_sqlite.py --jsonl "./getfiles/all_papers_2026-07-04_enriched_ror_refined.jsonl" --LLM_results "./LLM_Results/LLM_results_20260705_010755.json"
exit /b 0

:run
%*
if errorlevel 1 exit /b %errorlevel%
exit /b 0

