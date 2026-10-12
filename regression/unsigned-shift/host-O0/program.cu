#include <stdint.h>
__device__ uint32_t evaluate(uint32_t x) {
    x = static_cast<uint32_t>((x >> 1u));
    return x;
}
extern "C" __global__ void verify_kernel(const uint32_t* in, uint32_t* out, unsigned n) {
    unsigned i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) out[i] = evaluate(in[i]);
}
#include <stdio.h>
#include <stdlib.h>
#include <cuda_runtime.h>
void check(cudaError_t e) { if(e != cudaSuccess) { fprintf(stderr,"%s\n",cudaGetErrorString(e)); exit(3); } }
int main() {
    const uint32_t input[] = {4294967295u};
    constexpr unsigned n = sizeof(input)/sizeof(input[0]);
    uint32_t output[1], *a=nullptr, *b=nullptr;
    check(cudaMalloc((void**)&a,sizeof(input))); check(cudaMalloc((void**)&b,sizeof(output)));
    check(cudaMemcpy(a,input,sizeof(input),cudaMemcpyHostToDevice));
    verify_kernel<<<(n+127)/128,128>>>(a,b,n);
    check(cudaGetLastError()); check(cudaDeviceSynchronize());
    check(cudaMemcpy(output,b,sizeof(output),cudaMemcpyDeviceToHost));
    check(cudaFree(a)); check(cudaFree(b));
    for(auto x:output) printf("%llu\n",(unsigned long long)x);
    return 0;
}
