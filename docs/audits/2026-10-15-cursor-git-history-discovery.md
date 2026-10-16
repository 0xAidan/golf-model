# Cursor, Git and prior assistant prediction discovery

Audit date: 2026-10-15 (America/Toronto). Sources were inspected without editing their original contents. This is a discovery inventory, not proof that every forecast ever generated survives, and not a new backtest or profitability claim.

## Preserved evidence

The private recovery directory is `/Users/aidannugent/websites/golf-model-preservation/2026-10-15-cursor-discovery/`.

- `sources.jsonl`: exact file captures, LocalHistory snapshots, Git blobs, isolated conversation tables, prior Codex card capture, and explicitly unverified OCR. Each record has a content SHA-256, original source reference, source kind and compressed corpus path.
- `structured_sources.jsonl`: three independently valid JSON response/subtree captures recovered from Cursor terminal history. They retain original JSON pointers and capture/generated timestamps separately.
- `corpus/<sha256>.<extension>.gz`: content-addressed evidence; hashes refer to decompressed original captured bytes.
- `cursor-visual-classification.json`, `ocr/<image-sha256>.json`: image classifications and retained golf-related OCR lines with confidence and bounding boxes. Original image paths and hashes remain available; duplicate image copies were removed after verifying the originals.
- `remote-cursor-inventory.json`, `local-transcript-inventory.json`, `golf-workspace-manifest-index.json`, `prior-assistant-history-inventory.json`, `may-june-gap-leads.json`, and `summary.json`: bounded coverage and provenance inventories.

The corpus deliberately separates these source kinds:

| Source kind | Interpretation |
| --- | --- |
| `cursor_read_file_capture` | Contents returned by a historical file-read tool. `complete_read_capture` and `partial_read_capture` retain offset, limit, reported total lines and captured line count. |
| `cursor_local_history` | Complete bytes of a preserved editor file version, with its history index, snapshot path and editor timestamp. |
| `git_reachable_blob` | Exact committed file bytes, blob identity and first reachable change. This establishes repository presence, not public publication. |
| `cursor_terminal_api_capture` | Exact historical API JSON, or a complete JSON subtree from an otherwise truncated response. Live/completed views remain observations. |
| `cursor_forecast_table_snippet`, `cursor_transcript_forecast_table_snippet` | Isolated tables from conversation text. These can be suggestions, fixtures or summaries and remain unverified. Surrounding private chat prose was not exported. |
| `cursor_image_ocr` | Golf screenshot text, always `unverified_ocr`. OCR order is not reconstructed table alignment; its confidence is not a model probability. |
| `prior_codex_read_file_capture` | Card body present in a tool output from before the current goal, with session, line and call identity. |

No source kind proves a bet was placed. Research/shadow/trial cards, later generated cards, repeated prices and replays must not be pooled with frozen pre-event forecasts.

## Where the search reached

Local Cursor workspace manifests identified nine golf workspaces, including old local roots `~/Documents/golf-model`, `~/Documents/golf`, an event-cockpit worktree, and remote roots `/opt/golf-model`, `/root/golf-model`, `/root/opt/golf-model` and recovery worktrees. The local Cursor global database was opened through SQLite read-only access.

The bounded local search covered:

- 607 golf-associated conversation headers and 98,672 scoped bubbles, selected using workspace metadata and golf references rather than an indiscriminate dump of all chats.
- 177 golf LocalHistory resource indexes containing 2,285 versions. Ten output/report resources yielded 70 snapshot occurrences; ordinary source-code revisions were not presented as independent forecasts.
- All 372 local golf agent transcript files, including transcript identifiers absent from the scoped conversation-header list.
- All 149 unique golf-project Cursor images: local macOS Vision OCR completed with zero errors. A vocabulary of 1,048 source-corpus player names broadened detection beyond famous golfers. Final classifications were 20 forecast candidates, 95 golf statistics/UI images and 34 images without detected golf evidence. All 20 forecast candidates were visually inspected. Non-golf OCR text was not exported.

The remote VPS search covered 213 golf agent transcript files and 32 terminal files. It found 140 artifact-path references but no additional forecast tables under the conservative extractor. Remote Cursor LocalHistory contained 233 golf resources and 1,673 versions, with no output/card resources identified. The checked remote global `state.vscdb` path did not exist. These are explicit negative findings for the inspected locations, not proof that no other remote backups exist.

Git initially had only ten reachable commits because the checkout was shallow. Fetching full reachable GitHub history expanded that to 692 commits across the available branches, without checking out files or changing the working tree. The earliest reachable commit is `574e07361125c89ea47ebb8815fd5d7719a1de63` (2026-02-07). The scan recovered 25 artifact blob versions across 20 paths. Two unreachable blobs were also inspected for forecast-card headers; neither matched.

Prior assistant metadata was checked separately: one golf Claude transcript (76 records) and twelve golf Codex sessions from October 13–14 (11,038 records). The current October 15 goal was excluded. Decoding 2,651 prior tool-output strings recovered one Players card body. General assistant discussion was not imported as prediction evidence.

## Card versions and useful recoveries

Complete betting-card captures cover ten title variants and 28 distinct byte versions before OCR or the later prior-Codex recovery. Observed filenames include:

| Event | File dates recovered in complete card captures |
| --- | --- |
| WM Phoenix | February 7, including the differently named “2026” version |
| AT&T Pebble Beach | February 11 and 15, including a differently named “2026” version |
| Genesis | February 15 and 17, with multiple changed contents under the same name |
| Cognizant | February 23, 26 and 28; shadow versions remain separately identified |
| Arnold Palmer | March 8 |
| Houston | March 25, including trial/sandbox variants |
| Valero | April 1 |
| Masters | April 6; April 8 has independently captured partial slices, which were not stitched |

Examples of retained hashes:

- Houston trial #241 LocalHistory card: `d9eb0532cc9a8d4cfa1c73a7b426a02c2eaf99a6178a81af2e0416278b9c25fd`.
- Genesis methodology v3 LocalHistory: `62e0085d62b1c46bfbf5dac708e9d948b07dddba696bd9cf1514a790767727d3`. It contains model documentation/rankings and remains a methodology source.
- Players March 15 card body from prior Codex tool output: `3d1b6da4d48e2114e9bf505f9b24ec08c00b4592246a610b25f56906e6806ef7`, 10,299 bytes. Its March 15 generation date must not be rewritten as a pre-tournament forecast date.

At the initial text-corpus comparison, 29 content hashes were exact duplicates of the separately recovered local archives. Every occurrence retains its source provenance; repeated occurrences are not additional predictions. Other changed contents under an identical filename remain separate versions.

## Focused May–June gap

A second targeted pass covered 67 relevant Cursor conversations and 19,880 bubbles, looking for PGA Championship, Charles Schwab, Memorial, Myrtle Beach and Canadian Open evidence. Most matches were tests, ingestion logs or historical backtest output and were not promoted to forecast sources.

Three exact JSON captures materially improve the available evidence:

| Captured evidence | Identity and limits |
| --- | --- |
| Charles Schwab completed/dashboard response, captured June 1 at 15:45:22Z | SHA `9fb269051e7e3b7593e72f0a2f7361b53f894f2a672407627f2d20120778c31e`; 420,294 bytes. Includes 132 `rankings` and 132 `frozen_pre_teeoff_rankings`; source card path ends `charles_schwab_challenge_20260527.md`. A completed API response is not itself evidence of when those arrays were originally published. |
| Memorial live section | SHA `a42486578feab0a5ad4ef85fa3eeeeb17f91998c1cfe87b14a92df45f518708a`; 639,148 bytes, including 72 rankings and 72 frozen-pre-teeoff rows. Wrapper generated June 4 at 18:45:57Z; captured at 18:52:07Z. |
| Canadian Open upcoming section | SHA `b6294332d54bac890f4799a911972f18ce68d0b849f2ce75691e34e8b6b0d54a`; 163,139 bytes, including 72 rankings; same wrapper/capture timestamps. |

The June 4 whole response was truncated inside a later section. Its Memorial and Canadian sections are complete JSON subtrees with exact original offsets and pointers; no closing braces were invented and no partial versions were joined.

A visually inspected May 12 screenshot also shows the upcoming PGA Championship at Aronimink, rankings and Jon Rahm over Cameron Young at bet365 +110, displayed WIN 51.6% and EV 8.5%. Image SHA: `6984baafb5a5239d8280e3a666fa7fca167ec738881ece2c67af3376c2dd2387`. Its amber stale-snapshot warning remains part of the evidence. This is screenshot evidence, not a recovered original card or independently verified quote.

No original PGA/Myrtle Beach full card body was recovered by this bounded pass. The referenced May 27/June 4 filenames are leads, not automatically complete original file recoveries. Unavailable iCloud originals or databases may still contain stronger evidence.

## Integrity and remaining boundaries

All preserved corpus payloads were decompressed and checked against their recorded SHA-256. Original Cursor records, images, assistant sessions, historical outputs and archive containers were not deleted or rewritten. Only newly created duplicate image copies were removed after verifying that the original image hashes matched; references now point to the originals.

The record distinguishes a generated date written inside a card, an editor/chat capture time, a source API generation time and a verified pre-event cutoff. Missing timing stays unknown. Partial file captures, OCR, assistant suggestions, DataGolf-as-book UI rows, annotated design crops and completed replays remain explicitly limited evidence. Neither this corpus nor the search establishes that every week, every player or every historical market is covered. No 2025 original published forecast card was confirmed in this branch of the search.
