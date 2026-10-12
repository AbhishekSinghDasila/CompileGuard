"""Emit standalone C++, CUDA, and hand-written PTX from the legal IR."""
from .ir import validate


def expression(op, k, fault):
    if fault == 'shift-sign' and op == 'shr' and k:
        # Defined unsigned implementation of the deliberately incorrect sign fill.
        return f'((x >> {k}u) | ((x & 0x80000000u) ? (0xffffffffu << {32-k}u) : 0u))'
    symbol = {'add': '+', 'sub': '-', 'mul': '*', 'xor': '^', 'and': '&', 'or': '|', 'shl': '<<', 'shr': '>>'}[op]
    return f'(x {symbol} {k}u)'


def source(case, cuda=False, fault=None, device_only=False):
    validate(case)
    if fault not in (None, 'shift-sign', 'drop-last'):
        raise ValueError('Unknown synthetic fault')
    ops = case['ops'][:-1] if fault == 'drop-last' else case['ops']
    lines = '\n'.join(f'    x = static_cast<uint32_t>({expression(op, k, fault)});' for op, k in ops)
    qualifier = '__device__ ' if cuda else ''
    text = '#include <stdint.h>\n'
    text += f'{qualifier}uint32_t evaluate(uint32_t x) {{\n{lines}\n    return x;\n}}\n'
    reduction = case.get('kind') == 'reduce'
    if cuda:
        if reduction:
            text += '''extern "C" __global__ void verify_kernel(const uint32_t* in, uint32_t* out, unsigned n) {
    __shared__ uint32_t partial[128];
    unsigned t = threadIdx.x;
    uint32_t sum = 0;
    for (unsigned i = t; i < n; i += blockDim.x) sum += evaluate(in[i]);
    partial[t] = sum;
    __syncthreads();
    for (unsigned stride = 64; stride; stride >>= 1) {
        if (t < stride) partial[t] += partial[t + stride];
        __syncthreads();
    }
    if (t == 0) out[0] = partial[0];
}
'''
        else:
            text += '''extern "C" __global__ void verify_kernel(const uint32_t* in, uint32_t* out, unsigned n) {
    unsigned i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) out[i] = evaluate(in[i]);
}
'''
        if device_only:
            return text
    values = ','.join(f'{x}u' for x in case['inputs'])
    text += '#include <stdio.h>\n#include <stdlib.h>\n'
    if not cuda:
        loop = 'uint32_t sum=0; for(auto x:input) sum += evaluate(x); printf("%llu\\n", (unsigned long long)sum);' if reduction else 'for(auto x:input) printf("%llu\\n", (unsigned long long)evaluate(x));'
        # Volatile loads prevent the entire test from becoming constant printf calls.
        return text + f'int main() {{ volatile uint32_t input[] = {{{values}}}; {loop} return 0; }}\n'
    size = 1 if reduction else len(case['inputs'])
    grid = '1' if reduction else '(n+127)/128'
    text += '''#include <cuda_runtime.h>
void check(cudaError_t e) { if(e != cudaSuccess) { fprintf(stderr,"%s\\n",cudaGetErrorString(e)); exit(3); } }
'''
    return text + f'''int main() {{
    const uint32_t input[] = {{{values}}};
    constexpr unsigned n = sizeof(input)/sizeof(input[0]);
    uint32_t output[{size}], *a=nullptr, *b=nullptr;
    check(cudaMalloc((void**)&a,sizeof(input))); check(cudaMalloc((void**)&b,sizeof(output)));
    check(cudaMemcpy(a,input,sizeof(input),cudaMemcpyHostToDevice));
    verify_kernel<<<{grid},128>>>(a,b,n);
    check(cudaGetLastError()); check(cudaDeviceSynchronize());
    check(cudaMemcpy(output,b,sizeof(output),cudaMemcpyDeviceToHost));
    check(cudaFree(a)); check(cudaFree(b));
    for(auto x:output) printf("%llu\\n",(unsigned long long)x);
    return 0;
}}
'''


def ptx(case, arch='sm_75'):
    validate(case)
    if case.get('kind') == 'reduce':
        raise ValueError('Direct PTX supports map kernels only')
    instruction = {'add': 'add.u32', 'sub': 'sub.u32', 'mul': 'mul.lo.u32', 'xor': 'xor.b32',
                   'and': 'and.b32', 'or': 'or.b32', 'shl': 'shl.b32', 'shr': 'shr.u32'}
    ops = '\n'.join(f'    {instruction[op]} %r4, %r4, {k};' for op, k in case['ops'])
    return f'''.version 7.0
.target {arch}
.address_size 64
.visible .entry verify_kernel(.param .u64 input, .param .u64 output, .param .u32 count) {{
    .reg .pred %p;
    .reg .b32 %r<5>;
    .reg .b64 %rd<6>;
    ld.param.u64 %rd0, [input];
    ld.param.u64 %rd1, [output];
    ld.param.u32 %r0, [count];
    mov.u32 %r1, %ctaid.x;
    mov.u32 %r2, %ntid.x;
    mov.u32 %r3, %tid.x;
    mad.lo.u32 %r1, %r1, %r2, %r3;
    setp.ge.u32 %p, %r1, %r0;
    @%p bra DONE;
    mul.wide.u32 %rd2, %r1, 4;
    add.u64 %rd3, %rd0, %rd2;
    add.u64 %rd4, %rd1, %rd2;
    ld.global.u32 %r4, [%rd3];
{ops}
    st.global.u32 [%rd4], %r4;
DONE:
    ret;
}}
'''
