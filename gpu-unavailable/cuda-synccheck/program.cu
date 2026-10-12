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
#include <stdio.h>
#include <stdlib.h>
#include <cuda_runtime.h>
void check(cudaError_t e) { if(e != cudaSuccess) { fprintf(stderr,"%s\n",cudaGetErrorString(e)); exit(3); } }
int main() {
    const uint32_t input[] = {0u,1u,4294967295u,2147483648u,2147483647u,3562265906u,2699987374u,2656522106u,3802986287u,3701002945u,1553210608u,2479708607u,825873196u,3026113008u,298737106u,196814233u,2840104345u,978815630u,3320303242u,1242911821u,4231494220u,342703921u,3673561638u,999829240u,3721519026u,433797840u,1632629719u,1193887545u,1947382419u,2730243887u,3582477022u,1566942273u,698594025u};
    constexpr unsigned n = sizeof(input)/sizeof(input[0]);
    uint32_t output[33], *a=nullptr, *b=nullptr;
    check(cudaMalloc((void**)&a,sizeof(input))); check(cudaMalloc((void**)&b,sizeof(output)));
    check(cudaMemcpy(a,input,sizeof(input),cudaMemcpyHostToDevice));
    verify_kernel<<<(n+127)/128,128>>>(a,b,n);
    check(cudaGetLastError()); check(cudaDeviceSynchronize());
    check(cudaMemcpy(output,b,sizeof(output),cudaMemcpyDeviceToHost));
    check(cudaFree(a)); check(cudaFree(b));
    for(auto x:output) printf("%llu\n",(unsigned long long)x);
    return 0;
}
