# Study guide for the completed compiler verification project

## Understand the system in one pass

The system asks a precise question: for this legal program, these inputs, and this compiler configuration, does executing the compiled result produce the values required by the specification? Every component supports either answering that question or retaining enough evidence to investigate a disagreement.

Open the saved dashboard first. It shows real native jobs with separate optimization profiles. Then open `evidence/final-demo/demo.json` for the campaign, reduction and regression summary. Finally, open `evidence/final-demo/reduction/final/report.json` to see an intentionally wrong compiled result.

## The failure you can explain in an interview

The program applies an unsigned right shift by one. For an input with the high bit set, the required behavior inserts a zero into the highest bit. An arithmetic shift would instead extend the sign bit. The injected emitter fault intentionally implements that incorrect sign fill using defined unsigned operations, avoiding undefined behavior in the demonstration itself.

The original case contains three operations and four inputs. The reducer removes operations or inputs only if recompilation and repeated native execution still produce WRONG_RESULT. It eventually retains one right shift and one failing input. The corrected emitter compiles the same minimized case and produces the reference result at both optimization levels.

This is a seeded emitter defect used to validate the detection pipeline. It is not a claim that Clang miscompiled a correct program. That distinction is essential to the credibility of the project.

## Read the source in this order

### 1 Language semantics in ir.py

Start at `validate`, then `reference`, then `generate`. The legal language has eight operations over unsigned 32-bit values. Python integers do not wrap by themselves, so the interpreter masks after each operation. This explicitly models arithmetic modulo 2^32.

Shifts allow only 0 through 31. Inputs are initialized, bounded integers. There are no source-level pointers in the generated expression chain, no division, and no unbounded loops. The map kind produces one result per input. The reduction kind sums those results modulo 2^32.

Look at `transform`: adding zero, XORing twice with the same constant, and adding then subtracting the same constant preserve the specified semantics. Those preconditions make the metamorphic tests meaningful. Applying arbitrary “equivalent-looking” floating-point transformations would not have the same guarantee.

### 2 Code generation in emit.py

The C++ emitter spells out each operation with an unsigned constant and explicit uint32 assignment. Host input loads are volatile to prevent the entire test from being folded into constant print statements. Individual algebraic simplification is still allowed and is part of what the tests exercise.

The CUDA map kernel computes a unique index and guards its input/output access. Each thread owns one output lane. The shared-memory reduction always launches exactly one block of 128 threads. Every thread initializes its partial sum and reaches every barrier. Only participating threads perform additions, but the barrier sits outside that conditional. This keeps barrier participation uniform.

The direct PTX emitter declares a stable kernel entry with two pointers and an element count. Read its index computation, bounds branch, input load, operation sequence and output store. The IR shifts map to `shr.u32`, not signed shift instructions.

### 3 Execution and oracles in backend.py

An execution begins by writing source, input and profile artifacts. The interpreter computes expected values. A compiler adapter builds the selected program or module. Native execution is repeated; different observations become FLAKY_RESULT instead of a stable wrong-result finding.

The comparator checks output count, numeric format, uint32 range and exact element equality. Malformed output is a protocol failure. A compiler crash differs from a compiler diagnostic. A missing GPU differs from a passing run. Read the status handling before the happy path; most verification infrastructure mistakes happen when unrelated failures are collapsed into a single result.

The Python model is a harness fallback. Agreement with itself adds no independent compiler evidence, so dashboards count model and native passes separately. The useful independent path is compiled execution against the Python specification, supported by hand-derived boundary checks and bounded exhaustive tests.

### 4 Process isolation in process.py

Each invocation writes stdout and stderr to files instead of accumulating unbounded memory. The process loop checks elapsed time and output size, then terminates the process tree when a limit is exceeded. Full process memory and disk quotas are not implemented; these are cooperative local workers rather than a hostile multi-tenant execution service.

On Windows, the downloaded compiler failed inside this task's restrictive execution sandbox but succeeded when run outside it. That environment failure was investigated separately from language semantics. Ordinary use through the supplied local launcher does not run in that task sandbox.

### 5 Durable scheduling in store.py

A job's identity hashes the case, compiler profile and engine revision. SQLite has a primary key on that identity, so repeated enqueue attempts are idempotent. Claims use `BEGIN IMMEDIATE` to make selection and ownership assignment one transaction.

Each claim gets a unique owner token and a lease. A heartbeat extends the lease. An abandoned lease can be reclaimed. Completion updates only the current owner's running job, so a stale worker cannot overwrite a newer attempt. After the retry budget is exhausted, the job becomes a visible infrastructure failure.

Workers use separate connections and unique artifact directories. Parallelism is local; the project does not implement a remote cluster scheduler. The lease design still exposes the same fundamental concerns: duplicate delivery, abandoned work and conditional publication.

### 6 Reduction and regression in engine.py

The reducer accepts only reproducible WRONG_RESULT cases. It never treats a compile error as an interesting substitute. It uses at least three executions per candidate and memoizes candidates by content hash.

At a fixed point, no single operation or input can be removed while retaining the predicate. This is deletion-based one-minimality, not a proof of the globally smallest program. If the evaluation budget ends first, the result explicitly says minimality was not established. A final reproduction protects against a failure disappearing during the search.

The regression corpus stores expected values rather than merely recording “used to fail.” Before execution, the engine checks that those values still agree with the specification. It removes the synthetic injection for the corrected run.

### 7 GPU paths in gpu_worker.py

The worker loads the native CUDA driver, selects a device, creates a context, loads PTX or cubin, finds the kernel, allocates memory, launches, synchronizes and copies results back. A `finally` block releases allocations, module and context.

Driver loading and execution happen in a subprocess so a crash or timeout is contained. JIT PTX and offline cubin are distinct paths. Changing a driver may change JIT behavior even when the source and nvcc version are unchanged. A binary compiled for a different GPU architecture is not automatically portable.

Read these paths as implemented but hardware-unvalidated code. The supplied no-GPU evidence proves they are skipped honestly; it does not prove their device execution behavior.

## Questions you should be able to answer

1. Why does the reference interpreter mask after every operation?
2. Which source-language behavior would invalidate a differential compiler test?
3. Why are volatile input loads used in the native C++ emitter?
4. Why must all threads reach the reduction barriers?
5. How is a repeated mismatch different from a flaky result?
6. What happens if a worker crashes after claiming a job?
7. What stops an expired worker from overwriting a new result?
8. Why does reduction preserve the failure class?
9. What does one-minimal mean here?
10. Which results were actually run, and which require hardware you do not have?

## A concise demonstration script

“I built a compiler verification system with a specified unsigned-integer language, deterministic and metamorphic generation, native execution, persistent jobs and reproducible artifacts. This dashboard contains the recorded native campaign. Here is an intentionally seeded wrong-code fault. The system reproduces it, reduces it to one operation and one input, and verifies the corrected implementation. CUDA and PTX adapters are implemented, but I have not executed them on GPU hardware.”

Use the measured counts from VALIDATION.md. Do not claim all compilers are verified, that GPU validation occurred, or that the synthetic fault is an upstream bug.
