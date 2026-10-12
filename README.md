# Compiler Verification Lab

A complete local verification workflow for C++ and GPU compilers: generate legal programs, compile and execute them, compare with specified semantics, preserve failures, minimize them, and replay regressions. This release replaces the earlier starter project.

## Start here

On this Windows machine, double-click **START_HERE.cmd**. Python is already installed and the portable compiler is included in the Windows bundle. The launcher runs the automated tests, a native compiler campaign, fault detection, reduction and regression replay, then opens an offline dashboard. No NVIDIA GPU is required for this workflow.

To study the completed run without running anything, open **evidence/final-demo/campaign/index.html**, then read **STUDY_GUIDE.md**. The saved demonstration is a real compiled C++ run, not model simulation.

The source-only ZIP omits the portable compiler. Its Windows launcher downloads the pinned compiler and verifies its checksum automatically when a host compiler is unavailable. The Windows bundle includes that toolchain for offline use. Neither changes your system PATH.

## What is complete

| Feature | Implementation |
|---|---|
| Defined language semantics | uint32 arithmetic and bitwise operators, map and reduction kernels |
| Generation | Deterministic seeds, boundary cases, variable-depth programs, three metamorphic transformations |
| Native compilers | GCC/Clang argument adapters; portable Zig/Clang on Windows; configurable release/option profiles |
| GPU source | CUDA map kernels and synchronized shared-memory reduction kernels |
| PTX paths | CUDA to driver-JIT PTX, CUDA to offline cubin, direct PTX microtests |
| GPU execution | Isolated CUDA Driver API worker and standalone CUDA Runtime executables |
| Sanitizers | memcheck, initcheck, racecheck and synccheck profiles |
| Automation | Persistent SQLite work queue, local parallel workers, leases, heartbeats, retries and resume |
| Triage | Exact comparisons, crash/error/timeout classification, flaky-result detection and checksummed artifacts |
| Reduction | Real-backend reduction with repeated execution, a budget, and explicit minimality scope |
| Regression | Stored expected outputs checked against corrected profiles |
| Results | Searchable offline HTML dashboard, JSON reports and SQLite history |
| Delivery | One-click launcher, tests, CPU Dockerfile, CPU CI and manually triggered GPU CI definition |

CUDA/PTX execution is implemented but **has not been tested on NVIDIA hardware here**. Those paths report a skip when a GPU is absent. Docker, hosted CI, Linux/Jetson and additional compiler releases are supplied configurations, not executed validation claims. See VALIDATION.md for measured results.

## Commands

Run commands from the project directory with Python 3.10 or newer. No Python packages are required.

```powershell
python verifylab.py doctor
python -m unittest discover -s tests -v
python verifylab.py demo --count 24 --jobs 2 --out runs/my-demo
python verifylab.py campaign --count 100 --jobs 2 --out runs/my-campaign
python verifylab.py campaign --out runs/my-campaign --resume
python verifylab.py run --backend cpp --seed 42 --out runs/case42
python verifylab.py run --backend cpp --kind reduce --seed 5 --out runs/reduction-kernel
```

The default campaign uses an available host compiler at O0 and O2. If no compiler is available, it explicitly falls back to a model-only campaign; its dashboard reports zero native passes. The one-click launcher instead obtains a native compiler on supported Windows machines.

Use `--matrix configs/host.json` on a machine with both GCC and Clang. A matrix is a list of named profiles, each specifying a backend, an argument-array compiler command and flags. Different absolute compiler paths can select different installed releases without changing the engine.

For the supplied native fault evidence:

```powershell
python verifylab.py replay evidence/final-demo/reduction/final --out runs/reproduced-fault
python verifylab.py reduce evidence/final-demo/reduction/final --out runs/reduced-again
python verifylab.py regress evidence/final-demo/corpus --out runs/regression
```

The replay command intentionally exits 1 because the saved profile injects a known fault. The regression command removes injection and expects PASS. Replay checks all retained artifact hashes before executing. Profiles record the original compiler path and binary hash: when moving to another machine, use `run --case <saved-case> --backend cpp` with its local compiler to create a new run rather than pretending to reproduce the original environment exactly.

GPU commands, for a compatible NVIDIA environment:

```powershell
python verifylab.py campaign --matrix configs/gpu.json --count 16 --jobs 1 --out runs/gpu
python verifylab.py run --backend ptx-jit --seed 42 --out runs/ptx
```

The GPU matrix selects the detected device architecture for nvcc paths. Direct handwritten PTX uses ISA 7.0 and sm_75 as a conservative target; unsupported cases/devices are skipped. The direct-PTX emitter supports map kernels only. `configs/jetson.json` uses the same implementation with the device's installed nvcc and driver.

Exit codes: **0** all requested checks pass; **1** failure/error/incomplete work; **2** at least one skip and no failure. The demo considers deliberate fault detection successful only if reduction reproduces it and the corrected regression passes.

## Repository map

```text
verifylab.py                 CLI entry point
compilerlab/ir.py            specification, generator, metamorphic transformations
compilerlab/emit.py          C++, CUDA and PTX emitters
compilerlab/backend.py       compilation, execution, comparison and provenance
compilerlab/gpu_worker.py    isolated CUDA Driver API integration
compilerlab/process.py       time/output bounds and process-tree termination
compilerlab/store.py         SQLite leases and idempotent publication
compilerlab/engine.py        campaign, reduction, replay integrity and regression
compilerlab/report.py        offline dashboard
compilerlab/cli.py           user-facing commands
tests/test_complete.py      semantic and workflow tests
configs/                    host, GPU and Jetson matrices
scripts/                    launcher and pinned compiler bootstrap
evidence/final-demo/         completed native run and all reproduction artifacts
```

The scope is unsigned integer programs and deterministic reductions. This project does not claim formal compiler verification, full CUDA language coverage, a floating-point/ML test suite, or discovery of an upstream compiler defect. The injected fault is labeled synthetic throughout.
