"""Isolated CUDA Driver API worker, using ctypes and no CUDA Python package."""
import ctypes as C
import json
import os
from pathlib import Path
import sys


class Driver:
    def __init__(self):
        self.lib = (C.WinDLL('nvcuda.dll') if os.name == 'nt' else C.CDLL('libcuda.so.1'))
        self.bind('cuInit', [C.c_uint])
        self.bind('cuDeviceGet', [C.POINTER(C.c_int), C.c_int])
        self.bind('cuDeviceGetName', [C.c_char_p, C.c_int, C.c_int])
        self.bind('cuDeviceComputeCapability', [C.POINTER(C.c_int), C.POINTER(C.c_int), C.c_int])
        self.bind('cuDriverGetVersion', [C.POINTER(C.c_int)])
        self.bind('cuCtxCreate_v2', [C.POINTER(C.c_void_p), C.c_uint, C.c_int])
        self.bind('cuCtxDestroy_v2', [C.c_void_p])
        self.bind('cuModuleLoad', [C.POINTER(C.c_void_p), C.c_char_p])
        self.bind('cuModuleUnload', [C.c_void_p])
        self.bind('cuModuleGetFunction', [C.POINTER(C.c_void_p), C.c_void_p, C.c_char_p])
        self.bind('cuMemAlloc_v2', [C.POINTER(C.c_uint64), C.c_size_t])
        self.bind('cuMemFree_v2', [C.c_uint64])
        self.bind('cuMemcpyHtoD_v2', [C.c_uint64, C.c_void_p, C.c_size_t])
        self.bind('cuMemcpyDtoH_v2', [C.c_void_p, C.c_uint64, C.c_size_t])
        self.bind('cuCtxSynchronize', [])
        self.bind('cuLaunchKernel', [C.c_void_p] + [C.c_uint]*7 + [C.c_void_p, C.POINTER(C.c_void_p), C.POINTER(C.c_void_p)])
        self.call('cuInit', 0)
        self.device = C.c_int()
        self.call('cuDeviceGet', C.byref(self.device), 0)

    def bind(self, name, args):
        function = getattr(self.lib, name)
        function.argtypes, function.restype = args, C.c_int

    def call(self, name, *args):
        result = getattr(self.lib, name)(*args)
        if result:
            raise RuntimeError(f'{name} failed with CUDA status {result}')

    def info(self):
        name, major, minor, version = C.create_string_buffer(256), C.c_int(), C.c_int(), C.c_int()
        self.call('cuDeviceGetName', name, 256, self.device)
        self.call('cuDeviceComputeCapability', C.byref(major), C.byref(minor), self.device)
        self.call('cuDriverGetVersion', C.byref(version))
        return {'name': name.value.decode(), 'compute_capability': [major.value, minor.value], 'driver_version': version.value}

    def execute(self, module_path, case):
        context, module, function = C.c_void_p(), C.c_void_p(), C.c_void_p()
        a, b = C.c_uint64(), C.c_uint64()
        n = C.c_uint(len(case['inputs']))
        size = 1 if case.get('kind') == 'reduce' else n.value
        inputs = (C.c_uint32 * n.value)(*case['inputs'])
        outputs = (C.c_uint32 * size)()
        try:
            self.call('cuCtxCreate_v2', C.byref(context), 0, self.device)
            self.call('cuModuleLoad', C.byref(module), os.fsencode(str(Path(module_path).resolve())))
            self.call('cuModuleGetFunction', C.byref(function), module, b'verify_kernel')
            self.call('cuMemAlloc_v2', C.byref(a), C.sizeof(inputs))
            self.call('cuMemAlloc_v2', C.byref(b), C.sizeof(outputs))
            self.call('cuMemcpyHtoD_v2', a, inputs, C.sizeof(inputs))
            parameters = (C.c_void_p * 3)(C.cast(C.byref(a), C.c_void_p), C.cast(C.byref(b), C.c_void_p), C.cast(C.byref(n), C.c_void_p))
            grid = 1 if case.get('kind') == 'reduce' else (n.value + 127)//128
            self.call('cuLaunchKernel', function, grid, 1, 1, 128, 1, 1, 0, None, parameters, None)
            self.call('cuCtxSynchronize')
            self.call('cuMemcpyDtoH_v2', outputs, b, C.sizeof(outputs))
            return list(outputs)
        finally:
            for name, value in [('cuMemFree_v2', b), ('cuMemFree_v2', a), ('cuModuleUnload', module), ('cuCtxDestroy_v2', context)]:
                if value.value:
                    getattr(self.lib, name)(value)


def main():
    try:
        driver = Driver()
        if len(sys.argv) == 2 and sys.argv[1] == '--probe':
            print(json.dumps(driver.info()))
        else:
            case = json.loads(Path(sys.argv[2]).read_text())
            print('\n'.join(map(str, driver.execute(sys.argv[1], case))))
    except (OSError, RuntimeError, AttributeError) as error:
        print(str(error), file=sys.stderr)
        return 3
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
