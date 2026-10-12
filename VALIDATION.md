# Completed validation

Validated on 12 October 2026 on Windows x64 with Python 3.12.14 and the Clang 19.1.7 driver supplied by Zig 0.14.1.

| Check | Measured result |
|---|---|
| Unit and workflow tests | 26 passed |
| Generated/boundary/metamorphic cases | 42 |
| Native compiler jobs | 84 passed, zero failed |
| Profiles executed | Same Clang compiler at O0 and O2 |
| Executions per ordinary native job | 2 |
| Seeded fault | Detected in compiled C++ |
| Reduction | 3 operations / 4 inputs reduced to 1 operation / 1 input |
| Reduction predicate | At least 3 native executions per candidate |
| Corrected regression | 2 profiles passed |
| Saved native fault replay | WRONG_RESULT reproduced as expected |
| Artifact checksum audit | Passed for all native campaign bundles and final fault bundle |
| Campaign resume | Completed jobs were not repeated |
| Offline dashboard links | All campaign evidence links resolve |
| GPU configurations | 9 explicit GPU-unavailable skips |

The campaign includes 24 generated seed cases, 9 boundary cases and 9 metamorphic variants. The 42 cases run at two optimization levels for 84 jobs. The eight supported operations all occur in the campaign. Both map and modular-reduction cases are present. Passing these inputs does not establish exhaustive compiler correctness.

The deliberate fault's final comparison is expected 2147483647 versus actual 4294967295. Reduction used 11 distinct predicate evaluations and reached a deletion fixed point without exhausting its budget.

The semantic test suite checks all 256 small input values plus two uint32 boundary values against independent scalar formulas for eight operations and four constants each: 8,256 comparisons. Metamorphic tests cover 50 generated cases and three transformations each, including map and reduction semantics.

Other tests cover malformed cases/profiles, crash classification, output limits, timeouts, missing compilers, flaky output, artifact tampering, saved expectations, resume, interrupted enqueue, concurrent claims, stale ownership, lease expiry and retry exhaustion.

The first portable compiler attempt crashed inside the task's restrictive execution sandbox. Running the same compiler outside that sandbox succeeded. The retained final evidence comes from successful native compilation and execution, not from simulated compiler results.

## Explicit validation limits

- No NVIDIA GPU was available. CUDA kernels, PTX JIT/offline execution and sanitizer execution are implemented but hardware-unvalidated.
- GPU-unavailable tests exercise detection and classification only.
- GCC, other Clang versions, Linux, Jetson, Docker and hosted CI were not executed here.
- The fault is deliberately injected into emitted code. No upstream compiler bug was discovered or claimed.
- The model backend verifies infrastructure behavior only; final native campaign results contain no model passes.
- The project supports a bounded unsigned-integer language, not arbitrary C++, floating-point or ML compilation.

Machine-readable evidence is in evidence/validation.json and evidence/final-demo/. The source and compiler binary identities are retained with the campaign.
