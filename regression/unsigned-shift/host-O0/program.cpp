#include <stdint.h>
uint32_t evaluate(uint32_t x) {
    x = static_cast<uint32_t>((x >> 1u));
    return x;
}
#include <stdio.h>
#include <stdlib.h>
int main() { volatile uint32_t input[] = {4294967295u}; for(auto x:input) printf("%llu\n", (unsigned long long)evaluate(x)); return 0; }
