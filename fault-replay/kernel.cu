#include <stdint.h>
__device__ uint32_t evaluate(uint32_t x) {
    x = static_cast<uint32_t>(((x >> 1u) | ((x & 0x80000000u) ? (0xffffffffu << 31u) : 0u)));
    return x;
}
extern "C" __global__ void verify_kernel(const uint32_t* in, uint32_t* out, unsigned n) {
    unsigned i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) out[i] = evaluate(in[i]);
}
