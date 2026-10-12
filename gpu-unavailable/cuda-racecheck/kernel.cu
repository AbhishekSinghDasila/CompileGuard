#include <stdint.h>
__device__ uint32_t evaluate(uint32_t x) {
    x = static_cast<uint32_t>((x - 4294967295u));
    x = static_cast<uint32_t>((x ^ 0u));
    x = static_cast<uint32_t>((x - 136505587u));
    x = static_cast<uint32_t>((x - 2147483647u));
    x = static_cast<uint32_t>((x + 1801823908u));
    x = static_cast<uint32_t>((x >> 0u));
    x = static_cast<uint32_t>((x * 1461364854u));
    x = static_cast<uint32_t>((x * 4294967295u));
    x = static_cast<uint32_t>((x - 0u));
    x = static_cast<uint32_t>((x | 2592983555u));
    x = static_cast<uint32_t>((x + 2303082117u));
    x = static_cast<uint32_t>((x << 1u));
    return x;
}
extern "C" __global__ void verify_kernel(const uint32_t* in, uint32_t* out, unsigned n) {
    unsigned i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) out[i] = evaluate(in[i]);
}
