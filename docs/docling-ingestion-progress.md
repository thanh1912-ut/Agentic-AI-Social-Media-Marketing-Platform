# Docling ingestion progress

Updated: 2026-09-29 14:20 Asia/Ho_Chi_Minh.

Branch: `codex/docling-document-ingestion`. Tested working tree is based on
`aec998479d3d53c4743a662f61f5666a9835d242`; the changes below are not yet committed
or pushed. Scope includes ingestion/worker/API, knowledge chunking, frontend,
contracts and tests (M1/M2/M3 areas authorized by this task).

| Status | Work | Evidence / next step |
|---|---|---|
| DONE | Reproduce the original CSV failure | Old parser capped output at 2,000,000 characters and assumed comma delimiters. Source has 5,834,924 bytes, 41,188 data rows and 21 columns, separated by semicolons. |
| DONE | Integrate Docling 2.130.0 and local model setup | Actual five-format fixture conversions passed. Isolated Python 3.14.5 environment passes `pip check`; model manifest verifies 66 files. OCR and picture extraction are disabled. |
| DONE | Verify full CSV integrity | 44 batches, 41,188 data rows, 21 columns and 864,969 cells including header; full reconstructed cell checksum matched. Direct conversion: 9.83 s; child peak RSS 514,932,736 bytes. |
| DONE | Verify durable ingestion | Dedicated PostgreSQL/Redis, API upload and Celery ingestion worker persist normalized data and knowledge. Full CSV pipeline measured 22.27 s. |
| DONE | Separate extraction, knowledge and profile status | Missing DeepSeek no longer changes successful extraction/indexing into a parser failure. Updated the PostgreSQL application test to reflect these independent outcomes; targeted rerun passed. |
| DONE | Verify one live DeepSeek Brand Profile request | 2026-09-29, model `deepseek-flash`, one generation call, no repair. Three retrieved chunks came from the authorized MailGuard DOCX; zero CSV chunks. Revision 2 saved as an unconfirmed draft. |
| DONE | Verify result persistence in real-mode UI | Documents and Brand Profile remained visible after reload. DOCX upload used the authenticated API after browser file chooser automation timed out; UI upload is not claimed as verified. |
| IN_PROGRESS | Quality checks and release review | Full configured backend run: 238 passed, 1 skipped, 1 failed (obsolete expected status); that failed test passed after correction. Earlier frontend lint/typecheck and 47 tests passed. Production build remains NOT_RUN. |
| TODO | Finish acceptance gaps | Verify browser upload for all formats, prompt subprocess termination on lease loss, active-version behavior on failed reprocess, and remaining table/text edge cases. See verification report. |
| TODO | Commit and push | Review staged paths and secrets, run remaining checks, fetch and push feature branch; verify remote SHA. |

No Brand Profile has been confirmed automatically. No Facebook publication,
Meta live test, campaign generation, or extra DeepSeek generation was performed
as part of this document smoke test.
