#!/usr/bin/env python3
"""Read a UIKit BoundingPathData Assets.car without modifying Apple artifacts.

This is a narrow BOMStore inspector for the DATA rendition used by the FP6
SpringBoard assertion. It proves local catalog linkage and archive decoding;
it cannot prove that CoreUI selected the rendition on a running phone.
"""
import argparse
import hashlib
import json
import plistlib
import struct
from pathlib import Path

DEFAULT_ASSET = 'BoundingPathBitmap-1125x2436-375x812-3.00x'
CATALOG = 'System/Library/PrivateFrameworks/UIKitCore.framework/BoundingPathData.bundle/Assets.car'


class Catalog:
    def __init__(self, data):
        self.data = data
        if len(data) < 32 or data[:8] != b'BOMStore':
            raise ValueError('not a BOMStore catalog')
        _, _, _, index, index_size, variables, variables_size = struct.unpack('>8s6I', data[:32])
        table = self.slice(index, index_size)
        count = struct.unpack_from('>I', table)[0]
        if 4 + count * 8 > len(table):
            raise ValueError('truncated BOM block table')
        self.blocks = [struct.unpack_from('>II', table, 4 + i * 8) for i in range(count)]
        names = self.slice(variables, variables_size)
        self.variables = {}
        pos = 4
        for _ in range(struct.unpack_from('>I', names)[0]):
            block, length = struct.unpack_from('>IB', names, pos)
            pos += 5
            self.variables[names[pos:pos + length].decode('ascii')] = block
            pos += length

    def slice(self, offset, length):
        if offset < 0 or length < 0 or offset + length > len(self.data):
            raise ValueError('BOM extent outside catalog')
        return self.data[offset:offset + length]

    def block(self, index):
        return self.slice(*self.blocks[index])

    def entries(self, name):
        tree = self.block(self.variables[name])
        if tree[:4] != b'tree':
            raise ValueError('invalid BOM tree')
        root = struct.unpack_from('>I', tree, 8)[0]
        seen = set()

        def visit(index):
            if index in seen:
                raise ValueError('cycle in BOM tree')
            seen.add(index)
            node = self.block(index)
            leaf, count = struct.unpack_from('>HH', node)
            if 12 + count * 8 > len(node):
                raise ValueError('truncated BOM tree node')
            for pos in range(count):
                value, key = struct.unpack_from('>II', node, 12 + pos * 8)
                if leaf:
                    yield value, self.block(key)
                else:
                    yield from visit(value)
        yield from visit(root)


def inspect(path, asset):
    data = path.read_bytes()
    catalog = Catalog(data)
    facet = next((catalog.block(value) for value, key in catalog.entries('FACETKEYS')
                  if key.rstrip(b'\0') == asset.encode()), None)
    if facet is None:
        raise ValueError('asset name absent from FACETKEYS')
    if len(facet) < 6:
        raise ValueError('truncated facet')
    tokens = {struct.unpack_from('<H', facet, pos)[0]: facet[pos + 2:pos + 4]
              for pos in range(6, len(facet), 4)}
    identifier = tokens.get(17)
    if identifier is None:
        raise ValueError('facet has no identifier token')
    key_format = catalog.block(catalog.variables['KEYFORMAT'])
    if key_format[:4] != b'tmfk':
        raise ValueError('unsupported CoreTheme key format')
    count = struct.unpack_from('<I', key_format, 8)[0]
    attributes = struct.unpack_from('<' + 'I' * count, key_format, 12)
    identifier_slot = attributes.index(17)
    matches = []
    for block, key in catalog.entries('RENDITIONS'):
        if key[identifier_slot * 2:identifier_slot * 2 + 2] != identifier:
            continue
        rendition = catalog.block(block)
        raw = rendition.find(b'DWAR')
        if raw < 0 or raw + 12 > len(rendition):
            raise ValueError('matching rendition is not RAWD DATA')
        length = struct.unpack_from('<I', rendition, raw + 8)[0]
        payload = rendition[raw + 12:raw + 12 + length]
        if len(payload) != length:
            raise ValueError('truncated RAWD archive')
        archive = plistlib.loads(payload)
        if archive.get('$archiver') != 'NSKeyedArchiver':
            raise ValueError('unsupported bounding path archive')
        root = archive['$objects'][archive['$top']['root'].data]
        cls = archive['$objects'][root['$class'].data]['$classname']
        matches.append({'block': block, 'encoded_key': key.hex(), 'class': cls,
                        'width': root.get('width'), 'height': root.get('height'),
                        'node_count': root.get('nodeCount'), 'archive_bytes': length,
                        'archive_sha256': hashlib.sha256(payload).hexdigest()})
    if not matches:
        raise ValueError('asset facet has no linked rendition')
    return {'catalog': str(path), 'catalog_sha256': hashlib.sha256(data).hexdigest(),
            'asset': asset, 'renditions': matches,
            'scope': 'local file linkage and decoding only; CoreUI runtime selection unverified'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path, help='mounted iOS root or Assets.car path')
    parser.add_argument('--asset', default=DEFAULT_ASSET)
    args = parser.parse_args()
    path = args.path / CATALOG if args.path.is_dir() else args.path
    try:
        print(json.dumps(inspect(path, args.asset), indent=2))
    except (ValueError, KeyError, IndexError, struct.error, OSError, plistlib.InvalidFileException) as error:
        parser.exit(1, f'audit failed: {error}\n')


if __name__ == '__main__':
    main()
