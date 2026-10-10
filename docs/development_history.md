# DUTchMate Development History

Completed slice records are kept newest first. Current status and next work live
only in `docs/development_status.md`.

## 2026-10-10 — Feature 007 Final Pre-Commit Review and Commit Record

Completed the separately authorized complete final pre-commit review. No genuine
defect was found; production/source/tests/configuration/dependencies/contracts remain
unchanged from the T025 software-complete implementation. All25 tasks are checked;
feature007 is software-complete, while Phase1 and native/physical acceptance remain
incomplete. This reviewed snapshot is included in the authorized implementation
commit titled `Implement observation CLI` (Git revision `:/^Implement observation CLI`).
Its accepted parent baseline remains c2c9ce3153ae24f333b9dcd77565d633d7ac780d;
006 implementation remains b4c5730b2a5e593c10c06ad9e8f24c39e06f794b.

Reviewed the complete24-file feature diff against governing Core §§12–20/22–23,
007 spec FR-001–030/plan/data model/CLI contract, completed001–006 contracts,
all task markers and current development status. Thin Typer/HTTPX attach/status/
detach delivery, read-only fixed credential hygiene, one finite HTTP request,
strict bounded reported facts and fixed private output/exit handling preserve the
service's sole resource/domain/authentication/admitted-operation ownership.
No bootstrap/Profile/journal/lifecycle duplicate, second reader, unsafe help,
secret logging, deferred feature or new public contract. All35 existing lock package
rows remain unchanged; only the intentional CLI/framework/client transitives added.

Fresh final validation executed under verification-before-completion:

- `rtk proxy uv run ruff check .`: clean.
- `rtk proxy uv run mypy .`: clean,61 source files.
- `rtk proxy uv run lint-imports`:7 kept/0 broken,56 files/152 dependencies;
  no weakened boundary or new product exemption.
- `rtk proxy uv run pytest --tb=short --junitxml=/private/tmp/dutchmate-007-precommit-results.xml`:
  **2261 passed**, zero failures/errors/skips;924 Core/561 service/776 CLI, including
  all112 installed-process cases. XML count/skip/source-hash audits passed.
- Working-tree `git diff --check` and staged `git diff --cached --check`: clean;
  staged checks repeated after final review/commit bookkeeping.

Fresh process fixtures rebuilt wheel/sdist through uv and installed each with exact
locked dependencies in separate temporary environments. Real entry/main(args),
outside-cwd imports, privacy, native IPv4/IPv6 auth, OS SIGINT and closed pipes passed.
Independent wheel/sdist review confirms exact current source modules, only HTTPX/
Typer runtime metadata and dutchmate = dutchmate_cli.main:main. No mandatory editables,
Core/service package or generated/runtime/credential/cache/Graphify files in artifacts.

Staged the complete intended set:12 CLI package/source/test files,8 feature007
artifacts, root pyproject.toml/uv.lock and status/history. Inspected cached diff/stat,
names/modes and bytes: exactly24 regular text files, matching the reviewed tree;
no unrelated/generated/runtime/credential/Graphify file. Completed001–006 source/
contracts and Core are unchanged. The original staging area was empty; all prior
working-tree feature content and history records were preserved. No git hooks are
configured to start extra work; no Graphify rerun, Spec Kit or next slice was performed.

Current status and minimal spec/plan/quickstart/task metadata record the reviewed
commit snapshot and its title-based Git reference. The actual hash resolves from
Git after commit; no guessed/self-referential hash or second bookkeeping commit is
needed. Status now leaves selection/authorization of the next Phase1 slice to the
human. Commit and repository status are verified after the authorized operation;
all documentation links/task markers/whitespace/scope are checked before it.

Native validation remains macOS-only. Guarded ASGI/FakeSerial/temp SQLite and
Basic/Enhanced-shaped fixtures prove software lifecycle/client-loss/idle evidence/
neutrality; native service processes are inactive and controlled progress/failure
checkpoints are test-only. Native Linux/Windows, native active-DUT lifecycle/installed
capture and physical/electrical/Enhanced acceptance remain unexecuted. No physical
hardware or real account credential accessed. Nothing pushed; no next Phase1 slice
selected or started. Authorization ends after this feature007 review and commit.

## 2026-10-10 — Feature 007 T025 Fresh Final Software Gate and Diff Review

Completed only authorized T025; all25 feature007 tasks are checked. Feature007's
specified observation-CLI software scope is complete and ready for separately
authorized final review/commit. It remains uncommitted on main at
c2c9ce3153ae24f333b9dcd77565d633d7ac780d;006 implementation remains b4c5730.
No commit, push, next slice, Graphify rerun, physical hardware or real account
credential access. Phase1 and unexecuted platform/hardware acceptance remain incomplete.

Applied verification-before-completion and executed fresh final gates:

- `rtk proxy uv run ruff check .`: **passed**, no findings.
- `rtk proxy uv run mypy .`: **passed**,61 source files, no issues.
- `rtk proxy uv run lint-imports`: **7 kept/0 broken**,56 files/152 dependencies;
  no weakened contract, ignore_imports or new product exemption.
- `rtk proxy uv run pytest --tb=short --junitxml=/private/tmp/dutchmate-t025-results.xml`:
  **2261 passed**, zero failures/errors/skips. Breakdown:924 Core/561 service/776 CLI;
  CLI commands127/context139/lifecycle88/process112/transport310. XML counts audited.
- `rtk proxy git diff --check`: **clean**, before and after progress documentation;
  intended untracked-file whitespace/link/task/hash checks also passed.

Final intended diff review covers exactly24 files: four tracked changes (status/
history/root pyproject.toml/uv.lock) and20 untracked CLI package/source/tests/007
artifacts. Rechecked current production context/main/exchange and FR-001–030/CLI
contract, root/package configuration and guard/install harness. All source/test/
configuration/lock content hashes match T021's complete conformance review. No new
production defect or source/test/configuration/dependency correction was required.
Existing ordinary credential failures, strict reported wire facts, absolute client
deadline and T019 close-after-EPIPE behavior remain intact.

All35 pre-existing lock package rows retain identical metadata; only the intentional
client/transitive additions dutchmate-cli/httpx/httpcore/certifi/typer/shellingham
remain. CLI direct dependencies are only HTTPX/Typer within planned ranges; no Core/
service product dependency. AST/source/scope review confirms no bootstrap/domain
copies, secret logging, unsafe help/transport, second RX/ownership, resource access,
external launcher or deferred feature. Completed001–006 source/contracts and Core
are unchanged; schema-v1/Profile-v1/lifecycle/auth/browser rejection remain authoritative.

All four exact quickstart scope commands ran again: no CLI/Typer delivery imports in
Core/service; only serial_line_control's reported wire enum matched the CLI banned-
word search; completed001–006 diff and git ls-files graphify-out were empty. Intended
files have no symlinks, credential/journal/cache/build/runtime/generated Graphify
output. Prior working-tree changes and all existing history records are preserved.

Fresh full-suite process fixtures built wheel/sdist through uv, installed both with
all exact locked CLI transitives in separate temporary environments and exercised
the real entry/main(args) outside repo cwd. All112 process cases passed. Independent
artifact review confirms current module bytes in the wheel, all four modules in
sdist, exactly HTTPX/Typer Requires-Dist and dutchmate = dutchmate_cli.main:main.
No Core/service package, generated/runtime/credential/cache/graph files in artifacts;
no mandatory editable/global package reliance. Metadata/artifact results are saved
under /private/tmp/dutchmate-t025-installability.json.

Native evidence remains macOS: IPv4/IPv6 auth/browser gates, first/repeated OS SIGINT,
closed pipes and scripted-loopback default5s/10s timing. There were no platform/
IPv6 skips; none were counted as passed. Actual006 ASGI/bootstrap/runtime plus guarded
FakeSerial/temp SQLite and Basic/Enhanced-shaped fixtures prove software lifecycle,
client-loss settlement, idle binary evidence and neutrality only. Native service
processes remain inactive; test-only progress/failure checkpoints do not prove native
active-DUT lifecycle, installed capture or physical/Enhanced acceptance. Native
Linux/Windows and physical/electrical cases remain unexecuted. All parent/independent
CLI/service child hardware/real-account guards and actual authentication are intact.

Recorded actual counts/readiness in development_status.md and minimal spec/plan/
quickstart/task progress metadata. Two remaining planning notes in research and the
requirements checklist now explicitly identify their2026-10-08 planning snapshot,
so old no-install/all25-unchecked statements cannot be mistaken for current status.
No requirement/public contract changed. Resume Here stays within40 lines; all local
links/anchors/task markers/whitespace and the final24-file inventory were rechecked
after documentation. No remaining software task in007; stopped after T025 without
automatically performing final review/commit or starting further work.

## 2026-10-10 — Feature 007 T024 Code-Only Incremental Graphify Update

Completed only authorized T024, stopping before T025. Read docs/agent_tooling.md,
the local Graphify skill and incremental-update reference. Actual007 adds the CLI
workspace/package, context/client/main modules and installed entry, with tests and
new CLI/Core/service dependency-contract coverage. These module/package/dependency
changes meet the repository structural trigger; this is not planning-only work.
Core/service/completed001–006 public interfaces and production sources remain unchanged.

Verified Graphify0.9.48, the existing uv-managed interpreter from .graphify_python,
graph/manifest and ignore rules. Read-only AST preflight found165 files/~260537 words:
77 code/88 documents,12 changed code inputs, no deletions/sensitive exclusions or
pending queue. Inputs were10 CLI Python source/test files, apps/cli/pyproject.toml
and root pyproject.toml; no Markdown/semantic extraction was dispatched.

An initial offline `uv tool run --from graphifyy==0.9.48 python` inspection probe
attempted dependency resolution and failed for uncached wheels before running any
Python/updater. Used the already-installed uv-managed interpreter as required by
the skill's interpreter guard; no installation, upgrade, workspace dependency or
lock change. An initial preflight expected ruff.toml as code; actual detector scope
correctly excludes it. Both were read-only setup checks, not update invocations.

Exactly one logical update used the existing installed updater:
`graphify.watch._rebuild_code(Path('.'), changed_paths=selected_code, force=False,
block_on_lock=True)`. A temporary audit counted exactly one AST extraction and
asserted its12 input paths; no broadened queue, plain CLI full rescan, documentation
extraction, API/LLM call, extra labeling step or second update. Existing graph content
was retained through the updater's incremental merge.

Succeeded, exit0: **3195 nodes/9455 edges/137 communities**, from2891/8348/123.
Report records **zero input/output LLM tokens** and baseline c2c9ce31. Non-fatal
diagnostics: root pyproject.toml produced zero nodes and stays unstamped;34 existing
community labels were refreshed deterministically by their hubs. No retry, force
override or LLM relabel followed. Eleven selected inputs have current AST stamps;
one read-only incremental check leaves only the known zero-node root input.

Updater backed up four curated outputs under graphify-out/2026-10-10/ and regenerated
graph JSON/HTML/report/manifest/labels/signatures. Existing .gitignore:57 covers all
outputs and backups; git ls-files graphify-out is empty. No generated output staged
or committed; graph.json was never read directly by the agent.

Fresh read-only verification:

- `rtk proxy graphify explain apps_cli_src_dutchmate_cli_client_exchange` confirms
  client.py:L329 and extracted calls from attach/status/detach, wire validation,
  raw collector/encoder and fixed local errors.
- `rtk proxy graphify explain apps_cli_src_dutchmate_cli_main_main` confirms main.py:L138
  and the invocation/failure boundary. A shorter exchange query was ambiguous across
  production/test sources; the full node ID resolved it without a graph mutation.
- `rtk proxy graphify diagnose multigraph --json --max-examples 0`: zero missing/
  dangling endpoints, self-loops, exact duplicates or same-endpoint collapse in the
  saved graph. This post-build check cannot recover already-suppressed producer edges.
- Corpus/hash/manifest/report audits: all165 repository file hashes unchanged during
  the update;78 previous Markdown manifest rows/semantic-hash fields retained (their
  previous semantic hashes were empty). No documentation content re-extracted.
- `rtk proxy git check-ignore -v` verifies graph/report/HTML/manifest/labels/signatures/
  dated backups ignored; `rtk proxy git ls-files graphify-out` returns no files.
- Documentation/baseline/link/hash/task/whitespace checks preserve the24-file intended
  set, all source/test/config/dependency/contract content and existing history;
  task markers stop at T024, T025 unchecked. `rtk proxy git diff --check` rerun after docs.

Recorded the assessment/update here and synchronized current status plus minimal
spec/plan/quickstart/task progress metadata. Feature007 remains uncommitted on main
at c2c9ce3153ae24f333b9dcd77565d633d7ac780d. No production/test/contract/schema/Profile
change, software/static/packaging gate rerun, new platform/hardware acceptance,
Spec Kit, commit, push or next task. T021 full and T022 focused software results remain
prior recorded evidence; T025 must run its own fresh final gate. Native Linux/Windows,
native active-DUT lifecycle and physical/electrical acceptance remain unexecuted.
No physical hardware or real account credential accessed. Stopped after T024.

## 2026-10-10 — Feature 007 T023 Status/History Reconciliation

Completed only authorized T023, stopping before T024. Documentation-only change;
no production/test/configuration/dependency/contract revision, new software run,
platform/hardware acceptance, Graphify assessment/update, commit or push.
The verification-before-completion skill was applied to documentation checks.

Reconciled [development status](development_status.md) with actual007 scope and
T001–T022 evidence. Replaced duplicate per-task chronology with current delivered
behavior, progress, baseline, recorded-validation and acceptance-limit summaries.
The status document is188 lines; Resume Here is35 lines. Removed obsolete claims
that CLI delivery remained deferred or that no subsequent Phase1 slice had started.
All pre-existing history content, dated RED/GREEN/correction records and earlier
committed-feature evidence remain unchanged; this record is prepended newest first.
History contains no competing current-status/next-step section.

Current software scope is installable Typer attach/status/detach over existing006,
resource-free help, lexical explicit inputs, fixed read-only credential hygiene,
one finite HTTP request, bounded validated JSON and fixed diagnostics/exits/receipt
phase. Device Core/service remain the sole domain/authentication/operation/resource
owners; client exit/loss sends no retry/detach/service signal. No evidence delivery,
second reader, Profile/journal access, Enhanced production, MCP or later workflow
was documented as implemented. T019's demonstrated closed-pipe correction and
T021's six-state wording reconciliation are retained as completed evidence.

Baseline verified through git: branch main and HEAD
c2c9ce3153ae24f333b9dcd77565d633d7ac780d (Record feature006 commit); actual006
implementation b4c5730b2a5e593c10c06ad9e8f24c39e06f794b. All six001–006 implementation
commits in the status table are verified ancestors. Feature007/package/root tooling/
dependency/artifacts/progress changes remain uncommitted in the existing working
tree. No unmade007 commit or push is claimed. T001–T023 checked; T024–T025 unchecked.
Only007 progress metadata was aligned in spec/plan/quickstart/tasks; normative
contracts and completed source/tests remain unchanged.

Recorded evidence is explicitly separate from T023 verification: T021's full gate
2261 passes, Ruff clean/mypy61 files/7 kept imports; T022's eight focused selections
3132 passes covering2261 distinct cases, zero failures/errors/skips, both help0/
empty stderr, exact scope checks and temporary wheel/sdist installations. Prior
saved XML/count records were audited read-only; software/static gates were not
rerun or relabelled as fresh T023 results. T025's own fresh final gate remains pending.

Acceptance limits remain explicit: native macOS IPv4/IPv6 auth, installed OS signals/
closed pipes and scripted-loopback5s/10s timing are recorded software evidence.
Native service children have an inactive runtime; wait/signal fault checkpoints
use test-only controls. Guarded actual006 ASGI/FakeSerial/temp SQLite and shared
Basic/Enhanced-shaped fixtures demonstrate lifecycle/loss/idle binary readback and
neutrality in software. They do not establish native active-DUT lifecycle, installed
capture or Enhanced hardware support. No platform/IPv6 skips were reported as passes.
Native Linux/Windows and physical/electrical cases remain unexecuted; Windows
actual commands are unsupported by the current POSIX contract. No physical device
or real account credential was accessed. Existing003 JournalFailure context-manager
limitation and broader Phase1 workflow/hardware gaps remain outside007.

Fresh documentation verification executed:

- `rtk proxy git status --short`, `rtk proxy git log -3 --format='%H %s'` and read-only
  uv/Python git ancestry checks: actual main/HEAD/implementation baseline confirmed;
  all001–006 implementation commits are ancestors, intended24-file set preserved.
- Read-only `rtk proxy uv run python` documentation audits: Resume Here35 lines,
  local links/heading anchors valid, single current-status/next-action location,
  all prior history preserved, task markers stop at T023 and only six progress/
  documentation files changed. Product/test/config/lock/contract hashes unchanged.
- `rtk proxy git diff --check` and whole intended-file whitespace checks: clean;
  rerun after recording this evidence.

No pytest, Ruff, mypy, Import Linter, packaging, signal, socket or hardware scenario
was executed for this documentation-only task. Existing validation commands/results
remain in their original dated records. T024 was not assessed or executed, and T025
was not started; the exact pending scope lives only in the current status/tasks.

## 2026-10-10 — Feature 007 T022 Focused Quickstart and Exact Scope Searches

Completed only authorized T022, stopping before T023. HEAD remains
c2c9ce3153ae24f333b9dcd77565d633d7ac780d (006 implementation b4c5730); prior
working-tree changes preserved. No demonstrated007 failure required a correction.
No production, test, dependency/configuration or contract changes; only progress
documentation/task markers. Verification-before-completion applied to fresh focused
evidence. T025's final full-gate block was not run.

Executed every focused pytest command from007 quickstart, including its repeated
transport selection. Each used `rtk proxy uv run pytest <selection> --tb=short`
with `--junitxml=/private/tmp/dutchmate-t022-<name>.xml` for count/skip audits:

| Selection | XML name | Passed |
|---|---|---|
| apps/service/tests | service |561|
| apps/cli/tests/test_cli_context.py | context |139|
| apps/cli/tests/test_cli_commands.py | commands |127|
| apps/cli/tests/test_cli_transport.py (US1) | us1-transport |310|
| apps/cli/tests/test_cli_lifecycle.py | lifecycle |88|
| apps/service/tests core/tests | completed |1485|
| apps/cli/tests/test_cli_transport.py (US3) | us3-transport |310|
| apps/cli/tests/test_cli_process.py | process |112|

All eight selections have **zero failures/errors/skips**. Total **3132 passes**;
XML identity audit confirms **2261 distinct cases**, including776 CLI,561 service
and924 Core cases. Repeated service/transport selections account for the extra871
passes; these focused invocations are not a newly executed full `uv run pytest` gate.
Completed001–006 regressions remain unchanged.

Both exact help commands ran: `rtk proxy uv run dutchmate --help` and
`rtk proxy uv run dutchmate status --help`. Each returned0, emitted static help on
stdout and empty stderr; captured streams verified. Resource-free help/parser
behavior is also enforced by guarded grammar and installed-process tests.

Fresh process tests build wheel/sdist through uv into temporary destinations,
install both with all exact locked CLI transitives into separate fresh environments,
and verify metadata, real entry/main(args), outside-cwd imports, private diagnostics,
actual OS signals and pipe closure. No editable/global package reliance or product
external-program launcher. Native macOS evidence:10 authenticated status cases,
20 installed-auth cases across IPv4/IPv6,8 native SIGINT,8 closed-pipe cases and2
default5s/10s scripted-loopback timing cases; no platform/IPv6 skips.

Guarded real006 security/bootstrap/lifespan/ASGI/runtime with FakeSerial/temp SQLite
and existing Basic/Enhanced-shaped fixtures validates lifecycle/reported facts/idle
exact binary evidence. Twelve admitted attach/detach loss cases preserve service
ownership before/inside005; client loss causes no automatic retry/detach/status or
service signal. Test-side readback and timing/progress controls remain test-only.
Mocks/fixtures do not prove native active-DUT lifecycle or Enhanced hardware support.
Parent and independent CLI/service child physical/real-account guards remain active;
no physical transport or actual account credential accessed.

All four exact quickstart scope searches executed:

```bash
rtk proxy rg -n 'typer|dutchmate_cli' core/src apps/service/src
rtk proxy rg -n 'dutchmate_core|dutchmate_service|serial|sqlite3|subprocess|fastapi|uvicorn|mcp' apps/cli/src
rtk proxy git diff c2c9ce3 -- core apps/service specs/001-rx-continuous-evidence specs/002-basic-serial-adapter specs/003-durable-evidence-journal specs/004-dut-profile-policy specs/005-observation-runtime specs/006-local-observation-service
rtk proxy git ls-files graphify-out
```

First search: empty (rg's expected no-match exit1). Second: only client.py:145's
reported serial_line_control wire enum, no banned import/behavior. Completed-source/
contract diff and tracked Graphify files: empty. Root/package config/lock review and
content-hash audit preserve intentional prior CLI tooling/dependencies, all35 old
lock rows, strengthened boundaries, guards and the24-file intended set. No new
API/security/schema/Profile change or generated/runtime output in intended files.

Only documentation whitespace/scope/hash/task-marker checks followed results;
no Ruff/mypy/Import Linter/default-full-pytest rerun. T021 remains the latest full/
static gate; T025 must run its own fresh final gate. Native Linux/Windows, native
active-DUT lifecycle and physical/electrical acceptance remain unexecuted. Broader
T023 reconciliation was not performed, nor any T024 assessment/update, commit, push
or automatic next task. Task markers stop at T022; T023–T025 remain unchecked.

## 2026-10-10 — Feature 007 T021 Full Intended Diff and Contract Review

Completed only authorized T021, stopping before T022. HEAD remains
c2c9ce3153ae24f333b9dcd77565d633d7ac780d; preserved prior working-tree changes.
Reviewed all24 intended files: four tracked changes (status/history/root config/lock)
and20 untracked007 artifacts/CLI package/source/tests. No production defect was
demonstrated, so no source/test/dependency/configuration correction or manufactured
RED was introduced. No new public contract, Core revision or weakened import rule.

Review against Core §§12–20/22–23, relevant completed001–006 contracts, the active007
spec/plan/data model/contract and all3991 CLI test lines found:

| Requirements | Reviewed evidence and result |
|---|---|
| FR-001–004 | Installable Typer-only delivery, exactly three root commands; numeric target/required port, pure help/callback and fixed private usage errors. Grammar/context/process tests enforce zero preparation on help/rejection. |
| FR-005–007 | Fixed effective-UID/passwd-home credential; descriptor-relative no-follow read-only traversal, exact file hygiene/content and66-byte cap, cleanup on every path. No lock/marker/PID/repair/generation/refresh/bootstrap-policy replica. |
| FR-008–012 | One Bearer and exact Host, literal routes/methods, lexical unexpanded attach strings/exact two-field JSON, bodyless status/detach. Explicit no env/proxy/redirect/retry/fallback/discovery/autostart/preflight/follow-up. |
| FR-013–015 | Absolute monotonic10s wait/5s phases, raw identity streaming sliced at1MiB+1, strict media/UTF-8/duplicates/nonfinite/closed006 shapes/types. No Core values or cross-field policy/lifecycle predicates. |
| FR-016–019 | All six200 runtime states preserve complete facts/nullable values/ordered issues/opaque provenance and exit0; only documented HTTP/source/code pairs exit4. Bounded compact JSON and fixed local categories/exits/receipt phase; output failures remain honest. |
| FR-020–022 | Actual admitted-service loss tests preserve006 task ownership; explicit later status makes no attribution claim. Installed native SIGINT/closed pipes and private sentinels verify client-only interruption/fixed diagnostics; SDK channels and framework rendering disabled. |
| FR-023–025 | Core/service/schema-v1/Profile-v1/lifecycle/security unchanged. CLI imports only its package/framework/standard library; no DUT/Profile/journal access, reader, control/reconnect/external launcher. POSIX command checks precede account/network; help/import stay passive. |
| FR-026–028 | Real Typer grammar, distinct main(args)/installed wheel/sdist entries, actual006 auth/bootstrap/lifespan plus guarded fake resources. Identical fact assertions on existing Basic/Enhanced-shaped fixtures, idle exact binary readback and admitted-work loss. No auth bypass or physical-device selection. |
| FR-029–030 | Fresh software/static/import/installability checks passed. Test-only subprocess/import allowances match repository scope; no product exemptions, unnecessary dependencies, generated/runtime files or accidental deferred implementation. |

Documentation correction: the US1 status scenario omitted terminated, SC-003 said
five states, and completed T007's description said five. Updated those three007
references to the existing006 six-state wire contract, already enforced by24
wire-state regressions and lifecycle cases. No new behavior or enum, and no change
to001–006 or the CLI contract. Progress metadata records T021 only; broader final
status/history reconciliation was not performed.

Scope audit confirms all35 pre-existing lock package rows retain identical parsed
metadata, with only the intentional T002 additions certifi/dutchmate-cli/
httpcore/httpx/shellingham/typer. CLI's two direct dependencies remain HTTPX/Typer;
HTTPcore1.0.9 and Python3.14 match the plan. Workspace/mypy/test/import extensions
preserve existing boundaries; no ignore_imports, excluded test scope or extra product
exception. AST/source review confirms no domain/bootstrap copies or secret logging.
No credentials, journals, wheel/sdist output, caches or Graphify data in intended
files. Committed history records remain unchanged; all product/test/config/lock/
contract hashes are preserved by this slice.

Fresh executed validation:

- `rtk proxy uv run pytest --tb=short --junitxml=/private/tmp/dutchmate-t021-results.xml`:
  **2261 passed**, zero failures/errors/skips;776 CLI cases (commands127/context139/
  lifecycle88/process112/transport310), completed service561/Core924. XML audited,
  including24 all-six-state wire cases; actual temporary wheel/sdist installs rerun.
- `rtk proxy uv run ruff check .`: clean.
- `rtk proxy uv run mypy .`: clean,61 source files.
- `rtk proxy uv run lint-imports`: **7 kept/0 broken**,56 files/152 dependencies.
- `rtk proxy git diff --check`: clean; rerun after documentation changes.
- Read-only uv/Python inventory/hash/lock/history/XML audits:24 intended files,
  35 unchanged old lock rows, no completed-source/contract/Core changes.

Native evidence remains macOS IPv4/IPv6 auth, actual CLI signals/closed pipes and
scripted-loopback default timing; no platform/IPv6 skips. Guarded ASGI lifecycle/loss
and Basic/Enhanced-shaped data are software evidence, not native active-DUT or
Enhanced hardware acceptance. Native Linux/Windows and physical/electrical cases
were not executed. No physical hardware or real account credential accessed.
T021's required slice gate does not complete T022–T025; no focused quickstart group,
Graphify update, commit, push or subsequent task was executed automatically.

## 2026-10-10 — Feature 007 T020 US3 Software Validation GREEN

Completed only authorized T020, stopping before T021. Baseline remains
c2c9ce3153ae24f333b9dcd77565d633d7ac780d; preserved prior working-tree changes.
No production, tests, dependencies/configuration or contracts changed; verification
and progress documentation only. No new defect required correction.

Executed exact US3/completed quickstart selections with temporary account/physical
tripwires: `rtk proxy uv run pytest apps/cli/tests/test_cli_transport.py --tb=short
--junitxml=/private/tmp/dutchmate-t020-transport.xml`:310 passed. `rtk proxy uv run pytest
apps/cli/tests/test_cli_process.py --tb=short
--junitxml=/private/tmp/dutchmate-t020-process.xml`:112 passed. `rtk proxy uv run pytest
apps/service/tests core/tests --tb=short
--junitxml=/private/tmp/dutchmate-t020-completed.xml`:1485 passed (561 service/924 Core).
Zero failures/errors/skips in every selection;1907 targeted cases total.

Controlled transport/stream tests prove response retention/partial-delivery/phase
behavior, not hardware or service admission. Twelve actual006 admitted-loss cases
use guarded real bootstrap/security/ASGI/runtime with FakeSerial/temporary SQLite
and external-progress/test-clock boundaries; operations before/inside005 settle
after client deadline/read-loss/cancellation without direct owner/task cancellation.
No automatic retry/detach/status/service signal or mutation rollback assertion.
Manual later status observes facts only; Basic/Enhanced-shaped fixtures remain
software neutrality evidence, not real Enhanced support.

Native macOS evidence:10 status/auth cases (5 IPv6),20 installed auth/browser-gate
cases (10 IPv6),8 actual first/repeated SIGINT,8 closed stdout/stderr/both-pipe cases,
and2 unchanged-default native IPv4 HTTP timing checks. No native IPv6/platform skips.
Native installed-signal cases use an inactive real service; ASGI/fake mutation tests
do not become native active-DUT lifecycle or electrical acceptance. Native Linux/
Windows and all physical hardware remain unexecuted.

Installability selection freshly builds wheel/sdist through uv into temporary paths,
installs each with all CLI dependencies pinned from uv.lock in separate environments,
and verifies actual console entries/modules/dependencies/imports outside repo cwd
without editable/global package reliance. Reviewed and executed independent parent/
CLI-child/service-child hardware/real-account guards and private sentinel assertions:
no argv/token/cause/locals/header/body echo, traceback/color or shutdown diagnostic.
Tests use real006 authentication/browser rejection; no patched allow gate.

`rtk proxy uv run ruff check .` clean; `rtk proxy uv run mypy .`61 files clean;
`rtk proxy uv run lint-imports` seven kept/zero broken (56 files/152 dependencies).
All four quickstart scope commands ran:Core/service delivery-word search empty
(rg exit1/no matches), CLI search only allowed serial_line_control wire enum,
completed001–006 diff and tracked Graphify output empty. Fresh required slice gate
`rtk proxy uv run pytest --tb=short
--junitxml=/private/tmp/dutchmate-t020-results.xml`:2261 passed, zero failures/errors/
skips;776 CLI cases. XML/content hashes audited; diff checks clean before/after docs.
Updated status/history/task/progress labels; only T020 newly checked. Temporary
builds/environments/guards/hashes/XML remain outside repo; final T025 task not executed.

T021 remains unstarted: review full intended tracked/untracked diff against007
FR-001–030, CLI contract, Core and001–006; inspect apps/cli and root pyproject/uv.lock
for bootstrap/domain copies, secret logging, unsafe help/transport, unnecessary
dependencies, generated/runtime files or accidental deferrals. Fix genuine007
defects minimally with regression evidence only; do not weaken imports or revise Core.
No physical device or real account credential access, native Linux/Windows/active-DUT
lifecycle/hardware acceptance, Graphify refresh (assessment T024), commit/push or
later-task execution. Phase 1/feature final review remains incomplete.

## 2026-10-10 — Feature 007 T019 Closed-Pipe Shutdown Correction GREEN

Completed only authorized T019, stopping before T020. Baseline remains
c2c9ce3153ae24f333b9dcd77565d633d7ac780d; preserved prior working-tree changes.
Only apps/cli/src/dutchmate_cli/main.py changed among code/tests/configuration;
all T018 tests/client/context/configuration/dependencies/007 contracts and completed
001–006 source/contracts unchanged. No general entry/transport refactor or new framework.

Fresh unchanged closed-pipe selection reproduced4 RED/4 passing controls across
installed wheel/sdist: status stdout shutdown flush diagnostic and unusable stderr
exit120 instead of1. Standard-I/O-only disposable Python probes showed close after
EPIPE marks stdout/stderr closed even if close raises EPIPE again, allowing CPython
to skip final shutdown flush and preserve exit1 without diagnostics.

Added only a BrokenPipeError branch to existing _write: close the failed stream,
catch secondary ordinary close failure, then retain existing output_failed flow.
Writable stderr still receives the one fixed category with report_received after
validated output; unusable stderr permits exit1 only. No descriptor redirect, new
resource/abstraction, dependency, logging/signal change, HTTP retry/detach/follow-up,
service signal or policy/schema/runtime/ownership change. Normal writes/other errors
and the established client delivery phase remain intact.

`rtk proxy uv run pytest apps/cli/tests/test_cli_process.py -k closed_process_pipes
--tb=short --junitxml=/private/tmp/dutchmate-t019-red.xml`:4 expected RED/4 passed/
104 deselected. Same unchanged selection with dutchmate-t019-green.xml:8 passed/
104 deselected, zero failures/errors/skips, freshly built/installed wheel/sdist.
Fresh `rtk proxy uv run pytest --tb=short
--junitxml=/private/tmp/dutchmate-t019-results.xml`:2261 passed, zero failures/errors/
skips;776 CLI cases including all112 process cases,8 native SIGINT and20 actual IPv4/
IPv6 authentication cases. Existing admitted-service-loss/idle-binary cases remain GREEN.
`rtk proxy uv run ruff check .` clean; `rtk proxy uv run mypy .`61 files clean;
`rtk proxy uv run lint-imports` seven kept/zero broken (56 files/152 dependencies);
diff checks clean before/after docs. XML/source-content hashes audited. No tests
modified/xfail or weakened import/safety guard. Updated status/history/task/progress
labels; only T019 newly checked. Temporary probes/builds/environments/hashes/XML outside repo.

T020 remains unstarted: execute all US3 and completed001–006 quickstart regressions
plus static/import/installability checks; report mocked/native/platform/IPv6 evidence
honestly, inspect privacy/guard preservation and record actual results in history.
No hardware/Windows/Linux acceptance claim from macOS. The required T019 slice gate
does not complete T020's separate acceptance workflow. No physical device or real
account credential access, new native Linux/Windows/active-DUT lifecycle/hardware
acceptance, Graphify refresh (assessment T024), commit/push or later-task execution.

## 2026-10-10 — Feature 007 T018 Installed Process Tests; Closed-Pipe RED

Completed only authorized T018 test authoring, stopping before T019. Baseline remains
c2c9ce3153ae24f333b9dcd77565d633d7ac780d; preserved prior working-tree changes.
Added only apps/cli/tests/test_cli_process.py among code/tests/configuration. No
production, dependencies,001–006 contracts/source, service/Core or policy changes.

Added112 cases. UV built both wheel/sdist to temporary artifacts, installed each in
separate fresh environments with all CLI transitive versions pinned from uv.lock,
and verified modules/dependencies/real entries and imports outside repo cwd, without
editable/global package reliance. Each actual CLI child installs test-only
sitecustomize physical/real-account guards before product imports; independent parent
probes and006's unchanged guarded native service child prove their own tripwires.
Credentials remain in isolated files, never argv/environment. No product launcher.

Separate installed-entry/direct main(args) tests cover help/no-command/grammar privacy,
public Typer returned130/Abort, input-bearing framework/credential exceptions and
locals. Narrow test-owned SDK/framework progress probes retain real entry/client/
authentication. Native IPv4/IPv6 service auth, stale cached credential and browser/
Host rejection use actual006 bootstrap/security/lifespan and one inactive runtime.
First/repeated actual SIGINT130 before request/during delivery/after receipt preserve
phases; only CLI PIDs signalled, service remains alive/authenticated/unchanged.
No new native active-DUT lifecycle/electrical acceptance or hardware support claim.

Genuine defect: installed status with closed stdout emits output_failed/report_received
then CPython's extra 'Exception ignored while flushing sys.stdout' diagnostic;
closed stderr after a usage error exits120 instead of required exit1. Reproduced
identically for wheel/sdist: four failures named test_t018_closed_process_pipes_have_
fixed_output_failure_or_exit_only[wheel-status_stdout], [wheel-error_stderr],
[sdist-status_stdout], [sdist-error_stderr]. _write/_failure handle EPIPE locally but
leave buffered streams for interpreter final flushing. No T019 fix or xfail applied;
feature/process output acceptance remains RED. Help stdout/both-closed paths pass.

Initial package setup failed because offline cache lacked lock-pinned AnyIO's wheel;
normal UV install with exact lock pins resolved this without dependency/version
changes. Corrected only test callable/metadata typing. Independent parent guard
passed; both packaging probes passed. Fresh `rtk proxy uv run pytest
apps/cli/tests/test_cli_process.py --tb=short
--junitxml=/private/tmp/dutchmate-t018-focused.xml`:108 passed/4 genuine RED, zero errors/
skips. Final platform guard skips only unsupported native POSIX environments; no
native IPv6/platform skip occurred on macOS. Fresh `rtk proxy uv run pytest --tb=short
--junitxml=/private/tmp/dutchmate-t018-results.xml`:2257 passed/4 identical T018 RED,
zero other failures/errors/skips;all2149 prior tests remain GREEN,776 CLI cases total.
`rtk proxy uv run ruff check .` clean; `rtk proxy uv run mypy .`61 files clean;
`rtk proxy uv run lint-imports` seven kept/zero broken (56 files/152 dependencies);
diff checks clean before/after docs. XML/source-content hashes audited; completed
001–006 diff empty. Updated status/history/task/progress labels; only T018 newly checked.
Temporary builds/environments/guards/hashes/XML remain outside repo.

T019 remains unstarted: correct only T018-demonstrated entry-wrapper/log/interrupt/
output defects in main.py/client.py; suppress default value echo/tracebacks, preserve
local delivery phase and never change006 admitted ownership. If none, record no defect
without production changes. No physical device or real account credential access,
native Linux/Windows/active-DUT lifecycle or hardware acceptance, Graphify refresh
(assessment T024), commit/push or later-task execution.

## 2026-10-10 — Feature 007 T017 No Demonstrated Delivery Defect

Completed only authorized T017, stopping before T018. Baseline remains
c2c9ce3153ae24f333b9dcd77565d633d7ac780d; preserved prior working-tree changes.
Reviewed T016 evidence and client.py/context.py against active waiting/cancellation/
bounds/delivery-phase contracts. No T016 waiting/cancellation/bounds defect was
demonstrated. Recorded no defect without production or test changes; all source/
test/configuration/dependency/007 contract content hashes unchanged and completed
001–006 source/contracts diff empty. No sync HTTP worker, retry, service signal/
detach, Core timeout, public contract or service/Core policy revision introduced.

Fresh `rtk proxy uv run pytest apps/cli/tests/test_cli_transport.py -k t016
--tb=short --junitxml=/private/tmp/dutchmate-t017-focused.xml`:68 passed/242 deselected,
zero failures/errors/skips. Includes54 controlled-transport,12 actual admitted-
service-loss and2 unchanged-default native IPv4 timing cases. Existing native timing
evidence remains macOS/scripted HTTP; no installed-process/SIGINT acceptance inferred.
Fresh `rtk proxy uv run pytest --tb=short
--junitxml=/private/tmp/dutchmate-t017-results.xml`:2149 passed, zero failures/errors/
skips;664 CLI cases. `rtk proxy uv run ruff check .` clean; `rtk proxy uv run mypy .`
60 files clean; `rtk proxy uv run lint-imports` seven kept/zero broken (56 files/
152 dependencies); diff checks clean before/after docs. XML/content hashes audited.
Updated status/history/task/progress labels; only T017 newly checked. Temporary
hashes/XML remain outside repo. No T018 test_cli_process.py or package build started.

Exact deferred T018 scope: add installed console-process tests in test_cli_process.py
with parent/child hardware/real-account guards; main(args) privacy/exits distinct from
CliRunner, first/repeated SIGINT130/public Typer returned interrupt, private argv/
credential/exception sentinels, closed stdout/stderr, actual IPv4/IPv6 auth and
outside-cwd imports. Verify wheel/sdist/entry through uv into temporary locations;
no product external-program launcher. No physical device or real account credential
access, new native lifecycle/installed-process/hardware acceptance, Graphify refresh
(assessment T024), commit/push or later-task execution.

## 2026-10-10 — Feature 007 T016 Deadline/Loss/Phase Regressions GREEN

Completed only authorized T016, stopping before T017. Baseline remains
c2c9ce3153ae24f333b9dcd77565d633d7ac780d; preserved prior working-tree changes.
Only apps/cli/tests/test_cli_transport.py changed among code/tests/configuration;
no production, dependencies,001–006 contracts/source, service/Core or policy changes.

Added68 cases:54 controlled-transport,12 actual admitted-service-loss and2 native
IPv4 default-timing cases. Reuse real HTTPX client/existing wire fixtures. Shortened
test clock boundary asserts actual requested10s total, checking slow headers, empty
body waits, continual trickling and one shared header/body deadline; all four5s
phase settings remain actual request extensions. Test watchdogs are not Core timeouts.
No new clock port, sync HTTP worker or product injection point.

Already-buffered over-limit chunks are sliced to remaining1MiB+1 detection space;
no exact socket-read cap claimed. Reject truncated/partial/complete-bytes-but-lost
responses before receipt, close delivery and issue no additional request. Verify
setup not_submitted, attempted unknown, valid200 failed0/remote busy4 report_received,
and receipt retained through post-validation cancellation/encoding failure. Raw
client cancellation tests join headers/body delivery; no installed SIGINT claim.

Reuse unchanged guarded006 bootstrap/security/lifespan/runtime and strict FakeSerial/
temporary SQLite via the existing lifecycle fixture. Twelve attach/detach×before-Core/
inside-Core×deadline/read-loss/cancelled-wait cases gate actual service work. Only
client/ASGI delivery waiters are cancelled; shielded registered operations remain
live, then settle active/terminated after gate release with one backend/journal.
No automatic recovery/status/detach/retry/signal. A new explicit status observes
current facts but does not change the lost invocation's unknown receipt or claim
result recovery/attribution. No gate/authentication/ownership bypass.

Two scripted native loopback HTTP cases keep actual HTTPX/h11 defaults unchanged:
stalled headers hit5s read limit; progressing chunked whitespace ends at10s total,
despite repeated data. Focused XML case durations5.029s/10.150s include cleanup.
Numeric IPv4 on macOS only; no new IPv6/native Linux/Windows, service-lifecycle,
installed-process or hardware acceptance inferred from these timing checks.

Initial deterministic selection60 passed/244 deselected. Added six post-validation
phase cases; fresh `rtk proxy uv run pytest apps/cli/tests/test_cli_transport.py
-k t016 --tb=short --junitxml=/private/tmp/dutchmate-t016-focused.xml`:68 passed/
242 deselected, zero failures/errors/skips. No genuine RED or client defect found.
Fresh `rtk proxy uv run pytest --tb=short
--junitxml=/private/tmp/dutchmate-t016-results.xml`:2149 passed, zero failures/errors/
skips;664 CLI cases, transport310. `rtk proxy uv run ruff check .` clean;
`rtk proxy uv run mypy .`60 files clean; `rtk proxy uv run lint-imports` seven kept/
zero broken (56 files/152 dependencies); diff checks clean before/after docs.
XML/source-content hashes audited; completed001–006 diff empty. Updated status/history/
task/progress labels; only T016 newly checked. Temporary snapshots/XML outside repo.

T017 remains unstarted: correct only T016-demonstrated client waiting/cancellation/
bounds issues in client.py/context.py; no sync HTTP worker, retry, service signal/
detach or Core timeout. If already GREEN, record no defect without code changes.
No production correction made, physical device or real account credential accessed,
Graphify refresh (assessment T024), commit/push or later-task execution.

## 2026-10-10 — Feature 007 T015 US2 Software Validation

Completed only authorized T015, stopping before T016. Baseline remains
c2c9ce3153ae24f333b9dcd77565d633d7ac780d; preserved prior working-tree changes.
No production, test, dependency/configuration or contract changes; recorded actual
software validation and ownership evidence only.

Executed both US2 quickstart selections with temporary account/physical tripwires:
`rtk proxy uv run pytest apps/cli/tests/test_cli_lifecycle.py --tb=short
--junitxml=/private/tmp/dutchmate-t015-us2.xml`:88 passed. `rtk proxy uv run pytest
apps/service/tests core/tests --tb=short
--junitxml=/private/tmp/dutchmate-t015-completed.xml`:1485 passed (561 service/924 Core).
Zero failures/errors/skips in either selection. All54 T013 report assertions passed,
27 per existing Basic/Enhanced-shaped factory, including both idle-binary/readback
cases. Actual guarded006 security/app/lifespan/runtime and strict FakeSerial/normalized
fixtures with real temporary SQLite preserve software-only scope and authentication.

Ownership evidence reviewed: exactly one service runtime, one backend open/consumer,
capture continues after direct console main(args) returns, ambient all-byte/NUL/
non-UTF-8/CRLF data commits before later status, and only explicit detach closes the
run/reader/recorder once. Test-only bounded readback preserves bytes/order/provenance.
Console success/error/exit cleanup performs no service detach/signal/status follow-up;
client closes delivery only. This is direct-console/ASGI software evidence, not
installed process termination or actual SIGINT acceptance; those remain US3.

Ran all four exact quickstart scope commands. Core/service typer|dutchmate_cli search
empty (rg exit1/no matches); CLI banned-word search only serial_line_control wire enum,
no product import/behavior hit. `git diff c2c9ce3 --` completed001–006 paths empty;
`git ls-files graphify-out` empty. Root/package/Ruff/lock review confirms prior CLI
workspace/boundary changes only, seven unchanged contracts/no new exemption, all35
old package versions unchanged and only prior T002 client/transitive additions.

`rtk proxy uv run ruff check .` clean; `rtk proxy uv run mypy .`60 files clean;
`rtk proxy uv run lint-imports` seven kept/zero broken (56 files/152 dependencies).
Fresh slice gate `rtk proxy uv run pytest --tb=short
--junitxml=/private/tmp/dutchmate-t015-results.xml`:2081 passed, zero failures/errors/
skips;596 CLI cases. XML/source-content hashes audited; diff checks clean before/
after docs. Updated status/history/task/progress labels; only T015 newly checked.
No defect required correction. The slice gate does not complete the later T025 task;
temporary hashes/XML/lock snapshot remain outside repo.

T016 remains unstarted: add deadline/loss/phase regressions in test_cli_transport.py
for slow headers/empty waits/continual trickling10s total,5s phases, overflow chunks
sliced without an exact socket cap claim, invalid/partial responses, no automatic
requests and not_submitted→unknown→report_received independent of service admission.
Actual006 admitted attach/detach must settle after client loss; record genuine RED
if any. No T016 scenario, physical device or real account credential access, new
native lifecycle/installed-process/hardware acceptance, Graphify refresh (assessment
T024), commit/push or later-task execution. Phase 1/full CLI acceptance incomplete.

## 2026-10-10 — Feature 007 T014 No Demonstrated Client Defect

Completed only authorized T014, stopping before T015. Baseline remains
c2c9ce3153ae24f333b9dcd77565d633d7ac780d; preserved prior working-tree changes.
Reviewed T013 evidence and main.py/client.py against active reported-fact/privacy/
output contracts. T013 demonstrated no new-client presentation/integration defect;
its initial issues were corrected test fixture/expectation errors, not product RED.
Recorded that result without production or test changes. Source/test/configuration/
dependency and007 contract hashes unchanged;001–006 source/contracts diff empty.
No policy/schema/runtime/security revision or evidence delivery implementation.

Fresh `rtk proxy uv run pytest apps/cli/tests/test_cli_lifecycle.py -k t013
--tb=short --junitxml=/private/tmp/dutchmate-t014-focused.xml`:54 passed/34 deselected,
27 per existing Basic/Enhanced-shaped fixture, zero failures/errors/skips. Fresh
`rtk proxy uv run pytest --tb=short
--junitxml=/private/tmp/dutchmate-t014-results.xml`:2081 passed, zero failures/errors/
skips;596 CLI cases. `rtk proxy uv run ruff check .` clean; `rtk proxy uv run mypy .`
60 files clean; `rtk proxy uv run lint-imports` seven kept/zero broken (56 files/
152 dependencies); diff checks clean before/after documentation. XML/content hashes
audited. Updated status/history/task/progress labels; only T014 newly checked.
Temporary hashes/XML remain outside the repo. The repository gate verifies this
checkpoint and does not complete T015's separate acceptance task.

T015 remains unstarted: run US2/006/completed-core selections from007 quickstart.md
plus static/import/scope checks; record results in history, confirming one service
owner/RX and client exit never detaches. Real installed SIGINT/process acceptance
remains US3. No T015 execution, new native lifecycle/installed-process/hardware
acceptance, physical device or real account credential access, Graphify refresh
(assessment T024), commit/push or later-task work.

## 2026-10-10 — Feature 007 T013 Reported Facts and Idle Binary Regressions

Completed only authorized T013, stopping before T014. Baseline remains
c2c9ce3153ae24f333b9dcd77565d633d7ac780d; preserved prior working-tree changes.
Only apps/cli/tests/test_cli_lifecycle.py changed among code/tests/configuration;
no production, dependencies,001–006 contracts/source, service/Core or policy changes.

Added54 cases,27 per existing Core Basic/Enhanced-shaped backend factory, loaded by
file path independent of Core test collection. Real CLI main(args)/HTTPX execute on
a joined test worker/client loop; the test-only ASGI bridge schedules the real006
security/app/runtime on its existing owning loop. Retained actual isolated bootstrap,
credential path, lifecycle and resource tripwires. A test-only normalized preparation
edge connects existing fixtures to the real005 runtime and temporary SQLite; Profile
remains observation-only. This is no production Enhanced/Profile support claim.

Identical report assertions cover four terminal triggers across all backend/recorder
close combinations, keeping primary versus ordered cleanup/trigger/close/certainty
facts separate. Failed preparation/open preserve only allocated session/connection
IDs; gate attaching before journal/open/segment commit and draining after physical
release before recorder settlement. Full captured Profile remains exact after source
mutation/deletion. Host/device timestamp and loss variants remain reported facts;
opaque sorted provenance fields retain array order and null/bool/int/UTF-8 types.
A deliberately divergent closed wire report proves no client domain recomputation.

Ambient bytes including all256 values/NUL/non-UTF-8/CRLF commit between returned
console calls. Later status remains active; explicit detach joins one reader/backend/
recorder. Bounded real SQLite reopen/readback verifies bytes/order/segment provenance
only in tests; no CLI retrieval surface. The readback window restores test-side Path
helpers with no client invocation while preserving physical/account/no-service-reopen
tripwires. DEBUG-level logs/console reject private paths/tokens/causes/headers/bodies;
malformed remote output is fixed invalid_response5/unknown, without automatic cleanup.

Initial52 setup errors were test provenance fields not sorted as the existing Core
contract requires. Corrected test data/type annotation/import ordering. One test then
incorrectly expected failed-open physical release confirmed;005 explicitly leaves
release unconfirmed after any open attempt until successful connection close. Corrected
that expectation only. These are harness errors, not genuine007 product RED or defects.
Initial corrected52 passed; added two draining checks and DEBUG-level privacy coverage.

`rtk proxy uv run pytest apps/cli/tests/test_cli_lifecycle.py --tb=short
--junitxml=/private/tmp/dutchmate-t013-lifecycle.xml`:88 passed, zero failures/errors/
skips, including all54 new cases. Fresh `rtk proxy uv run pytest --tb=short
--junitxml=/private/tmp/dutchmate-t013-results.xml`:2081 passed, zero failures/errors/
skips. `rtk proxy uv run ruff check .` clean; `rtk proxy uv run mypy .`60 files clean;
`rtk proxy uv run lint-imports` seven kept/zero broken (56 files/152 dependencies);
diff checks clean before/after docs. XML and pre-change content hashes audited;
completed001–006 diff empty. Updated status/history/task/progress labels; only T013
newly checked. Temporary snapshots/XML outside repo.

No new-client presentation/integration defect demonstrated; no production fix made.
T014 remains unstarted: correct only demonstrated T013 new-client presentation/
integration defects in main.py/client.py with focused regression evidence; if none,
record no defect without production change. Never revise001–006 policy/schema/runtime/
security or implement evidence delivery. No T014 execution, physical device or real
account credential access, new native lifecycle/installed-process/hardware acceptance,
Graphify refresh (assessment T024), commit/push or later-task work.

## 2026-10-10 — Feature 007 T012 Attach/Detach Delivery GREEN

Completed only authorized T012, stopping before T013. Baseline remains
c2c9ce3153ae24f333b9dcd77565d633d7ac780d; preserved prior working-tree changes.
Only apps/cli/src/dutchmate_cli/main.py and client.py changed among code/tests/
configuration; no context, tests, package/dependency,001–006 source/contract or
service/Core changes. No new abstractions or ownership/domain policy.

Added Typer attach with required string --profile/--journal and bodyless detach.
Validate target and existing AttachPaths lexical values before credential/network;
no expansion/file checks. Each callback reads the credential once, calls the
existing async exchange once and uses the established validated-record output/
exit boundary. Root callback remains passive; static help covers all three commands
and distinguishes exit0 report delivery from active capture or confirmed cleanup.

Added only fixed request mapping in client.exchange: attach POST with exactly
profile_path/journal_path JSON, detach POST without body, status GET without body.
Literal006 routes, existing one-request transport settings,10s overall/5s phase
limits, raw/output bounds, closed wire validation, privacy, errors and request_outcome
remain. No retry/preflight/status follow-up/implicit detach or duplicated Profile/
journal/lifecycle logic; actual resources and admitted work remain service-owned.

Fresh `rtk proxy uv run pytest apps/cli/tests/test_cli_commands.py
apps/cli/tests/test_cli_lifecycle.py -k t011 --tb=no
--junitxml=/private/tmp/dutchmate-t012-red.xml`:67 expected RED/5 passed/89 deselected.
After wiring, same selection with --tb=short and dutchmate-t012-green.xml:72 passed/
89 deselected, no test changes. Initial mypy caught a request/response body variable
name collision; renamed request_body before the final gate.

Fresh `rtk proxy uv run pytest --tb=short
--junitxml=/private/tmp/dutchmate-t012-results.xml`:2027 passed, zero failures/errors/
skips, all XML cases audited. `rtk proxy uv run ruff check .` clean;
`rtk proxy uv run mypy .`60 files clean; `rtk proxy uv run lint-imports` seven kept/
zero broken (56 files/152 dependencies); diff checks clean before/after docs.
Installed `rtk proxy uv run dutchmate attach --help` and detach --help each exited0.
Pre-change content-hash audit confirms unchanged CLI tests/context/config/dependencies;
completed001–006 diff empty. Scope search hits only existing capability/Profile wire
strings, no forbidden product imports/resource calls. Temporary snapshots/XML outside repo.
Updated status/history/task/progress labels; only T012 newly checked.

T013 remains unstarted: add reported-fact/privacy/failure/idle-binary regressions in
test_cli_lifecycle.py for primary versus cleanup/trigger/certainty separation,
nullable committed IDs, immutable reported Profile and no recomputed admissibility.
Run identical report assertions against existing Basic/Enhanced-shaped fixtures;
real temporary journal readback stays in tests only. Record genuine RED only if
new gaps appear. No new T013 scenario, native lifecycle/installed-process/hardware
acceptance claim, physical device or real account credential access, Graphify refresh
(assessment T024), commit/push or later-task execution.

## 2026-10-10 — Feature 007 T011 Lifecycle and Grammar RED

Completed only authorized T011 test authoring, stopping before T012. Baseline remains
c2c9ce3153ae24f333b9dcd77565d633d7ac780d; preserved the previous working tree.
No production, dependency,001–006 source/contract, service/Core or policy changes.

Added38 cases to apps/cli/tests/test_cli_commands.py and34 cases in new
apps/cli/tests/test_cli_lifecycle.py. Grammar requires actual lifecycle command/help
recognition before asserting invalid inputs, preventing unknown-command rejection
from masquerading as lexical validation. Cover explicit bounded absolute Profile/
journal strings, literal/unexpanded paths and exact006 fields, bodyless detach,
missing/global/extra/unsupported options, resource-free help, no defaults/autostart/
service commands and one credential/request. No CLI path file inspection permitted.

Lifecycle tests reuse006's unchanged guarded real bootstrap/security/lifespan/runtime
fixture with strict FakeSerial and temporary SQLite. HTTPX's external transport alone
is bridged to the real ASGI app on the owning loop. Scoped resource tripwires allow
actual server Profile/backend/journal preparation while rejecting client calls.
Cover normal attach/detach, inactive detach, busy, Profile errors, cleanup uncertainty,
failed startup, stale credential/browser rejection, all six typed valid200 runtime
states including failed exiting0, all four normalized runtime rejection kinds and
fixed internal-service failures. The private paths=AttachPaths test seam is provisional;
only documented HTTP mapping is normative. Harness validity is independently GREEN.
No native lifecycle/installed-process or physical acceptance inferred from ASGI/fakes.

Executed `rtk proxy uv run pytest apps/cli/tests/test_cli_commands.py -k t011
--tb=short --junitxml=/private/tmp/dutchmate-t011-grammar.xml`:34 expected RED/4 passed,
89 deselected. `rtk proxy uv run pytest apps/cli/tests/test_cli_lifecycle.py --tb=short
--junitxml=/private/tmp/dutchmate-t011-lifecycle.xml`:33 expected RED/1 passed.
Missing T012 command registration/fixed exchange mapping explains every failure;
existing tests remain GREEN. Corrected a test resolver import to its public adapter
module after mypy rejected the incidental observation_runtime reexport.

Fresh full `rtk proxy uv run pytest --tb=short
--junitxml=/private/tmp/dutchmate-t011-results.xml`:1960 passed/67 expected T011 RED,
zero other failures/errors/skips. XML audited all2027 cases:34 grammar/33 lifecycle
failures, all named test_t011_* and matching missing-wiring expectations. Of72 new
cases, five controls already pass. Full feature gate is intentionally RED until T012.
`rtk proxy uv run ruff check .` clean; `rtk proxy uv run mypy .`60 files clean;
`rtk proxy uv run lint-imports` seven kept/zero broken (56 files/152 dependencies);
diff checks clean. Updated status/history/task/progress labels; only T011 newly checked.

T012 remains unstarted: add only Typer attach/detach wiring in main.py and necessary
fixed request mapping in client.py to make T011 GREEN; lexical context before
credential/network, at most one request, no retry/preflight/status follow-up/implicit
detach or duplicated Profile/journal/lifecycle logic. No physical device or real
account credential accessed, hardware/electrical/native Linux/Windows acceptance,
Graphify refresh (assessment T024), commit/push or later-task execution.

## 2026-10-10 — Feature 007 T010 US1 Native Status Acceptance

Completed only explicitly authorized T010, stopping before T011. Baseline remains
c2c9ce3153ae24f333b9dcd77565d633d7ac780d;001–006 source/contracts and all35 old locked
versions unchanged. Preserved prior working-tree changes; no dependency/package,
service/Core, authentication-policy or attach/detach implementation change.

Added16 cases in apps/cli/tests/test_cli_transport.py. Reused006's unchanged service
process helper by private test loading: one independently guarded child safety probe
and ten native IPv4/IPv6 status cases (valid, stale credential, mismatched Host,
Origin and Sec-Fetch). Actual controlled launcher, private bootstrap/flock/dirty
marker/credential, security middleware, lifespan and one real inactive runtime;
actual CLI read-only credential helper, async HTTPX/h11 socket path and main(args).
Parent/child physical-serial/enumeration and real-account guards remain; child
forbids run preparation. Status invokes no Profile/Basic/journal preparation.

Every invocation issued one GET/no body with one read/Bearer and selected authority,
no DNS/proxy/trace extension/replay. Stale valid token rejected by the cached service
credential without reread/retry; authenticated Host/browser provenance rejection
preserved. Actual responses closed, client/service logs and diagnostics private,
one native listener/runtime, joined test-owned service cleanup/credential removal/
confirmed marker. Both numeric families passed on macOS with zero native IPv6 skips.
No installed CLI-status child, mutation, capture, lifecycle or process SIGINT scenario
was added; those remain later acceptance. New service children are test-owned only.

Inspected pinned HTTPX send/auth/redirect/stream/log paths, HTTPcore emitting loggers/
trace formatting and Typer public error/completion/help paths against explicit
client settings. Demonstrated one007 diagnostic projection defect: pinned Typer
converts help's broken pipe to SystemExit1, which the wrapper mislabeled internal_failure.
Three root/no-command/status help probes failed RED with that wrong fixed category;
narrow main.py correction classifies only an OS EPIPE context as output_failed.
Only errno/category inspected, no exception text/cause/locals emitted. Two additional
checks preserve internal_failure for unexpected integer/private-text framework exits.
Five SDK regression cases GREEN; no additional demonstrated product defect remains.

Executed exact US1 selections: `rtk proxy uv run pytest apps/cli/tests/test_cli_commands.py
--tb=short`89 passed; `rtk proxy uv run pytest apps/cli/tests/test_cli_transport.py
--tb=short --junitxml=/private/tmp/dutchmate-t010-transport.xml`242 passed. Initial
native selection11 passed. Installed `rtk proxy uv run dutchmate --help` and
`rtk proxy uv run dutchmate status --help` each exited0 with static help/no service
target, credential or hardware work, verified before and after the projection fix.

Fresh full `rtk proxy uv run pytest --tb=short
--junitxml=/private/tmp/dutchmate-t010-results.xml`:1955 passed, zero failures/errors/
skips, XML audited (16 T010 cases). Ruff clean after local test import ordering fix;
mypy59 files clean; seven Import Linter contracts kept (56 files/152 dependencies);
diff checks clean before/after docs. Quickstart scope searches found only the allowed
serial-line capability string, no forbidden product import,001–006 diff or tracked
Graphify output. SDK/version/baseline/static boundaries unchanged; temporary XML
remains outside repo. Updated status/history/task/progress labels.

T011 remained unstarted: add RED test_cli_lifecycle.py and attach/detach grammar
in test_cli_commands.py for explicit bounded absolute --profile/--journal mapped
to006 fields without CLI file checks, bodyless detach, missing/extra/unsupported
options, no service/autostart/defaults, existing busy/Profile/runtime/HTTP categories,
every valid200 including failed exiting0, real guarded006 composition and zero
CLI resource imports/calls. Production wiring belongs to T012.
US1 is not complete lifecycle/console-process acceptance. No physical device or real
account credential accessed, native Linux/Windows/electrical acceptance, Graphify
refresh (assessment T024), commit/push or later-task execution.

## 2026-10-10 — Feature 007 T009 Pure Status Console Entry

Completed only explicitly authorized T009, stopping before T010. Baseline remains
c2c9ce3153ae24f333b9dcd77565d633d7ac780d;001–006 source/contracts unchanged. Preserved
the existing working tree and locked dependency versions. No attach/detach behavior.

Added apps/cli/src/dutchmate_cli/main.py: Typer root/status with global host/optional
parser port, passive options callback and no-command/help0 without account/credential/
platform/network preparation. Actual status validates its target, reads the existing
credential once, calls the T008 async client and routes its bounded UTF-8 record
verbatim: valid200 stdout0 including failed state, remote error stderr4. One local
invocation owns options/receipt phase; no global HTTP owner, new request model,
Core/service imports, policy/ownership replica or resource management.

Console wrapper uses public pinned Typer APIs/standalone_mode=False/fixed program
name, disabled suggestions/completion/pretty exceptions/locals/color and fixed client
diagnostics. Handle public TyperException/Abort, returned130 and outer KeyboardInterrupt
without exception show/format/text/locals; restore Typer's installed exception hook.
Output failure preserves receipt phase and permits exit-only failure if stderr is
unusable, with no repeated exception fallback or service cleanup request.
Registered dutchmate=dutchmate_cli.main:main in apps/cli/pyproject.toml only after
module creation; uv rebuilt the editable CLI/installed script during the focused run.
Entry metadata/import resolves outside repo cwd; no actual installed command launched.

Fresh `rtk proxy uv run pytest apps/cli/tests/test_cli_commands.py --tb=no
--junitxml=/private/tmp/dutchmate-t009-red.xml`:86 missing-main RED failures.
Initial implementation made all86 GREEN. Added three already-GREEN unit cases for
inactive/failed/remote-error validated record routing, exact selected target/one
credential handoff and no network preparation. They substitute only the client
result boundary; authenticated/native/installed-process acceptance remains later.
Focused89 passed. Ruff/mypy59 files/seven import contracts clean.

First full gate exposed122 failures/1817 passes: existing context import-purity
test reloaded the canonical module after main had imported client, invalidating
cached exception-enum identity. Isolated reproduction confirmed client._invalid
then raised TypeError instead of its fixed failure. Corrected only that test to
execute the same source via runpy in an isolated namespace under its existing
account/file tripwires; no test bypass or production hot-reload compatibility layer.
CLI-only selection454 passed after correction.

Final `rtk proxy uv run pytest --tb=short
--junitxml=/private/tmp/dutchmate-t009-results.xml`:1939 passed, zero failures/errors/
skips, XML audited. `rtk proxy uv run ruff check .` clean; `rtk proxy uv run mypy .`
59 files clean; `rtk proxy uv run lint-imports` seven kept/zero broken (56 files/
151 dependencies); diff checks clean before/after docs. All35 old lock versions
unchanged; lock changes remain only prior T002 additions. Status/history/task/progress
labels reconciled; T010 remained unchecked/unstarted. Temporary XML stays outside repo.

Exact T010 scope recorded: run US1 quickstart commands, targeted/static/import checks
and actual006 authenticated status integration in test_cli_transport.py; inspect
HTTPX/httpcore/Typer logging/error paths and fix only demonstrated007 security/
transport/projection defects. US1 is not complete lifecycle/console-process acceptance.
No T010 scenario, hardware/real-account credential access, native Linux/Windows/
electrical acceptance, Graphify refresh (assessment T024), commit/push or later task.

## 2026-10-10 — Feature 007 T008 Bounded Status Client

Completed only explicitly authorized T008, stopping before T009. Baseline remains
c2c9ce3153ae24f333b9dcd77565d633d7ac780d;001–006 source/contracts unchanged. Preserved
the existing working tree; no package/dependency change, main.py or console entry.

Added only apps/cli/src/dutchmate_cli/client.py: a concrete short-lived HTTPX async
status exchange, invocation-local receipt phase and fixed local error/exit encoding.
Exact numeric authority (including80/bracketed IPv6), one Bearer and JSON/identity
headers; explicit HTTP/1/no HTTP/2/no proxy/env/redirect/retry, one connection/zero
kept pool,5s phases and one absolute10s waiting deadline. Stream raw bytes with
1MiB+1 sliced detection cap and close delivery on every result. Strict UTF-8 JSON
with duplicate/nonfinite rejection, exact media/encoding and closed006 keys/types/
string enums/error pairs; bounded compact UTF-8 record plus LF. No domain/Profile
predicates or cross-field recomputation: nullable IDs, primary/cleanup/trigger/
certainty/admissibility, opaque provenance and all six runtime states preserved.
No account/Profile/journal/DUT/terminal I/O, service/Core imports, global HTTP owner,
generic client/DTO framework, mutation timing, retry or service cleanup request.

T007 was freshly RED225 before implementation. Authority review found its float
stop_bits output-expansion fixture contradicted004/006's integer wire type. Corrected
that test to verify the encoder cap directly with a typed report; added float-wire
rejection before production code (226 RED). This corrects the prior T007 record's
overflow claim without changing a product rule or weakening the wire contract.

Initial implementation225 passed/one logging privacy failure. Isolated case passed;
order-dependent reproduction and parent metadata traced the cause to pytest attaching
handlers directly to non-propagating parents. Parent.disabled does not disable child
records. Pinned SDK source inspection identified its emitting channels; disable both
parents and HTTPX/HTTPcore emitting loggers without changing global logging policy.
Temporary diagnostic instrumentation removed; focused226 then passed.

First full gate exposed one encoder-test exception alias made stale by existing
context import-purity reload tests (1849 passed/87 failures,86 already expected).
Corrected the private helper assertion to use its actual ordinary exception class
and fixed category value; production behavior unchanged. Final focused226 passed.
Fresh `rtk proxy uv run pytest --tb=short
--junitxml=/private/tmp/dutchmate-t008-results.xml`:1850 passed/86 expected T006 failures,
zero errors/skips; every XML failure audited as absent T009 command/console module.
No unexpected failure remains; overall feature gate remains intentionally RED.

`rtk proxy uv run ruff check .` clean (one automatic review timeout resolved by its
single permitted retry); `rtk proxy uv run mypy .`58 files clean; `rtk proxy uv run
lint-imports` seven contracts kept (54 files/143 dependencies); diff checks clean.
Installed client imports outside repo cwd verified, no console entry, all35 old
lock versions unchanged. Final scope search hit only the legitimate serial-line
capability string, no forbidden imports. Status/history/task/progress labels updated.

T009 remained unstarted: pure Typer root/status command and console main wrapper
in main.py, register dutchmate script only then; public pinned APIs/standalone_mode=False,
help0/fixed diagnostics/no pretty locals/logs, valid200 stdout JSON0 including failed,
remote error stderr4; make T006 GREEN. No attach/detach behavior in that task.
Actual authenticated integration is T010, delayed/admitted/native/installed-process
acceptance later. No physical hardware/real-account credential accessed, native
Linux/Windows/electrical acceptance, Graphify refresh (assessment T024), commit/push
or later-task execution.

## 2026-10-09 — Feature 007 T007 Transport Contracts RED

Completed only explicitly authorized T007 test authoring and RED verification,
stopping before T008. Baseline remains c2c9ce3153ae24f333b9dcd77565d633d7ac780d.
Preserved earlier working-tree changes; no production, package/dependency/static
guard or001–006 contract changes. No client.py/main.py/console entry created.

Added apps/cli/tests/test_cli_transport.py with225 cases. Test-owned HTTPX transport/
stream substitution retains the actual SDK request/response machinery; native
connections/resolution and whole-response read/aread/json/text/content are tripwired.
Literal006 wire reports avoid using production codecs as their own oracle.
Tests cover one exact status GET/no body/query, numeric family/port80/IPv6-bracket
Host, one Bearer, JSON/identity headers, no Origin/Sec-Fetch/Upgrade/cookies/token
elsewhere, explicit HTTP/1/one connection/zero kept pool/retries0/no proxy/env/
redirect/fallback. Check actual SDK timeout extensions and an absolute10s deadline
active during request/raw streaming with5s phase limits; progressing chunks do not
recreate the outer timeout. Delayed response expiration/admission/native tests stay
with T016/T018; this checkpoint does not claim those behaviors passed.

Raw body tests accept1MiB, detect excess at1MiB+1 despite a misleading length,
and watch the private accumulator slicing an already-buffered oversized chunk;
no exact socket-read cap is claimed. Encoded record tests check compact UTF-8 with
non-ASCII preserved and1MiB excluding LF. The initial numeric re-encoding overflow
fixture remained RED here and was corrected under T008's integer-wire review.
Strict UTF-8/JSON duplicate/nonfinite/truncation, exact media/identity encoding,
closed nested keys/types/enums and malformed h11 plain-text400 rejection covered.
Duplicate/nonfinite cases are otherwise complete envelopes, so missing strict
decoding cannot hide behind unrelated shape rejection. JSON object key order is
free; array order and nullable/scalar facts remain authoritative.

Preserve all reported states/facts (including failed200 exit0), primary/cleanup/
trigger/close/certainty/nullable/admissibility and opaque provenance without domain
reconstruction. Task/quickstart's five-state shorthand was resolved by existing
006/Core authority: all six states, including terminated, in both service phases
and host/device-shaped wire variants. No governing semantic rule was changed.
All29 documented HTTP/source/code pairs deliver exit4; unknown/mismatched/extra
diagnostics reject. Local table covers ten fixed codes/three delivery phases;
request/stream errors stay unknown, validated reports advance report_received,
and no redirect/auth-refresh/transport retry occurs. Guard debug propagation and
private request/response/exception sentinels. Ordinary fixed failures stay input-free.

The module documents its provisional private T008 invocation/state/record and
accumulator test seams, not new public APIs or generic client/DTO layers. Actual
authenticated006 integration remains T010, real fixture/lifecycle acceptance later.
Public API/contracts are unchanged; no service policy/auth/bootstrap is copied.

Final `rtk proxy uv run pytest apps/cli/tests/test_cli_transport.py --tb=short
--junitxml=/private/tmp/dutchmate-t007-focused.xml`:225 expected RED failures.
`rtk proxy uv run pytest --tb=short --junitxml=/private/tmp/dutchmate-t007-results.xml`:
1624 passed/311 expected failures, zero errors/skips. Audited every XML failure:
225 T007 missing client (T008),86 prior T006 missing main (T009), nothing else.
Full suite is intentionally RED; no passing feature gate or HTTP acceptance claim.
Temporary XML stays outside repo. Ruff clean; mypy57 files clean after local
test-harness typing corrections; seven import contracts kept; diff checks clean.

Updated status/history/progress labels and checked only T007 beyond prior tasks;
quickstart's state-count summary corrected against the authoritative006 contract.
T008 remained unstarted: one concrete async HTTPX exchange and wire-shape validation
in client.py, explicit settings/outer monotonic deadline/raw cap/fixed local
categories/delivery phase, make T007 GREEN; no global HTTP owner, generic client/
DTO framework, Core/service imports or mutation timing. No console implementation.
No physical device/real-account credential access, Graphify refresh, commit/push or
later-task execution. Native Linux/Windows/hardware acceptance remain unexecuted.

## 2026-10-09 — Feature 007 T006 Command Contracts RED

Completed only explicitly authorized T006 test authoring and RED verification;
stopped before T007. Baseline remains c2c9ce3153ae24f333b9dcd77565d633d7ac780d.
Preserved the existing T001–T005/planning working tree; no production, dependency,
package, static guard or001–006 contract changes.

Added apps/cli/tests/test_cli_commands.py with86 cases covering pure root callback,
no-command/root/status help0 (including help after invalid target storage and mocked
unsupported platform), exact global option ordering, equals syntax/final repeated
values, valid targets reaching one credential boundary without network, and fixed
invalid_arguments2 for missing/invalid targets, misplaced/unknown/private arguments.
Completion/version/URL/token/credential/timeout/env/output options and short port
alias reject; environment cannot supply the required target. CliRunner exercises
real Typer grammar with standalone_mode=False; direct main(args) verifies normalized
JSON/exits without native error text. Public TyperException/Abort, real Typer's
returned130, outer KeyboardInterrupt and unexpected exceptions are separate probes;
exception show/str/format and private argv/exception/local/log sentinels are guarded.
Harness restores Typer's global exception hook after direct invocation.

Tests use existing isolated-account/physical-device fixtures and per-invocation
account/credential/platform/file/resolver/socket/HTTP tripwires. Framework probes
substitute only the Typer boundary; they do not claim actual CLI or installed-process
SIGINT acceptance. Missing main.py is a per-test RED failure, not a collection error;
main.py/client.py/console entry remain absent. T009 implements these command contracts.

Executed `rtk proxy uv run pytest apps/cli/tests/test_cli_commands.py --tb=short`:
86 expected RED failures. Full `rtk proxy uv run pytest --tb=short
--junitxml=/private/tmp/dutchmate-t006-results.xml`:1624 passed/86 failed, zero errors/
skips. Audited all86 XML failures: only test_cli_commands, each reporting T009
command/console implementation absent. No other failure observed; full suite is
intentionally RED, not a passing feature gate. Temporary XML remains outside repo.
`rtk proxy uv run ruff check .` clean; `rtk proxy uv run mypy .`56 files clean;
`rtk proxy uv run lint-imports` seven kept/zero broken; diff checks clean after docs.

Updated current status/history and007 progress labels; checked only T006 beyond
the prior five. T007 remains unstarted: RED test_cli_transport.py for one status
request, exact Host (including80/IPv6 brackets)/one Bearer, no Origin/proxy/env/
redirect/retry/DNS/fallback,10s absolute/5s phase waits, raw uncompressed1MiB+1
retention/1MiB acceptance, strict UTF-8/media/duplicate/nonfinite/closed006 wire and
output bounds, all five states, fixed HTTP/local exit/envelope mappings. No domain
predicate duplication or raw diagnostics; transport implementation belongs to T008.

No physical device or real-account credential accessed; native evidence macOS only.
No hardware/Linux/Windows acceptance, installed console-process tests, Graphify
refresh, commit/push or subsequent task executed.

## 2026-10-08 — Feature 007 T001–T005 Observation CLI Foundation

Completed only the explicitly authorized first five tasks, stopping before T006.
Baseline remains main c2c9ce3153ae24f333b9dcd77565d633d7ac780d;006 implementation
b4c5730b2a5e593c10c06ad9e8f24c39e06f794b and001–006 source/contracts unchanged.
Preserved the existing007 planning/status/history working-tree edits.

- T001: read Core/007 spec/plan/contracts/data model/research/quickstart/tasks,
  active status and006 contract; inspect runtime/service and actual parent/child
  hardware/real-account guards. Executed `rtk proxy uv run pytest apps/service/tests
  --tb=short`:561 passed, zero failures/errors/skips. Initial sandbox cache denial
  was resolved by permitted uv/cache/test-owned loopback execution.
- T002: minimal apps/cli pyproject/Ruff/__init__, workspace/test/mypy coverage,
  temporary-account/physical-device test tripwires and strengthened seven import
  contracts. `rtk proxy uv add --package dutchmate-cli 'typer>=0.27.3,<0.28'
  'httpx>=0.28.1,<0.29'` resolved Typer0.27.3/HTTPX0.28.1/HTTPcore1.0.9 and their
  legitimate transitives. All35 prior locked versions unchanged, including Click.
  Public TyperException/Abort and installed package/context/SDK imports outside
  repository cwd verified; no console entry exists. Mypy initially identified
  duplicate unpackaged conftest modules; explicit namespace bases plus existing
  Core/service test roots fixed discovery without test exclusions or package copies.
- T003/T004:137 missing-context RED failures, then137 GREEN in the exact context
  selection. Added only context.py: passive typed options, exact numeric target,
  bounded absolute POSIX attach strings, ordinary fixed-category failures and fixed
  effective-UID/passwd credential read. No-follow descriptor-relative read-only
  traversal, final regular UID/0600/single-link checks,66-byte partial-read/detection
  bound, exact lowercase64hex+LF and cleanup on success/failure. No lock/marker,
  directory policy/repair, file fallback, Profile/journal access, network, Typer
  callback or Core/service imports. Two further cleanup/directory-marker boundary
  checks were already GREEN and required no production change:139 final passes.
- T005: fresh `rtk proxy uv run ruff check .` clean; `rtk proxy uv run mypy .`
  clean across55 files; `rtk proxy uv run lint-imports` seven kept/zero broken
  (51 files/134 dependencies); `rtk proxy uv run pytest`1624 passed, zero failures/
  errors/skips; `rtk proxy git diff --check` clean before/after documentation.
  Scope searches found no forbidden production imports;001–006 diff empty.

Updated status/history and007 progress labels/task markers only, preserving governing
contracts. T006 remains unstarted: RED test_cli_commands.py for pure callback,
global host/port ordering, no-command/root/status help0 without account/credential/
network/platform I/O, fixed invalid_arguments2 for missing/invalid targets and
unknown/input-bearing arguments, absent extra options, CliRunner grammar plus
direct console-wrapper public Typer error/interrupt privacy. It adds tests only;
HTTP exchange tests/implementation and console entry are T007–T009.

No commit/push/Graphify refresh (assessment belongs to T024), physical-device access,
real-account credential read or hardware acceptance. Native software evidence is
macOS only; Linux/Windows and electrical/physical acceptance remain unexecuted.
Full CLI acceptance, deadlines/reports/lifecycle/installed console processes and
all broader deferrals remain outside this foundation slice.

## 2026-10-08 — Feature 007 Observation CLI Specified, Planned and Tasked

Completed only the explicitly accepted lean specify → plan → tasks workflow for
minimal authenticated observation-only CLI, with Typer mandated by the user.
Sequential repository numbering found001–006 and assigned007-observation-cli;
Git remains main at c2c9ce3153ae24f333b9dcd77565d633d7ac780d, with006 implementation
b4c5730b2a5e593c10c06ad9e8f24c39e06f794b unchanged. Managed template resolver,
setup-plan and setup-tasks ran in sequence; no extension hooks existed. Ignored
.specify/feature.json records the feature context and remains untracked.

Eight artifacts define three prioritized stories,30 requirements and25 unchecked
tasks. Exact first group T001–T005 is baseline/package/tooling, endpoint/credential
RED/GREEN primitives and foundation validation only; commands/HTTP begin later.
No new source/tests/package/dependency/lock changes or product resources created.

Settled: dutchmate root attach/status/detach with global exact numeric host/default
127.0.0.1 or::1 and required port, explicit absolute Profile/fresh journal arguments;
fixed existing passwd-home credential read-only/no-follow/0600 UID regular single-
link/65+1 bound; one Bearer request, no URL/env/proxy/redirect/retry/fallback/autostart.
Typer callback/help pure; safe public exception/interrupt APIs; no traceback/input
diagnostics. Three-module delivery only, no Core/service production imports or
duplicated Profile/runtime/journal/backend/auth-policy/ownership logic.

Output is compact complete JSON; valid200 report exits0 even failed runtime, never
asserting active capture/cleanup. Valid remote errors exit4; usage2, credential/
platform3, transport/protocol5, interrupt130, internal/output1. Local client errors
carry not_submitted/unknown/report_received for HTTP delivery only.10-second total
HTTP deadline/5-second phases, raw retained response1MiB+1/output1MiB+LF. No exact
socket-read ceiling claimed; client loss never cancels service-owned admitted work,
detaches/retries/signals service or recovers a lost response through later status.

Prior read-only targeted Graphify and current source inspection established dependencies;
two read-only planning research agents verified official Typer/HTTPX/Python sources.
Planned typer>=0.27.3,<0.28 and httpx>=0.28.1,<0.29, with public TyperException and
HTTPcore>=1.0.9 compatibility checked during T002. No actual dependency/SDK test
acceptance claimed from metadata. Research records primary sources/license rationale.
Core/service transitive boundaries stay strict; new direct-only external CLI bans
permit required framework internals as documented, without product exemptions.

Documentation checks verified file links/format, requirements/task coverage, bounds/
exits/delivery-phase consistency, sequential workflow, ignored feature state, source/
config/baseline hashes, Resume Here length and git diff --check. Existing001–006
software gates are prior evidence, not rerun results. No unresolved product decision;
no Spec Kit extra stages/implementation, Graphify refresh, commit/push or hardware.
Native macOS-only prior evidence and unexecuted Linux/Windows/physical acceptance
limits retained. Service management/evidence/Monitor/follow/TX/Control/handoff/
reconnect/catalogue/Profile discovery/Enhanced/MCP/AI remain deferred.

## 2026-10-08 — Feature 006 Commit and Baseline Reconciliation

Completed the explicitly authorized final pre-commit review and committed the full
intended25-file feature006 set as
`b4c5730b2a5e593c10c06ad9e8f24c39e06f794b`
(`Implement local observation service`). Staged diff/stat/blob inventory matched
the validated working tree; no unrelated/generated/runtime/credential/Graphify
files. git diff --cached --check passed before commit; no new defect was found.
Fresh full validation is recorded immediately below:1485 passed, zero failures/
errors/skips, Ruff clean, mypy51 files clean, five import contracts kept/zero broken.

After successful implementation commit, reconciled current status and minimal
feature checkpoint metadata in a documentation-only follow-up, recording the actual
full implementation hash without attempting to embed a commit's own hash in itself.
Feature006 is software-complete and committed; all30 tasks complete. Features001–005
and Core/schema/Profile/runtime semantics remain unchanged. Native validation was
macOS only; Linux/Windows native and physical/electrical acceptance are unexecuted.
No physical hardware accessed or validated, push, next-slice implementation or
Spec Kit run. Generated Graphify output remains ignored; no additional update.

## 2026-10-08 — Feature 006 Final Pre-Commit Review and Validation

Performed the explicitly authorized final pre-commit review against Core, active
feature006 FR-001–030/spec/plan/contract/data model, all30 completed tasks and
current status. Reviewed the complete intended tracked/untracked inventory and
confirmed source/test/configuration identical to the completed T030 baseline.
No new genuine feature006 defect or correction was required.

Fresh commands through rtk proxy/env UV_CACHE_DIR=/private/tmp/dutchmate-feature006-uv-cache
uv run: Ruff clean; mypy51 source files clean; Import Linter five contracts kept/
zero broken,49 files/125 dependencies. Full guarded pytest with permitted local
loopback access:1485 passed in16.96 seconds, zero failures/errors/skips. JUnit:
/private/tmp/dutchmate006-precommit-full.xml. Native validation macOS only; Linux/
Windows native and all physical/electrical acceptance remain unexecuted. No
physical hardware accessed or validated.

Core/completed001–005 remain unchanged, including schema-v1, Profile-v1 and005
lifecycle/cancellation/cleanup. All22 baseline locked versions preserved. Reviewed
authenticated three-route delivery, persistent owning-loop runtime, bounded owned
mutations, selected loopback family, private per-UID bootstrap and joined truthful
cleanup. No deferred workflow/client/Enhanced behavior, insecure bypass, secret
logging, extra reader or backend-identity branch found.

Intended feature set is25 files:four existing modifications plus21 new service/
specification files. Source/test/configuration hashes, scope searches, task markers
and tracked/untracked whitespace verified. Generated Graphify output remains ignored;
no additional update, unrelated/runtime/credential artifact or hardware acceptance
claim. Commit subject authorized: Implement local observation service. Actual commit
identity and completed baseline reconciliation are recorded after successful commit.

## 2026-10-08 — Feature 006 T030 Fresh Final Software Gate and Diff Review

Executed only T030 using verification-before-completion. Read active spec/plan/
contracts/tasks and current status, inspected tracked/untracked intended changes,
and verified parent/child test hardware/account guards before running the full gate.
Systematic debugging of the initial failures confirmed the sandbox's local socket
restriction; no production/test correction was needed.

All Python commands used rtk proxy/env UV_CACHE_DIR=/private/tmp/dutchmate-feature006-uv-cache
uv run. Actual fresh gate results:

| Check | Result |
|---|---|
| ruff check . | All checks passed |
| mypy . | No issues in51 source files |
| lint-imports | Five contracts kept/zero broken;49 files/125 dependencies |
| pytest --junitxml=/private/tmp/dutchmate006-t030-full.xml |1485 passed, zero failures/errors/skips;15.77 seconds |
| git diff --check | Clean before documentation and again after recording results |

The initial sandboxed full run recorded34 failures/1451 passes in7.71 seconds.
Every failure was test_service_process socket allocation with PermissionError:
[Errno1] Operation not permitted; no other failure/error/skip. Preserved separate
JUnit /private/tmp/dutchmate006-t030-sandbox.xml. Automatic approval permitted the
same full guarded suite with local socket access; that rerun passed all cases.
No bypass, test weakening, added skip or code change resolved the environment limit.

Final JUnit verifies924 Core,90 bootstrap,226 HTTP,38 process,111 projection and96
runtime passes. Native macOS IPv4 and IPv6 process cases actually ran; no platform/
IPv6 skips counted as passes. Fake transports/temporary journals and isolated
account state were used throughout; no physical device accessed or validated.
Linux/Windows native acceptance and all physical/electrical acceptance remain
unexecuted; Windows service implementation is deferred by the accepted contract.

Final intended diff review found no new feature006 scope/contract defect. Reviewed
service source, security/logging/telemetry, bounded projection/input, persistent
owning-loop runtime, registered request lifetime, signal/startup/shutdown cleanup,
stale/duplicate ownership, package/import configuration and lockfile. Basic/SQLite
remain at the existing edge; primary/cleanup/trigger/certainty remain distinct.
Core and completed001–005 source/specifications are identical to committed HEAD.
No evidence/Profile schema changes, extra reader, reconnect/discovery, backend-
identity branching or deferred workflow/client/Enhanced behavior was introduced.

Intended inventory:25 files, comprising four tracked modifications (status/history,
root pyproject.toml/uv.lock) and21 new files (five service source, six test/guard,
two service config and eight feature artifacts). No unrelated/generated/runtime/
credential files. All22 baseline locked versions preserved; unused httpx/httpcore/
certifi and telemetry SDK remain absent. Service dependencies are intentional.
Root/core architecture constraints remain intact; existing exemptions not weakened.
Generated Graphify output/backups remain ignored; no second update was run.

All146 repository files were unchanged throughout the gate/review before final
documentation bookkeeping. Updated status/history and minimal spec/plan/quickstart/
task completion metadata only; all30 tasks now checked. Verified source/test/config
hashes, local links, task markers, baseline/HEAD, Resume Here length, tracked/
untracked whitespace and intended inventory after docs. Feature006 is software-
complete and ready for separately authorized final review and commit, remaining
uncommitted and unaccepted by the human. Phase1 remains incomplete. No staging,
commit, push, next-slice work, physical-hardware action or hardware acceptance claim.
Stopped after T030.

## 2026-10-08 — Feature 006 T029 Code-Only Incremental Graphify Update

Executed only T029. Read docs/agent_tooling.md and local Graphify skill/update
reference. Actual feature006 adds the service workspace/package and bootstrap,
HTTP security/projection, lifespan/composition and controlled server modules,
plus service dependency-contract coverage. These module additions and delivery
boundaries meet the structural trigger. Shared Core interfaces and completed
001–005 source/contracts remain unchanged; this is not a planning-only update.

Verified installed Graphify0.9.48 and existing interpreter/graph/manifest. Read-only
AST incremental preflight:146 files/~224416 words,66 code/80 documents,13 changed
code sources, no deletions or sensitive exclusions. No pending change queue could
expand the bounded input. Selected only the12 service package/source/test files
and root pyproject.toml; no documents dispatched for extraction.

Exactly one invocation used the existing installed updater:
graphify.watch._rebuild_code(Path('.'), changed_paths=changed_code,
force=False, block_on_lock=True). This preserves the existing graph and avoids
the plain CLI update's full code/Markdown rescan. No semantic extraction, API/LLM
calls, extra labeling command, second update or software test run.

Update succeeded, exit0:2891 nodes/8348 edges/123 communities, from2435/6370/117.
Report records zero input/output LLM tokens. Non-fatal diagnostics: root
pyproject.toml produced zero nodes and remains unstamped;36 community labels were
refreshed deterministically from their hubs. No retry or LLM relabeling followed.
Graphify backed up four curated outputs and regenerated JSON/HTML/report/manifest/
labels/signatures under ignored graphify-out/. No generated output was staged.

Read-only query confirms service security/composition, Core runtime and Basic edge
symbols; its1200-token budget truncates broader traversal, so targeted explain
run_service confirms server.py:L125 and extracted create_app/bind/server calls.
Manifest checks verify all12 service sources and unchanged semantic hashes for70
previous Markdown sources. A read-only incremental check reports only the known
zero-node root pyproject.toml remaining; no second update. graph.json was never
read directly. Existing ignore rules cover outputs/labels/signatures/backups, with
no tracked generated graph files. All146 repository files were unchanged by the
update before documentation bookkeeping.

Recorded evidence here, updated current status and synchronized minimal spec/plan/
quickstart/task metadata. T001–T029 checked; T030 remains unchecked. Verified
source/test/configuration hashes, task markers, documentation links, Resume Here
length and git diff --check. No production/test/dependency/contract/schema change,
Spec Kit, final full gate, commit, push, next slice or physical-hardware action.
Feature006 remains uncommitted; final validation/acceptance pending. Native/hardware
limits and prior software evidence retain their earlier meanings. Stopped T029.

## 2026-10-08 — Feature 006 T028 Development Status/History Reconciliation

Executed only T028. Replaced accumulated task-checkpoint narration in current
status with the actual service scope, baseline, progress, evidence and limitations.
Detailed completed records below remain intact and newest first. Reconciled task
bookkeeping and spec/plan/quickstart checkpoint metadata without changing contracts.

Verified main HEAD `ed11051015a4e56f81a4737bc55dad322f82f622` (Record feature 005
commit), and actual accepted feature-005 implementation commit
`2824c0dc3ecc63684f573b3b0a55c621e18e069f` (Implement observation runtime lifecycle).
Features001–005 remain committed/accepted; feature006 remains uncommitted, with
T001–T028 checked and T029–T030 unchecked. No final acceptance claim is made.

Current scope records the installable service, fixed per-UID private bootstrap/
credential, deterministic HTTP security, three lifecycle endpoints, one owning-loop
runtime, eight strongly owned pending mutations, controlled numeric loopback server/
signals and ordered joined cleanup. Basic/SQLite stay at the existing edge; no
Core/Profile/schema revision or backend-identity branching. Preserved conservative
uncertainty blocking, retained failed/cancelled journals and all workflow deferrals.

Distinguished the recorded T026 full1485-pass software gate from T027's14 unique
focused commands (1485 distinct cases across overlapping selections). Removed stale
current dependency claims: test-only httpx/httpcore/certifi were removed in T026;
all22 baseline versions remain unchanged. Current import coverage is five contracts,
with three unchanged Core boundaries. Earlier feature-005 Graphify maintenance is
explicitly historical; feature-006 structural assessment remains unexecuted here.

Native process/IPv6 evidence is macOS only. Windows service implementation is
deferred; Linux/Windows native and physical/electrical acceptance are unexecuted. The
existing feature-003 JournalFailure/context-manager limitation remains outside
features005/006. No unresolved feature-006 product decision is recorded.

Documentation verification: checked relative file links, task counts and completion
metadata, Resume Here length (under40 lines), baseline/commit references, unchanged
Core/completed001–005 diff and all73 snapshotted non-documentation file hashes;
git diff --check clean. Six documentation/checkpoint files changed this turn.
No software tests/static gate/build rerun for this documentation-only task. Prior
validation results above are recorded evidence, not fresh runs. No Spec Kit,
Graphify update, commit, push, next slice or physical-hardware action. Stopped T028.

## 2026-10-08 — Feature 006 T027 Focused Quickstart/Scope Validation GREEN

Executed only T027 using verification-before-completion. Extracted every focused
pytest command before the quickstart's final full-gate section; ran all14 unique
commands, covering repeated runtime-file commands once. Scope searches and focused
static/import checks also ran. No failure or source/test/config correction needed.

Commands through rtk proxy/env UV_CACHE_DIR=/private/tmp/dutchmate-feature006-uv-cache;
JUnit /private/tmp/dutchmate006-t027-<ID>.xml. All zero failures/errors/skips:

| ID | Focused pytest arguments | Passed |
|---|---|---|
|01| apps/service/tests/test_service_runtime.py -k test_t021 --tb=short |31|
|02| core/tests/contract/test_acquisition_lifecycle.py core/tests/unit/test_runtime_model.py core/tests/contract/test_observation_runtime.py core/tests/contract/test_observation_composition.py core/tests/integration/test_observation_runtime.py --tb=short |349|
|03| apps/service/tests/test_service_bootstrap.py --tb=short |90|
|04| apps/service/tests/test_service_http.py -k 'not t011' --tb=no |182|
|05| core/tests apps/service/tests/test_service_bootstrap.py --tb=short |1014|
|06| apps/service/tests/test_service_http.py apps/service/tests/test_service_projection.py -k 'not t011' --tb=short |293|
|07| apps/service/tests/test_service_http.py -k t011 --tb=short |44|
|08| apps/service/tests/test_service_http.py --tb=short |226|
|09| apps/service/tests/test_service_runtime.py --tb=short |96|
|10| core/tests/contract/test_observation_runtime.py core/tests/contract/test_observation_composition.py core/tests/integration/test_observation_runtime.py --tb=short |244|
|11| apps/service/tests/test_service_runtime.py -k test_t015 --tb=short |24|
|12| apps/service/tests/test_service_runtime.py -k test_t017 --tb=short |six|
|13| apps/service/tests/test_service_process.py --tb=short |38|
|14| apps/service/tests/test_service_bootstrap.py apps/service/tests/test_service_runtime.py --tb=short |186|

XML union by classname/name covers1485 distinct cases; overlapping counts are not
added. This is focused-command evidence, not a fresh default-suite/full-gate run.
The final full-gate block was deliberately not executed and remains T030.

Additional actual checks:

- uv run ruff check apps/service pyproject.toml:clean.
- uv run mypy .:51 files clean; uv run lint-imports:five kept/zero broken,
  49 files/125 dependencies. No contract/exemption change.
- Both exact quickstart scope searches return no matches (expected exit1);
  Core/source/package baseline diff and tracked graph output empty.
- Parsed committed/current lockfiles:22 baseline versions preserved; removed
  httpx/httpcore/certifi remain absent. No dependency change this turn.
- git diff --check and final checkpoint/task-marker/hash/whitespace audits clean.

All56 source/config hashes unchanged, including every hardware/bootstrap guard
and all production/test modules. Native macOS IPv6 loopback ran; zero platform/
IPv6 skips were counted as passes. Other-platform and physical-hardware acceptance
remain unexecuted. No physical device accessed, modified or validated.
Updated six checkpoint/status/history files only; formal T028 scope/baseline/limits
reconciliation remains separate and unexecuted. T027 checked, T028–T030 unchecked.
No T028 work, Spec Kit rerun, Graphify update (T029 pending), commit, push or next
Phase1 slice started. Stopped after T027.

## 2026-10-07 — Feature 006 T026 Complete Diff Review and Privacy Correction GREEN

Executed only T026. Reviewed governing Core §§13–19, active006 FR-001–030,
spec/plan/data model/contract and completed001–005 contracts against all intended
tracked/untracked changes. Source, test guards, dependencies/lockfile, installable
package, import boundaries and generated/runtime artifact inventory inspected.

| Requirement group | Review result |
|---|---|
| FR-001–008 | One persistent owning-loop runtime/worker; numeric selected family only; fixed per-UID safe bootstrap, bounded marker/private token; no import resources/override/fork/daemon manager |
| FR-009–014 | Exact raw Host/Origin/Sec-Fetch/Bearer ordering, query/Upgrade/path/method/body bounds before Profile/preparation; explicit fresh inputs; no test auth bypass |
| FR-015–020 | Existing Basic/SQLite edge, normalized closed projections, actual primary/cleanup facts, eight strongly owned operations with delivery-only cancellation and no history |
| FR-021–025 | Admission close, registered joins, runtime detach/immutable settlement, truthful uncertainty, cancellation-resistant cleanup and reverse partial-startup unwind; marker/fsync facts intact |
| FR-026 | One demonstrated framework telemetry diagnostic leak corrected below |
| FR-027–030 | Core/schema-v1/Profile/runtime/neutrality intact, physical guards preserved, import contracts unweakened and full software gate GREEN |
| Scope/package/artifacts | No CLI/retrieval/streaming/TX/Control/reconnect/handoff/catalogue/Enhanced/MCP/AI; only intended files, no credentials/journals/generated graph; unused dependency removed |

Privacy defect: installed FastAPI0.142.2 defaults inherit configured ambient
OpenTelemetry providers. Its native exception logger emitted a synthetic private
delivery error independently of the disabled Uvicorn loggers. An actual API ambient
provider-slot regression was observed RED with the input-bearing exception, then
GREEN after explicit tracing/metrics/logs/operation_spans/auto_configure=False in
app composition. Public FastAPI configuration only; no OTel SDK/exporter added.
Qualified the contract/research under the existing FR-026 input-log prohibition;
no Core rule/public wire contract or product decision changed.

Initial test probing patched only the API's re-exported getter and mistakenly saw
the internal no-op provider; an incomplete abstract logger also failed test setup.
Corrected the fixture to install the actual provider slot and implement the full
logger API before accepting RED evidence. The final regression is an actual
captured emission, not a configuration-string assertion or mock-only proof.

Dependency review: no Python test imports or uses httpx. Ran uv remove --dev httpx
--offline; uv updated pyproject.toml/uv.lock and removed httpx0.28.1/httpcore1.0.9/
certifi2026.7.22. No unrelated upgrade; all22 committed baseline versions preserved,
FastAPI/Uvicorn and their required transitives unchanged. Client/library bans kept.
Historical T002 installation records remain; active plan/testing inventory updated.

Fresh verification through rtk proxy/env UV_CACHE_DIR=/private/tmp/dutchmate-feature006-uv-cache:

- uv run pytest apps/service/tests/test_service_http.py -k test_t026 --tb=short:
  one correct RED → one GREEN; telemetry-red.xml/telemetry-green.xml under
  /private/tmp/dutchmate006-t026-*.
- uv run ruff check .:clean; uv run mypy .:51 files clean; uv run lint-imports:
  five kept/zero broken,49 files/125 dependencies.
- uv run pytest --tb=short --junitxml=/private/tmp/dutchmate006-t026-full.xml:
  1485 passed, zero failures/errors/skips (924 Core/90 bootstrap/226 HTTP/38 process/
  111 projection/96 runtime). Native loopback permitted with hardware tripwires.
- uv build --package dutchmate-service --out-dir /private/tmp/dutchmate006-t026-wheel
  --offline:sdist and wheel built successfully. Installed service/Core imports from
  /private/tmp succeed; no product working-directory assumption introduced.
- Core/source/package/001–005 artifact diff empty; forbidden service reader/
  hardware/identity searches no matches; no graph output tracked.
- git diff --check and final source/config/task/whitespace audits clean.

Changed app.py, one HTTP regression, pyproject.toml/uv.lock and eight review/
checkpoint/contract/status/history/research documents.52 other prior source/config
hashes unchanged. No other conformance defect found; all earlier tests remain GREEN.
T026 checked, T027–T030 unchecked; final acceptance remains pending. No T027 workflow,
Spec Kit rerun, Graphify update (T029 pending), commit, push or physical-hardware
access/validation. Native software evidence macOS only. Stopped after T026.

## 2026-10-07 — Feature 006 T025 US3 and Completed Regressions GREEN

Executed only T025 using verification-before-completion. Ran both US3 quickstart
commands and every completed-feature/Core regression selection named in the guide,
with hardware guards unchanged. No failure, production/test/configuration change
or correction needed; full feature review remains the separately authorized T026.

Fresh commands via rtk proxy/env UV_CACHE_DIR=/private/tmp/dutchmate-feature006-uv-cache;
JUnit /private/tmp/dutchmate006-t025-<id>.xml, all zero failures/errors/skips:

| ID | uv run command | Result |
|---|---|---|
| us3-process | pytest apps/service/tests/test_service_process.py --tb=short |38 passed |
| us3-runtime | pytest apps/service/tests/test_service_bootstrap.py apps/service/tests/test_service_runtime.py --tb=short |186 passed |
| core-bootstrap | pytest core/tests apps/service/tests/test_service_bootstrap.py --tb=short |1014 passed (924 Core/90 bootstrap) |
| core-005 | pytest core/tests/contract/test_acquisition_lifecycle.py core/tests/unit/test_runtime_model.py core/tests/contract/test_observation_runtime.py core/tests/contract/test_observation_composition.py core/tests/integration/test_observation_runtime.py --tb=short |349 passed |
| core-lifecycle | pytest core/tests/contract/test_observation_runtime.py core/tests/contract/test_observation_composition.py core/tests/integration/test_observation_runtime.py --tb=short |244 passed |

Selections overlap; counts are not added as unique cases. Complete001–005 Core
behavior remains GREEN, including normalized backend neutrality, exact RX/evidence,
Basic ownership/open/close, schema-v1 durable retrieval/retention, immutable Profile
semantics and005 lifecycle/failure/certainty. US3 verifies guarded duplicate/stale
owners, numeric IPv4/IPv6-only/no-fallback, h11 privacy, startup stop latching,
request/cleanup cancellation ownership and honest publication/physical facts.

Additional checks:

- uv run ruff check apps/service pyproject.toml and uv run ruff check .:clean.
- uv run mypy .:51 files clean; uv run lint-imports:five kept/zero broken,
  49 files/125 dependencies. No boundary weakened or exemption added.
- Both quickstart rg scope searches return no matches (expected exit1).
  git diff ed11051 -- core/src core/pyproject.toml and tracked graph output empty.
- Parsed committed/current uv.lock:all22 baseline locked versions unchanged.
- uv run pytest --tb=short --junitxml=/private/tmp/dutchmate006-t025-full.xml:
  1484 passed, zero failures/errors/skips, including all earlier regressions.
- git diff --check and final checkpoint whitespace/task-marker/hash audits clean.

All56 source/config hashes unchanged. Native process tests ran on macOS with
IPv6 available and zero skips; no unsupported-platform/IPv6 skip counted as a pass.
Linux/Windows service and electrical/hardware acceptance remain unexecuted.
Helper processes use temporary state/loopback sockets and independent physical
serial/discovery tripwires. No real DUT accessed, modified or validated.
Updated six checkpoint/status/history files and qualified the quickstart's old
1013 Core/bootstrap count as historical (current1014). T025 checked; T026–T030
unchecked. No T026 review, Spec Kit rerun, Graphify update (T029 pending), commit,
push or subsequent slice started. Stopped after T025.

## 2026-10-07 — Feature 006 T024 Failure/Publication/Process Exercise GREEN

Executed only T024 with test-driven-development and verification-before-completion.
Ran existing injected partial-startup/shutdown/cleanup cases and all real isolated
process cases. Added one parameterized function/nine OS publication cases to
test_service_runtime.py; no production, dependency/configuration or contract change.

The matrix targets false marker, credential and true marker at file fsync,
replacement and directory fsync. It retains actual private files, writes, atomic
replacement and bootstrap; only the selected failing operation is injected.
True-marker cases attach through actual Runtime/fake Basic/temporary SQLite and
prove final recorder/backend close once, no remaining read, credentials absent,
socket closed and account guard still held before replacement or fsync. Earlier
startup faults prove resources genuinely absent/closed without inventing a runtime.
Observed prior-marker preservation and restart eligibility/blocking remain explicit.

Successful true replacement followed by failed directory fsync leaves visible
true only after actual cleanup. The call raises teardown_incomplete and records
no successful confirmation; no rollback or durable-success claim. Other true
publication faults leave false and block restart. False after-replace publication
failure retains conservative blocking state; completed credential-failure unwind
may confirm empty startup resources and preserves the original bootstrap failure.
No production defect found; no correction needed. An initial probe expectation
incorrectly required a runtime for credential-stage failures; corrected it to
verify actual absence. It was a test setup issue, not production failure.

Fresh commands via rtk proxy/env UV_CACHE_DIR=/private/tmp/dutchmate-feature006-uv-cache:

- uv run pytest apps/service/tests/test_service_runtime.py -k test_t024 --tb=short
  --junitxml=/private/tmp/dutchmate006-t024-publication.xml:nine GREEN,87 deselected.
- Temporarily suppressing the launcher's marker-publication failure flag produces
  three intended RED failures for true file-fsync/replace/directory-fsync; restored
  production passes all nine. XML publication-mutation-red.xml; exact server bytes
  restored, with no permanent production mutation or weakened assertion.
- uv run pytest apps/service/tests/test_service_bootstrap.py
  apps/service/tests/test_service_runtime.py apps/service/tests/test_service_process.py
  --tb=short --junitxml=/private/tmp/dutchmate006-t024-failures-process.xml:
  224 GREEN (90 bootstrap/96 runtime/38 process), zero failures/errors/skips.
- uv run ruff check .:clean; uv run mypy .:51 files clean; uv run lint-imports:
  five kept/zero broken,49 files/125 dependencies; git diff --check clean.
- uv run pytest --tb=short --junitxml=/private/tmp/dutchmate006-t024-full.xml:
  1484 passed, zero failures/errors/skips.924 Core/90 bootstrap/225 HTTP/38 process/
  111 projection/96 runtime; earlier1475 remain GREEN. Native process execution
  uses only temporary state/loopback sockets and independent hardware tripwires.

All55 other prior source/config hashes unchanged. Removing T024 test/import
additions reconstructs the exact prior runtime source hash. Updated seven
checkpoint/status/history/research documents; T024 checked, T025–T030 unchecked,
Resume Here bounded. No T025 selections, Spec Kit rerun, Graphify update (T029
pending), commit, push or physical-hardware access/validation. Native macOS software
evidence only; unsupported-platform/other-platform/hardware acceptance not implied.
Stopped after T024.

## 2026-10-07 — Feature 006 T023 Joined Shutdown/Bootstrap Cleanup GREEN

Executed only T023 using test-driven-development, systematic-debugging and
verification-before-completion. Implemented the ordered pipeline in app.py,
server.py and bootstrap.py; no Core/package/dependency/001–005 contract change.
Final service acceptance and the separately authorized T024 exercise remain pending.

Admission closes before HTTP drain. Strongly owned shielded lifecycle tasks join
every registered operation, including attach not yet inside Core, before calling
runtime.detach on the owning loop. Repeated waiter cancellation cannot cancel
those tasks; hung startup/close retains the loop and account guard without timeout.
Final immutable RuntimeStatus crosses to bootstrap, with actual reason/primary/
cleanup/certainty facts preserved; no runtime/task/resource handle or cross-loop
status call. Stopping status projects inspectable facts while mutations remain503.

Confirm true only after owner_settled AND physical_release_confirmed AND
recorder_close_confirmed plus successful credential invalidation/socket cleanup.
Failed state with all cleanup confirmed is eligible; settled uncertainty remains
false/teardown_incomplete and blocks restart. Partial startup unwinds acquired
resources, confirms only this invocation's successfully published false marker,
and never rewrites a rejected pre-existing marker. Marker replacement/fsync facts
remain honest without rollback claims. No extra backend/journal close, reconnect,
cleanup retry, forced abandonment, takeover or deferred product behavior.

Initial eight app shutdown failures reproduced freshly before code. The pipeline
makes all31 T021 cases GREEN. A startup-lifespan stop initially revealed Uvicorn's
listener list is initialized only after startup; installed source confirmed the
listener-free drain needs an empty initialized list. Corrected within T023.
Two genuine cleanup defects were covered narrowly: credential release retried a
failed unlink, and HTTP-drain failure could still publish a clean marker after
successful Core cleanup. Sticky invalidation and a failed-drain flag correct them.
Each regression was observed RED → GREEN; stopping-status suppression was also
mutation-checked RED → GREEN. Original T021 assertions were not weakened.

Fresh commands via rtk proxy/env UV_CACHE_DIR=/private/tmp/dutchmate-feature006-uv-cache:

- uv run pytest apps/service/tests/test_service_runtime.py -k
  'test_t021_lifespan_shutdown or test_t021_shutdown_joins or test_t021_shutdown_keeps'
  --tb=no --junitxml=/private/tmp/dutchmate006-t023-before-red.xml:eight RED;
  same selection after implementation:eight GREEN (/private/tmp/dutchmate006-t023-app.xml).
- uv run pytest apps/service/tests/test_service_runtime.py -k test_t021:
  30 GREEN/one startup-stop failure, then all31 GREEN after the empty-list correction;
  full runtime file85 GREEN before the two new runtime regressions.
- uv run pytest apps/service/tests/test_service_bootstrap.py:90 GREEN including
  new no-retry regression; focused before-fix failure/after-fix GREEN recorded in
  /private/tmp/dutchmate006-t023-invalidation-red.xml and bootstrap.xml.
- uv run pytest apps/service/tests/test_service_process.py --tb=short
  --junitxml=/private/tmp/dutchmate006-t023-process.xml:38 GREEN, zero errors/skips.
  Includes native loopback IPv4/IPv6, token clean restart and startup signal latch.
- Focused status/HTTP-drain mutation/failure runs:one intended RED each → GREEN;
  XMLs /private/tmp/dutchmate006-t023-status* and http-drain-*.
- uv run ruff check .:clean; uv run mypy .:51 files clean; uv run lint-imports:
  five kept/zero broken,49 files/125 dependencies; git diff --check clean.
- uv run pytest --tb=short --junitxml=/private/tmp/dutchmate006-t023-full.xml:
  first1474 GREEN, then fresh1475 GREEN after the failed-HTTP-drain correction,
  zero failures/errors/skips. Final breakdown:924 Core,90 bootstrap,225 HTTP,
  38 process,111 projection and87 runtime. No watchdog needed; the T022 block resolves.

Changed three service production modules and two focused test files only, plus
seven checkpoint/status/history/research documents.51 other prior source/config
hashes unchanged; Core/package/dependencies/lockfile and earlier HTTP/process/
projection test files unchanged. Task23 checked; T024–T030 unchecked. Resume Here
remains bounded. No T024 exercise, Spec Kit rerun, Graphify update (T029 pending),
commit, push or physical-hardware access/validation. Native software evidence is
macOS only; Linux/Windows service and electrical acceptance unexecuted. Stopped T023.

## 2026-10-07 — Feature 006 T022 Controlled Listener/Signals Delivered

Executed only T022 using test-driven-development, systematic-debugging for exposed
helper failures, and verification-before-completion. Added server.py; app.py gains
only a private monotonic stop latch, admission checks and conservative settlement
handoff. No registry/runtime join, physical/recorder certainty inspection or true
marker publication was implemented. T023 remains required for joined shutdown.

Verified installed Uvicorn0.54.0 Config/Server/LifespanOn and Python3.14 Runner
source. One controlled worker/main-thread asyncio loop uses h11/lifespan-on,
numeric IPv4/default or explicit V6ONLY IPv6, no reload/WS/proxy trust/access logs.
No import-time app/runtime/listener/bootstrap or external launch overrides.
The launcher owns coalesced SIGINT/SIGTERM handlers before directories/lock through
guard disposal; no force_exit or signal replay. A checked lifespan retains actual
Uvicorn startup/protocol/drain machinery and rejects later TCP readiness after a
startup stop. All three Uvicorn input loggers disabled with propagationFalse.
Known unsettled work keeps the loop/guard alive. Settled interim shutdown retains
false marker/reports teardown_incomplete; no complete service acceptance claim.

Fresh RED before production: process34 expected missing-server failures/one safety
pass, JUnit /private/tmp/dutchmate006-t022-before-red.xml. Two dormant test-helper
defects surfaced once the missing module existed: os.mkdir's mode= keyword was
not forwarded; a signal.signal mock failed to reflect installed handlers through
getsignal, allowing Runner to substitute its cancellation handler. Reproduced
with input-free diagnostics, corrected only those external adapter probes and added
focused regressions. Six new cases cover fresh bootstrap/context/stop admission/
signal-probe behavior. Bootstrap-keyword mutation:one intended RED then GREEN;
stop-latch mutation:two RED then GREEN; signal probe:one RED then GREEN. No test
acceptance assertion weakened. Security/route/body validation still precedes service
admission and Profile/preparation; an initial extra body-before-stop expectation
was corrected to that governing order before final verification.

Commands via rtk proxy/env UV_CACHE_DIR=/private/tmp/dutchmate-feature006-uv-cache:

- uv run pytest apps/service/tests/test_service_process.py --tb=short
  --junitxml=/private/tmp/dutchmate006-t022-process.xml:37 passed/one expected T023
  failure at clean marker publication, zero errors/skips. Actual isolated loopback
  IPv4/IPv6-only, unavailable IPv6/occupied-port no fallback, guard exclusion/stale
  safety, h11 fixed400 privacy and twelve startup signal cases verified. Sandbox
  escalation authorized loopback tests only; every helper blocks physical access.
- uv run pytest core/tests apps/service/tests/test_service_bootstrap.py
  apps/service/tests/test_service_projection.py --tb=short
  --junitxml=/private/tmp/dutchmate006-t022-base.xml:1124 passed.
- uv run pytest apps/service/tests/test_service_http.py
  apps/service/tests/test_service_runtime.py -k 'not test_t021' --tb=short
  --junitxml=/private/tmp/dutchmate006-t022-existing-delivery.xml:279 passed,
  31 deselected. Includes all original276 delivery/runtime cases and three new
  HTTP/signal regressions; original924 Core/89 bootstrap/111 projection remain GREEN.
- uv run pytest apps/service/tests/test_service_runtime.py -k
  'test_t021_lifespan_shutdown or test_t021_shutdown_joins or test_t021_shutdown_keeps'
  --tb=no --junitxml=/private/tmp/dutchmate006-t022-app-pending.xml:
  eight expected app join/detach RED failures,77 deselected, zero errors/skips.
- Six new focused cases GREEN; mutation/probe XMLs under /private/tmp/dutchmate006-t022-*.
- uv run ruff check .:clean; uv run mypy .:51 files clean; uv run lint-imports:
  five kept/zero broken,49 files/125 dependencies; git diff --check clean.

Full required pytest was attempted, not omitted or claimed GREEN. The isolated
test-tool supervisor ran `python -m pytest -vv --tb=short` with1472 collected;
after the signal probe correction it blocked at
test_t021_launcher_closes_admission_before_draining_existing_http_delivery, where
the active run has not been joined. A30-second watchdog killed only that isolated
hardware-blocked test process group and exited124. Log:
/private/tmp/dutchmate006-t022-full.log. No completed summary/JUnit result; remaining
launcher shutdown/failure cases unexecuted, not passed. An earlier attempt exposed
the signal mock defect and then blocked at the following active uncertainty case.
This is test supervision, not a production lifecycle timeout/forced abandonment.

Changed source/tests:server.py, app.py, test_service_http.py, test_service_process.py
and the signal probe in test_service_runtime.py.51 other prior source/config hashes
unchanged; Core/package/dependencies/lockfile unchanged. Reconciled seven checkpoint
documents including actual dependency API research. T022 checked, T023–T030
unchecked; no T023 implementation. Graphify assessment/update remains T029.
No Spec Kit rerun, commit, push, physical-hardware access or hardware validation.
Native loopback/bootstrap evidence is macOS software evidence only. Stopped T022.

## 2026-10-07 — Feature 006 T021 Shutdown/Startup Contracts RED

Executed only T021 using test-driven-development and verification-before-completion.
Added ten functions/31 cases to apps/service/tests/test_service_runtime.py; no
production, previous test behavior, dependency/configuration or contract change.

Eight cases execute actual authenticated guarded ASGI lifespan with one real
owning-loop ObservationRuntime, existing fake Basic and temporary SQLite. They
expose missing automatic detach (one active-run/four cleanup-gate failures) and
premature shutdown completion (one queued attach/two startup-gate failures).
Assertions require final evidence before recorder close, registered work joined
before detach, no attach_cancelled substitution, hung work kept pending through
repeated lifecycle cancellation and the original unconfirmed ownership guard.
The test-only fallback releases fake gates and joins real Core cleanup AFTER
the failing assertions; it never cancels a service operation or attests cleanup.

Twenty-three cases target the planned public run_service and are RED for absent
dutchmate_service.server. Their downstream launcher assertions are unexecuted.
The harness preserves real bootstrap/app/Core/Uvicorn lifecycle, replaces only
network operations, and delivers to installed signal callbacks without sending
signals to pytest. It checks admission before draining held HTTP delivery,
coalesced SIGINT/SIGTERM without force_exit, active/already-settled uncertainty
without cleanup retry/reset, failed-but-confirmed runtime cleanup, credential/
socket/marker cleanup errors, partial startup reverse unwinding and guard retention.
Startup stop is injected at directory/lock/marker/socket/token/lifespan. Immutable
settled snapshots permit bootstrap assertions after loop exit without cross-loop
runtime.status calls. No physical transport or actual TCP bind is used by T021.

Fresh commands via rtk proxy/env UV_CACHE_DIR=/private/tmp/dutchmate-feature006-uv-cache:

- uv run pytest apps/service/tests/test_service_runtime.py -k test_t021 --tb=short
  --junitxml=/private/tmp/dutchmate006-t021-red.xml:31 expected failures,53 deselected.
- uv run pytest core/tests apps/service/tests/test_service_bootstrap.py
  apps/service/tests/test_service_http.py apps/service/tests/test_service_projection.py
  --tb=short --junitxml=/private/tmp/dutchmate006-t021-earlier-base.xml:1347 passed.
- uv run pytest apps/service/tests/test_service_runtime.py -k 'not test_t021'
  --tb=short --junitxml=/private/tmp/dutchmate006-t021-earlier-runtime.xml:
  53 passed,31 deselected. No global task-name selector drops older Core cases.
- uv run pytest --tb=no --junitxml=/private/tmp/dutchmate006-t021-full.xml:
  65 expected failures/1401 passes, zero errors/skips. XML audit:34 unchanged T020
  missing-launcher failures and31 T021 failures; no unrelated failing case.
- uv run ruff check .:clean; uv run mypy .:50 files clean; uv run lint-imports:
  five kept/zero broken,43 files/114 dependencies; git diff --check clean.
- Source-hash audit:54 other source/config files unchanged. Removing only T021
  additions/imports reconstructs the exact SHA-256 of the prior runtime test file.

Corrected a misplaced new test block and local helper typing/import details before
final RED verification; no production fix or new product decision. Updated six
checkpoint documents; T021 checked, T022–T030 unchecked. App RED gates leave later
join/cancellation assertions unexecuted; launcher/hardware/software acceptance is
not claimed. Native execution remains macOS only. No T022 or later implementation,
Spec Kit rerun, Graphify update, commit, push or physical-hardware access/validation.
Stopped after T021.

## 2026-10-07 — Feature 006 T020 Isolated Process Contracts RED

Executed only T020 using test-driven-development and verification-before-completion.
Added apps/service/tests/test_service_process.py:35 cases, including34 contracts
against the planned public run_service entry point and one subprocess safety probe.
No production, existing test, dependency/configuration or completed contract change.

The tests cover controlled single-worker Uvicorn/h11/asyncio/lifespan settings,
unsupported external launch overrides, no import resources/post-lock fork/DNS/proxy
trust, default numeric IPv4 and explicit IPv6-only listener, unavailable IPv6 and
occupied-port rejection without fallback, per-UID exclusion across ports, stable
lock inode, stale/malformed/idle-crashed owners and no cleanup inference from death.
Credential scenarios use private file reads only: cached process token, safe modes,
no live rotation, removal and fresh eligible-incarnation rotation. Real h11 cases
expect its fixed input-free400 text/plain response, not invented application JSON;
supplied secrets/paths/body and pre-ASGI warnings cannot leak into supported logs.
Repeated SIGINT/SIGTERM are injected at directory/lock/marker/socket/token/lifespan
boundaries to assert latched stop, no later readiness and no force_exit.

The executable test helper substitutes only the isolated passwd account home and
observes actual bootstrap/runtime/Uvicorn/socket boundaries. It independently blocks
physical serial factories/discovery, Profile/run preparation, real-account bootstrap,
DNS and fork; parent pytest monkeypatches are not assumed to cross process boundaries.
Only temporary state/loopback sockets are permitted; harness timeout/kill applies
only to its own hardware-blocked children and is not production abandonment policy.
No actual credential enters argv/env/URL/audit output. Fixture tokens are synthetic.

Fresh commands via rtk proxy/env UV_CACHE_DIR=/private/tmp/dutchmate-feature006-uv-cache:

- uv run pytest apps/service/tests/test_service_process.py --tb=no
  --junitxml=/private/tmp/dutchmate006-t020-red.xml:34 expected failures/one pass.
- uv run pytest core/tests apps/service/tests/test_service_bootstrap.py
  apps/service/tests/test_service_http.py apps/service/tests/test_service_projection.py
  apps/service/tests/test_service_runtime.py --tb=short
  --junitxml=/private/tmp/dutchmate006-t020-earlier.xml:1400 passed.
- uv run pytest --tb=no --junitxml=/private/tmp/dutchmate006-t020-full.xml:
  34 expected failures/1401 passes, zero errors/skips. XML audit confirms every
  failure is ModuleNotFoundError for dutchmate_service.server, not a setup error.
- uv run ruff check .:clean; uv run mypy .:50 source files clean;
  uv run lint-imports:five kept/zero broken,43 files/114 dependencies.
- git diff --check and final untracked whitespace/task-marker/hash checks clean.

The first helper-only probe unnecessarily allocated a port and hit sandbox bind
denial; it now uses a fixed unused configuration value without opening a socket.
Corrected new helper typing/lint issues; no production defect or correction.
The safety probe runs successfully in a child, but all34 launcher tests stop at
the missing module: actual process/listener/h11/IPv6/startup acceptance remains
unexecuted, not passed or skipped. Native execution is macOS only.
All54 prior source/config hashes unchanged. Reconciled six checkpoint documents;
T020 checked, T021–T030 unchecked. No T021 or later behavior, Spec Kit rerun,
Graphify update, commit, push or physical-hardware access/validation. Stopped T020.

## 2026-10-07 — Feature 006 T019 US2 Quickstart and Feature-005 Regressions GREEN

Executed only T019 using verification-before-completion. Ran all unique US2
quickstart pytest commands plus the complete005 focused regression selection.
The repeated runtime-file command in the guide was covered by one fresh invocation;
subsets are intentionally overlapping and their counts are not added as distinct
tests. No production/test/config change or failure correction was needed.

Commands through rtk proxy/uv with
UV_CACHE_DIR=/private/tmp/dutchmate-feature006-uv-cache; all pytest selections have
zero failures/errors/skips and JUnit /private/tmp/dutchmate006-t019-<id>.xml:

| ID | uv run command | Result |
|---|---|---|
| http-t011 | pytest apps/service/tests/test_service_http.py -k t011 --tb=short |44 passed,179 deselected |
| http | pytest apps/service/tests/test_service_http.py --tb=short |223 passed |
| runtime | pytest apps/service/tests/test_service_runtime.py --tb=short |53 passed |
| core-us2 | pytest core/tests/contract/test_observation_runtime.py core/tests/contract/test_observation_composition.py core/tests/integration/test_observation_runtime.py --tb=short |244 passed |
| failure | pytest apps/service/tests/test_service_runtime.py -k test_t015 --tb=short |24 passed,29 deselected |
| binary | pytest apps/service/tests/test_service_runtime.py -k test_t017 --tb=short |six passed,47 deselected |
| core-005 | pytest core/tests/contract/test_acquisition_lifecycle.py core/tests/unit/test_runtime_model.py core/tests/contract/test_observation_runtime.py core/tests/contract/test_observation_composition.py core/tests/integration/test_observation_runtime.py --tb=short |349 passed |

The scenarios verify normal lifecycle/status mapping, busy Profile-read-only
semantics, capacity before Profile I/O, admitted task ownership independent of
delivery, cancellation/failure/certainty separation, kept journals, exact ambient
binary bytes, final evidence-before-recorder-close and existing bounded readback.
Identical applicable normalized-fixture assertions preserve reported clock domains,
scoped loss, capabilities and opaque provenance. No HTTP retrieval or production
Enhanced behavior is implied; fixture results prove software neutrality only.

Additional fresh checks:

- uv run ruff check apps/service pyproject.toml and uv run ruff check .: clean.
- uv run mypy .:49 source files clean.
- uv run lint-imports: five kept/zero broken,43 files/114 dependencies.
- Quickstart rg searches for Core delivery imports and forbidden service hardware/
  private Acquisition decoding/backend identity matches: no matches (expected exit1).
- git diff ed11051 -- core/src core/pyproject.toml: empty.
- git ls-files graphify-out: empty; no generated graph output tracked.
- Reviewed pyproject.toml/uv.lock diff: intended service workspace/test dependencies
  and two added import boundaries only; no new dependency changes in this task.
  Parsed committed/current lockfiles: all22 baseline package versions unchanged;
  additions are service/FastAPI/Uvicorn/httpx and required transitives.
- uv run pytest --tb=short --junitxml=/private/tmp/dutchmate006-t019-full.xml:
  1400 passed, zero failures/errors/skips:924 completed Core regressions,
  89 bootstrap,223 HTTP,111 projection/input and53 lifetime/failure/integration cases.
- git diff --check and final untracked whitespace/task-marker/source-hash checks clean.

All54 source/config hashes unchanged, including every production/test/guard module,
dependencies, lockfile and architecture contracts. Reconciled task/spec/plan/quickstart
and status/history checkpoint metadata; T019 checked, T020–T030 unchecked. Corrected
the quickstart's historical T014 runtime-file count to distinguish23 then/53 now.
US2 software checkpoint is verified, not complete service/process/listener/shutdown
or hardware acceptance. No T020 process tests, sockets or launcher code added; no
Spec Kit rerun, Graphify update (T029 assessment pending), commit, push or physical-
hardware access/validation. Native bootstrap remains macOS-only; no actual h11/
listener/process/other-platform/hardware acceptance. Stopped after T019.

## 2026-10-07 — Feature 006 T018 Scoped Consumer/Architecture Review, No Correction

Executed only T018 using source inspection, focused searches and
verification-before-completion. Reviewed current service source/runtime tests
against Core §17.4/service boundaries, active006 spec/plan/contract and completed
003–005 contracts. No demonstrated defect or governing conflict found; no production,
test, dependency/configuration or completed contract change required.

Context: one real runtime is constructed in guarded async lifespan, bound to its
serving loop/thread. Async status/mutation routes call the Core guard before
Profile/preparation; service operation tasks/callbacks execute on that loop. No
service threadpool dispatch, sync runtime endpoint or rebinding. Existing foreign-
loop/thread regressions prove rejection leaves resources/ownership untouched.

Ownership/handles: service invokes only the existing Basic composition edge and
runtime.detach; it opens no DUT backend/stream itself. HTTP receive/disconnect
observation is delivery traffic, not another physical reader. Bootstrap os.open/
read/close handles only private account files/lock. Status returns explicit closed
immutable fields, not tasks, backends, serial handles or recorders. Test-only runtime
spies/fake serial fields/weak task probes are not public service handles; journal
reopen is confined to test readback after confirmed terminal cleanup.

Snapshot/neutrality: http.py consumes AcquisitionSnapshot directly, separates actual
primary failure, close_failed, trigger, committed provenance and release certainty,
and never inspects legacy Acquisition.failure/_consumer_task/_close_task/_generation.
Normalized loss variants and generic provenance rendering are not backend identity
decoding. Basic naming appears only at the accepted composition edge/tests; shared
delivery has no backend-kind branch or host-only time/loss/capability assumption.
Both existing normalized shapes run identical applicable lifecycle/status tests,
preserving their reported facts; no Enhanced production behavior introduced.

Compatibility: git diff ed11051 -- core/tests core/src core/pyproject.toml and
specs/003-durable-evidence-journal specs/004-dut-profile-policy
specs/005-observation-runtime is empty. Existing schema-v1/sequence/retention/
retrieval, explicit immutable Profile-v1, in-memory association/fresh destinations,
005 lifecycle/cancellation/cleanup and no automatic reconnect remain authoritative.
No forbidden service source search matches for threadpool/physical factory/events/
legacy-private Acquisition access/backend identity equality. Other search matches
were inspected as bootstrap descriptors, normalized facts or test-only dependencies.

Fresh commands through rtk proxy/uv with
UV_CACHE_DIR=/private/tmp/dutchmate-feature006-uv-cache:

- uv run pytest apps/service/tests/test_service_runtime.py --tb=short:
  53 passed (/private/tmp/dutchmate006-t018-runtime.xml).
- uv run pytest apps/service/tests/test_service_http.py -k 'foreign or wrong_context'
  --tb=short: six passed,217 deselected (/private/tmp/dutchmate006-t018-context.xml).
- uv run ruff check .: clean; mypy .:49 source files clean.
- uv run lint-imports: five kept/zero broken,43 files/114 dependencies.
- uv run pytest --tb=short --junitxml=/private/tmp/dutchmate006-t018-full.xml:
  1400 passed, zero failures/errors/skips:924 completed Core regressions,
  89 bootstrap,223 HTTP,111 projection/input and53 lifetime/failure/integration cases.
- git diff --check and final untracked whitespace/task-marker/source-hash checks clean.

All54 existing source/config hashes unchanged. Updated only task/spec/plan/quickstart
checkpoint metadata and development status/history; T018 checked, T019–T030 unchecked.
No T019 work, Spec Kit rerun, Graphify update (known localized consumer review;
feature structural assessment remains T029), commit, push or physical-hardware action/
validation. Native bootstrap remains macOS-only software testing; no actual
listener/h11/process/other-platform/hardware or complete service acceptance.
Stopped after T018 with no correction required.

## 2026-10-07 — Feature 006 T017 HTTP Binary Capture/Readback and Neutrality GREEN

Executed only T017 with focused regression/mutation verification and
verification-before-completion. Added two parameterized functions/six cases plus
test-only durable commit/readback helpers in test_service_runtime.py. Actual
FastAPI/ASGI security/bootstrap/runtime/Acquisition and temporary SQLite remain
in use. No production code, completed Core contract or existing backend fixture
implementation was changed. No actual listener, h11 or physical serial used.

Two Basic cases use the completed attach_basic_observation edge and real Basic
adapter with the existing strict serial dependency. Its scripted read gates are
configured before open/first read. All256 byte values plus NUL/invalid UTF-8 and
ambient chunks commit between requests; one case loses attach response delivery
after active publication. Subsequent status does not change the run or require a
reader, and detach preserves immutable Profile/run/session/provenance facts.
Journal-assigned sequences0..4, exact payloads, one active read, one close and
final segment commit before recorder close are independently asserted.

Four normalized cases parameterize the same test over existing Basic/Enhanced-
shaped fixture factories and detach/autonomous-disconnect endings. Test preparation
creates the real journal before fixture construction/open, resolves the unchanged
Basic Profile and invokes actual runtime.attach. It supplies a generic opaque
schema37 provenance envelope with bool/null/int/NUL-Unicode fields, preserving
reported capabilities/timestamp domains/loss unchanged. No shared backend identity
branch or production Enhanced Profile selection/behavior is added. HTTP status
while attaching has known session but no fabricated descriptor/committed provenance;
busy preparation is rejected without a second journal/fixture. Active/terminal
facts, raw domain/timestamp values, cause/stop intent, stable repeated status/detach,
one reader/open/close and no reconnect have identical applicable assertions.

After confirmed terminal cleanup, tests call the existing real journal.open API,
captured before fixture no-reopen guards. That capture is used only by test readback,
never service composition. Two-record pages preserve fixed snapshot bounds,
continuation/truncation semantics and exact committed records/payload/provenance;
no retention gap is fabricated. No HTTP retrieval/stream/Monitor surface added.

All six cases passed against existing production; no genuine defect found.
Three temporary process-local mutations independently prove the assertions: RX
payload transformation causes six intended failures; forcing host/nanosecond clock
facts causes two Enhanced-shaped failures/two Basic controls pass; forcing loss
unobservable causes the same two failures/two controls pass. No production file
edited by diagnostics, authentication bypass or physical action.

Commands through rtk proxy/uv with
UV_CACHE_DIR=/private/tmp/dutchmate-feature006-uv-cache:

- uv run pytest apps/service/tests/test_service_runtime.py -k test_t017 --tb=short:
  six passed,47 deselected (/private/tmp/dutchmate006-t017-focused.xml).
- Diagnostic /private/tmp/dutchmate_t017_mutations.py bytes/domain/loss:
  six/two/two intended failures, zero errors/skips; JUnit
  /private/tmp/dutchmate006-t017-mutation-*.xml.
- uv run pytest apps/service/tests/test_service_runtime.py --tb=short:
  53 passed (/private/tmp/dutchmate006-t017-runtime.xml).
- uv run ruff check .: clean; mypy .:49 source files clean.
- uv run lint-imports: five kept/zero broken,43 files/114 dependencies.
- uv run pytest --tb=short --junitxml=/private/tmp/dutchmate006-t017-full.xml:
  1400 passed, zero failures/errors/skips:924 completed Core regressions,
  89 bootstrap,223 HTTP,111 projection/input and53 lifetime/failure/integration cases.
- git diff --check and final untracked whitespace/task-marker/source-hash/AST checks clean.

Original runtime test/function/class ASTs unchanged;53 other source/config hashes
unchanged, including all production, existing Core fixtures, other tests/guards,
dependencies, lockfile and architecture contracts. Reconciled task/spec/plan/quickstart
and status/history metadata; T017 checked, T018–T030 unchecked. No T018 review or
correction, Spec Kit rerun, Graphify update (T029 assessment pending), commit, push
or physical-hardware access/validation. Native bootstrap remains macOS-only;
software Enhanced-shaped neutrality is not Enhanced hardware/production support.
Controlled process/listener/shutdown and complete service acceptance remain later
work. Stopped after T017.

## 2026-10-07 — Feature 006 T016 Integration Review, No Correction Required

Executed only T016 using verification-before-completion. Reviewed T015's failure/
lifetime outcomes and mutation evidence against the active service spec/plan/
contract, Core service boundary and feature-005 failure/certainty matrix. Inspected
app.py ownership/normalization and http.py snapshot/issue/status projection.
No demonstrated service wrapper/failure/projection defect or governing contract
conflict was found. T015's EIO injector and diagnostic-hook problems were test/tool
corrections, not evidence of a production defect; neither requires further changes.

The current service projects actual primary_failure_kind, close_failed, trigger,
committed provenance and cleanup certainty independently. Failed RuntimeStatus
remains200; normalized rejections preserve categories without raw input/cause.
Owned operations survive delivery loss, retain no completed history and leave Core
cause/stop/cleanup semantics authoritative. Failed-create/open/append/close artifacts
remain retained without reopen/retry or invented cleanup confirmation. No service
correction, Core/schema/Profile/Acquisition revision or additional test was warranted.

Fresh commands through rtk proxy/uv with
UV_CACHE_DIR=/private/tmp/dutchmate-feature006-uv-cache:

- uv run pytest apps/service/tests/test_service_runtime.py -k test_t015 --tb=short:
  24 passed,23 deselected, zero errors/skips
  (/private/tmp/dutchmate006-t016-focused.xml).
- uv run ruff check .: clean; mypy .:49 source files clean.
- uv run lint-imports: five kept/zero broken,43 files/114 dependencies.
- uv run pytest --tb=short --junitxml=/private/tmp/dutchmate006-t016-full.xml:
  1394 passed, zero failures/errors/skips:924 completed Core regressions,
  89 bootstrap,223 HTTP,111 projection/input and47 lifetime/failure cases.
- git diff --check and final untracked whitespace/task-marker/source-hash checks clean.

All54 existing source/config hashes unchanged, including all production, tests,
guards, dependencies, lockfile and architecture contracts. Updated only task/spec/
plan/quickstart checkpoint metadata and development status/history; T016 checked,
T017–T030 unchecked. No Spec Kit rerun, Graphify update (documentation-only step;
feature structural assessment remains T029), commit, push, hardware access/validation
or T017 work. Native bootstrap remains macOS-only software testing; no actual
listener/h11/process/other-platform/hardware or complete service acceptance.
Stopped after T016 with no production/test change required.

## 2026-10-07 — Feature 006 T015 Failure/Lifetime Regressions GREEN

Executed only T015 using focused regression/TDD verification and systematic-debugging
for the initial disconnect fixture. Added six parameterized functions/24 cases plus
test-only journal hooks/stable-terminal assertions to test_service_runtime.py.
No production code, underlying Core behavior or T016 correction was changed.
Real private bootstrap/auth/ASGI/runtime/Profile/Basic/SQLite remain in use, with
temporary files and the existing strict fake serial dependency. Physical/discovery
and real-account bootstrap guards remain active; no permissive security path.

Preparation matrix covers an unknown failed-create artifact without inventing a
session or recorder certainty, existing destination unchanged, and constructor
failure after real create with successful/failed recorder close. Failed-open cases
preserve unconfirmed physical release independently of recorder closure/close_failed.
Initial append failures retain known descriptor without fabricated committed
provenance; backend/recorder cleanup combinations remain ordered and independent.

Active/final matrix covers RX recording failure, transport failure, transport primary
followed by failed final append, clean autonomous disconnect, disconnect followed by
append plus both cleanup failures, and failed final append during explicit detach.
Disconnect retains terminal cause precedence despite primary/cleanup failure;
earlier transport primary survives subsequent recording failure. Actual journal
assigned sequences/committed boundaries remain honest, with no fabricated final
record. Close-only combinations have no primary acquisition failure even though
legacy Acquisition may encode transport failure. Failed journals/session identities
remain; raw file images, status and detach repeat unchanged without second cleanup,
reopen or automatic reconnect. Uncertain cleanup blocks a new fresh destination.

Three repeated HTTP cancellations during gated failed open/initial append preserve
Core stop intent none and eventual startup failure independently of lost delivery.
Only HTTP tasks are cancelled; test gates release/join Core work before fixture
cleanup. Backend/recorder close attempts are counted once; no extra physical reader
or service evidence API. Journal faults occur at the real adapter boundary and
post-close failure still supplies no positive recorder certainty.

Initial run:22 passes/two failures caused by using errno.EIO as fake device loss.
The existing Basic adapter classifies ENODEV/ENXIO as device loss; EIO is transport
failure. Inspected that code/contract and corrected the injector to ENODEV, retaining
the intended disconnect assertions. Fresh focused matrix then passed all24. No
genuine production defect found. Existing implementation already satisfied the
new regressions, so no artificial product failure or T016 work was introduced.

Three temporary process-local delivery-projector mutations verify independent
assertions without editing production files: close_failed relabelled as primary
transport (two intended failures/two controls pass); failed-open physical release
and admissibility optimistically true (two intended failures); disconnect cause
relabelled acquisition_failure after append/cleanup faults (one intended failure/
one control pass). Initial diagnostic plugin used the wrong pytest hook phase;
corrected before recording mutation evidence. Setup errors are not counted as RED.
Fresh normal runs have no diagnostic mutation/plugin active.

Commands through rtk proxy/uv with
UV_CACHE_DIR=/private/tmp/dutchmate-feature006-uv-cache:

- uv run pytest apps/service/tests/test_service_runtime.py -k test_t015 --tb=short:
  24 passed,23 deselected (/private/tmp/dutchmate006-t015-focused.xml).
- Diagnostic mutation script /private/tmp/dutchmate_t015_mutations.py primary,
  certainty and cause: respectively two/two/one intended assertion failures,
  zero errors/skips; JUnit /private/tmp/dutchmate006-t015-mutation-*.xml.
- uv run pytest apps/service/tests/test_service_runtime.py --tb=short:
  47 passed (/private/tmp/dutchmate006-t015-runtime.xml).
- uv run ruff check .: clean; mypy .:49 source files clean.
- uv run lint-imports: five kept/zero broken,43 files/114 dependencies.
- uv run pytest --tb=short --junitxml=/private/tmp/dutchmate006-t015-full.xml:
  1394 passed, zero failures/errors/skips:924 completed Core regressions,
  89 bootstrap,223 HTTP,111 projection/input and47 lifetime/failure cases.
- git diff --check and final untracked whitespace/task-marker/source-hash/AST checks clean.

All original runtime test/function/class ASTs unchanged;53 other prior source/config
hashes unchanged, including every production module, other tests/guards, Core,
dependencies, lockfile and architecture contracts. Reconciled task/spec/plan/quickstart
and status/history metadata; T015 checked, T016–T030 unchecked. No Spec Kit rerun,
Graphify update (T029 assessment pending), commit, push or physical-hardware action/
validation. Native bootstrap remains macOS-only; no listener/h11/process/other-platform/
hardware or full service acceptance. Stopped after T015; T016 not executed.

## 2026-10-07 — Feature 006 T014 Bounded Operation Ownership GREEN

Executed only T014 using TDD, systematic-debugging for exception retention and
verification-before-completion. Fresh original lifetime baseline:12 expected
ownership failures/nine passes before production work
(/private/tmp/dutchmate006-t014-red.xml). No T015 failure behavior was implemented.

Updated app.py with a private set of at most eight pending service operation tasks.
After existing security/body checks, pending caller cancellation submits nothing;
ready/capacity checks, task creation/strong registration and completion callback
installation are atomic before yielding or Profile I/O. Already done entries are
pruned before capacity decisions. Each task immediately invokes the existing Basic
edge or runtime.detach when scheduled. No queue, replay, public job or second RX path.

HTTP delivery waits on shielded work and a separate receive/disconnect observer.
Delivery cancellation/disconnect/send failure never cancels the registered task or
signals005 attach_cancelled. Even work not yet inside Core remains owned. Only the
delivery observer and outer shield future are cancelled during delivery cleanup;
service tasks retain no direct cancellation path. Completion consumes outcomes,
removes entries and releases task/input/result references. Core stop intent,
primary/cleanup/certainty and all underlying contracts remain authoritative.

First implementation:20 lifetime passes/one failure;223 HTTP tests passed. The
lost-response exception case retained a completed task and triggered a loop report.
Temporary diagnostics inspected reference types only (no credential/input values),
identifying a loop exception context referencing the task. Inspected the installed
Python3.14 asyncio.shield implementation: cancelling its outer future installs
_log_on_exception on inner work, which reports a later exception despite registry
consumption. No logger bypass, private callback mutation or weakened assertion used.
Normalized Core results/errors inside the owned task to closed bounded HTTP responses
before shielding; late normalized failures no longer raise into shield. The original
exception consumption/weak-reference test then passed; all21 originals unchanged.

Added one parameterized regression/two cases in test_service_runtime.py: an
observed disconnect while attach/detach is registered but still before Core invocation
must finish delivery with zero response/preparation and leave the owned operation
pending/uncancelled. Releasing the test gate then settles it normally with unchanged
stop intent. Temporarily disabling disconnect observation produced two expected
failures; restored code made both GREEN
(/private/tmp/dutchmate006-t014-disconnect-red.xml). No direct service-task cancellation.

Fresh commands through rtk proxy/uv with
UV_CACHE_DIR=/private/tmp/dutchmate-feature006-uv-cache:

- uv run pytest apps/service/tests/test_service_runtime.py --tb=short:
  23 passed, zero failures/errors/skips (/private/tmp/dutchmate006-t014-green.xml).
- uv run pytest apps/service/tests/test_service_http.py --tb=short:223 passed
  (/private/tmp/dutchmate006-t014-http.xml); full final run reverified after correction.
- uv run ruff check .: clean; mypy .:49 source files clean.
- uv run lint-imports: five kept/zero broken,43 files/114 dependencies.
- uv run pytest --tb=short --junitxml=/private/tmp/dutchmate006-t014-full.xml:
  1370 passed, zero failures/errors/skips:924 completed Core regressions,
  89 bootstrap,223 HTTP,111 projection/input and23 lifetime cases.
- git diff --check and final untracked whitespace/task-marker/source-hash/AST checks clean.

Only app.py and the new two-case runtime regression change executable code. All
original runtime test/function/class ASTs remain unchanged;52 other source/config
hashes unchanged, including all Core, HTTP helpers/tests, bootstrap/guards,
dependencies, lockfile and architecture contracts. Reconciled task/spec/plan/quickstart
and status/history metadata; T014 checked, T015–T030 unchecked. No Spec Kit rerun,
Graphify update (T029 assessment pending), commit, push or physical-hardware
access/validation. Native bootstrap is macOS-only software testing; no controlled
listener/h11/process/other-platform/hardware acceptance or full feature acceptance.
Startup/shutdown joining remains T022/T023. Stopped after T014.

## 2026-10-07 — Feature 006 T013 Normal HTTP Lifecycle Wiring GREEN

Executed only T013 using TDD, systematic-debugging for the failed-open assertion,
and verification-before-completion. Fresh T011 baseline:33 missing-route failures/
11 validation passes before production work (/private/tmp/dutchmate006-t013-red.xml).
Added only normal async POST attach/detach handlers in service app.py. Existing
HTTP validators read bounded replayed body; no FastAPI input-echo model or resource
probe. Core loop/thread guard precedes Profile/preparation; one persistent runtime
calls existing attach_basic_observation/runtime.detach and projects each returned
immutable status, including failed/terminal facts, directly as200. Existing response
helpers preserve Profile/runtime/wrapper rejection categories without raw inputs.
Outer auth/Host/Origin gate and docs/redirect/debug settings remain intact.

Basic/SQLite construction stays at the completed composition edge, with bounded
Profile read before busy admission and no journal/backend preparation when rejected.
No new adapter/factory/evidence API, backend branch, extra RX reader, Core/schema/
Profile/Acquisition change, request registry/shielding, server or shutdown work.

First focused run had45 passes/one failure: the T011 failed-open fixture assumed
attach_admissible true after a simulated open exception. Feature-005 contract §7
failure table explicitly says Backend.open failure leaves physical release
unconfirmed; Acquisition sets that fact false before open, and shared runtime
projects it unchanged. HTTP also projected correctly. Corrected the test's false
assumption, asserting physical=false, recorder=true, owner settled, primary transport
failure, close_failed=false and admissibility=false. No production inference or
uncertainty reset added. Existing retained-journal and subsequent status checks pass.

Reconciled two T009 historical absent-endpoint tests as enabled-route authentication
tripwires: missing Bearer returns401 before receive/body/Profile/preparation. T013's
new surface supersedes their old404 checkpoint. Other HTTP test/function/class ASTs
are unchanged except the failed-open regression above;52 other prior source/config
hashes unchanged, including HTTP helpers, all Core/T012 tests, dependencies and
architecture contracts. Only app.py and test_service_http.py changed in executable code.

Fresh commands through rtk proxy/uv with
UV_CACHE_DIR=/private/tmp/dutchmate-feature006-uv-cache:

- uv run pytest apps/service/tests/test_service_http.py --tb=short:223 passed,
  zero errors/skips (/private/tmp/dutchmate006-t013-http-green.xml).
  All44 T011 cases now GREEN, after the33 RED baseline; two migrated auth cases GREEN.
- uv run pytest apps/service/tests/test_service_runtime.py --tb=short:
  12 expected T014-scope failures/nine passes
  (/private/tmp/dutchmate006-t013-lifetime-red.xml).
- uv run ruff check .: clean; mypy .:49 files clean.
- uv run lint-imports: five kept/zero broken,43 files/113 dependencies; no weakening.
- uv run pytest --tb=no --junitxml=/private/tmp/dutchmate006-t013-full.xml:
  12 expected T014-scope failures/1356 passes, zero errors/skips (1368 cases).
  All924 completed Core regressions,89 bootstrap,223 HTTP and111 projection cases pass.
- git diff --check and final new-file whitespace/task-marker/source-hash/AST checks clean.

Remaining failures are exactly T012's pending-cancel attach/detach pair, registration/
strong ownership pair, startup/close delivery-cancellation four cases, mixed/attach
capacity pair, and completed-reference consumption pair. Normal direct-await wiring
exposes two previously masked pending-cancel failures; those pending requests can
invoke Core. Four active-publication delivery cases and sibling-error isolation now
pass. Twelve ownership assertions deliberately remain RED rather than implementing
T014 early. No complete service/cancellation/capacity/shutdown acceptance claimed.

Reconciled task/spec/plan/quickstart/status/history metadata; T013 checked,
T014–T030 unchecked. No Spec Kit rerun, Graphify update (T029 assessment pending),
commit, push or physical-hardware access/validation. Native bootstrap is macOS-only
software testing; peers are simulated, no listener/h11/other-platform/hardware
acceptance. Stopped after T013.

## 2026-10-07 — Feature 006 T012 Request Lifetime/Registry Contracts RED

Executed only T012 using the existing TDD/verification workflow. Added
apps/service/tests/test_service_runtime.py: eight parameterized functions/21 cases.
Real controlled app, private isolated bootstrap/credentials, serving-loop runtime
and T011's Profile/SQLite/Basic fixture remain in use. No production delivery/
registry implementation or authentication/process-ownership bypass was added.
All53 previous source/config hashes unchanged, including earlier tests/guards,
Core, service production, dependencies, lockfile and import contracts.

Pre-registration cancellation while receiving, disconnect before body completion
and pending cancellation at final-body delivery assert zero Core submission/
Profile/preparation on both mutations. Registration tests queue HTTP cancellation
before a newly created child task's first execution, then require an independently
owned Core call even before entering the real runtime. A weakly held future/task
cycle avoids an Event or test task supplying a false strong owner; GC assertions
require the service to retain admitted work after delivery disappears.

Real journal startup/close gates cover attach/detach delivery cancellation and
repeated cancellation without synthesizing attach_cancelled or altering explicit
detach intent. Active response publication covers cancellation, signalled disconnect
and header/body send failure without rollback or stopping capture; no exact wire-
disconnect observation order is invented. Capacity tests hold eight attach-only
or mixed mutations before Core execution; require ninth503 before Profile I/O and
reuse a completed slot. One operation error cannot cancel a held sibling.

Twelve repeated lost deliveries in each result/error case assert independent
invocation without replay/deduplication, no unhandled task exceptions and collection
of completed task/result/error references. Weak-referenceable returned status values
preserve every validated immutable Core field, separating service result retention
from Core's legitimate last-status snapshot. Probes retain no strong service tasks,
paths or returned values. Gates only control external progress; they implement no
registry/lifecycle policy. Teardown releases gates/joins observed calls and restores
patches before test-only runtime cleanup; client simulation never directly cancels
service operation tasks. Test watchdogs are not product lifecycle timeouts.

Initial static checks identified fixture re-export/import ordering and optional
reference narrowing; corrected within the new test file. Header publication gates
now pause only successful200 responses so absent-route failures are deterministic,
not timeout artifacts. An initial broad 'not t012' baseline selector omitted122
older Core cases sharing that task identifier; explicit baseline files were rerun
and all1303 passed. No production defect was fixed or product contract changed.

Fresh commands through rtk proxy/uv with
UV_CACHE_DIR=/private/tmp/dutchmate-feature006-uv-cache:

- uv run pytest apps/service/tests/test_service_runtime.py --tb=short:
  15 expected failures/six passes (/private/tmp/dutchmate006-t012-red.xml).
  JUnit inspection confirms every failure is HTTP404 before mutation submission;
  no fixture/setup or timeout failure counted as expected RED.
- uv run pytest core/tests apps/service/tests/test_service_bootstrap.py
  apps/service/tests/test_service_projection.py apps/service/tests/test_service_http.py
  -k 'not t011' --tb=short:1303 passed,44 deselected, zero errors/skips
  (/private/tmp/dutchmate006-t012-earlier-green.xml).
- uv run ruff check . and new-file ruff format --check: clean.
- uv run mypy .:49 source files clean.
- uv run lint-imports: five kept/zero broken,43 files/112 dependencies.
- uv run pytest --tb=no --junitxml=/private/tmp/dutchmate006-t012-full.xml:
  48 expected failures/1320 passes, zero errors/skips (1368 cases).
  T011 retains33 missing-route failures/11 passes; T012 adds15 failures/six passes.
- git diff --check and final untracked whitespace/task-marker/source-hash checks clean.

Deeper lifetime/registry assertions remain acceptance expectations blocked by
missing route wiring; no software/service/ownership acceptance claimed. Reconciled
task/spec/plan/quickstart and status/history metadata. T012 checked; T013–T030 unchecked.
No Spec Kit rerun, Graphify update (T029 assessment pending), commit, push, physical-
hardware access or validation. Native bootstrap remains macOS-only software testing;
no real listener/h11/other-platform/hardware acceptance. Stopped after T012.

## 2026-10-07 — Feature 006 T011 HTTP Lifecycle/Mapping Contracts RED

Executed only T011 with the existing test-driven-development and verification
workflow. Added14 parameterized functions/44 cases to
apps/service/tests/test_service_http.py. No production route/registry/lifecycle
implementation was added. Controlled app and credential checks use the existing
real private bootstrap on an isolated account home; one real runtime is recorded
on its loop/thread. Physical serial/discovery and real-account guards remain.

The explicit T011 fixture permits real temporary Profile/SQLite/Basic composition;
other HTTP tests retain all previous Profile/preparation tripwires. It loads the
existing strict fake serial dependency by repository-relative file location without
adding an undeclared import path. Real adapter initialization is injected only with
that dependency. Journal creation/close stay real and reopen is a tripwire. Normal
requests remain connected after their body. Test-only fallback runtime.detach joins
resources even when a RED assertion prevents HTTP detach; uncertain cleanup retains
the false marker instead of claiming cleanup. No additional physical reader.

Coverage includes both simulated peer families; normal attach/status/detach and
inactive/repeated detach; captured Profile without reread; exact Basic selector/
UART values; retained failed journals and fresh run/session/
destination on later attach; no overwrite/reopen. Real Core-seeded busy and failed
close states test409 and bounded65,537-byte Profile read before busy rejection,
with preparation/destination-probe tripwires. All11 Profile categories are first
verified against the real resolver, then asserted as HTTP422 without admission.
Real foreign loops on the same/another thread exercise attach/detach500 before
Profile/preparation. Mapping-only cases supply valid immutable Core statuses for
all six states (including failed/immediate clean terminal) and normalized edge
failures, verifying200 is not an active-capture assertion. Actual app path/method,
query and missing-path checks prohibit aliases/defaults/discovery/resource work.

Initial verification identified test-harness errors: a journal create spy accepted
an unsupported session_id keyword, and inserted code displaced two original T009
assertions. Both were corrected before the final RED evidence. All original test
function/class ASTs/assertions are unchanged except the preparation fixture's
explicit T011 opt-in;52 other source/config hashes unchanged, including all Core,
service production, dependencies, lockfile and architecture contracts. No product defect
or governing contract change was found; required HTTP wiring remains unimplemented.

Fresh commands through rtk proxy/uv with
UV_CACHE_DIR=/private/tmp/dutchmate-feature006-uv-cache:

- uv run pytest apps/service/tests/test_service_http.py -k t011 --tb=no:
  33 expected failures/11 passes,179 deselected
  (/private/tmp/dutchmate006-t011-red.xml). Every failure is absent-route404,
  verified from JUnit results; no setup-error or unrelated failure counted as RED.
- uv run pytest -k 'not t011' --tb=short:1303 passed,44 deselected,
  zero errors/skips (/private/tmp/dutchmate006-t011-earlier-green.xml).
- uv run ruff check .: all checks passed; HTTP test formatting verified.
- uv run mypy .:48 source files clean.
- uv run lint-imports: five kept/zero broken,43 files/112 dependencies.
- uv run pytest --tb=no --junitxml=/private/tmp/dutchmate006-t011-full.xml:
  33 expected T011 failures/1314 passes, zero errors/skips (1347 cases).
  Earlier1303 remain GREEN;11 new validation checks already pass. Gate is RED as
  required by this test-only task, not complete feature/service acceptance.
- git diff --check and final untracked whitespace/task-marker/source-hash checks clean.

Reconciled task/spec/plan/quickstart and current status/history checkpoint metadata.
T011 checked; T012–T030 unchecked. Quickstart keeps completed US1 selections
separate from T011 RED cases. Historical T009 absent-endpoint assertions require
reconciliation when T013 adds routes. No Spec Kit rerun, Graphify update (T029
assessment pending), commit, push, physical-hardware access or validation.
Only native macOS bootstrap and simulated peers were exercised; no listener,
h11, other-platform or hardware acceptance. Stopped after T011; no T012 file/tests.

## 2026-10-07 — Feature 006 T010 US1 Verification and Logging Review GREEN

Executed only T010 using verification-before-completion. Reviewed active spec,
plan/contract/quickstart, current committed baseline ed11051 and app.py/http.py.
No demonstrated service security/projection defect; no production/test changes
or new RED cycle required. All53 existing source/config hashes unchanged.

Reviewed supported inactive ASGI delivery: no logging/print/exception-stringifying
calls in either module, debug/docs/OpenAPI/redirects disabled, outer security before
routing/body/resource work, normalized Runtime/Profile/routing/projection errors,
and fixed post-response delivery exception raised outside the original handler.
Inspected installed FastAPI0.142.2/Starlette1.7.0 middleware: debug tracebacks are
disabled; status exceptions are normalized inside the async endpoint and routing
errors have the app's closed handler. Existing log-capture cases assert no credential,
header/body/URL/path/raw-exception echo. Credential cache and bounded generic
projection remain unchanged. No permissive testing path or resource preparation.

Controlled Uvicorn launcher configuration (access/error/general loggers disabled,
propagation disabled) and malformed pre-ASGI h11 diagnostics remain T020/T022.
No listener/server exists yet; their logging behavior is not validated or accepted
by this US1 checkpoint. No general logging framework/configuration added.

Fresh commands through rtk proxy/uv with
UV_CACHE_DIR=/private/tmp/dutchmate-feature006-uv-cache:

- uv run pytest apps/service/tests/test_service_http.py --tb=no:179 passed
  (/private/tmp/dutchmate006-t010-http.xml).
- uv run pytest core/tests apps/service/tests/test_service_bootstrap.py --tb=short:
  1013 passed (/private/tmp/dutchmate006-t010-baseline.xml).
- uv run pytest apps/service/tests/test_service_http.py
  apps/service/tests/test_service_projection.py --tb=short:290 passed
  (/private/tmp/dutchmate006-t010-us1.xml).
- uv run ruff check apps/service pyproject.toml and uv run ruff check .: clean.
- uv run mypy .:48 source files clean.
- uv run lint-imports: five kept/zero broken,43 files/112 dependencies.
- uv run pytest --tb=short --junitxml=/private/tmp/dutchmate006-t010-full.xml:
  1303 passed, zero failures/errors/skips:924 completed regressions,89 bootstrap,
  179 HTTP/composition and111 projection/input cases.
- Quickstart scope searches: no Core delivery imports, forbidden service hardware/
  private-acquisition/backend-identity matches, Core source/package diff or tracked
  graph output. No matches are expected, not command failures.
- git diff --check and final untracked whitespace/task-marker/source-hash checks clean.

Reconciled task/spec/plan/quickstart and status/history checkpoint metadata only,
including the stale task-count paragraph. T010 checked; T011–T030 unchecked.
No Spec Kit rerun, Graphify update (structural assessment remains T029), commit,
push, physical-hardware access or validation. Native bootstrap ran on macOS only;
Linux/Windows/listener/h11/hardware acceptance remains unexecuted. US1 is not full
service acceptance. Stopped after T010; no T011 tests or behavior added.

## 2026-10-07 — Feature 006 T009 Inactive Async App Composition GREEN

Executed only T009 using test-driven-development and verification-before-completion.
Added23 composition cases to apps/service/tests/test_service_http.py. All23 were
expected RED for absent dutchmate_service.app before production work, then GREEN:
/private/tmp/dutchmate006-t009-red.xml and dutchmate006-t009-green.xml.
Real isolated PrivateBootstrap/credential checks remain intact; no auth substitute.

New apps/service/src/dutchmate_service/app.py constructs one ObservationRuntime
only in async lifespan after a prepared private single-use launch context. Missing,
unprepared, mismatched and reused contexts reject before construction; the context
belongs to its original process. Factory/import has no bootstrap/runtime/listener
resource effects. One inactive runtime persists across requests on its serving
loop/thread. Async GET status projects existing immutable facts with normalized
context failure mapping; real foreign-loop/same-thread and foreign-thread calls
return500 runtime/wrong_execution_context without rebinding or state changes.
The outer pure ASGI gate covers every HTTP path; docs/OpenAPI/redirects/debug are
disabled, and FastAPI routing errors use fixed closed response helpers.

No attach/detach route, operation registry, resource preparation, controlled server/
socket/signal handling or joined service shutdown was added. App lifespan leaves
bootstrap credential/marker/guard untouched; the real isolated test owner performs
cleanup. Tests retain Profile/journal/backend/hardware tripwires.50 other existing
source/config hashes are unchanged, including all Core/bootstrap/http.py/guards/
dependencies/architecture contracts. No product contract or schema revision.
Focused tests found no production defect; targeted mypy identified the ASGI test
harness's Awaitable-versus-Coroutine annotation, corrected with an async task wrapper.

Fresh final gate through rtk proxy/uv with
UV_CACHE_DIR=/private/tmp/dutchmate-feature006-uv-cache:

- uv run ruff check .: all checks passed.
- uv run mypy .:48 source files clean.
- uv run lint-imports: five kept/zero broken,43 files/112 dependencies.
- uv run pytest --tb=short --junitxml=/private/tmp/dutchmate006-t009-full.xml:
  1303 passed, zero failures/errors/skips:924 completed001–005 regressions,
  89 bootstrap,179 HTTP/security/composition and111 projection/input cases.
- git diff --check and final untracked-file whitespace/metadata/scope checks clean.

Reconciled task/spec/plan/quickstart and current status/history metadata only;
T009 checked, T010–T030 remain unchecked. No Spec Kit rerun, Graphify update
(structural assessment remains T029), commit, push or physical-hardware action/
validation. Native bootstrap tests ran on macOS; Linux/Windows/listener/h11/hardware
acceptance is not claimed. Stopped after T009; T010 was not executed.

## 2026-10-07 — Feature 006 T008 Pure HTTP Gate/Helpers GREEN

Executed only T008 using test-driven-development, systematic debugging for the
observed peer/mapping failures, and verification-before-completion. Fresh original
T006/T007 selection recorded259 expected RED cases, all absent HTTP module, before
production work (/private/tmp/dutchmate006-t008-red.xml).

Implemented only apps/service/src/dutchmate_service/http.py: pure ASGI peer and
exact raw Host/Origin/Sec-Fetch/Bearer checks in contract order; cached credential
getter/constant-time comparison; no proxy trust, URI credentials, additional routes
or Upgrade bypass. Security precedes receiving/parsing body and downstream work.
Request validation enforces media, strict UTF-8/JSON/unique keys/types/absolute
path bytes and zero-body rules, without Profile/file/resource access. HTTP body
capture/replay is finite request delivery buffering, not a UART reader or job queue.
Observed delivery disconnect stops delivery without scheduling resource work.

Closed status projection uses immutable Profile/RuntimeStatus/Acquisition facts,
direct primary/close projection, normalized domain/loss variants, and opaque generic
provenance snapshots without backend registry/identity branch, private dump or
legacy inference. Scalar-by-scalar UTF-8 JSON retains at most1MiB+1 bytes and fails
overflow before a partial successful response. Error categories are whitelisted;
typed Runtime/Profile rejection mapping preserves existing codes without detail/
traceback/input logging. Every application response gains no-store caching policy.
No app, lifespan, runtime/Acquisition instance, routes executing lifecycle, service
operation registry, listener/server, timeout, process manager or hardware created.

First focused run:258 passed/one failed. Existing peer regression showed Python3.14
classifies ::ffff:127.0.0.1 as IPv6 loopback; explicit ipv4_mapped rejection restored
peer-first403 rather than reaching Host400. Static raw_path narrowing also corrected.
Review added six focused typed-downstream Runtime/Profile rejection regressions:
all six RED against generic500, then GREEN after using normalized rejection helper.
Two body replay regressions were verified with a temporary replay-removal mutation
(two RED) and restored production code (two GREEN), proving single/chunked bodies
and later disconnect reach the downstream boundary without loss.

Original T006 function/class ASTs and all original assertions are unchanged; only
two T008 regression functions/eight cases and their required imports were added.
All T007 tests and49 other prior source/config hashes remain unchanged, including
Core/bootstrap/guards/dependencies/lockfile/architecture. No Core contract revision.

Fresh final gate through rtk proxy/uv with
UV_CACHE_DIR=/private/tmp/dutchmate-feature006-uv-cache:

- uv run ruff check .: all checks passed.
- uv run mypy .:47 source files clean.
- uv run lint-imports: five kept/zero broken,40 files/104 dependencies.
- uv run pytest --tb=short --junitxml=/private/tmp/dutchmate006-t008-full.xml:
  1280 passed, zero failures/errors/skips:924 completed regressions,89 bootstrap,
  156 security/mapping/replay and111 projection/input cases. All original259 are GREEN.
- git diff --check: clean before/after metadata; final new-file whitespace/link/
  task-marker/scope checks pass.

The earlier1278-pass full gate was broadened only for the two new replay checks;
the fresh final run includes both. Reconciled task/spec/plan/quickstart and current
status/history; checked T008 only, T009–T030 remain unchecked. No Spec Kit rerun,
Graphify update (structural assessment remains T029), dependency change, commit,
push or physical-hardware access/validation. Software helper checks do not claim
complete FastAPI/service/process/listener/platform/hardware acceptance. Stopped after T008.

## 2026-10-07 — Feature 006 T007 Projection/Input Contracts RED

Executed only T007 using the existing test-driven-development/verification workflow.
Added apps/service/tests/test_service_projection.py with23 parameterized functions,
111 final cases against planned pure internal status_response(status, service_state)
and async validate_request(scope, receive) helpers. No production http.py, app,
runtime/Acquisition instance, listener or validator/projector substitute was created.

Tests use actual immutable Core values and a normalized opaque provenance object
with an unexposed private object. Literal closed expected JSON checks include
all RuntimeStatus keys/nulls/states, exact Profile fields/policy/limits, sorted
reported capabilities, host/device clock descriptors and observer-scoped versus
unobservable loss. Unknown backend kinds/schema37 and generic scalar fields round
trip without registry/identity branching/stringification or private-handle dumps.
Descriptor knowledge does not fabricate committed connection/segment IDs;
terminal provenance stays historical. Primary failure/close failure/trigger and
ordered cleanup facts remain independent;200 failed status cannot imply admissibility.
Unicode/control data round trips; literal1MiB bounds reject overflow without truncating
or mutating Core status. Exact response-bound tests calibrate only unspecified
serializer whitespace overhead, not the independently fixed bound or schema.

Raw ASGI body tests cover exactly16384 bytes, byte16385 with a receive tripwire,
oversized indivisible frames without another receive, strict UTF-8/JSON/media,
duplicate/extra keys, nonfinite values/type coercion, invalid Unicode surrogate
paths, absolute/no-NUL1..4096 UTF-8 byte paths, byte4097 rejection, no expansion/
stripping/probing, and status/detach zero-body rules. Error envelopes remain fixed
categories without input/traceback echo. Existing account/physical-hardware guards
and new pure-helper Profile/resource/path-I/O tripwires remain active.
These are helper/raw-ASGI contracts, not HTTP listener/process/hardware acceptance.

Initial110 expected RED cases were all missing dutchmate_service.http. Final review
uses acquiring snapshots for active status rather than impossible lifecycle fixtures,
applies closed-key checks to every status shape, and adds two surrogate-path cases.
Final result111 expected RED failures, all the missing HTTP module; no collection
errors/skips or assertion weakening to make unbuilt helpers pass.

Fresh commands through rtk proxy/uv with
UV_CACHE_DIR=/private/tmp/dutchmate-feature006-uv-cache:

- uv run pytest apps/service/tests/test_service_projection.py --tb=no --no-summary
  --junitxml=/private/tmp/dutchmate006-t007-red.xml:111 expected failures.
- uv run pytest apps/service/tests/test_service_http.py --tb=no --no-summary
  --junitxml=/private/tmp/dutchmate006-t007-t006-red.xml:148 unchanged expected failures.
- uv run pytest core/tests apps/service/tests/test_service_bootstrap.py --tb=short
  --junitxml=/private/tmp/dutchmate006-t007-earlier-green.xml:1013 passed,
  zero failures/errors/skips, including89 bootstrap cases.
- uv run pytest --tb=no --no-summary
  --junitxml=/private/tmp/dutchmate006-t007-full.xml:259 expected failures/1013 passes,
  zero errors/skips. All failures are in the two RED service test files and caused
  by missing dutchmate_service.http; the full default gate is intentionally RED.
- Ruff clean; mypy46 files clean; five import contracts kept/zero broken,
  37 files/90 dependencies. Diff/new-file whitespace and documentation audits clean.

All49 prior source/config hashes remain identical, including T006/bootstrap tests,
Core, dependency lock and architecture settings. Only the new projection test and
completion metadata/status/history change this turn. Checked T007 only; T008–T030
remain unchecked. Normative contracts/schema/Profile/runtime/deferrals unchanged.
No T008 implementation, dependency installation, Spec Kit rerun, Graphify update,
physical-hardware access/validation, commit or push. Stopped after T007.

## 2026-10-07 — Feature 006 T006 Security Contracts RED

Executed only T006 using test-driven-development and verification-before-completion.
Added apps/service/tests/test_service_http.py:20 parameterized contract functions,
148 cases against the intended internal SecurityGate(app, config, credential getter)
ASGI boundary. No production http/app/server, runtime or gate substitute was created.

Tests use actual isolated private bootstrap/credential files and raw ASGI messages;
the downstream boundary probe contains no security policy. Existing tripwires block
physical serial/discovery and real account bootstrap. New tripwires block receive/
body consumption, downstream calls, Profile resolution, journal create/open and
Basic construction/open before security rejection. Literal outcomes come from the
active contract, not implementation helpers.

Coverage: exact/duplicate/malformed Host and header-name casing; IPv4/IPv6 peers,
selected family/other IPv4 loopback and no proxy trust; every Origin/Sec-Fetch
presence including empty/null/duplicates; authenticated no-Origin eligibility;
exact single Bearer syntax and compare_digest seam; gate priority across all
routes/methods; no query/cookie/body/environment credential transport; exact raw
paths/no encoded/absolute aliases; authenticated Upgrade/HEAD/OPTIONS/docs/redirect
rejection; process-cached credential and memory invalidation; credential/input-free
responses/logs and normalized unexpected downstream failure. This is raw ASGI
gate validation, not actual FastAPI/Uvicorn/h11/process/listener acceptance.

Initial146 RED cases all failed for absent dutchmate_service.http. Corrected only
a local test-helper typing/style issue, then added two allowed IPv4 loopback peer
cases. Final focused result:148 expected RED failures, zero errors/skips, all
ModuleNotFoundError for the same missing HTTP module. No assertion was weakened
to emulate a gate or make RED cases pass.

Fresh commands through rtk proxy/uv with
UV_CACHE_DIR=/private/tmp/dutchmate-feature006-uv-cache:

- uv run pytest apps/service/tests/test_service_http.py --tb=no --no-summary
  --junitxml=/private/tmp/dutchmate006-t006-red.xml:148 expected failures.
- uv run pytest core/tests apps/service/tests/test_service_bootstrap.py --tb=short
  --junitxml=/private/tmp/dutchmate006-t006-earlier-green.xml:1013 passed,
  zero failures/errors/skips, including89 unchanged bootstrap cases.
- uv run pytest --tb=no --no-summary
  --junitxml=/private/tmp/dutchmate006-t006-full.xml:148 expected failures and
  1013 passed, zero errors/skips; all failures belong to test_service_http.py
  and the missing gate module. Full default gate is intentionally RED, not passing.
- uv run ruff check .: clean; uv run mypy .:45 files clean;
  uv run lint-imports: five kept/zero broken,37 files/90 dependencies.
- git diff --check and new-file whitespace/document audits: clean.

Hash audit preserves all48 existing source/config files, including Core, bootstrap,
existing tests/guards, dependencies/uv.lock and architecture settings. Only the new
test file and completion metadata/status/history change during this turn.
Checked only T006; T007–T030 remain unchecked. No normative scope/schema/Profile/
runtime change, Spec Kit rerun, Graphify update, dependency installation, HTTP gate
implementation, physical-hardware access/validation, commit or push. Stopped after T006.

## 2026-10-07 — Feature 006 T001–T005 Bootstrap Foundation GREEN

Executed only the explicitly authorized first five tasks. T001 verified main/HEAD
ed11051015a4e56f81a4737bc55dad322f82f622 and completed005 code2824c0d; reviewed
governing lifecycle/service contracts and existing planned working-tree changes.
The exact quickstart five-file005 baseline selection passed349 tests before any
dependency/package work, with existing physical-hardware sentinels active.

T002 added only installable apps/service metadata/import package, scoped Ruff
configuration, isolated test account-home/real-account tripwires and physical serial/
discovery guards. uv added workspace dutchmate-core, FastAPI0.142.2/Uvicorn0.54.0
and root test-only httpx0.28.1, constrained to their verified minor lines and locked.
Actual imports/signatures/Python3.14.3 and MIT/BSD metadata checked; service/Core
imported from /private/tmp through uv without working-directory assumptions.
All22 existing package versions are unchanged;16 required packages added including
service/transitives. An initial sandbox DNS failure was resolved by the authorized
network-enabled uv retry; no unresolved infrastructure failure remains.
Root test/mypy paths now cover service. Three existing import contracts are
unchanged; two added boundaries forbid Core→service and direct service hardware/
subprocess/deferred-client imports. No ignore_imports or product TID251 bypass.

Applied test-driven-development: T003 added87 meaningful configuration/filesystem/
guard/token/marker/failure contracts. Initial run:87 RED failures, all missing
dutchmate_service.bootstrap; JUnit at /private/tmp/dutchmate006-bootstrap-red.xml.
T004 implements only the private bootstrap module: explicit immutable config,
read-only normalized exception category with ordinary transport, passwd-UID path,
validated no-follow directory-relative fds, stable non-inheritable nonblocking
lock, bounded strict marker/credential reads, safe atomic private publication,
token ownership/removal and explicit cleanup facts. No runtime, listener or HTTP.
All87 original cases went GREEN without changed assertions.

Review/systematic debugging found two bounded bootstrap defects. Failed lock
creation was mistaken for optional file absence and leaked AssertionError;
failed publication unlinked its temporary name without checking replacement
identity. Two focused tests reproduced both RED before fixes, then all89 went
GREEN. Creation failure now remains normalized; cleanup preserves a replacement
file. Tests also prove publication-before-fsync failure can leave an owned token/
true marker visible without claiming rollback, cleanup uncertainty stays false,
stale/unsafe files are not repaired, and normal exception transport is preserved.

T005 used verification-before-completion and ran the full gate through rtk proxy/uv
with UV_CACHE_DIR=/private/tmp/dutchmate-feature006-uv-cache:

- uv run ruff check .: all checks passed.
- uv run mypy .: no issues in44 source files.
- uv run lint-imports: five kept/zero broken;37 files/90 dependencies.
- uv run pytest --tb=short --junitxml=/private/tmp/dutchmate006-t005-full.xml:
  1013 passed, zero failures/errors/skips (924 existing plus89 bootstrap).
- git diff --check: clean before/after completion documentation; untracked source/
  planning whitespace and final paths reviewed.

Core code/tests,003 schema-v1,004 Profile-v1,005 lifecycle/cancellation/cleanup,
product rules and hardware policy unchanged. Reconciled task/spec/plan/quickstart/
research metadata and development status/history; only T001–T005 are checked.
T006 and all later tasks remain unbuilt. No Spec Kit rerun, Graphify update
(final structural assessment remains T029), HTTP gates/routes/server/runtime
composition, physical hardware access/validation, commit or push. Native bootstrap
software tests ran on macOS; Linux/Windows/service/hardware acceptance is not claimed.
Stopped after T005.

## 2026-10-07 — Feature 006 Local Observation Service Specified, Planned and Tasked

Executed only the explicitly authorized lean specify → plan → tasks workflow.
Repository Spec Kit1.0.12 uses sequential directories; the next prefix was006,
creating specs/006-local-observation-service. No extension hooks are configured.
Managed template resolution/setup scripts created the feature/plan/tasks context;
their BRANCH labels identify that context, while actual Git remains main.
The ignored .specify/feature.json selects006; no scaffold/integration file changed.
Verified baseline ed11051 records accepted feature005 implementation
2824c0dc3ecc63684f573b3b0a55c621e18e069f.

Generated eight focused artifacts: spec, quality checklist, plan, research, data
model, local HTTP/bootstrap contract, quickstart and tasks. Core and completed
001–005 contracts govern. Scope is exactly observation-only attach/status/detach,
one persistent runtime and local process/security delivery; no evidence retrieval,
streaming, CLI or workflow behavior. All30 tasks remain unchecked.

Settled Linux/macOS POSIX bootstrap with fixed per-UID stable-inode OS lock,
private process-lifetime256-bit Bearer token and bounded entire-incarnation
cleanup marker separate from journal schema-v1. Duplicate processes reject on
any port; stale uncertainty blocks startup without PID stealing or automatic
recovery. IPv4 numeric default/explicit IPv6-only listener, exact Host, rejection
of every Origin/Sec-Fetch header, authenticated absent-Origin requests and security
ordering before body/Profile/resources are explicit. Supported logs never echo
credentials or supplied inputs; only three versioned routes are planned.

HTTP request delivery cannot cancel strongly owned service operations or synthesize
feature005 attach_cancelled. Shutdown closes admission, joins registered tasks
including not-yet-invoked attach, then detaches/joins runtime. Physical/recorder
uncertainty remains authoritative; no timeout or forced abandonment. Status
projects generic immutable normalized facts without task/resource handles.
Basic/SQLite remains at the existing edge;003 schema-v1/004 Profile-v1/005
lifecycle are unchanged. Windows service support and external operator recovery
are explicit limitations, not accepted hardware/platform behavior.

Two read-only research reviews required by the planning skill and primary
FastAPI/Python/ASGI/Uvicorn sources informed the design. Review corrected four
planning gaps: startup stop remains latched, true-marker replacement followed by
failed fsync does not falsely claim rollback/durability, trusted root ancestors
are distinct from account-private directories, and new direct service import
bans allow legitimate indirect Basic/framework dependencies while existing Core
contracts remain intact. Corresponding regression tasks are explicit.

Document audit passed: eight artifacts,30 sequential requirements/seven outcomes,
30 sequential unchecked tasks (US1 five/US2 nine/US3 six, foundation/final ten),
six parallel test markers in three pairs, valid relative links/balanced fences,
no unresolved markers/template placeholders/whitespace faults, and31 Resume Here
lines. Git diff checking and final path review confirm documentation-only changes.
No Ruff/mypy/Import Linter/pytest implementation gate was run; planning validation
is not software acceptance. No dependency installation/lockfile change, production
or test code, Graphify update, extra Spec Kit stage, commit, push, device discovery
or physical-hardware action/validation. Stopped after planning.

## 2026-10-06 — Feature 005 Final Pre-Commit Review and Commit

Reviewed the complete feature-005 change set against Core, FR-001–030, the
internal runtime contract, plan, all completed T001–T028 definitions, completed
feature contracts and development status. No new scope/contract defect was found;
production code and tests needed no correction. Single generation/reader ownership,
direct Acquisition snapshot projection, loop/thread ownership, cancellation-resistant
cleanup, recorder-after-Acquisition joins and conservative reuse gating remain intact.
Basic/SQLite construction stays at the edge; Profile/session association remains
in memory, schema-v1 and evidence semantics remain unchanged, and all deferrals persist.

Used verification-before-completion and reran the complete gate through rtk proxy/uv
with UV_CACHE_DIR=/private/tmp/dutchmate-feature005-uv-cache:

- uv run ruff check .: all checks passed.
- uv run mypy .: no issues in 40 source files.
- uv run lint-imports: three contracts kept, zero broken; 31 files/77 dependencies.
- uv run pytest --tb=short --junitxml=/private/tmp/dutchmate-feature005-precommit.xml:
  924 passed, zero failures/errors/skips; existing fail-closed hardware guards active.
- git diff --check and git diff --cached --check: clean after completion metadata
  reconciliation; the complete intended 21-file staged diff/stat was inspected.

Reconciled current development status for the explicitly authorized commit, and
made pre-commit planning metadata explicitly refer to its T028 checkpoint rather
than retain stale current-status claims. Earlier history entries remain unchanged.
The commit is identified by subject `Implement observation runtime lifecycle`,
following parent 6d10cf72014c46d7eeb5481b26857222ee40b7fd on main; Git records its hash.
Generated Graphify output/backups, local tooling, temporary journals and gate
reports are excluded. No additional Graphify update or Spec Kit stage was run.

Feature 005 is software-complete; Phase 1 is incomplete. No physical device was
accessed or validated, no hardware acceptance is claimed, nothing was pushed,
and no subsequent development slice was selected or started.

## 2026-10-06 — Feature 005 T028 Fresh Final Software Gate GREEN

Executed only T028. Used verification-before-completion and ran the fresh full
repository gate through rtk proxy/uv with
UV_CACHE_DIR=/private/tmp/dutchmate-feature005-uv-cache:

- uv run ruff check .: all checks passed.
- uv run mypy .: no issues in 40 source files.
- uv run lint-imports: all three contracts kept, zero broken; 31 files and
  77 dependencies analyzed, with no new exemption or weakened rule.
- uv run pytest --tb=short --junitxml=/private/tmp/dutchmate-t028-full.xml:
  924 passed, zero failures/errors/skips. JUnit confirms 349 feature-005 cases,
  565 completed-feature regressions and ten T019 fixture checks. All US1/US2/US3
  and T024 correction regressions remain GREEN.
- git diff --check: clean before documentation edits, then rerun clean after
  completion records were reconciled; untracked-file whitespace also verified.

Reviewed the final tracked diff against accepted baseline 6d10cf7 and all
untracked feature additions, including runtime/Basic composition, additive
Acquisition snapshot/join behavior, tests/fixture gates, import-contract changes
and planning/completion metadata. No new feature-005 defect or failed required
check remained; no production/test correction or extra validation rerun was
needed. Schema-v1/evidence/Backend/Profile contracts, dependencies/lockfile,
exports, authority ordering and accepted scope/deferrals remain unchanged.
Runtime uses normalized facts only; one owner/reader and actual joins preserve
evidence and conservative cleanup certainty. Default hardware guards remain
active. Generated Graphify output/backups are ignored and not tracked.

Reconciled final spec/plan/tasks/quickstart and development status/history as
software-complete and ready for final human review/commit. All 28 task markers
are checked; T026's previously restricted marker now reflects its completed
two-file reconciliation record, without rerunning T026 or changing that record.
No further feature/task, Spec Kit stage or Graphify update is started. Only
completion documentation changes in T028; hashes preserve all production,
tests/fixtures/configuration and normative contracts. The pre-existing
feature-003 JournalFailure context-manager limitation remains separately
documented and outside feature 005; it does not fail this feature's required gate.

HEAD/accepted committed baseline remains
6d10cf72014c46d7eeb5481b26857222ee40b7fd on main, with features 001–004 accepted.
Feature 005 remains uncommitted working-tree content pending final human review
and an explicit commit instruction. No human acceptance, commit, release, Phase 1
completion or physical-hardware/electrical/Enhanced-hardware acceptance is claimed.
No physical device was enumerated, opened, modified or tested. Stopped after T028.

## 2026-10-06 — Feature 005 T027 Code-Only Incremental Graphify Update

Executed only T027. Read the repository Graphify guidance and local skill/update
reference. Assessed the actual accepted-baseline diff, including the two new
production modules runtime.py/adapters/observation_runtime.py, shared Acquisition
snapshot()/join_terminated()/snapshot values and runtime coverage in the existing
dependency contracts. These satisfy the module/shared-interface structural
trigger; earlier per-slice graph runs do not substitute for this final assessment.

Verified installed Graphify 0.9.48 and existing interpreter/output/manifest before
updating. Corpus preflight found 126 files/~172,144 words, with no skipped-sensitive
files, 38 changed code sources and no deletions. The installed CLI's plain update
path rescans the full corpus and Markdown AST headings; to honor code-only
incremental scope, exactly one invocation used the existing
graphify.watch._rebuild_code(Path('.'), changed_paths=changed_code,
force=False, block_on_lock=True) updater via Graphify's installed interpreter.
Only changed code paths were passed; existing graph/documentation content was
preserved. No semantic extraction, API/LLM calls, fresh full extraction, labeling
command, second update or runtime test execution.

Update succeeded (exit 0): 2,435 nodes, 6,370 edges and 117 communities, compared
with 2,240/5,241/116 before the run. The report records zero input/output LLM
tokens. Non-fatal diagnostics were one zero-node source (pyproject.toml) and
34 community labels refreshed deterministically from their hubs. No retry or
LLM relabeling followed. The updater backed up four curated output files and
refreshed graph JSON, HTML, report, manifest and labels under ignored graphify-out/.

Read-only graphify explain verifies ObservationRuntime, attach_basic_observation,
AcquisitionSnapshot and join_terminated at their actual source locations; report/
manifest checks confirm the indexed symbols and successful output. graph.json
was never read directly. Git check-ignore verifies graph/report/HTML/manifest/
labels/backups are covered by the existing graphify-out/ rule, and git ls-files
finds no tracked generated graph output. Source/test/configuration hashes remain
unchanged; generated output is not staged or committed.

Recorded T027 completion in development status/history and checked only T027
in tasks.md. T026's deliberately untouched marker remains as it was; completion
is recorded in the reconciled development status. No other planning artifact,
production/test/dependency/contract/schema change, Spec Kit, commit or physical
hardware action/acceptance claim. Documentation links/whitespace/scope verified.
Stopped after T027; T028 remains unchecked and its fresh full software gate was
not run. Prior software validation remains prior evidence, not a new T028 result.

## 2026-10-06 — Feature 005 T026 Development Status/History Reconciliation

Executed only T026 and changed only development_status.md and this history.
Reconciled the active Phase 1/feature-005 working-tree milestone, recorded
validation evidence, remaining acceptance work, limitations and deferrals.
Replaced the accumulated chronological status narrative with a current summary
and checkpoint tables; prior completed-slice records are retained unchanged below.
Removed stale claims that US3 termination and runtime/Profile activation remain
unimplemented. Detailed feature/task evidence stays in history, while current
status and the authorized stopping point remain solely in development status.

Read-only Git verification confirms branch main and HEAD
6d10cf72014c46d7eeb5481b26857222ee40b7fd. The accepted baseline remains 6d10cf7,
including feature 004; committed milestones 001/002/003 are respectively
a13522c/e2cd2cf/15890e59. Feature 005 remains modified/untracked working-tree
work. No feature-005 commit, baseline advancement or complete feature acceptance
is claimed. All implementation/review through T025 is delivered; T026's
documentation reconciliation is complete. Task/spec/plan/quickstart files and
their T026 progress markers are deliberately untouched under the user's explicit
two-file restriction; current completion is recorded in development status.

Validation is reconciled as prior software evidence: T024's latest full gate
passed 924 cases and its feature focus passed 349; T025's 21 focused test/five
architecture-scope commands passed, including 349 feature cases, 565 completed
regressions and ten fixture checks. T025 omitted its final-gate block. T026 reruns
no software tests, static suite or hardware cases and makes no fresh software-gate
claim. Documentation verification checks actual Git references, local links,
whitespace, bounded Resume Here and the two-file change scope.

No physical device has been accessed, modified or validated. Fake/temporary-
journal and Enhanced-shaped tests establish software contracts only; real
platform/electrical acceptance cases remain unexecuted, never reported as passed.
The feature-003 JournalFailure context-manager limitation remains separately
recorded, while feature-005 preparation-error transport is fixed. Scope/deferrals
and normative Core/contracts are unchanged. No code/test/dependency/configuration
change, commit, Spec Kit or Graphify operation. Earlier history entries retain
their original checkpoint claims. T027/T028 remain unexecuted; this reconciliation
does not perform their structural assessment/update or final software gate.

## 2026-10-06 — Feature 005 T025 Quickstart Focused Scenarios/Scope Checks GREEN

Executed only T025. Read quickstart and ran all 21 focused pytest commands and
five architecture/scope commands before its final implementation-gate block,
with the documented file selections/filters. All commands succeeded. No
unrestricted full pytest or final-gate block was run; T028 retains that step.
The three canonical focused runs pass 105 foundational/value, 214 runtime/
composition and 30 integration cases. Combined feature focus passes 349,
completed-feature regressions 565, and T019 fixture checks ten. US1 groups pass
91/65/21/six; T024 correction check 15; US3 58 (T020 34/T021 24); US2 94
(T012 35/T013 27/T014 32), T016 preparation subset 22, and Acquisition
regressions 64. All selected tests have zero failures/errors/skips.

Focused scenarios cover resolved-Profile startup, binary/ambient continuous RX,
actual consumer/physical-close joining before recorder close, bounded durable
readback/retention, repeated cancellation, partial preparation/start failures,
retained journals and uncertainty blocking, immediate/active disconnect with no
reopen, explicit fresh sessions, both normalized shapes, direct primary/close
snapshot facts, derived admissibility/impossible statuses, exact loop/thread
ownership and runtime-versus-Basic-edge busy semantics. No demonstrated code/
test defect, changed expectation, weakened gate, or fixture/capability emulation.

Quickstart architecture checks keep all three Import Linter contracts (31 files/
77 dependencies), Ruff clean and mypy 40 files clean. Schema search reports
version 1; the specified SQLite/model/Backend diff is empty. Shared-runtime
searches show only inward Core/standard-library imports, no backend/framework/
physical-device dependency or identity branch, no private/legacy Acquisition
access, automatic reconnect, lifecycle deadline or evidence reconstruction.
Concrete Basic/SQLite/Profile construction stays at the composition edge.

One documentation count was stale after T024: excluding T020/T021 selects 291,
comprising the original 277 earlier cases and 14 new T024 cases. The quickstart
description is clarified; selectors and tests are unchanged. Hashes confirm all
42 source/test/configuration files, dependencies/lockfile and normative contracts
unchanged. Only six progress/count-description artifacts change. Documentation
whitespace checks pass; no final-gate diff-check block is executed. Commands
used rtk proxy and the documented uv run/--no-sync variants with
UV_CACHE_DIR=/private/tmp/dutchmate-feature005-uv-cache.

T024's full 924-pass result remains prior evidence; no fresh full-suite/final-gate
claim is made for T025. Updated only T025 checkbox, spec/plan/quickstart progress,
development status and this record. Routine slice recording does not complete
T026's feature-level status/history reconciliation. No Spec Kit, Graphify, commit,
physical hardware action or acceptance claim; accepted baseline remains 6d10cf7.
Documentation-only work has no structural Graphify trigger; whole-feature
assessment remains T027. Stopped after T025; T026–T028 remain unchecked.
Complete feature acceptance is deferred, including the fresh final gate at T028.

## 2026-10-06 — Feature 005 T024 Full Contract/Scope Review and Correction GREEN

Executed only T024. Reviewed the full tracked/untracked feature-005 diff against
FR-001–030 and the internal contract: ownership/context/admission (001–007),
startup/cleanup/cancellation/retained journals (008–016), bounded in-memory
association/status/additive Acquisition facts and compatibility (017–024), and
composition/sequence/retention/neutrality/hardware-free scope (025–030).
Inventoried the new runtime/Basic composition modules, additive Acquisition API,
test consumers and package exports. Existing root exports and module import
surfaces are preserved; pyproject adds only runtime coverage to two existing
import contracts. No dependency/lockfile churn or new/relaxed exemption.
Schema-v1, evidence/Backend/Profile persistence contracts and all deferrals remain
unchanged. Status holds normalized current/last values with no Profile-source/
journal-destination path, raw diagnostics, live handle or unbounded summary history.

Reproduced one genuine feature-005 defect: frozen/slotted PreparationFailure
rejects standard contextlib __traceback__ restoration with TypeError. Runtime
then mistakes the normalized report for internal-contract failure and loses the
known session, original primary and actual cleanup certainty, blocking even
confirmed-cleanup reuse. Two direct sync/async and four real temporary-journal
runtime regressions went RED for this defect; eight fact reassignment/deletion
checks passed. After the bounded correction, all 14 new cases and the unchanged
normalization case pass. JUnit confirms identical new RED/GREEN case sets.

Only PreparationFailure changes in production: normal RuntimeError transport
attributes remain writable, while all four normalized fact fields remain read-
only and validated. Constructor/replacement/equality/hash behavior and fixed
message are preserved and verified. RuntimeStatus copies only normalized facts,
never exception transport metadata. No lifecycle, Acquisition, composition,
persistence/schema, policy or fixture behavior changes. All existing model tests/
helpers are unchanged; new regressions are appended. One stale composition-test
comment is corrected without executable changes. No other scope/contract defect
was found. The existing feature-003 JournalFailure interoperability limitation
remains outside this correction's scope.

Fresh feature focus passes 349; full hardware-free pytest passes 924, zero
failures/errors/skips. Ruff passes; mypy three targeted/40 full files passes;
all three Import Linter contracts are kept (31 files/77 dependencies); tracked/
untracked whitespace checks pass. Commands used rtk proxy and uv run --no-sync
with UV_CACHE_DIR=/private/tmp/dutchmate-feature005-uv-cache.

Hashes preserve all other production/tests/fixtures/configuration; AST/prefix
checks confirm earlier model tests and executable composition tests unchanged.
Updated T024 checkbox, spec/plan/quickstart progress, development status and this
record. Normative Core/contracts, schema-v1, dependencies/lockfile, exports and
accepted baseline 6d10cf7 are unchanged. No Spec Kit, Graphify, commit or physical
hardware action/acceptance claim. The localized exception fix has no module/
shared-interface/dependency-direction trigger; whole-feature structural Graphify
assessment remains T027. Stopped after T024; T025–T028 remain unchecked and full
feature acceptance is deferred. T025 runs focused quickstart scenarios/scope
searches and fixes only demonstrated failures, deferring its final gate to T028.

## 2026-10-06 — Feature 005 T023 US3 Regression/Architecture Review GREEN

Executed only T023. Fresh feature-005 focus passes 335; the quickstart completed-
feature regression selection passes 565, including Acquisition/Basic/Profile/
SQLite compatibility. Fresh full hardware-free pytest passes 910 with no
failures/errors/skips. JUnit confirms the complete case set is exactly feature
focus plus completed regressions plus ten T019 fixture checks. All 58 T020/T021
cases are GREEN, including identical 12-case T021 sets on both backend shapes.
No test expectations, deterministic gates, shared fixtures or production changed.

Reviewed shared runtime/Acquisition and the fixture/integration/generation tests
for T023's four prohibited assumptions. No backend-identity policy branch or
host-clock assumption was found: capabilities/observability drive RX/loss checks,
reported timestamp domains/origins are preserved, and progression compares only
within the current domain/origin. Enhanced-specific fixture checks support event
emission/counters, not shared lifecycle policy or Basic capability emulation.
The fixture reports device ticks/scoped loss/non-serial disconnect and adds no
future GPIO/helper/USB/firmware/framing/timing or Enhanced Profile behavior.

Generation review confirms admitted ownership prevents replacement until
notification/startup/consumer/physical-close/recorder work is settled. The owner
drains notification waits and joins Acquisition before recorder close/terminal
publication. Only notification waits may be cancelled by runtime; no runtime
reader/close cancellation or reopen path is added. Captured old results and
guarded stop intent cannot publish into the next generation. No stale mutation
or other in-scope defect was found, so no code/test correction or RED cycle was
manufactured. The normalized snapshot retains direct primary/close facts and
committed historical provenance; runtime reconstructs no lifecycle facts from
journal records.

Ruff passes; mypy passes 40 files; all three Import Linter contracts are kept
(31 files/77 dependencies), without exemptions. Quickstart searches show schema
version 1 and no committed-baseline diff to SQLite, evidence/model or normalized
Backend contracts. Tracked/untracked whitespace checks pass. Commands used
rtk proxy and uv run --no-sync with
UV_CACHE_DIR=/private/tmp/dutchmate-feature005-uv-cache.

Hashes confirm all 42 source/test/configuration files, dependencies/lockfile and
architecture rules unchanged. Updated only T023 checkbox, spec/plan/quickstart
progress, development status and this record. Normative contracts/Core/schema-v1
and accepted baseline 6d10cf7 are unchanged. No Spec Kit, Graphify, commit, physical
hardware action or acceptance claim. Review/documentation-only work has no
structural Graphify trigger; whole-feature assessment remains T027. Stopped after
T023; T024–T028 remain unchecked. Complete runtime acceptance remains deferred;
T024 performs the full-diff/FR-001–030 contract, consumer/export and scope review.

## 2026-10-06 — Feature 005 T022 Autonomous Runtime Termination GREEN

Executed only T022. Runtime now handles autonomous Acquisition termination in
the existing generation owner. It races explicit stop and public termination
notification waits, publishes detaching, then drains both notification waiters.
Only an unfinished Event notification wait is cancelled; no Acquisition startup,
RX consumer, backend-close or join work is cancelled. Notification helpers
never publish independently, no extra reader/buffer is added, and all lifecycle
mutation remains on the bound owning loop/thread.

Successful public Acquisition.start return is tracked independently from active
publication. Only acquiring snapshots without observed terminal trigger or
pending stop publish active; early disconnect/recording/transport termination
instead enters cleanup and returns a historical terminal result. Observed
termination's final append/close work is joined without submitting another stop.
An unobserved explicit stop still calls Acquisition.stop. Both paths await
join_terminated before recorder close and settle all owned notification/resource
work before publishing the terminal summary. Admission/cancellation handling,
fresh-session-only activation and conservative uncertain-cleanup blocking remain
unchanged; late old-generation waiters retain captured immutable results.

Observed disconnected trigger now takes terminal-reason precedence over startup/
acquisition failure and detach/cancellation, even with final append/close errors.
Actual primary/cleanup failures independently force failed state. Existing direct
primary_failure_kind/close_failed projection remains separate from trigger,
committed historical provenance and physical release certainty. No legacy
Acquisition.failure decoding, private Acquisition access, evidence reconstruction,
backend/timestamp branch, automatic reconnect/reopen, deadline or abandonment.

Fresh pre-change T020/T021 run reproduced 41 assertion failures/17 passes; after
implementation the same unchanged 58 cases all pass. JUnit confirms exact case-set
identity, zero errors/skips and both backend shapes GREEN. Whole feature focus
passes 335, including earlier cancellation/failure/ordering contracts. Fresh full
hardware-free pytest passes 910, zero failures/errors/skips. Ruff passes; mypy
one targeted/40 full files passes; all three Import Linter contracts are kept
(31 files/77 dependencies); tracked/untracked whitespace checks pass. Commands
used rtk proxy and uv run --no-sync with
UV_CACHE_DIR=/private/tmp/dutchmate-feature005-uv-cache.

Only runtime.py changes among 42 source/test/configuration files; hashes preserve
all tests/fakes, Acquisition, Basic/composition/Profile/SQLite modules, dependencies/
lockfile and architecture rules. Updated T022 checkbox, spec/plan/quickstart
progress, development status and this record. Normative contracts/schema-v1 and
accepted baseline 6d10cf7 are unchanged. No Spec Kit, Graphify, commit or physical
hardware action/acceptance claim. This private lifecycle change adds no public
interface/module/dependency-direction change; whole-feature structural Graphify
assessment remains T027. Stopped after T022; T023–T028 remain unchecked. A passing
slice gate is not complete runtime acceptance. T023 performs the US3/current-
feature/completed-feature regression and architecture review specified in tasks.md.

## 2026-10-06 — Feature 005 T021 Parameterized Lifecycle/Readback Contracts

Executed only T021. Added 24 integration cases using the two existing fixture
factories: each runs the same 12 cases with eight passes/four expected failures.
The original six real Basic/fake-serial composition cases and their helpers
remain unchanged apart from imports. Each new preparation creates a temporary
fresh SQLite journal before constructing its unopened normalized fixture;
shared runtime receives the same resolved observation-only Profile. The test
edge supplies a generic version-1 provenance envelope with opaque backend
schema 37, without changing reported capabilities/timestamps/loss or implementing
Enhanced Profile selection, hardware/protocol behavior, or production code.

Sixteen cases pass: attaching/busy/active status with no repeated preparation,
exact binary/ambient byte capture and journal sequences, reported host/device
timestamp domains, commit-gated origin-reset publication with a lower new-clock
value, reported observer-loss scope versus upstream unobservability without
emulation, explicit missing-RX rejection before reader/segment creation with
retained empty journal, actual physical-close/consumer joining before recorder
close, fresh explicit run/session/connection/segment identities with historical
prior status, bounded fixed-snapshot continuation after ambient RX/detach/reopen,
and rolling expiry with original timestamp domain. Real reopen/readback confirms
persisted policy/envelope, fixed schema-v1 tables/columns/version and absence of
durable full-Profile identity/name/source path.

Eight cases are RED against the unchanged runtime: active disconnect (two),
disconnect observed before attach result delivery (two), and autonomous RX-
recording/transport failure cleanup (four). Assertions require autonomous
ordered cleanup, observed terminal cause, historical committed provenance,
independent actual failure/cleanup certainty, no fabricated evidence or reopen,
and idempotent settled detach. Both shapes produce matching case sets/results.
No xfail/skip, collection, watchdog or teardown errors. New-harness mistakes
were corrected before recording results: nonexistent capability attribute,
UTF-8 decoding of arbitrary binary persisted values, and assuming complete
retrieval after prefix expiry. Correct assertions use reported supports(), raw
bytes, and the documented partial outcome. No production defect was corrected.

Fresh earlier five-file focus passes 277, including all six original integration
cases. Full hardware-free pytest collects 910: 869 pass, with only 33 existing
T020/eight T021 assertion failures and no errors/skips. JUnit confirms focused/
full T021 failure identities, identical per-shape sets/results and unchanged
T020 failure families/counts. Required full gate remains intentionally RED.
Ruff passes, mypy passes 40 files, all three Import Linter contracts are kept
(31 files/77 dependencies), and tracked/untracked whitespace checks pass.
Commands used rtk proxy and uv run --no-sync with
UV_CACHE_DIR=/private/tmp/dutchmate-feature005-uv-cache.

Hashes confirm only the integration module changed among 42 source/test/
configuration files; all production, other tests/shared fixtures, dependencies/
lockfile and architecture rules are unchanged. Updated T021 checkbox, spec/plan/
quickstart progress, development status, and this record. Normative contracts,
schema-v1 and accepted baseline 6d10cf7 are unchanged. No Spec Kit, Graphify,
commit, physical hardware action or acceptance claim. Test-only work has no
production structural Graphify trigger. Stopped after T021; T022–T028 remain
unchecked. T022 implements autonomous normalized Acquisition observation,
terminal-before-active handling and independent cause/primary/close projection
on the owning loop/thread, then runs T020/T021.

## 2026-10-06 — Feature 005 T020 Runtime Termination Contracts RED

Executed only T020. Added 34 contracts in test_observation_runtime.py: eight
autonomous disconnect cases across final append/backend/recorder failures,
four autonomous RX-recording/transport failures, four immediate disconnect
and two acquisition-failure cases before active delivery, four start-return
disconnect/stop/cancellation races, eight disconnect/detach/failure combinations,
two cancelled-detach waiters, one historical late-result/new-generation case,
and one queued-but-unobserved disconnect plus failed initial append.

Real Acquisition and temporary SQLite journals remain authoritative. Test-local
recorder faults and start-return/consumer-tail gates control submitted work;
the existing normalized event-delivery gate distinguishes queued from observed
disconnect. A legacy-failure access tripwire requires normalized snapshot use.
Assertions keep observed trigger, actual primary failure, close_failed, committed
historical provenance and release certainty separate, require one open/reader/
close, join consumers before recorder close, retain journals, and forbid reopen
or stale-generation publication. Cleanup releases gates and drains real work
after assertions, without attesting production cleanup or adding product deadlines.

Focused RED run records 33 assertion failures and one pass. Twelve expose absent
autonomous cleanup; six expose active delivery after observed termination;
14 expose incorrect disconnect precedence over detach/cancellation or primary
failure; one late-generation case first exposes absent autonomous settlement.
The unobserved-event case passes: failed initial append prevents RX claim, so
disconnect cannot be asserted and committed connection identity remains absent.
No xfail/skip, watchdog, collection, or teardown failures. Initial test setup
cancelled two detach tasks before entry; confirmed admission now precedes
cancellation, and both cases fail for the intended terminal-reason defect.
No production defect was corrected in this test-only scope.

Fresh earlier five-file feature focus passes 277. Full hardware-free pytest
collects 886: 853 pass, with only the same 33 T020 assertion failures and zero
errors/skips. JUnit verifies exact focused/full failure identities. The full
gate is intentionally RED. Ruff passes, mypy passes 40 files, all three Import
Linter contracts are kept (31 files/77 dependencies), and tracked/untracked
whitespace checks pass. Commands ran through rtk proxy and uv run --no-sync
with UV_CACHE_DIR=/private/tmp/dutchmate-feature005-uv-cache.

SHA-256 comparison confirms only runtime contract tests changed among 42
source/test/configuration files. Earlier runtime tests/helpers are unchanged
apart from one import; all production, shared fakes, integration tests, other
tests, dependencies/lockfile and architecture rules are untouched. Updated
T020 checkbox, spec/plan/quickstart progress, development status, and this record.
Normative contracts, schema-v1 and accepted baseline 6d10cf7 are unchanged.
No Spec Kit, Graphify, commit, physical hardware action or acceptance claim.
The test-only addition has no production structural Graphify trigger.
Stopped after T020; T021–T028 remain unchecked, and T020 awaits T022 implementation.

## 2026-10-05 — Feature 005 T019 Shared Fixture Lifecycle Gates GREEN

Executed only T019. Shared fakes now expose default-open FixtureLifecycleGate
checkpoints for backend open, connection read, normalized event delivery,
consumer exit, and close. Each gate has entered/allow events and no elapsed-time
behavior. Tests opt in by clearing allow; default stream/factory behavior stays
the same. Simple counters record open invocations, successful reader claims,
and close invocations (including no-ops). A no-op close does not re-enter its
checkpoint. One authoritative normalized iterator is retained.

Ten fixture-focused checks in test_backend.py run identically against the two
existing factories: delayed open return (two), delayed read/event delivery with
exact binary bytes, reported timestamp domain, terminal ordering and rejection
of a second reader (four), independent close/consumer completion with idempotent
reclose (two), and reported missing-RX rejection that drains close before raising
without claiming a reader (two). They use actual normalized fixtures and the
existing Acquisition, not runtime status/cause policy from T020. All ten went
RED solely for missing gates, then all ten passed. No xfail/skip or production
implementation. Test watchdogs bound hangs without creating runtime deadlines.

Existing Enhanced-shaped device timestamps, scoped observer loss, origin reset,
normalized non-serial disconnect and reported capabilities are unchanged. RX
rejection reuses the existing descriptor. No new event, GPIO/helper/USB/framing/
firmware/device timing, Enhanced Profile selection, or Enhanced support claim.
All original 30 backend cases remain GREEN, as do current lifecycle/Acquisition
loss/origin/reset/disconnect cases. Compatibility passes 94 (40 backend,
22 lifecycle, 32 acquisition). Fresh full pytest passes 852, zero failures/errors/
skips, including all 277 previous feature-005 cases. JUnit verifies RED/GREEN
case-set identity and exact compatibility/full counts.

Ruff passes; mypy two targeted/40 full files pass; all three Import Linter
contracts kept (31 files, 77 dependencies); tracked/untracked whitespace clean.
New-harness B009 and typing issues were corrected using typed reflection only
for fixture-only metadata, direct known connection attributes, a coroutine
wrapper for anext, and cleanup over the declared iterator port rather than an
assumed aclose method. No rule/exemption or production API changed.

SHA-256 comparison confirms only shared fakes and the backend fixture contract
test changed among 42 source/test/configuration files; all production, runtime
tests, other tests, dependencies/lockfile, and architecture rules are untouched.
Original backend test bodies and the Enhanced connection semantics are unchanged.
Updated T019 checkbox, spec/plan/quickstart progress, development status, and
this record. No Spec Kit, Graphify, commit, or physical hardware action/acceptance
claim. The test-only extension adds no production structural Graphify trigger.
Accepted baseline remains 6d10cf7. Stopped at T019; T020–T028 remain unchecked.
T020 adds RED runtime status/immediate-active-disconnect/recording-failure/
racing-stop cases; autonomous runtime observation remains later T022 work.

## 2026-10-05 — Feature 005 T018 US2 Regression/Architecture Review GREEN

Executed only T018. All 94 US2 regressions pass: 35 request/cancellation cases
(T012), 27 preparation/transfer cases (T013), and 32 failure/teardown/certainty
cases (T014). Deterministic gates continue to hold actual prepare/open/append/
read/consumer/close work; no gate or expectation was weakened. Feature-005 focus
passes 277 and fresh full hardware-free pytest passes 842, zero failures/errors/
skips. JUnit reports confirm exact counts and all earlier work remains GREEN.

Reviewed every physical/recorder certainty assignment and admission/settlement
path in runtime.py and the composition adapter. Physical release comes only
from authoritative Acquisition snapshots; post-transfer recorder confirmation
requires successful original close. Settled detach returns the stored immutable
summary without retrying cleanup, and exact derived admission rejects uncertainty
before preparation. Failed-open release stays unconfirmed, and later library
no-op close cannot attest success or unblock another run. The edge owns local
cleanup until transfer, retains original primary/close outcomes and known IDs,
and keeps failed artifacts without probing/reopen/deletion/retry. Recorder close
follows Acquisition's actual consumer/close join. No no-op-close/reset path that
falsely clears uncertainty or other in-scope defect was found; no code correction.

Targeted Ruff and mypy (runtime/composition and their two contract test modules)
pass; full Ruff and mypy pass (40 files). All three Import Linter contracts kept
(31 files, 77 dependencies). Scope searches show no shared backend-identity
branch, legacy/private Acquisition failure access, physical-device call, owner
cancellation, or lifecycle deadline. Schema-v1 remains 1 and SQLite schema,
backend, and evidence contracts have no committed-baseline diff. No architecture
contract/exemption or dependency changed; tracked/untracked whitespace is clean.

SHA-256 comparison confirms all 42 source/test/configuration files unchanged,
including runtime, composition, Acquisition, shared fixtures, all deterministic
tests, pyproject.toml, and uv.lock. Only the T018 checkbox and progress in spec,
plan, quickstart, development status, and this newest-first record changed.
No production implementation, test rewrite, Spec Kit stage, Graphify update,
commit, or physical hardware action/acceptance claim. This review-only change
adds no structural Graphify trigger. Accepted baseline remains 6d10cf7.

Stopped at T018; T019–T028 remain unchecked. T019 extends only deterministic
current-contract gates in shared test fixtures, reusing existing Enhanced-shaped
timestamps/loss/origin-reset/non-serial-disconnect/RX-rejection behavior. US3
autonomous termination/neutrality and all accepted delivery/hardware deferrals
remain later work. This passing current suite is not complete runtime acceptance.

## 2026-10-05 — Feature 005 T017 Runtime Failure/Cleanup GREEN

Executed only T017 in runtime.py. Status now projects actual snapshot
primary_failure_kind separately from close_failed, preserving the first primary
and one acquisition/backend cleanup fact before one recorder fact. Physical
release certainty equals the snapshot's authoritative field; owned recorder
closure is confirmed only on successful close. No legacy failure decoding,
private Acquisition fields, evidence reconstruction, raw cause/context values,
or backend identity branch. Startup success/failure are private generation facts
used to distinguish startup primary from subsequent acquisition primary.

Normalized preparation failures retain reported identity, primary, and local
cleanup certainty/issue without reclosing untransferred resources. Unexpected
exceptions or invalid returned lifecycle subsets become internal contract
failure with unconfirmed recorder cleanup. A well-formed policy mismatch retains
its known ID and closes the recorder without constructing/opening Acquisition.
Failed Acquisition start/stop/backend close still joins actual consumer/close
work before recorder close; recorder failure is independent and never overwrites
the primary. Terminal settlement follows joined owned work, uses failed state
for any issue, and preserves the applicable explicit/startup cause and first stop
intent. No-op close/terminal detach cannot clear uncertainty; exact derived
admission blocks it for the runtime's lifetime. Confirmed cleanup allows only
a fresh explicit generation/session at a fresh destination.

Fresh pre-change T014: 29 RED failures and three passes. The same unchanged 32
cases now pass, including both legacy/snapshot counterexamples, first/final
append failures, reported missing RX, both close failure combinations, pending
consumer/journal gates, permanent uncertainty, idempotent detach, and confirmed-
cleanup retry. All 27 T013 cases pass too: the five formerly deferred failed-open/
policy-mismatch cases are GREEN. The 64 Acquisition regressions passed before
implementation and in the final suite. Combined feature-005 focus passes 277;
full hardware-free pytest passes 842, zero failures/errors/skips. JUnit reports
verify exact RED/GREEN case sets and removal of all 34 prior failures.

Ruff passes; mypy passes runtime.py and all 40 full files; all three Import
Linter contracts kept (31 files, 77 dependencies); tracked/untracked whitespace
clean. SHA-256 comparison confirms all 41 other source/test/configuration files
unchanged, including all tests, Acquisition, Basic composition/adapter, Profile,
SQLite schema/evidence semantics, dependencies/lockfile, and architecture rules.
Public method signatures/immutable values and normative contracts are unchanged.
Only shared runtime failure/projection/cleanup behavior and private preparation
validation/generation facts changed. No test correction or exemption was needed.

Updated T017 checkbox, spec/plan/quickstart progress, development status, and
this record. No Spec Kit rerun, commit, physical hardware action/acceptance claim,
or Graphify update. This single-module private lifecycle/projection change adds
no module/shared-interface/dependency-direction change requiring Graphify.
Accepted baseline remains 6d10cf7. Stopped at T017; T018–T028 remain unchecked.
T018 is the dedicated US2 regression/static/architecture review, including
elimination of any discovered no-op-close/reset path that clears uncertainty.
US3 autonomous termination observation, terminal-before-active/disconnect cause
priority, extended Enhanced-shaped neutrality, and all delivery/hardware work
remain deferred. A passing current suite is not complete runtime acceptance.

## 2026-10-05 — Feature 005 T016 Preparation Cleanup GREEN

Executed only T016 in adapters/observation_runtime.py. The edge still performs
nonmutating context validation and bounded explicit Profile resolution before
authoritative runtime admission. Its unsubmitted preparation closure creates
the fresh journal then translates/constructs one unopened Basic backend. Success
transfers those resources unchanged. No backend open/RX, discovery, fallback,
new schema, or lifecycle policy moves into the edge.

Creation and translation/construction exceptions now become PreparationFailure
with bounded normalized source/code facts. Existing JournalFailure, ProfileFailure,
and NormalizedBackendFailure categories are retained; unexpected exceptions use
internal_contract_failure. Only exact CREATE invalid_input/journal_exists prove
recorder pre-open closure; other create failures remain unconfirmed with absent
ID, even if committed metadata exists. No artifact identity probing, reopen,
deletion, or retry. After an obtained journal, failure closes it once before
reporting its known identity, retained file, first primary, and independent
recorder-close outcome. A failed close stays unconfirmed even if later close
would be a no-op. Failures are raised outside handlers so raw cause/context,
detail strings, and adapter objects do not cross the preparation boundary.

Fresh pre-change T013 run: 26 RED failures and one pass. Its unchanged 22
preparation cases comprised 21 RED failures/one pass; all 22 now pass. Whole
T013 now has 22 passes and five expected deferred failures:

- `test_t013_failed_open_keeps_session_but_never_proves_physical_release`:
  device_not_found, permission_denied, io_failure, unexpected (four cases).
- `test_t013_transferred_recorder_policy_mismatch_is_closed_before_any_open`:
  one case.

These require shared-runtime T017 handling, which was not implemented. All 29
T014 failures (families recorded below) also remain unchanged. Combined
feature-005 focus excluding those five T013 cases and T014 passes 240. Full
pytest collects 842: 808 pass and exactly 34 expected deferred failures, zero
errors/skips. JUnit confirms unchanged case sets, all 21 preparation fixes,
and no extra failure/watchdog/cleanup error. T015's 35 request/cancellation cases
and all earlier completed-feature/US1 tests remain GREEN. This is a GREEN edge-
preparation checkpoint, not a passing full gate or accepted runtime feature.

Ruff passes; mypy passes the changed adapter and all 40 full files; all three
Import Linter contracts kept (31 files, 77 dependencies); tracked/untracked
whitespace clean. The additional direct domain import uses the existing
normalized backend failure and preserves inward direction. SHA-256 comparison
confirms all 41 other source/test/configuration files unchanged: runtime.py,
Acquisition, Basic/SQLite/Profile implementations, every test, dependencies/
lockfile, and architecture rules. No test correction or exemption was needed.

Updated T016 checkbox, spec/plan/quickstart progress, development status, and
this record. No Spec Kit rerun, commit, physical hardware action/acceptance claim,
or Graphify update. The localized private normalization/cleanup change adds no
module/shared-interface/dependency-direction change requiring Graphify. Accepted
baseline remains 6d10cf7. Stopped at T016; T017–T028 remain unchecked. T017 is
shared-runtime failure/certainty/projection handling with T014 and Acquisition
regressions; autonomous observation and other accepted deferrals remain later.

## 2026-10-05 — Feature 005 T015 Request/Cancellation GREEN

Executed only T015 in runtime.py. Existing owning-loop/thread validation and
exact derived fail-fast admission are retained. Stop intent admits once under
the short lifecycle lock; later detach/attach_cancelled requests cannot replace
it. Stop handling checks generation identity before any mutation, protecting
new runs from late old-generation cancellation. Admitted attach/detach callers
shield and join their captured owner despite repeated cancellation, then
propagate the original CancelledError. Caller cancellation takes precedence if
the joined owner raises; owner failure normalization/cleanup remains later work.
No caller cancels the owner, no external I/O holds the lifecycle lock, and no
second open, runtime timeout, process lock, dispatch, or abandonment is added.
The normal terminal reason reflects the first detach/attach_cancelled intent.

Before production edits, the fresh unchanged T012 suite had 20 RED failures and
15 passes: six startup attach cancellations, two internal-active-publication
cancellations, nine detach checkpoints, two first-stop-intent races, and one
cancelled old-generation waiter. The same 35 cases then passed unchanged.
They cover before-admission versus admitted cancellation, repeated cancellation
during prepare/open/append/read/close, shared cleanup, retained journals,
post-success caller cancellation, busy/context rejection before preparation,
and captured old-generation results after a fresh explicit attach.

Combined feature-005 focus excluding T013/T014 passes 218. Fresh full pytest
collects 842: 787 pass, exactly 55 deferred failures (26 T013 and 29 T014), zero
errors/skips. JUnit confirms identical RED/GREEN case sets and removal of all
20 T012 failures, with unchanged T013/T014 sets. Their named failure families
remain recorded in the preceding T013/T014 entries. This is a GREEN request/
cancellation checkpoint, not a passing full gate or accepted runtime feature.
Preparation cleanup, failure/status/certainty handling, and autonomous terminal
observation remain later tasks; none was implemented here.

Ruff passes; mypy passes runtime.py and all 40 full files; all three Import
Linter contracts kept (31 files, 76 dependencies); tracked/untracked whitespace
checks clean. SHA-256 comparison confirms all 41 other source/test/configuration
files unchanged, including every test, Acquisition, Basic edge, SQLite schema,
dependencies/lockfile, and architecture rules. Public signatures, immutable
values, Profile association, evidence semantics, and composition boundary are
unchanged. Only two private request/cancellation helpers and normal request
handling/terminal-intent projection changed in production; no test correction.

Updated T015 checkbox, spec/plan/quickstart progress, development status, and
this record. No Spec Kit rerun, commit, or physical hardware action/acceptance
claim. Accepted baseline remains 6d10cf7. Graphify was not updated for a localized
private-helper behavior change without module/shared-interface/dependency
changes. Stopped at T015; T016–T028 remain unchecked. T016 is partial-preparation
cleanup and normalized PreparationFailure at the Basic composition edge, with
retained artifacts/known IDs, exact pre-open certainty exceptions, and T013 checks.

## 2026-10-05 — Feature 005 T014 Runtime Failure/Teardown RED

Executed only T014: added 32 deterministic cases to the existing runtime
contract module. Twelve projection cases exercise clean, close-only, recording,
and transport-before-failed-append snapshots, each with successful/failed
recorder close. They require actual snapshot primary_failure_kind independently
from close_failed, no legacy interpretation, first primary preservation, and
zero/one/two ordered normalized cleanup facts. Real counterexamples retain
transport primary despite legacy recording failure, and no primary despite
close-only legacy transport failure.

Eight startup cases cover failed first append/reported missing RX with every
backend/recorder close combination: retained known session, returned descriptor
but no fabricated committed provenance, startup cause independent of stop
intent, and attempted cleanup despite primary failure. Four consumer-tail cases
hold the actual consumer after its body/notification and require joining before
recorder close, including pending failure projection and owner settlement only
after resource work finishes. Four certainty cases check busy rejection during
physical and recorder cleanup, exact derived admission, permanent uncertainty,
idempotent terminal detach without cleanup retry, and rejection despite later
library no-op close. Two confirmed-cleanup retries require a fresh explicit
destination/run/session after primary failure. Two preparation reports preserve
primary/local-close facts and known identity without reclosing untransferred
resources.

Test fixtures use actual temporary SQLite journals and inherited Acquisition
start/stop/snapshot/join behavior. A legacy failure property tripwire rejects
runtime access; a test-only consumer tail gates actual task completion without
changing snapshots or implementing lifecycle policy. Explicit detach drives
active-failure cleanup; autonomous runtime observation remains later work.
Test-only cleanup releases gates, joins real Acquisition work, and closes
journals after assertions without attesting successful production cleanup.
No production timeout, forced abandonment, extra reader, shared-fake extension,
backend identity branch, or production change.

Focused result: 29 expected RED failures and three passes, zero errors/skips.

| RED test family | Failures |
|---|---|
| `test_t014_projects_primary_and_close_snapshot_facts_without_legacy_inference` | 11 |
| `test_t014_startup_primary_survives_both_ordered_cleanup_failures` | 8 |
| `test_t014_consumer_join_precedes_recorder_close_even_after_failure_notification` | 3 |
| `test_t014_admissibility_stays_blocked_until_settled_and_uncertainty_latches` | 3 |
| `test_t014_confirmed_cleanup_after_primary_failure_allows_only_new_explicit_run` | 2 |
| `test_t014_preparation_primary_and_local_cleanup_facts_survive_without_reclose` | 2 |

Failures expose missing primary/cleanup issue projection, leaked startup/
recorder-close/preparation exceptions, and failed cleanup reported as clean
termination. Clean projection, consumer-join ordering, and settled reuse pass.
No xfail/skip or implementation fix is added; T014 remains RED pending T017.

Earlier feature-005 focus passes 183 with T012/T013/T014 deselected. Fresh full
pytest collects 842: 767 pass and exactly 75 expected failures (29 T014, 26 T013,
20 T012), zero errors/skips. JUnit reports confirm the exact focused/full T014
failure set and no additional/watchdog/cleanup errors. All earlier completed-
feature and US1 cases remain GREEN; the existing T012/T013 RED sets are preserved.
This is a RED test-delivery checkpoint, not a passing full gate or runtime acceptance.

Ruff passes; mypy passes the changed test file and all 40 full files; all three
Import Linter contracts kept (31 files, 76 dependencies); tracked/untracked
whitespace checks clean. SHA-256 comparison of 42 source/test/configuration
files confirms only the runtime contract test changed. Its original 100
cases/helpers are unchanged apart from imports. Core/normative contracts,
production, shared fixtures, dependencies/lockfile, and schema-v1 are untouched.

Updated T014 checkbox, spec/plan progress, quickstart, development status, and
this record. No Spec Kit rerun, Graphify update, commit, physical hardware action,
or hardware acceptance claim. This test-only change adds no production structure
or contract requiring Graphify. Accepted baseline remains 6d10cf7. Stopped at
T014; T015–T028 remain unchecked. T015 is request/cancellation implementation
and T012 validation; failure/teardown implementation remains T017.

## 2026-10-05 — Feature 005 T013 Preparation/Ownership Transfer RED

Executed only T013: added 27 cases to the existing composition contract module.
Four category/operation cases check that only CREATE invalid_input/journal_exists
affirm pre-open recorder cleanup; a structural-invalid destination case uses
the actual SQLite validator. Nine failed-create cases cover before any artifact,
partial artifact, and actual committed metadata without returning the journal,
with normalized IO/capacity or unexpected failures. Guards prohibit identity
probing, reopen, deletion, and retry during failure normalization; unknown
SessionId remains absent even when the test fixture knows the committed ID.

Eight translation/construction cases fail after a real journal is obtained,
with normalized/unexpected primary errors and successful/failed local recorder
close. They require known identity, retained empty journal, one local close,
independent cleanup outcome, and no raw cause/context or arbitrary detail
crossing the preparation boundary. Four failed-open cases require failed status,
known session, absent invented descriptor/provenance, confirmed recorder close,
and unconfirmed physical release regardless of the backend's error category.
One mismatched-policy case requires closing the transferred recorder before
any backend open. Preparation uses the existing admission probe; transfer
tests exercise actual runtime/Acquisition. No substitute lifecycle or shared
fixture changes. Test-only cleanup releases obtained journals without claiming
that production cleanup succeeded; test watchdogs add no runtime deadline.

Focused result: 26 expected RED failures and one pass, zero errors/skips.
Failures expose leaked create/translation/construction/open exceptions instead
of normalized PreparationFailure/failed RuntimeStatus, and an attempted backend
open before policy-mismatch rejection. CREATE journal_exists already passes,
including cause/context suppression. No xfail/skip or production correction.
Preparation normalization and shared-runtime failure handling remain later work.

Earlier feature-005 focus passes 183 with T012/T013 deselected; the original
21 composition cases also passed before these additions. Fresh full pytest
collects 810: 764 pass, exactly 26 T013 plus the existing 20 T012 failures,
zero errors/skips. JUnit inspection confirms focused/full T013 failure sets,
the documented T012 assertion families, and no additional/watchdog/cleanup error.
This is an intentional RED test-delivery checkpoint, not a passing full gate.

Ruff passes; mypy passes the changed test file and all 40 full files; all three
Import Linter contracts are kept (31 files, 76 dependencies); diff whitespace
is clean. SHA-256 comparison confirms only the composition contract test changed
among 42 existing source/test/configuration files. Its original 21 cases/helpers
are unchanged apart from imports; all production/config/T012 work is untouched.

Updated T013 checkbox, spec/plan progress, quickstart, development status, and
this record. No Spec Kit rerun, Graphify update, new dependency/lockfile change,
commit, physical hardware action, or hardware acceptance claim. Graphify is
unneeded for this test-only change without production structure/contract changes.
Accepted baseline remains 6d10cf7. T014–T028 remain unchecked; stopped at T013.

## 2026-10-03 — Feature 005 T012 Request/Cancellation Races RED

Executed only T012: added 35 deterministic cases to the existing runtime
contract test module. Test-local gates exercise concurrent already-resolved
busy attach with forbidden Profile I/O/preparation, owning-context validation
before lock/mutation, detach during startup, three simultaneous detach waiters,
and cancellation before admission/during prepare/open/append/read/close.
Controlled first-commit callbacks test cancellation after internal active
publication but before attach delivery; recorder-close callbacks schedule a
fresh explicit run before old-generation caller-result delivery. Repeated
cancellation, first-stop-intent precedence, and post-success caller cancellation
are covered. Tests use actual runtime/Acquisition and temporary SQLite journals,
one normalized simulated RX path, and public status/results. No runtime
substitute, production change, shared fixture change, or physical access.

Focused result: 20 expected RED failures and 15 passes, zero errors/skips.
RED assertions show cancellation escaping before owned work settles: six
startup attach cases, two active-publication cases, nine detach checkpoints,
two stop-intent races, and one cancelled old-generation waiter. They remain
RED for the later T015 implementation; no xfail/skip or production fix was added.
The passing cases verify existing admission/context rejection, shared detach
cleanup, pre-admission and post-success cancellation behavior, and uncancelled
captured-generation delivery. Test-only watchdogs impose no runtime deadline.

Earlier feature-005 focus passed 183 with only the 35 T012 cases deselected.
Fresh full hardware-free pytest collected 783: 763 passes and exactly the same
20 expected T012 failures, zero errors/skips. JUnit reports confirmed both
failure sets and assertion reasons; no cleanup/watchdog failure occurred.
This is a RED test-delivery checkpoint, not a passing full gate or accepted
runtime feature. Cancellation/stop-intent production behavior is still deferred.

Ruff passes; mypy passes the changed test file and all 40 full files; all three
Import Linter contracts are kept (31 files, 76 dependencies); diff whitespace
is clean. Two test-harness typing errors were corrected without production
changes. SHA-256 comparison of 42 existing source/test/configuration files
confirms only the runtime contract test changed; its earlier 65 cases/helpers
are unchanged apart from the added evidence import.

Updated T012 checkbox and progress in spec/plan/tasks/quickstart, development
status, and this record. No Spec Kit rerun, dependency/lockfile change, commit,
or hardware acceptance claim. The accepted baseline remains 6d10cf7. Graphify
was not updated for this test-only change without production structure or
contract changes. T013–T028 remain unchecked; no later task was implemented.

## 2026-10-03 — Feature 005 T011 US1 Regression Checkpoint GREEN

Executed only T011: active quickstart US1/foundation checks passed 181 initially,
and all 565 completed-feature regressions passed. Reviewed the accepted Core,
spec/plan/internal contract, normal runtime/Basic composition, additive
Acquisition diff, immutable association, event-loop guards, derived admission,
single RX ownership, cleanup ordering, and unchanged journal contracts.
Cancellation/failure transfer and autonomous terminal behavior remain later work.

Review reproduced one in-scope defect: RuntimeRejectedError's frozen/slotted
dataclass blocked contextlib's standard __traceback__ assignment, masking the
normalized rejection with TypeError. Six regression cases went RED: all four
categories through a generator context manager, actual no-loop construction,
and actual invalid attach through an async generator context manager. Corrected
only that exception class in runtime.py to an ordinary RuntimeError with the
same validated, read-only kind and string. Normal exception transport fields
remain assignable; immutable run/status/issue values, context guards, resource
preparation, admission, and orchestration did not change. No new exception
framework or compatibility layer was introduced. All six went GREEN unchanged.

Final focused feature-005 tests passed 183; fresh full hardware-free pytest
passed 748, zero failures/errors/skips. JUnit reports verified exact RED/GREEN
sets and counts. Targeted Ruff/mypy/Import Linter and final full gate passed:
mypy eight targeted/40 full files, three import contracts kept (31 files,
76 dependencies), whitespace clean. A new-test Ruff B010 diagnostic was
corrected with the repository's dynamic-field assignment pattern; no rule or
exemption changed. Scope hashes verified all 40 other source/test/configuration
files unchanged, and reconstruction of the prior RuntimeRejectedError block
verified runtime.py's remaining code unchanged. Basic composition, Acquisition,
SQLite schema-v1, backend/evidence/Profile contracts, dependencies, and existing
contract/integration tests were untouched.

Updated T011 checkbox, spec/plan progress, quickstart, status, and this record.
No Graphify update was required for a localized fix without module/dependency
or normalized contract changes. The separate JournalFailure/contextlib defect
from T010 remains unmodified because evidence.py is outside the approved scope.
No Spec Kit stage, physical hardware action/acceptance, or commit occurred.
Accepted code baseline remains 6d10cf7. This is the US1 happy-path regression
checkpoint, not complete runtime acceptance; T012–T028 remain unchecked.

## 2026-10-03 — Feature 005 T010 End-to-End Readback GREEN

Added only T010's six cases in
`core/tests/integration/test_observation_runtime.py`. Real explicit TOML
resolution, ObservationRuntime, Basic adapter, Acquisition, and SQLite append/
reopen/retrieval compose the observation run. Only physical serial construction
uses the existing private fake seam; an append spy observes real durable commit
acknowledgments, and read gates supply deterministic ambient output.

Coverage proves exact binary/ambient bytes and ordered final explicit-stop
boundaries after detach/reopen; record-count and charged-byte rolling quotas,
coalesced discard counts/timestamps, explicit wholly/partly expired references;
fixed-snapshot pages across later RX, detach, and reopen; and expiry between
pages during continued capture. Removing the source Profile does not alter the
in-memory summary. Reopen preserves session policy and effective provenance,
while inspection of schema-v1 persisted values finds no DUT identity/name or
Profile source path. No durable full-Profile association is claimed.

The initial run passed four and failed two cases because new-test expectations
incorrectly assumed retrieval limits were clamped and Basic provenance fields
lacked their effective_* prefix. Existing feature-003/Basic contracts and code
identified both errors; only new tests were corrected. All six then passed.
This is compatibility coverage for existing code, not a production RED/GREEN
implementation pair. The error path additionally exposed an existing
JournalFailure interoperability defect: contextlib generator context managers
assign __traceback__, which frozen/slotted JournalFailure rejects with TypeError
on Python 3.14, masking the original normalized exception. A minimal independent
contextmanager reproduction confirmed it. It remains unmodified/outside this
task and outside T011's permitted production correction files.

Fresh full hardware-free pytest passed 746 with zero failures/errors/skips,
including the earlier 175 feature-005 cases. Ruff passed; mypy checked 40 files;
all three Import Linter contracts kept (31 files, 76 dependencies); diff
whitespace clean. JUnit reports verified focused/full counts. Hash verification
confirmed all 41 pre-existing source/test/configuration files unchanged.

Updated T010 checkbox, spec/plan progress headers, quickstart, status, and this
record. No runtime/Acquisition/adapter/schema/dependency/shared-fixture changes,
Graphify update (no production interface/dependency change), Spec Kit stage,
physical hardware action/acceptance, or commit occurred. Accepted code baseline
remains 6d10cf7. T011–T028 are unchecked; this checkpoint does not claim complete
feature-005 acceptance.

## 2026-10-03 — Feature 005 T009 Basic Observation Composition GREEN

Implemented only T009 in the new adapter module
`core/src/dutchmate_core/adapters/observation_runtime.py` and stopped.
attach_basic_observation checks context using nonmutating runtime.status,
resolves the bounded explicit Profile before admission without a busy precheck,
then hands runtime.attach a preparation closure capturing the explicit journal
destination. Busy may read/parse the Profile but creates/opens no journal,
constructs/opens no backend, and performs no run preparation or discovery.

Admitted preparation creates fresh SQLite with exactly Profile.session_policy,
then translates the captured values and constructs the unopened Basic backend.
It never opens the backend, starts RX, or resumes an existing journal. CREATE
journal_exists becomes the existing normalized PreparationFailure with no new
SessionId and confirmed pre-open recorder cleanup, without overwriting/reopening
the destination or constructing a backend. The existing Basic private serial
factory seam supports fake-only tests; no new public injection API, provider
hierarchy, or package re-export was introduced. Broader partial-preparation
failure/cleanup semantics remain the later T013/T016 work.

RED/GREEN: fresh T007 run failed all 21 cases on the missing composition API.
All unchanged cases passed after implementation, including context/read/admission
order, busy and invalid-Profile precedence, exact path/policy/configuration,
journal-before-backend startup, existing-file protection, and source replacement/
removal. Combined feature-005 focus passed 175; full hardware-free pytest passed
740, with zero failures/errors/skips. JUnit inspection verified the RED and GREEN
sets. Ruff passed; mypy no issues in 39 files; all three import contracts kept
(31 files, 76 dependencies); diff whitespace clean. No new defect was found.

Feature progress headers, T009 checkbox, quickstart, status, and this history
record were updated. One code-only Graphify update produced 2,240 nodes, 5,241
edges, 116 communities; 22 labels refreshed from hubs. The known non-fatal
zero-node pyproject.toml warning recurred; generated output stays ignored and no
semantic extraction ran. Existing source/config/tests, shared runtime and
Acquisition, adapters, package exports, dependencies, architecture rules, and
schema-v1 were unchanged. Accepted baseline remains 6d10cf7; no commit was made.

T010–T028 remain unchecked. End-to-end runtime composition readback acceptance,
US2 failure/cancellation/transfer validation, and US3 autonomous terminal behavior
remain pending; the passing current gate does not claim complete feature-005
acceptance. No Spec Kit stage or physical hardware access/acceptance occurred.

## 2026-10-03 — Feature 005 T008 Normal Observation Lifecycle GREEN

Implemented only T008 in `core/src/dutchmate_core/runtime.py` and stopped.
ObservationRuntime binds immediately to the constructing running loop/thread;
construction without a loop and lifecycle calls in other contexts reject before
validation, locks, mutation, or resource preparation. Synchronous status only
reads/project immutable Acquisition snapshots, without scheduling or mutation.

Derived admission creates one generation owner and captures the immutable
resolved Profile. Preparation occurs only after admission, followed by fresh
Acquisition.start and active-result publication. Normal explicit detach requests
stop, joins Acquisition stop/termination (including consumer/physical-close and
final evidence work), then closes the recorder. Terminal summary publication
follows quiescent resource work; detach waiters join the actual completed owner.
Only one current/last immutable summary remains and runtime resource references
are released. Locks do not span external awaits. No adapter import, backend
identity branch, alternative RX reader, process lock, resource/task handle,
retrieval surface, durable Profile field, or schema change was introduced.

RED/GREEN: fresh pre-implementation T006 run failed all 65 cases on missing
ObservationRuntime. The same unchanged cases passed after implementation;
foundation plus runtime focus passed 154 cases. The full hardware-free suite
collected 740: 719 passed, exactly 21 expected T007 missing-composition failures,
zero errors/skips. JUnit inspection verified the failure sets. Full pytest
exits 1 as intended; this is not complete runtime acceptance or a GREEN full gate.
Ruff passed; mypy reported no issues in 38 files; all three import contracts kept
(30 files, 68 dependencies); diff whitespace clean. Static checking caught an
optional RunId dereference in the task name; using the admitted local RunId
resolved it without changing behavior or tests.

Progress headers, T008 checkbox, quickstart, status, and this record were updated.
One code-only Graphify update produced 2,234 nodes, 5,199 edges, 108 communities;
24 labels refreshed from hubs. The known non-fatal zero-node pyproject.toml
warning recurred. Generated output stays ignored; no semantic extraction ran.
Existing tests, Acquisition and adapters, dependencies, schema-v1, architecture
rules, and committed baseline 6d10cf7 are unchanged; no commit was created.

T009–T028 remain unchecked. Basic composition, integration readback acceptance,
US2 cancellation/failure/transfer validation, and US3 autonomous termination
remain unimplemented/unaccepted. Normal-path evidence does not claim those
semantics. No Spec Kit stage or physical-hardware action/acceptance occurred.

## 2026-10-03 — Feature 005 T007 Basic Composition Contracts Staged RED

Delivered only the authorized T007 test step and stopped. Added
`core/tests/contract/test_observation_composition.py` with 21 cases. Each fails
explicitly on the missing Basic composition module/API (T009), without
collection errors, skips, xfail, production stubs, or lifecycle implementation.
A small admission probe captures guard/admission inputs and the preparation
callable; it implements no run ownership. T006 remains the runtime contract.

Contracts enforce context guard before any Profile read/stat; bounded explicit
Profile resolution before admission even while busy; invalid/missing/oversized/
unsupported Profile failure before busy; and no rejected journal create/open,
backend construct/open, Acquisition construction, destination inspection, or
hardware discovery. Preparation uses real temporary SQLite journals and the
actual Basic adapter with the existing private fake serial injection. Tests
cover exact path/policy/configuration, journal before unopened backend
construction/open, single existing Acquisition startup, no existing-file
overwrite/reopen, and captured values after Profile replacement/removal.

Fixture smoke passed bounded capture, immutable resolved values, exact journal
policy, fake-only Basic open, acknowledged segment provenance, single reader/
close, and existing-file protection, using existing production contracts only.
The initial full run found one new test-guard defect: a direct serial.tools
import violated the existing repository serial-surface contract. Reproduction
and source inspection isolated that import; a named fail-closed monkeypatch
target replaced it. The contract was not changed or exempted and passed again.

Final validation through uv with --no-sync and temporary UV_CACHE_DIR: Ruff
clean; mypy no issues in 38 files; all three import contracts kept (29 files,
66 dependencies); focused T001–T005 tests 89 passed; T007 focus 21 expected RED.
Full pytest collected 740, with 654 passed and exactly 86 expected failures:
65 T006 missing-runtime assertions and 21 T007 missing-composition assertions.
JUnit inspection verified those exact sets and zero errors/skips. This is an
intentional RED checkpoint, not a GREEN full gate or complete-feature acceptance.

Feature progress headers, task checkbox, quickstart, status, and this history
record were updated. T008–T028 remain unchecked. Production files, existing
foundation/T006 tests, shared fixtures, dependencies, schema-v1, and architecture
contracts are unchanged. No Spec Kit stage, Graphify update, or commit was run.
No physical hardware was discovered, enumerated, opened, accessed, or validated.

## 2026-10-03 — Feature 005 T006 Normal-Runtime Contracts Staged RED

Delivered only the authorized T006 test step and stopped. Added
`core/tests/contract/test_observation_runtime.py` with 65 collected cases over
the documented public lifecycle surface. A small test-only Protocol keeps
strict typing possible before the runtime implementation exists. Missing
ObservationRuntime produces explicit assertion failures rather than collection
errors; no fake runtime, production stub, skip, or xfail conceals the RED state.

Contracts cover construction on the owning running loop/thread; rejection
without a running loop before lock/task creation; same-context attach/detach
and nonmutating synchronous status; wrong context before locks, argument
validation, mutation, or preparation; and no rebinding after termination/loop
closure. The 45-case calling-context matrix covers attach/detach/status on
inactive/active/terminated runs in five contexts, including moving the same
loop to another thread to test thread binding separately from loop identity.
Returned immutable snapshots may be read elsewhere without runtime access.

Normal-run cases cover direct resolved-Profile busy rejection without any
Profile I/O/preparation; gated attaching/active/detaching status and committed
identity facts; fresh run/session/connection identities; exact policy by value;
idempotent inactive/settled detach; and physical close/consumer completion/final
append before recorder close. All resource work uses test-local deterministic
gates, the existing Basic-shaped normalized fake, and a real temporary SQLite
journal. Test watchdogs bound the checks, not production lifecycle behavior.

A fixture smoke check found that the Basic-shaped fake's default opaque
provenance intentionally lacks a durable envelope. Root-cause inspection of
the existing durable acquisition tests and feature-003 contract led to a
test-local normalized PersistedConnectionProvenance; the shared fixture and
journal code were unchanged. The corrected harness passed existing Acquisition
start/stop/join with exact teardown ordering and no runtime substitute.

Final verification through uv with --no-sync and a temporary UV_CACHE_DIR:
Ruff clean; mypy no issues in 37 files; all three import contracts kept (29
files, 66 dependencies); earlier feature-005 tests 89 passed; full pytest
collected 719, with 654 passed and exactly 65 expected T006 failures. JUnit
inspection confirmed every failure is the missing-runtime assertion in the new
file, with zero errors/skips and no earlier failure. Full pytest exits 1 as
intended; this is not a GREEN full software gate or feature acceptance.

Task/progress headers, quickstart, status, and this history record now describe
the RED checkpoint. T007–T028 remain unchecked; production runtime/composition,
cancellation/failure/disconnect implementation, delivery, and all accepted
deferrals remain unbuilt. No Spec Kit stage or Graphify update was run for this
test-only step; no dependency, architecture contract, schema-v1, or production
file was changed. The committed baseline remains 6d10cf7; no commit was created.
No physical hardware was discovered, enumerated, opened, accessed, or validated.

## 2026-10-03 — Feature 005 Foundations Complete (T001–T005 Only)

Completed the explicitly authorized first group and stopped at T005. The
accepted committed baseline remains `6d10cf7` on `main`; these changes are in
the working tree, with no new commit. T006–T028 are unchecked. No Spec Kit
stage was rerun, and no ObservationRuntime orchestration, Basic composition,
delivery, or deferred feature was implemented.

T001 confirmed the baseline and affected Acquisition/Basic/Profile/SQLite
consumers with 390 passing hardware-free tests. T002/T003 added the validated
frozen AcquisitionSnapshot and generation-captured join_terminated barrier.
Descriptor is distinct from acknowledged segment provenance; origin-reset
publication follows acknowledgment. Disconnect trigger is retained before a
possibly failed final append. The actual first non-close primary failure is
tracked at occurrence separately from physical-close failure and release
certainty, without decoding legacy failure. Legacy method returns, failure
objects, restart admission, Backend/evidence contracts, and schema-v1 remain
unchanged. The barrier waits startup settlement and actual consumer/close tasks,
returning its captured generation even if a newer start has replaced current
status.

T004/T005 added immutable run/state/intent/reason/issue/status values,
normalized request/preparation failures, and the minimal preparation/recorder
Protocols. RuntimeStatus computes admissibility from the exact state/settlement/
physical/recorder predicate and rejects impossible status combinations.
Prepared resources expose the immutable policy for comparison by value with
Profile; enforcement on runtime transfer remains orchestration work. Import
contracts now place runtime above Acquisition and prohibit runtime importing
adapters, with no exemption or dependency change. Complete Profile/session
association remains in-memory only as specified, not a new durable field.

RED/GREEN evidence: 15 initial Acquisition scenarios failed on missing additive
APIs, then passed. Review caught missing constructor validation that could admit
raw objects/non-boolean facts into the new snapshot; seven additional cases
failed with DID NOT RAISE, then passed after validation. All 67 runtime-value
cases failed because the planned module was absent, then passed; this includes
the complete 48-case state/owner/cleanup matrix. The final focused set passed
131 tests. No unresolved defect was found; existing cleanup-attestation limits
and legacy failure distinctions remain intentional documented constraints.

The full required gate passed through uv with --no-sync and an explicit
temporary UV_CACHE_DIR: Ruff clean; mypy no issues in 36 files; Import Linter
kept all three contracts (29 files, 66 dependencies); pytest passed 654 tests
with zero failures/skips; git diff --check clean. No lockfile changed. Partial
status, feature-artifact progress headers, and task checkboxes were updated.

One Graphify 0.9.48 code-only incremental update captured the new module and
shared interface additions: 2,113 nodes, 4,824 edges, 112 communities. It
reported the known non-fatal zero-node pyproject.toml warning and refreshed 23
community labels from their hubs. Generated output remains ignored; no semantic
extraction or labeling call was made.

All validation used fakes and temporary journals with the existing fail-closed
serial sentinel. No physical device was discovered, opened, modified, accessed,
or validated. Runtime orchestration and event-loop enforcement remain unbuilt;
Basic/SQLite composition, service/CLI, Monitor/TX/Control, reconnect/handoff,
session catalogue/durable Profile metadata, Enhanced/MCP/AI, and hardware
acceptance remain deferred.

## 2026-10-03 — Feature 005 Observation Runtime Planning Complete

Completed the explicitly authorized lean Spec Kit specify → plan → tasks
workflow for `005-observation-runtime`, using the repository's sequential
directory numbering. Git remains on `main`; no branch or commit was created.
The committed production baseline remains `6d10cf7` and features 001–004 remain
accepted. Feature 005 has eight planning artifacts and 28 unchecked future
implementation tasks; no production code or implementation test was written.

The internal contract defines inactive/attaching/active/detaching/terminated/
failed states, fail-fast busy attach, joined detach, one shielded generation
owner, immutable Profile activation, journal-before-backend startup, and
Acquisition/backend/consumer settlement before recorder close. Cancellation
requests stop and joins cleanup instead of cancelling physical/journal work;
partial failures preserve primary and bounded cleanup facts. Created journals
remain after failed/cancelled startup and later attaches create fresh sessions.

Profile/session association is one in-memory current/last run mapping only.
Existing durable policy and effective segment provenance remain historical;
schema-v1 is unchanged, and complete Profile or DUT/Profile identity recovery
after restart is not claimed. The plan adds only minimal normalized Acquisition
snapshot/join facts and a concrete Basic/SQLite composition edge, with shared
lifecycle tested identically against the existing Enhanced-shaped fixture.

Read-only research identified absent cleanup attestations in failed Basic open
and most failed journal-create paths. The design conservatively blocks reuse
of that runtime instance rather than silently inferring release or expanding
adapter contracts. Process restart/replacement is not proof of release.
Unexpected disconnect ends the run without automatic reopen and remains its
observed cause even if caller stop or cleanup failure races it.

Planning verification checked all eight artifacts for relative links, balanced
fences, missing template placeholders, sequential FR/SC/task identifiers,
required task format/file paths, story counts, parallel markers, and scope.
The document audit passed: 30 requirements, seven outcomes, 28 unchecked tasks
(US1 six, US2 seven, US3 five, setup/foundation/review ten), six parallel-marked
test tasks, and a 26-line Resume Here section. Diff whitespace and final changed
paths were also reviewed. uv's initial audit invocation could not write the
default cache in the sandbox; rerunning with an explicit temporary cache and
`--no-sync` succeeded without dependency changes.

No Ruff/mypy/Import Linter/pytest implementation gate was run: this task changed
planning/status/history documents only and introduced no executable code.
Future software validation is explicit in the task list/quickstart. No Graphify
update was required for documentation-only changes. Service/delivery, workflows,
TX/Control, reconnect/handoff, session catalogue, durable Profile metadata,
Enhanced production behavior, MCP/AI, and physical acceptance remain deferred.
No hardware was discovered, opened, accessed, modified, or validated.

## 2026-10-03 — Feature 004 Observation-Only DUT Profile Complete (T001–T021)

Completed the feature-004 production implementation and completion
documentation through T021. The software resolves one explicit caller-supplied
path containing strict, human-authored UTF-8 TOML with
`profile_version = 1`. The closed format is bounded to 65,536 serialized bytes;
resolution reads at most 65,537 bytes and enforces that ceiling on the captured
bytes before decoding or parsing. It returns immutable backend-neutral values
for DUT identity/name, explicit Basic selection and exact expected device, UART
configuration, DTR/RTS open intent, observation policy, and the existing
feature-003 `SessionPolicy` constructed directly from all six explicit finite
limits.

Profile v1 requires RX and evidence recording to remain enabled as mandatory
observation invariants. Its current permissions remain fail closed: UART TX,
semantic Control, and automatic reconnect are disabled. Opposite values and
recognized TX, Interact/console, Control, reconnect, or reacquire configuration
fail explicitly as `unsupported_behavior`; they are never silently ignored.
The deterministic failure matrix also distinguishes filesystem failures,
oversized input, invalid syntax, incompatible version, missing/unknown fields,
invalid values, and unsupported backends without exposing a parser tree,
partial result, or raw exception cause/context.

The generic Profile module contains no Basic or pySerial implementation type.
A TOML adapter owns filesystem/format resolution, and a separate pure Basic
adapter-side translator maps the resolved snapshot field-for-field into the
existing feature-002 `BasicSerialOpenRequest`. Resolution and translation do
not enumerate or open a device, construct a backend, start acquisition, create
a journal/session, or own lifecycle. No registry or generalized Profile manager
was introduced.

T018's final implementation review found and corrected four bounded defects.
Recognized Interact/console configuration had been classified as an unknown
field rather than unsupported behavior; invalid path values could leak a raw
`ValueError`; normalized failures retained raw exceptions through
`__context__`; and the quickstart import-search exclusion did not match the
nested Basic adapter path. Focused RED/GREEN regressions cover the behavioral
corrections, and the search was corrected and rerun.

Post-correction software validation passed 217 focused feature-004 tests and
565 full-repository tests with no failures or skips. Ruff passed, mypy reported
no issues in 33 source files, all 3 Import Linter contracts were kept after
analyzing 28 files and 56 dependencies, and `git diff --check` passed.

T020 confirmed that the shared Profile module and two adapter modules satisfy
Graphify's structural-change criteria, then ran the one required code-only
incremental update with Graphify 0.9.48. The ignored graph now contains 1,928
nodes, 4,471 edges, and 96 communities. Graphify reported one non-fatal
zero-node source (`pyproject.toml`) and refreshed 23 community names from their
hubs after the community set changed. No semantic/LLM extraction ran and no
generated Graphify output entered version control.

T021's fresh final gate passed: Ruff reported no violations; mypy reported no
issues in 33 source files; Import Linter kept all 3 contracts after analyzing 28
files and 56 dependencies; pytest passed 565 tests with 0 skipped and 0 failed;
and `git diff --check` passed. Feature 004 is software-complete and ready for
commit. The final pre-commit review corrected stale spec/status completion
metadata and found no production-contract defect.

Lifecycle and ownership, session orchestration, service/HTTP and authentication,
CLI, Monitor/follow, TX/Interact/console execution, semantic Control execution,
reconnect, release/reacquire/handoff, Enhanced, MCP, Profile discovery/default
paths, Profile writing/migration/overlay/reload, and numerical product defaults
remain deferred. No physical hardware was enumerated, opened, accessed,
modified, or validated, and no electrical or platform acceptance is claimed.

## 2026-10-01 — Feature 003 Durable Evidence Journal Complete (T001–T030)

Completed the feature-003 implementation and completion documentation for one
SQLite-backed durable session journal. The delivered software provides
immutable finite session policy, generic opaque provenance envelopes, canonical
exact-byte evidence storage, serialized durable append and reopen, rolling
bounded retention with a coalesced marker, stable reference resolution, bounded
fixed-snapshot raw pages, and fail-closed compatibility/corruption handling.
SQLite connections remain confined to their journal-owned single worker and
shared acquisition depends only on the backend-neutral recorder contract.

The accepted durability guarantee is intentionally limited to clean reopen and
tested software process-crash recovery under committed SQLite transactions.
Exactly-once retry after commit-before-return ambiguity, arbitrary power-loss or
lying flush hardware, and filesystem, media, directory, backup, or live-copy
survival are explicitly not guaranteed.

T028's final review found one lifecycle defect: cancellation of create/open
after worker submission could discard a successful bootstrap result without
closing its SQLite connection. A parametrized RED regression reproduced both
paths. The correction waits for the bootstrap worker, recovers a successful
result, closes the connection on that same owning worker, and then propagates
cancellation. The focused regression passed 2 tests, journal contract/recovery
passed 78 tests, the complete feature-003 group passed 137 tests, and the full
repository passed 347 tests with no failures. Ruff, mypy, all three Import
Linter contracts, and `git diff --check` passed in the T030 software validation.

Final pre-commit review found one further boundedness defect: corrupt persisted
sequence metadata could make open validation materialize an enormous expected
range before reporting corruption. A focused RED regression intercepted the
attempt at the signed-64-bit terminal value. Validation now compares row count
and contiguous sequence values without allocating from the persisted span; the
regression is GREEN. This is a fail-closed corruption correction only and adds
no persistence framework, migration, repair, or delivery behavior. The
corrected final candidate passed 348 tests with no failures or skips; Ruff,
mypy, all three Import Linter contracts, and `git diff --check` passed.

Graphify's structural-change criteria were evaluated. The one earlier
feature-003 incremental update already captured the new SQLite adapter and
shared provenance interface (1,426 nodes, 3,039 edges, 78 communities); T028's
localized private helper and regression test did not require another update.
No physical hardware was enumerated, opened, accessed, modified, or validated,
and no power-loss acceptance was performed.

## 2026-10-01 — Feature 003 Fail-Closed Open Validation (T026)

Made the T025 compatibility/corruption matrix GREEN with a bounded SQLite
adapter correction. Open now forces rollback-journal processing before
application validation, classifies stored decode failures as open failures,
maps malformed persisted invariants to corrupt-journal outcomes, and proves a
validated connection writable with a rolled-back no-op update before applying
the physical page ceiling. Supported generic envelopes still round-trip unknown
backend provenance kind/schema values opaquely, while SQLite operational errors
retain their normalized operational classifications. No migration, repair,
salvage, delivery behavior, or physical hardware work was added. The complete
feature-003 group passed 135 tests and the full repository passed 345 tests.

## 2026-10-01 — Feature 003 Compatibility/Corruption RED Matrix (T025)

Added 15 software-only contract cases for incompatible application, store,
record, and generic provenance-envelope versions; opaque unknown backend
provenance; missing schema objects; malformed metadata/payload invariants;
aggregate/sequence corruption; failed integrity checks; locked/read-only opens;
source preservation; and the rollback-recovery-before-validation exception.
The focused selection produced the intended 8 failures and 7 passing controls.
All 120 earlier feature-003 tests remain GREEN. No production code or physical
hardware was touched.

## 2026-10-01 — Feature 003 Pagination Validation Gate (T024)

Completed the software-only validation checkpoint before compatibility and
corruption work. The exact quickstart retention/reference/retrieval selection
passed 40 tests; the complete durable-journal model, codec, contract, recovery,
and acquisition-integration group passed 120 tests; and feature-001 evidence
ordering and timestamp regressions passed 64 tests. The full repository passed
330 tests. Ruff, mypy, all three Import Linter contracts, and
`git diff --check` passed. No defect was found and no production or test code
changed. No physical hardware was accessed.

## 2026-10-01 — Feature 003 Stable Pagination Continuation (T023)

Completed fixed-snapshot continuation and explicit between-page expiry for the
bounded raw evidence journal. Continuations now preserve the first page's
exclusive snapshot boundary, exclude later appends, report a newly expired
cursor-to-low-water interval with the current coalesced retention marker, and
resume retained sequence-key retrieval without changing T022's page bounds or
whole-record behavior. Both remaining T021 RED cases pass. No external cursor
encoding, delivery schema, or physical hardware behavior was added.

## 2026-10-01 — Feature 003 Bounded Raw Retrieval (T022)

Implemented policy-capped, whole-record raw evidence pages ordered by durable
sequence, with charged-byte accounting, oversized-next-record reporting, and
typed keyset continuation cursors. Retrieval values now live in the planned
backend-neutral `evidence.py` contract; SQLite remains confined to its adapter
and journal worker. T020's nine pagination cases pass. Five T021 cursor,
lock-release, and cancellation cases pass; fixed-snapshot continuation and
between-page expiry remain intentionally RED for T023. No physical hardware
was accessed.

## 2026-09-30 — Feature 003 Durable Journal Foundation (T001–T005)

Completed the software-only durable value, codec, and SQLite bootstrap
foundation. No physical device was enumerated, opened, modified, or validated.

### Delivered

- Added immutable session identity, finite session policy with independent
  retrieval ceilings, signed-64-bit persisted counter/sequence validation,
  stable references, retention endpoints, retrieval values, and normalized
  journal failures.
- Added generic provenance envelope version 1 with opaque backend kind/schema
  version and scalar-only sorted fields. Basic serial owns its flattened
  mapping; unknown conforming backend values remain opaque and round-trip.
- Added strict canonical JSON metadata codecs for all four current evidence
  variants, exact RX BLOB handling, and deterministic logical byte charge.
- Added one-session SQLite schema-version-1 create/open/close with `DUTM`
  application identity, 4096-byte pages, rollback `DELETE`, `synchronous=FULL`,
  persisted immutable policy, and no added runtime dependency.
- Persisted `max_database_pages` as policy while reapplying and verifying
  `max_page_count` on every writable create/open. Oversized databases and an
  unavailable requested ceiling have distinct normalized failures.
- Confined each connection's creation, use, and close to one journal-owned
  `ThreadPoolExecutor(max_workers=1)` worker with one asyncio serialization
  gate. Shared Core still does not import adapters; no architecture exemption
  was added.
- Stopped before durable append, retention, retrieval, recovery subprocesses,
  cancellation/commit ambiguity, delivery surfaces, or hardware behavior.

### Validation Evidence

- RED: the initial model suite failed 45 tests for missing feature-003 values;
  the codec/bootstrap suite failed 14 tests for absent codecs/journal behavior;
  two follow-up invariant tests failed before their minimal validations were
  added.
- `uv run --frozen pytest core/tests/unit/test_evidence_journal_model.py
  core/tests/unit/test_sqlite_evidence_codec.py
  core/tests/contract/test_sqlite_evidence_journal.py -q`: 62 passed.
- `uv run --frozen ruff check .`: passed.
- `uv run --frozen mypy .`: no issues in 25 source files.
- `uv run --frozen lint-imports`: 3 contracts kept, 0 broken.
- `uv run --frozen pytest`: 272 passed, 0 skipped, 0 failed.
- `git diff --check`: passed.
- No physical hardware was touched.

## 2026-09-30 — Feature 002 Basic Serial Backend Adapter (T001–T020)

Completed the first production Basic serial adapter behind feature 001's
normalized backend contract. This is a software-only completion record; no
physical serial device was accessed or validated.

### Delivered

- Added and locked pySerial 3.5 plus types-pyserial 3.5.0.20260712, confined
  pySerial imports and implementation types to
  `dutchmate_core.adapters.basic_serial`, and extended shared Core only with
  opaque immutable connection provenance and normalized failure values.
- Required an exact explicit platform device name. The adapter performs no
  enumeration, discovery, URL handling, automatic choice, implicit default, or
  fallback selection.
- Constructed `serial.Serial(port=None)`, configured the complete supported
  UART, flow-control, exclusivity, and line-state intent while closed, and
  called `open()` exactly once after configuration. Successful provenance
  preserves selected/opened names and requested/effective configuration.
- Applied DTR and applicable static RTS intent before open; under RTS/CTS, RTS
  remains driver-managed. Provenance records the preconfigured-while-closed
  strategy and honestly marks glitch-free transition as not guaranteed and
  physical electrical state as not verified. This is serial-open handling, not
  semantic Control.
- Reported only `uart_receive`. Successful connections receive fresh
  connection/segment identity and a fresh host-observation timestamp
  domain/origin; acquisition copies adapter provenance unchanged without a
  Basic identity branch.
- Implemented one sequential blocking `read()` at a time through
  `asyncio.to_thread`, capturing `monotonic_ns` immediately after read return
  in the same worker. Normalized RX preserves exact bytes and return order;
  empty reads emit nothing, and no adapter queue, prefetch path, or concurrent
  reader exists.
- Normalized open, read, and close failures without leaking pySerial/OS objects.
  Device loss is emitted only when stable exception attributes positively
  identify disappearance; ambiguous failures remain `read/io_failure`, and
  exception message text never controls classification.
- Implemented caller/lifecycle-thread `cancel_read()`, mandatory outstanding
  read completion before one physical close, and idempotent repeated/concurrent
  close. Acquisition remains non-restartable through physical teardown,
  preserves an established primary failure, blocks restart after unconfirmed
  release, and emits no duplicate terminal segment evidence.
- Added fake-driven adapter-through-acquisition coverage for immutable
  provenance, ambient exact-byte RX, host timestamp provenance, device loss,
  ambiguous read failure, explicit stop/close ordering, and second-owner
  rejection.
- Added fail-closed hardware-safety guards: the default test suite cannot invoke
  the physical serial factory, and static tests reject serial enumeration,
  pySerial URL handlers, URL-like selectors, or automatic device selection.

### T019 Correction

Final diff review found an FR-024 defect: a failing `cancel_read()` caused the
adapter to skip joining the outstanding blocking read and proceed to physical
close. A focused RED regression observed one physical close while the read was
still active. The corrected close path always awaits that read before its
single physical close while retaining the normalized cancellation failure;
the focused contract suite then passed 56 tests.

### Validation Evidence

- `uv run --frozen ruff check .`: passed.
- `uv run --frozen mypy .`: no issues in 20 source files.
- `uv run --frozen lint-imports`: 3 contracts kept, 0 broken.
- `uv run --frozen pytest`: 210 passed, 0 skipped, 0 failed.
- `git diff --check`: passed.
- Focused feature-002 model, adapter-contract, integration, and safety groups
  passed; all feature-001 regression groups remained GREEN.
- Focused diff/search review found no Basic identity branch or pySerial object
  outside the adapter boundary; no discovery/URL-handler path, raw exception
  leak, concurrent/duplicate RX path, timestamp-based evidence ordering,
  semantic Control, TX, reconnect, delivery surface, Enhanced implementation,
  firmware, or MCP was introduced.
- No physical serial hardware was enumerated, opened, modified, or validated.
  Platform/electrical acceptance remains explicitly deferred.

## 2026-09-29 — Feature 001 Lifecycle Correction

Closed the teardown and terminal-state gaps found in the final pre-commit
review.

### Delivered

- Acquisition now remains non-restartable in `stopping` until its one physical
  connection close finishes; successful teardown exposes `stopped` only after
  close completion.
- Each acquisition consumer captures its generation's termination event, so a
  prior task cannot signal a later generation.
- Backend-open failure now enters `failed`, signals termination, preserves and
  re-raises the original exception, creates no connection/segment evidence or
  consumer task, and permits a later valid start.
- Unexpected normal stream completion now records a transport-failure segment
  end before teardown.
- Close failure cannot strand acquisition in `stopping`. An existing primary
  recording/transport failure is preserved; otherwise close failure becomes the
  terminal transport failure. Because physical close is unconfirmed, a new
  owner remains rejected.
- Removed the deferred `ownership_lost` segment reason and ownership-loss
  lifecycle wording from the focused feature 001 documents.

### Validation Evidence

- RED: 5 focused lifecycle tests failed for the intended missing behavior:
  premature `stopped`, open failure left in `starting`, absent stream-end
  evidence, premature `failed` during close, and duplicate terminal evidence
  when close failed.
- GREEN: focused acquisition suite passed 29 tests; feature quickstart suites
  passed 31 model/backend tests and 35 evidence/acquisition tests.
- `uv run --frozen ruff check .`: passed.
- `uv run --frozen mypy .`: no issues in 15 source files.
- `uv run --frozen lint-imports`: 2 contracts kept, 0 broken.
- `uv run --frozen pytest`: 66 passed, 0 skipped, 0 failed.
- `git diff --check`: passed.
- No physical hardware was touched.

Feature `001-rx-continuous-evidence` is ready to commit against its focused
specification. Real adapters, durability, workflows, delivery surfaces, and
later phases remain deferred.

## 2026-09-29 — Feature 001 Timestamp-Regression Correction

Closed the final conformance gap found during T019–T021 review.

### Delivered

- Added acquisition regression coverage for decreasing timestamps and proved
  the original path incorrectly stopped normally while recording the offending
  observation.
- Added a per-segment baseline shared by timestamped RX/loss observations. The
  baseline advances only after successful evidence recording and resets after a
  successfully recorded timestamp-origin segment transition.
- A decreasing timestamp in the current domain/origin now ends the segment with
  an explicit transport failure. Earlier evidence and sequence values remain
  unchanged; the offending observation is not recorded.
- Strengthened origin-reset coverage to accept a lower timestamp in the new
  domain/origin, while preserving equal-timestamp behavior within a segment.

### Validation Evidence

- RED: 2 focused tests failed because acquisition returned `stopped` instead of
  `failed` for RX→RX and loss→RX timestamp regressions.
- GREEN: focused acquisition suite passed 24 tests.
- `uv run --frozen ruff check .`: passed.
- `uv run --frozen mypy .`: no issues in 15 source files.
- `uv run --frozen lint-imports`: 2 contracts kept, 0 broken.
- `uv run --frozen pytest`: 61 passed, 0 skipped, 0 failed.
- `git diff --check`: passed.
- No physical hardware was touched.

Feature `001-rx-continuous-evidence` now satisfies its focused specification.
Real adapters, durability, workflows, delivery surfaces, and later phases remain
deferred.

## 2026-09-29 — Feature 001 Validation and Documentation (T019–T021)

Completed the T019–T021 validation/documentation slice for the first Phase 1
software foundation. The feature remains open because final specification
review found one implementation gap not covered by the passing suite.

### Delivered

- Established the Python 3.14 uv workspace and `dutchmate-core` package.
- Added the normalized backend and single-consumer connection boundary.
- Added exact-byte RX evidence, Core-assigned journal sequence ordering,
  connection/segment provenance, timestamp-domain/origin validation, and
  observer-scoped loss evidence.
- Added exclusive continuous acquisition, explicit disconnect/stop/failure
  behavior, and timestamp-origin segment transitions.
- Proved backend-neutral shared behavior with hardware-free Basic-shaped and
  Enhanced-shaped test fixtures. The Enhanced-shaped fixture is not a real
  backend and simulates no helper protocol, firmware, USB framing, or hardware
  timing.
- Added import-linter contracts for inward Core module dependencies and the
  production/test-framework boundary.

### Validation Evidence

- `uv sync --all-packages --dev`: resolved 20 packages; audited 19 packages.
- Focused quickstart suites: 31 model/contract tests and 28
  evidence/acquisition tests passed.
- `uv run --frozen ruff check .`: passed.
- `uv run --frozen mypy .`: no issues in 15 source files.
- `uv run --frozen lint-imports`: 2 contracts kept, 0 broken.
- `uv run --frozen pytest`: 59 passed, 0 skipped, 0 failed.
- `git diff --check`: passed.
- Scope scan found no Basic identity branch, serial/framework dependency,
  Enhanced implementation, or later-phase product code above the normalized
  boundary.
- No physical hardware was touched.

### Limitations Retained

Real Basic serial transport and hardware acceptance, durable persistence and
retention, workflows, service/HTTP, CLI, Enhanced hardware/protocol/firmware,
and MCP remain deferred. The in-memory journal and both backend shapes are
software test infrastructure, not production adapters or durability claims.

Graphify's initial code-only structural index was generated for the new shared
interfaces. Its diagnostic reported 29 dangling endpoints and 62 same-endpoint
collapsed-edge candidates; documentation semantic indexing was unavailable
because Graphify's optional backend package is not installed.

Final specification review found that acquisition does not reject an undeclared
decreasing timestamp in the current domain/origin, contrary to the feature
specification's Edge Cases. No production behavior was added because this slice
was restricted to T019–T021. A focused red-green correction remains required
before feature `001` can be declared complete. That gap was closed by the newer
record above.
