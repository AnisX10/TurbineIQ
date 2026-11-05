import argparse
import json
import struct
from pathlib import Path


def read_document(path: Path) -> dict[str, object]:
    blob = path.read_bytes()
    magic, version, length = struct.unpack_from('<4sII', blob)
    if magic != b'glTF' or version != 2 or length != len(blob):
        raise ValueError(f'{path} is not a valid GLB 2.0 container')
    json_length, json_type = struct.unpack_from('<II', blob, 12)
    if json_type != 0x4E4F534A:
        raise ValueError(f'{path} does not start with a JSON chunk')
    return json.loads(blob[20:20 + json_length].decode('utf-8'))


def structure(path: Path) -> dict[str, object]:
    document = read_document(path)
    result = {}
    for key in ('nodes', 'meshes', 'materials', 'animations'):
        values = document.get(key, [])
        result[key] = {
            'count': len(values),
            'names': [value.get('name') for value in values],
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(structure(args.input), indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
