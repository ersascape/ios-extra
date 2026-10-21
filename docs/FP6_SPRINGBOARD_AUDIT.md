# FP6 SpringBoard bounding-path audit

## Phone evidence

The USB capture `/tmp/fp6-blackboot-69f9878.pcap` contains repeated SpringBoard
SIGABRT records with this exception:

```
_UIScreenComplexBoundingPathUtilities _loadBitmapForScreen:type:
Failed to load bounding path bitmap data from the asset manager for asset name:
BoundingPathBitmap-1125x2436-375x812-3.00x
```

The same log describes the main display as `375x812@3x`, pixel size
`1125x2436`. This is consistent with the requested asset's name. It does not
prove all CoreUI rendition selection traits are correct. The capture filename
is a diagnostic label, not independent identification of the running kernel.
The reported gradual black screen has not been proven to be a panel shutdown;
this capture establishes a concurrent userspace crash loop.

## Local filesystem evidence, 2026-10-21

Read-only inspection of the previously built
`/home/ersa/Dev/ios-extra/research/fp6-rootfs-tegu-20261021/fp6-ios-root-tegu.hfs`
found the exact requested asset in:

```
System/Library/PrivateFrameworks/UIKitCore.framework/BoundingPathData.bundle/Assets.car
```

The catalog's SHA-256 is
`0a53453f1e096f70ccb38618b0b8c32fa950f71dc3b559c4ce556825517aa04d`.
It is byte-identical to the same catalog read directly from the original
`/home/ersa/Downloads/ipsw-20H392/OS.dmg`. Thus this local root-copy step neither
omitted nor changed the catalog. The running phone's filesystem has not been
independently compared with this local image.

A catalog name search alone is insufficient. Parsing the BOMStore links shows:

- FACETKEYS block 16 contains the requested name; its facet value is block 17.
- Identifier bytes `664d` link to RENDITIONS block 72, offset `0x4100`.
- Its RAWD DATA is a valid 3,090-byte NSKeyedArchiver archive.
- The root object is `_UIBoundingPathBitmap`, width 1125, height 2436,
  nodeCount 1340.
- Archive SHA-256:
  `799026f7d7fe3cd6728dfb9987ddbe3c53aa7eb8516cee8002c77e8a34e56bda`.

The archive uses a generic `CoreStructuredImage` rendition name. Absence of a
readable `BoundingPathBitmap-1125x2436-375x812-3.00x.data` string therefore does
not mean its data is missing.

The bundle Info.plist identifies `com.apple.uikit.BoundingPathData`, executable
`BoundingPathData`, and UIDeviceFamily `[1,2]`. This audit did not change Apple
files, kernel geometry, device identity, or the phone.

## Reproduce the local check

On an already mounted read-only root:

```
python3 tools/fp6-bounding-path-audit.py /path/to/root
```

The helper also accepts an Assets.car path and `--asset NAME`. It inspects the
BOM tree, links the exact facet to the corresponding rendition, and decodes the
archive. It does not load CoreUI, emulate its matching algorithm, prove file
readability in SpringBoard's process, or inspect the currently booted root.

## Remaining cause and next useful evidence

Replacing a supposedly missing catalog or dropping the iPhone X geometry is
not justified by this evidence. First establish whether the phone's actual
catalog matches the verified local one. If it does, instrument CoreUI's bundle
resolution, rendition key selection and returned NSData length immediately
before UIKit's assertion. Distinguish a nil DATA lookup from a nonnil archive
that fails decoding. Preserve the matching status-bar geometry while resolving
that runtime failure. No SpringBoard fix or successful home-screen boot is
claimed by this audit.
