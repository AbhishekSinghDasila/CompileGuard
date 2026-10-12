#include <stdint.h>
uint32_t evaluate(uint32_t x) {
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
#include <stdio.h>
#include <stdlib.h>
int main() { volatile uint32_t input[] = {0u,1u,4294967295u,2147483648u,2147483647u,3562265906u,2699987374u,2656522106u,3802986287u,3701002945u,1553210608u,2479708607u,825873196u,3026113008u,298737106u,196814233u,2840104345u,978815630u,3320303242u,1242911821u,4231494220u,342703921u,3673561638u,999829240u,3721519026u,433797840u,1632629719u,1193887545u,1947382419u,2730243887u,3582477022u,1566942273u,698594025u}; for(auto x:input) printf("%llu\n", (unsigned long long)evaluate(x)); return 0; }
