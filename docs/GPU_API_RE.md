# Metal device loading on the iOS 16.7.16 image

Source: the existing iPhone X 20H392 arm64 dyld shared cache. Analysis performed
offline with `ipsw`; the original cache was read, not edited. All extracted
strings, symbols and disassembly stay ignored under `research/gpu-api/`.
The symbol-analysis cache is on the external drive at
`/run/media/dipa/android/ios-extra-work/api-cache.a2s` (approximately 730 MiB).

## Observed device loading path

The following virtual addresses are unslid addresses in this cache:

| Function | Address | Observed behavior |
| --- | --- | --- |
| `MTLCreateSystemDefaultDevice` | `0x181a37760` | Initializes the device array once, then selects through its dispatch queue |
| `MTLDeviceArrayInitialize` block | `0x181a34050` | Initializes array/debug wrappers, then calls `MTLRegisterDevices` |
| `MTLRegisterDevices` | `0x181b144c8` | Enumerates `IOAcceleratorES` services, resolves a plugin class for each and initializes a device |
| `getMetalPluginClassForService` | `0x181a3c7c8` | Resolves the bundle and class using IOKit properties, then checks the class hierarchy |

`MTLRegisterDevices` calls `IOServiceMatching("IOAcceleratorES")` and
`IOServiceGetMatchingServices`, iterates the returned services and passes each
service to `getMetalPluginClassForService`. A successful result is allocated
and receives `initWithAcceleratorPort:` with the service handle. A non-nil
instance is added through `MTLAddDevice`.

`getMetalPluginClassForService`:

1. Reads `MetalPluginName` from the service with
   `IORegistryEntryCreateCFProperty`; requires a string.
2. Constructs `/System/Library/Extensions/<MetalPluginName>.bundle` and uses
   `NSBundle bundleWithPath:`.
3. Reads optional string `MetalPluginClassName` from the same service and
   resolves it through `classNamed:`. If unavailable or unresolved, it uses
   the bundle's `principalClass`.
4. Requires the resolved class to be a subclass of `_MTLDevice`; otherwise
   returns nil.

These steps are established by disassembly, rather than inferred solely from
string presence. Local evidence files: `metal-default-device.asm`,
`metal-enumeration.asm`, `metal-register-devices.asm`,
`metal-plugin-loader.asm` and `metal-symbols.txt` in `research/gpu-api/`.

## Engineering implication and remaining work

A custom userspace Metal device plugin selected through a compatible kernel
service is a concrete candidate integration boundary. This permits designing
our own command transport between an Adreno plugin and SweetGPU, rather than
assuming the existing AGX plugin can execute on Adreno.

This does not yet prove a custom plugin loads, that `_MTLDevice` initialization
succeeds with a minimal service, or that CoreAnimation accepts it. The next
API experiment should be an isolated test process that enumerates a custom
plugin; keep it out of the compositor's discovery path until its required
methods and failure behavior are understood.

Still to trace or implement:

- Base `_MTLDevice` initialization and the minimum service properties/user
  client contract; inherited versus overridden behavior.
- Resource, texture, command queue, encoder, synchronization and IOSurface
  interfaces expected by the framework and compositor.
- Shader compilation entry points, AIR/library inputs, specialization and
  pipeline caching. A plugin entry point is not an Adreno compiler frontend.
- CoreAnimation renderer selection and its required Metal feature set.

The actual image also contains `AppleMetalGLRenderer` with a dependency on
Metal. An OpenGLES backend should therefore be evaluated from the observed
loading path; the presence of GLES APIs alone does not establish an independent
hardware route.
