     1|---
     2|name: systematic-debugging
     3|description: "4-phase root cause debugging: understand bugs before fixing."
     4|version: 1.1.0
     5|author: the project
     6|license: MIT
     7|platforms: [linux, macos, windows]
     8|metadata:
     9|  hermes:
    10|    tags: [debugging, troubleshooting, problem-solving, root-cause, investigation]
    11|    related_skills: [clean-code, ddd-development, pd, plan, subagent-driven-development, test-driven-development]
    12|---
    13|
    14|# Systematic Debugging
    15|
    16|## Overview
    17|
    18|Random fixes waste time and create new bugs. Quick patches mask underlying issues.
    19|
    20|**Core principle:** ALWAYS find root cause before attempting fixes. Symptom fixes are failure.
    21|
    22|**Violating the letter of this process is violating the spirit of debugging.**
    23|
    24|## The Iron Law
    25|
    26|```
    27|NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST
    28|```
    29|
    30|If you haven't completed Phase 1, you cannot propose fixes.
    31|
    32|## When to Use
    33|
    34|Use for ANY technical issue:
    35|- Test failures
    36|- Bugs in production
    37|- Unexpected behavior
    38|- Performance problems
    39|- Build failures
    40|- Integration issues
    41|
    42|**Use this ESPECIALLY when:**
    43|- Under time pressure (emergencies make guessing tempting)
    44|- "Just one quick fix" seems obvious
    45|- You've already tried multiple fixes
    46|- Previous fix didn't work
    47|- You don't fully understand the issue
    48|
    49|**Don't skip when:**
    50|- Issue seems simple (simple bugs have root causes too)
    51|- You're in a hurry (rushing guarantees rework)
    52|- Someone wants it fixed NOW (systematic is faster than thrashing)
    53|
    54|## The Four Phases
    55|
    56|You MUST complete each phase before proceeding to the next.
    57|
    58|---
    59|
    60|## Phase 1: Root Cause Investigation
    61|
    62|**BEFORE attempting ANY fix:**
    63|
    64|### 1. Read Error Messages Carefully
    65|
    66|- Don't skip past errors or warnings
    67|- They often contain the exact solution
    68|- Read stack traces completely
    69|- Note line numbers, file paths, error codes
    70|
    71|**Action:** Use `read_file` on the relevant source files. Use `search_files` to find the error string in the codebase.
    72|
    73|### 2. Reproduce Consistently
    74|
    75|- Can you trigger it reliably?
    76|- What are the exact steps?
    77|- Does it happen every time?
    78|- If not reproducible → gather more data, don't guess
    79|
    80|**Action:** Use the `terminal` tool to run the failing test or trigger the bug:
    81|
    82|```bash
    83|# Run specific failing test
    84|pytest tests/test_module.py::test_name -v
    85|
    86|# Run with verbose output
    87|pytest tests/test_module.py -v --tb=long
    88|```
    89|
    90|### 3. Check Recent Changes
    91|
    92|- What changed that could cause this?
    93|- Git diff, recent commits
    94|- New dependencies, config changes
    95|
    96|**Action:**
    97|
    98|```bash
    99|# Recent commits
   100|git log --oneline -10
   101|
   102|# Uncommitted changes
   103|git diff
   104|
   105|# Changes in specific file
   106|git log -p --follow src/problematic_file.py | head -100
   107|```
   108|
   109|### 4. Gather Evidence in Multi-Component Systems
   110|
   111|**WHEN system has multiple components (API → service → database, CI → build → deploy):**
   112|
   113|**BEFORE proposing fixes, add diagnostic instrumentation:**
   114|
   115|For EACH component boundary:
   116|- Log what data enters the component
   117|- Log what data exits the component
   118|- Verify environment/config propagation
   119|- Check state at each layer
   120|
   121|Run once to gather evidence showing WHERE it breaks.
   122|THEN analyze evidence to identify the failing component.
   123|THEN investigate that specific component.
   124|
   125|### 5. Trace Data Flow
   126|
   127|**WHEN error is deep in the call stack:**
   128|
   129|- Where does the bad value originate?
   130|- What called this function with the bad value?
   131|- Keep tracing upstream until you find the source
   132|- Fix at the source, not at the symptom
   133|
   134|**Action:** Use `search_files` to trace references:
   135|
   136|```python
   137|# Find where the function is called
   138|search_files("function_name(", path="src/", file_glob="*.py")
   139|
   140|# Find where the variable is set
   141|search_files("variable_name\\s*=", path="src/", file_glob="*.py")
   142|```
   143|
   144|### Phase 1 Completion Checklist
   145|
   146|- [ ] Error messages fully read and understood
   147|- [ ] Issue reproduced consistently
   148|- [ ] Recent changes identified and reviewed
   149|- [ ] Evidence gathered (logs, state, data flow)
   150|- [ ] Problem isolated to specific component/code
   151|- [ ] Root cause hypothesis formed
   152|
   153|**STOP:** Do not proceed to Phase 2 until you understand WHY it's happening.
   154|
   155|---
   156|
   157|## Phase 2: Pattern Analysis
   158|
   159|**Find the pattern before fixing:**
   160|
   161|### 1. Find Working Examples
   162|
   163|- Locate similar working code in the same codebase
   164|- What works that's similar to what's broken?
   165|
   166|**Action:** Use `search_files` to find comparable patterns:
   167|
   168|```python
   169|search_files("similar_pattern", path="src/", file_glob="*.py")
   170|```
   171|
   172|### 2. Compare Against References
   173|
   174|- If implementing a pattern, read the reference implementation COMPLETELY
   175|- Don't skim — read every line
   176|- Understand the pattern fully before applying
   177|
   178|### 3. Identify Differences
   179|
   180|- What's different between working and broken?
   181|- List every difference, however small
   182|- Don't assume "that can't matter"
   183|
   184|### 4. Understand Dependencies
   185|
   186|- What other components does this need?
   187|- What settings, config, environment?
   188|- What assumptions does it make?
   189|
   190|---
   191|
   192|## Phase 3: Hypothesis and Testing
   193|
   194|**Scientific method:**
   195|
   196|### 1. Form a Single Hypothesis
   197|
   198|- State clearly: "I think X is the root cause because Y"
   199|- Write it down
   200|- Be specific, not vague
   201|
   202|### 2. Test Minimally
   203|
   204|- Make the SMALLEST possible change to test the hypothesis
   205|- One variable at a time
   206|- Don't fix multiple things at once
   207|
   208|### 3. Verify Before Continuing
   209|
   210|- Did it work? → Phase 4
   211|- Didn't work? → Form NEW hypothesis
   212|- DON'T add more fixes on top
   213|
   214|### 4. When You Don't Know
   215|
   216|- Say "I don't understand X"
   217|- Don't pretend to know
   218|- Ask the user for help
   219|- Research more
   220|
   221|---
   222|
   223|## Phase 4: Implementation
   224|
   225|**Fix the root cause, not the symptom:**
   226|
   227|### 1. Create Failing Test Case
   228|
   229|- Simplest possible reproduction
   230|- Automated test if possible
   231|- MUST have before fixing
   232|- Use the `test-driven-development` skill
   233|
   234|### 2. Implement Single Fix
   235|
   236|- Address the root cause identified
   237|- ONE change at a time
   238|- No "while I'm here" improvements
   239|- No bundled refactoring
   240|
   241|### 3. Verify Fix
   242|
   243|```bash
   244|# Run the specific regression test
   245|pytest tests/test_module.py::test_regression -v
   246|
   247|# Run full suite — no regressions
   248|pytest tests/ -q
   249|```
   250|
   251|### 4. If Fix Doesn't Work — The Rule of Three
   252|
   253|- **STOP.**
   254|- Count: How many fixes have you tried?
   255|- If < 3: Return to Phase 1, re-analyze with new information
   256|- **If ≥ 3: STOP and question the architecture (step 5 below)**
   257|- DON'T attempt Fix #4 without architectural discussion
   258|
   259|### 5. If 3+ Fixes Failed: Question Architecture
   260|
   261|**Pattern indicating an architectural problem:**
   262|- Each fix reveals new shared state/coupling in a different place
   263|- Fixes require "massive refactoring" to implement
   264|- Each fix creates new symptoms elsewhere
   265|
   266|**STOP and question fundamentals:**
   267|- Is this pattern fundamentally sound?
   268|- Are we "sticking with it through sheer inertia"?
   269|- Should we refactor the architecture vs. continue fixing symptoms?
   270|
   271|**Discuss with the user before attempting more fixes.**
   272|
   273|This is NOT a failed hypothesis — this is a wrong architecture.
   274|
   275|---
   276|
   277|## Red Flags — STOP and Follow Process
   278|
   279|If you catch yourself thinking:
   280|- "Quick fix for now, investigate later"
   281|- "Just try changing X and see if it works"
   282|- "Add multiple changes, run tests"
   283|- "Skip the test, I'll manually verify"
   284|- "It's probably X, let me fix that"
   285|- "I don't fully understand but this might work"
   286|- "Pattern says X but I'll adapt it differently"
   287|- "Here are the main problems: [lists fixes without investigation]"
   288|- Proposing solutions before tracing data flow
   289|- **"One more fix attempt" (when already tried 2+)**
   290|- **Each fix reveals a new problem in a different place**
   291|
   292|**ALL of these mean: STOP. Return to Phase 1.**
   293|
   294|**If 3+ fixes failed:** Question the architecture (Phase 4 step 5).
   295|
   296|## Common Rationalizations
   297|
   298|| Excuse | Reality |
   299||--------|---------|
   300|| "Issue is simple, don't need process" | Simple issues have root causes too. Process is fast for simple bugs. |
   301|| "Emergency, no time for process" | Systematic debugging is FASTER than guess-and-check thrashing. |
   302|| "Just try this first, then investigate" | First fix sets the pattern. Do it right from the start. |
   303|| "I'll write test after confirming fix works" | Untested fixes don't stick. Test first proves it. |
   304|| "Multiple fixes at once saves time" | Can't isolate what worked. Causes new bugs. |
   305|| "Reference too long, I'll adapt the pattern" | Partial understanding guarantees bugs. Read it completely. |
   306|| "I see the problem, let me fix it" | Seeing symptoms ≠ understanding root cause. |
   307|| "One more fix attempt" (after 2+ failures) | 3+ failures = architectural problem. Question the pattern, don't fix again. |
   308|
   309|## Quick Reference
   310|
   311|| Phase | Key Activities | Success Criteria |
   312||-------|---------------|------------------|
   313|| **1. Root Cause** | Read errors, reproduce, check changes, gather evidence, trace data flow | Understand WHAT and WHY |
   314|| **2. Pattern** | Find working examples, compare, identify differences | Know what's different |
   315|| **3. Hypothesis** | Form theory, test minimally, one variable at a time | Confirmed or new hypothesis |
   316|| **4. Implementation** | Create regression test, fix root cause, verify | Bug resolved, all tests pass |
   317|
   318|## Hermes Agent Integration
   319|
   320|### Investigation Tools
   321|
   322|Use these Hermes tools during Phase 1:
   323|
   324|- **`search_files`** — Find error strings, trace function calls, locate patterns
   325|- **`read_file`** — Read source code with line numbers for precise analysis
   326|- **`terminal`** — Run tests, check git history, reproduce bugs
   327|- **`web_search`/`web_extract`** — Research error messages, library docs
   328|
   329|## Python Debugging (pdb + debugpy)
   330|
   331|Three tools, picked by situation:
   332|
   333|| Tool | When |
   334||---|---|
   335|| **`breakpoint()` + pdb** | Local, interactive, simplest. Add `breakpoint()` in source, run normally. |
   336|| **`python -m pdb`** | Launch script under pdb with no source edits. |
   337|| **`debugpy`** | Remote/headless. Talks DAP, works for long-lived processes (gateway, daemon). |
   338|
   339|### pdb Quick Reference
   340|
   341|| Command | Action |
   342||---|---|
   343|| `n` | next line (step over) |
   344|| `s` | step into |
   345|| `r` | return from current function |
   346|| `c` | continue |
   347|| `w` | where (stack trace) |
   348|| `p expr` / `pp expr` | print / pretty-print |
   349|| `b file:line` | set breakpoint |
   350|| `interact` | drop into full Python REPL in current scope |
   351|| `!stmt` | execute arbitrary Python |
   352|
   353|### Recipe: Local breakpoint
   354|```python
   355|def compute(x, y):
   356|    result = some_helper(x)
   357|    breakpoint()           # drops into pdb here
   358|    return result + y
   359|```
   360|
   361|### Recipe: Debug pytest
   362|```bash
   363|pytest tests/test_module.py::test_name --pdb       # drop on failure
   364|pytest tests/test_module.py::test_name --trace     # drop at start
   365|pytest tests/test_module.py --showlocals --tb=long  # show locals
   366|# NOTE: pdb doesn't work under xdist. Add -p no:xdist
   367|```
   368|
   369|### Recipe: Post-mortem
   370|```python
   371|import pdb, sys
   372|try:
   373|    run_the_thing()
   374|except Exception:
   375|    pdb.post_mortem(sys.exc_info()[2])
   376|```
   377|
   378|### Recipe: Remote debug with debugpy
   379|```python
   380|import debugpy
   381|debugpy.listen(("127.0.0.1", 5678))
   382|debugpy.wait_for_client()
   383|debugpy.breakpoint()
   384|```
   385|Or launch: `python -m debugpy --listen 127.0.0.1:5678 --wait-for-client script.py`
   386|
   387|### Recipe: remote-pdb (cleanest for agents)
   388|```python
   389|from remote_pdb import set_trace
   390|set_trace(host="127.0.0.1", port=4444)
   391|# Then: nc 127.0.0.1 4444
   392|```
   393|
   394|### Pitfalls
   395|- pdb under pytest-xdist silently does nothing — use `-p no:xdist`
   396|- `breakpoint()` in CI hangs — add pre-commit grep: `rg -n 'breakpoint()' --type py`
   397|- `PYTHONBREAKPOINT=0` disables all breakpoints
   398|- pdb only debugs current thread — use debugpy for multithreaded
   399|- For asyncio: `await` inside pdb needs Python 3.13+ or workarounds on older versions
   400|
   401|## Node.js Debugging (node inspect + CDP)
   402|
   403|Two tools:
   404|
   405|| Tool | When |
   406||---|---|
   407|| **`node inspect`** | Built-in, zero install, CLI REPL. Quick poking. |
   408|| **CDP via `chrome-remote-interface`** | Scriptable from agent loops, many breakpoints. |
   409|
   410|### node inspect REPL
   411|```bash
   412|node inspect path/to/script.js
   413|node --inspect-brk $(which tsx) path/to/script.ts
   414|```
   415|
   416|| Command | Action |
   417||---|---|
   418|| `c` / `cont` | continue |
   419|| `n` / `next` | step over |
   420|| `s` / `step` | step into |
   421|| `sb('file.js', 42)` | set breakpoint |
   422|| `bt` | backtrace |
   423|| `repl` | drop into REPL in current scope |
   424|| `exec expr` | evaluate expression |
   425|
   426|### Attach to running process
   427|```bash
   428|kill -SIGUSR1 <pid>  # enable inspector
   429|node inspect -p <pid>
   430|```
   431|
   432|### Pitfalls
   433|- `--inspect` vs `--inspect-brk`: `-brk` pauses on first line
   434|- Default port 9229 — collisions with multiple processes
   435|- `--inspect` on parent does NOT inspect children — use `NODE_OPTIONS`
   436|- Source maps: use `sb('src/app.tsx', N)` only with CDP clients, not `node inspect` CLI
   437|
   438|## Hermes TUI Debugging
   439|
   440|Hermes slash commands span three layers: Python registry → tui_gateway JSON-RPC → Ink/TypeScript frontend.
   441|
   442|### Investigation
   443|1. Check if command exists in TUI: `search_files --pattern "/commandname" --file_glob "*.ts" --path ui-tui/`
   444|2. Check Python backend: `search_files --pattern "CommandDef" --path hermes_cli/commands.py`
   445|3. Check gateway: `search_files --pattern "complete.slash|slash.exec" --path tui_gateway/`
   446|
   447|### Common Issues
   448|- **Command in TUI but not autocomplete** — missing from `COMMAND_REGISTRY` in `hermes_cli/commands.py`
   449|- **Command in autocomplete but doesn't work** — check handler in `tui_gateway/server.py`
   450|- **Behavior differs CLI vs TUI** — different implementations; check both `cli.py` and TUI local handler
   451|- **Config persists but UI doesn't update** — also patch nanostore state: `patchUiState(...)`
   452|
   453|### Debugging Tactics
   454|- **Python side hangs** — use `remote-pdb` at handler entry
   455|- **Ink side not reacting** — use `node inspect` in `app.tsx` slash dispatch
   456|- **Registry mismatch** — compare `COMMAND_REGISTRY` entry against TUI local command list
   457|
   458|## With delegate_task
   459|
   460|For complex multi-component debugging, dispatch investigation subagents:
   461|
   462|```python
   463|delegate_task(
   464|    goal="Investigate why [specific test/behavior] fails",
   465|    context="""
   466|    Follow systematic-debugging skill:
   467|    1. Read the error message carefully
   468|    2. Reproduce the issue
   469|    3. Trace the data flow to find root cause
   470|    4. Report findings — do NOT fix yet
   471|
   472|    Error: [paste full error]
   473|    File: [path to failing code]
   474|    Test command: [exact command]
   475|    """,
   476|    toolsets=['terminal', 'file']
   477|)
   478|```
   479|
   480|### With test-driven-development
   481|
   482|When fixing bugs:
   483|1. Write a test that reproduces the bug (RED)
   484|2. Debug systematically to find root cause
   485|3. Fix the root cause (GREEN)
   486|4. The test proves the fix and prevents regression
   487|
   488|## Real-World Impact
   489|
   490|From debugging sessions:
   491|- Systematic approach: 15-30 minutes to fix
   492|- Random fixes approach: 2-3 hours of thrashing
   493|- First-time fix rate: 95% vs 40%
   494|- New bugs introduced: Near zero vs common
   495|
   496|**No shortcuts. No guessing. Systematic always wins.**
   497|