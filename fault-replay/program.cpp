#include <stdint.h>
uint32_t evaluate(uint32_t x) {
    x = static_cast<uint32_t>(((x >> 1u) | ((x & 0x80000000u) ? (0xffffffffu << 31u) : 0u)));
    return x;
}
#include <stdio.h>
#include <stdlib.h>
int main() { volatile uint32_t input[] = {4294967295u}; for(auto x:input) printf("%llu\n", (unsigned long long)evaluate(x)); return 0; }
