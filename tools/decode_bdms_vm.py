"""Statically decode the captured BDMS 1.0.1.19-fix.01 VM bundle.

This tool never imports or executes JavaScript. It accepts the exact researched
bundle, decodes its data container, and disassembles the observed instruction
format. A different bundle requires reviewing its loader and instruction set.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import zlib
from pathlib import Path


EXPECTED_SHA256 = "a0e46f84476d63a1fa57bdcb47223e0e545c6ce0c3dacdd2818180dfa087909e"
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_DECODED_BYTES = 4 * 1024 * 1024
ONE_OPERAND = {0, 3, 4, 5, 15, 17, 20, 23, 30, 31, 38, 39, 41, 46,
               47, 48, 52, 53, 59, 60, 63, 67, 69, 71, 72, 73}
TWO_OPERANDS = {54, 61, 74}
STRING_OPERANDS = {5, 15, 20, 30, 46, 47, 48, 60, 67, 69, 72, 73}
OP_NAMES = [
    "call", "le", "gt", "enum_init", "enum_next", "global_ref", "strict_ne",
    "object", "get_index", "true", "void", "mod", "bit_and", "instanceof",
    "set_index", "set_global", "set_index_keep", "and_jump", "dup", "ushr",
    "set_property", "subtract", "resume_abrupt", "case_jump", "typeof",
    "delete_index", "pop", "false", "nan", "not", "get_property", "or_jump",
    "lt", "undefined", "this", "shr", "positive", "bit_not", "integer",
    "array", "pre_increment", "jump_if_false", "divide", "negative",
    "pre_decrement", "multiply", "number_constant", "getter", "setter",
    "throw", "post_increment", "bit_or", "abrupt_jump", "jump", "set_local",
    "in", "shl", "strict_eq", "eq", "construct", "get_global", "local_ref",
    "ne", "closure", "ge", "infinity", "post_decrement", "define_property",
    "add", "typeof_global", "bit_xor", "jump_if_true", "declare_global",
    "string", "get_local", "null", "return",
]
BRANCH_NOTES = {
    17: "falsy: keep value and jump; truthy: pop and continue",
    23: "pop comparison; equal: pop discriminant and jump; unequal: retain discriminant",
    31: "truthy: keep value and jump; falsy: pop and continue",
    41: "pop condition; falsy: jump; truthy: continue",
    52: "abrupt completion f=1; l=target; unwind finally before applying target",
    53: "unconditional relative jump",
    71: "pop condition; truthy: jump; falsy: continue",
}


class DecodeError(ValueError):
    """The input does not match the reviewed data format."""


class Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def byte(self) -> int:
        if self.pos >= len(self.data):
            raise DecodeError("Truncated VM data")
        value = self.data[self.pos]
        self.pos += 1
        return value

    def integer(self) -> int:
        # W() is signed LEB128 with JavaScript's signed 32-bit result.
        value = shift = 0
        for _ in range(5):
            part = self.byte()
            value |= (part & 127) << shift
            shift += 7
            if not part & 128:
                if shift < 32 and part & 64:
                    value |= -1 << shift
                value &= 0xFFFFFFFF
                return value if value < 0x80000000 else value - 0x100000000
        raise DecodeError("Invalid VM integer")

    def count(self, limit: int) -> int:
        value = self.integer()
        if not 0 <= value <= limit:
            raise DecodeError("VM count exceeds format limits")
        return value

    def string(self) -> str:
        start = self.pos
        while self.byte() < 248:
            pass
        try:
            return self.data[start:self.pos - 1].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DecodeError("Invalid UTF-8 string constant") from exc


def location(source: str, offset: int) -> dict:
    prefix = source[:offset]
    return {"line": prefix.count("\n"),
            "column": len(prefix.rsplit("\n", 1)[-1].encode("utf-16-le")) // 2}


def disassemble(code: list[int], strings: list[str], function_count: int) -> list[dict]:
    instructions = []
    pc = 0
    while pc < len(code):
        opcode = code[pc]
        if not 0 <= opcode < len(OP_NAMES):
            raise DecodeError(f"Unknown opcode at PC {pc}: {opcode}")
        width = 2 if opcode in TWO_OPERANDS else int(opcode in ONE_OPERAND)
        operands = code[pc + 1:pc + 1 + width]
        if len(operands) != width:
            raise DecodeError(f"Truncated instruction at PC {pc}")
        item = {"pc": pc, "opcode": opcode, "name": OP_NAMES[opcode],
                "operands": operands}
        if opcode in STRING_OPERANDS:
            if not 0 <= operands[0] < len(strings):
                raise DecodeError(f"Invalid string index at PC {pc}")
            item["constant"] = strings[operands[0]]
        if opcode == 63 and not 0 <= operands[0] < function_count:
            raise DecodeError(f"Invalid function index at PC {pc}")
        if opcode in {17, 23, 31, 41, 52, 53, 71}:
            item["target_pc"] = pc + 1 + width + operands[0]
            item["branch_semantics"] = BRANCH_NOTES[opcode]
        instructions.append(item)
        pc += 1 + width
    boundaries = {item["pc"] for item in instructions} | {len(code)}
    for item in instructions:
        if "target_pc" in item and item["target_pc"] not in boundaries:
            raise DecodeError(f"Jump target is not an instruction boundary at PC {item['pc']}")
    return instructions


def decode_bundle(raw: bytes) -> dict:
    if len(raw) > MAX_SOURCE_BYTES:
        raise DecodeError("Source exceeds size limit")
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_SHA256:
        raise DecodeError("Unsupported bundle SHA-256; review its loader and opcodes first")
    source = raw.decode("utf-8")
    matches = list(re.finditer(r'\}\("([A-Za-z0-9+/=]{1000,})"\),X', source))
    if len(matches) != 1:
        raise DecodeError("Expected exactly one reviewed VM data container")
    match = matches[0]
    packed = base64.b64decode(match[1], validate=True)
    seed = sum(packed[4:8]) % 256
    compressed = bytes(value ^ ((seed + seed % 10 * index) % 256)
                       for index, value in enumerate(packed[8:]))
    decoder = zlib.decompressobj(wbits=-15)
    try:
        data = decoder.decompress(compressed, MAX_DECODED_BYTES + 1)
    except zlib.error as exc:
        raise DecodeError("Invalid raw DEFLATE stream") from exc
    if (len(data) > MAX_DECODED_BYTES or not decoder.eof
            or decoder.unused_data or decoder.unconsumed_tail):
        raise DecodeError("Incomplete, oversized, or trailing DEFLATE data")
    reader = Reader(data)
    strings = [reader.string() for _ in range(reader.count(10000))]
    functions = []
    for index in range(reader.count(10000)):
        argc = reader.count(10000)
        strict = reader.integer()
        if strict not in (0, 1):
            raise DecodeError("Invalid function strict flag")
        exceptions = [[reader.integer() for _ in range(4)]
                      for _ in range(reader.count(10000))]
        code = [reader.integer() for _ in range(reader.count(100000))]
        functions.append({"index": index, "argument_count": argc, "strict": bool(strict),
                          "exceptions": exceptions, "bytecode": code})
    if reader.pos != len(data):
        raise DecodeError("Unconsumed VM data")
    for function in functions:
        function["instructions"] = disassemble(function["bytecode"], strings, len(functions))
        boundaries = {item["pc"] for item in function["instructions"]} | {len(function["bytecode"])}
        for entry in function["exceptions"]:
            if (entry != sorted(entry)
                    or any(value not in boundaries for value in entry)):
                raise DecodeError(f"Invalid exception table in function {function['index']}")
    coordinates = {}
    for name, marker in {
        "entry_J": "function J(t,r,e,n)",
        "closure_D": "function D(t,r)",
        "interpreter_X": "function X(t,r,e,n)",
        "dispatch_d": "function d(){for(;;){var t=o[a++]",
        "native_call": "n.apply(d,e)",
        "read_integer_W": "function W(t){for(var r=0,e=0;;)",
        "read_string_K": "function K(t){for(var r=-1,e=new Array;;)",
    }.items():
        offsets = [m.start() for m in re.finditer(re.escape(marker), source)]
        if len(offsets) != 1:
            raise DecodeError(f"Missing or ambiguous reviewed marker: {name}")
        coordinates[name] = location(source, offsets[0])
    coordinates["encoded_data"] = location(source, match.start(1))
    return {"source_sha256": digest, "packed_bytes": len(packed), "xor_seed": seed,
            "decoded_bytes": len(data), "consumed_bytes": reader.pos,
            "locations_zero_based": coordinates, "strings": strings, "functions": functions}


def match_executed(decoded: dict, observed: list[dict]) -> list[dict]:
    matches = []
    for observation in observed:
        if not isinstance(observation, dict):
            raise DecodeError("Observed bytecode entries must be objects")
        bytecode = observation.get("bytecode")
        if not isinstance(bytecode, list) or not all(type(x) is int for x in bytecode):
            raise DecodeError("Invalid observed bytecode")
        pc = observation.get("pc")
        if type(pc) is not int or not 0 <= pc <= len(bytecode):
            raise DecodeError("Invalid observed PC")
        found = [f for f in decoded["functions"] if f["bytecode"] == bytecode]
        matches.append({"pc": pc, "words": len(bytecode),
                        "function_indices": [f["index"] for f in found]})
    return matches


def readable_disassembly(decoded: dict, selected: list[int] | None = None) -> str:
    count = len(decoded["functions"])
    indices = list(range(count)) if selected is None else list(dict.fromkeys(selected))
    if any(type(index) is not int or not 0 <= index < count for index in indices):
        raise DecodeError("Selected function index is out of range")
    lines = [f"BDMS static disassembly; SHA-256 {decoded['source_sha256']}",
             "PC counts integer words, not source columns or decoded-file bytes.",
             "Relative jump targets use the PC AFTER reading opcode and operands.",
             "LOCAL depth=0 means current scope; slot 0=parent, 1=arguments, 2+=parameters.",
             "CALL pops arguments, callee, then this; VM closures enter g(), other functions use apply().",
             "Completion states: f=0 normal, f=1 abrupt jump, f=2 return, f=3 throw.", ""]
    for index in indices:
        function = decoded["functions"][index]
        lines.append(f"FUNCTION {index}: args={function['argument_count']} "
                     f"strict={function['strict']} words={len(function['bytecode'])}")
        for start, catch, finally_, end in function["exceptions"]:
            lines.append(f"  EXCEPTION start={start} catch={catch} finally={finally_} end={end}")
        for item in function["instructions"]:
            operands = ", ".join(map(str, item["operands"]))
            annotation = []
            if "constant" in item:
                annotation.append(json.dumps(item["constant"], ensure_ascii=False))
            if item["opcode"] in TWO_OPERANDS:
                annotation.append(f"depth={item['operands'][0]} slot={item['operands'][1]}")
            if "target_pc" in item:
                annotation.append(f"target={item['target_pc']}; {item['branch_semantics']}")
            if item["opcode"] == 22:
                annotation.append("if f != 0, leave dispatcher and run completion handler y()")
            suffix = " ; " + "; ".join(annotation) if annotation else ""
            lines.append(f"  {item['pc']:05d}  {item['name'].upper():20} {operands}{suffix}")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--executed", type=Path, help="Optional captured bytecode JSON")
    parser.add_argument("--text-output", type=Path, help="Optional human-readable disassembly")
    parser.add_argument("--function", type=int, action="append", dest="functions",
                        help="Select a function for text output; repeat to select several")
    args = parser.parse_args()
    if args.functions and not args.text_output:
        parser.error("--function requires --text-output")
    try:
        with args.source.open("rb") as handle:
            decoded = decode_bundle(handle.read(MAX_SOURCE_BYTES + 1))
        if args.executed:
            observed = json.loads(args.executed.read_text(encoding="utf-8"))
            if not isinstance(observed, list):
                raise DecodeError("Observed bytecode must be a JSON list")
            decoded["observed_matches"] = match_executed(decoded, observed)
        text = readable_disassembly(decoded, args.functions) if args.text_output else None
        for path in (args.output, args.text_output):
            if path is not None and path.exists():
                raise FileExistsError(f"Output already exists: {path}")
        if args.text_output and args.output.resolve() == args.text_output.resolve():
            raise DecodeError("JSON and text outputs must be different files")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # Refuse to silently overwrite a prior research artifact.
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump(decoded, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        if args.text_output:
            args.text_output.parent.mkdir(parents=True, exist_ok=True)
            with args.text_output.open("x", encoding="utf-8") as handle:
                handle.write(text)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(json.dumps({"sha256": decoded["source_sha256"],
                      "strings": len(decoded["strings"]), "functions": len(decoded["functions"]),
                      "decoded_bytes": decoded["decoded_bytes"],
                      "observed_matches": decoded.get("observed_matches", [])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
