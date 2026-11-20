"""Pure Python reconstruction of the captured BDMS 1.0.1.19-fix.01 signer.

This is a research implementation of VM function 150 and its arithmetic
helpers, not a production replacement. Browser observations are explicit
inputs: this module does not invent browser state, load JavaScript, access
cookies, or make network requests. The query is the exact pre-signature query
string and the body must already have been normalized by the request wrapper.

Reviewed source SHA-256:
    a0e46f84476d63a1fa57bdcb47223e0e545c6ce0c3dacdd2818180dfa087909e
"""

from __future__ import annotations

import argparse
import base64
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Sequence

from gmssl import sm3


SOURCE_SHA256 = "a0e46f84476d63a1fa57bdcb47223e0e545c6ce0c3dacdd2818180dfa087909e"
SALT = "dhzx"
ALPHABET_S3 = "ckdp1h4ZKsUB80/Mfvw36XIgR25+WQAlEi7NLboqYTOPuzmFjJnryx9HVGDaStCe"
ALPHABET_S4 = "Dkdpgh2ZmsQB80/MfvV36XI1R45-WUAlEixNLwoqYTOPuzKFjJnry79HbGcaStCe"
STANDARD_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
JS_WHITESPACE = "\u0009\u000b\u000c\u0020\u00a0\ufeff\n\r\u2028\u2029\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u202f\u205f\u3000"


def int32(value: int | float | str) -> int:
    """ECMAScript ToInt32 for the numeric/string values used by this bundle."""
    if isinstance(value, str):
        text = value.strip(JS_WHITESPACE)
        try:
            if not text:
                value = 0
            elif text.lower().startswith(("0x", "0o", "0b")):
                value = int(text, 0)
            else:
                value = float(text)
        except ValueError:
            value = 0
    if not math.isfinite(value):
        return 0
    result = math.trunc(value) & 0xFFFFFFFF
    return result if result < 0x80000000 else result - 0x100000000


def utf16_units(text: str) -> list[int]:
    raw = text.encode("utf-16-le", errors="surrogatepass")
    return [raw[i] | raw[i + 1] << 8 for i in range(0, len(raw), 2)]


def text_bytes_139(text: str) -> list[int]:
    """Function139: UTF-16 units, dropping a unit's zero high byte."""
    result = []
    for value in utf16_units(text):
        if value & 0xFF00:
            result.append(value >> 8)
        result.append(value & 255)
    return result


def sm3_bytes(value: str | Sequence[int]) -> list[int]:
    data = value.encode("utf-8") if isinstance(value, str) else bytes(value)
    return list(bytes.fromhex(sm3.sm3_hash(list(data))))


def cipher_280(key: Sequence[int], plaintext: Sequence[int]) -> list[int]:
    """Function280's reversed-state, multiplicative-KSA stream cipher.

    Values are JavaScript UTF-16 code units. In particular, this helper is not
    standard RC4: both its initial permutation and KSA recurrence differ.
    """
    if not key:
        raise ValueError("Function280 requires a nonempty key")
    state = list(range(255, -1, -1))
    j = 0
    for i in range(256):
        j = (j * state[i] + j + key[i % len(key)]) % 256
        state[i], state[j] = state[j], state[i]
    result = []
    i = j = 0
    for value in plaintext:
        i = (i + 1) % 256
        j = (j + state[i]) % 256
        state[i], state[j] = state[j], state[i]
        result.append((value ^ state[(state[i] + state[j]) % 256]) & 0xFFFF)
    return result


def encode_130(units: Sequence[int], alphabet: str) -> str:
    """Function130 masks UTF-16 input units to eight bits before encoding."""
    if len(alphabet) != 64 or len(set(alphabet)) != 64:
        raise ValueError("Expected a 64-character alphabet")
    encoded = base64.b64encode(bytes(value & 255 for value in units)).decode("ascii")
    return encoded.translate(str.maketrans(STANDARD_ALPHABET, alphabet))


class RandomTape:
    """A finite sequence of recorded Math.random results; exhaustion is an error."""

    def __init__(self, values: Sequence[float]):
        self.values = list(values)
        self.position = 0

    def __call__(self) -> float:
        if self.position >= len(self.values):
            raise ValueError("Recorded random sequence exhausted")
        value = self.values[self.position]
        self.position += 1
        return value


@dataclass(frozen=True)
class BrowserDimensions:
    inner_width: int
    inner_height: int
    outer_width: int
    outer_height: int
    avail_width: int
    avail_height: int
    screen_width: int
    screen_height: int
    platform: str

    def serialize(self) -> str:
        # Function150 PC1061 builds an object in precisely this property order;
        # functions140/141 join its values using a pipe.
        numbers = (self.inner_width, self.inner_height, self.outer_width,
                   self.outer_height, self.avail_width, self.avail_height,
                   self.screen_width, self.screen_height)
        return "|".join([*(str(int32(n)) for n in numbers), self.platform])


@dataclass(frozen=True)
class RuntimeInputs:
    """Observed state, with no defaults for unobserved browser dependencies.

    ``ua_environment_bits`` is vt() (function699), ``tracking_bits`` is the
    effective N() result (or zero when track.mode is nonzero), and
    ``environment_record`` is nr() (function697). ``prefix_environment_flags``
    is the flags element from the second nr() observation in function144.

    The misspellings pemrissions/grnated occur in the actual bundle. The four
    microphone booleans describe those exact properties; they do not describe
    the real Permissions API or permission grants.
    """

    navigator_user_agent: str
    browser_name: str
    now_ms: int
    date_ms: int
    previous_timestamp_ms: int
    call_count_before: int
    ua_environment_bits: int
    tracking_bits: int
    environment_record: Sequence[int]
    prefix_environment_flags: int
    wheel_marker: int
    vendor_ink: int
    dimensions: BrowserDimensions
    own_microphone_granted: bool
    own_microphone_readonly: bool
    prototype_microphone_grnated: bool
    prototype_microphone_readonly: bool

    def __post_init__(self):
        if len(self.environment_record) != 5:
            raise ValueError("nr() must provide exactly five observed values")
        if self.wheel_marker not in (3, 11, 12):
            raise ValueError("Unknown onwheelx._Ax branch result")
        if self.call_count_before < 0:
            raise ValueError("Call count cannot be negative")

    @classmethod
    def from_dict(cls, value: dict) -> "RuntimeInputs":
        fields = dict(value)
        fields["dimensions"] = BrowserDimensions(**fields["dimensions"])
        return cls(**fields)


@dataclass(frozen=True)
class SignatureResult:
    signature: str
    random_values: list[float]
    call_count_after: int
    intermediates: dict


def normalize_browser_fixture(raw: dict, prefix_environment_flags: int, *,
                              prefix_observation_source: str) -> dict:
    """Map a captured ``{input, captures}`` record to explicit signer inputs.

    ``fixedMs`` must identify a clock explicitly fixed by the collector; the
    second Date read is never inferred from the first timestamp. The caller
    must supply both the second nr() flags and their observation provenance.
    No signatures, URLs, or captured inputs are printed by this helper.
    """
    if (isinstance(prefix_environment_flags, bool)
            or not isinstance(prefix_environment_flags, int)):
        raise ValueError("Explicit integer prefix environment flags are required")
    if not isinstance(prefix_observation_source, str) or not prefix_observation_source.strip():
        raise ValueError("Prefix environment observation provenance is required")
    inp = raw["input"]
    if "fixedMs" not in inp or isinstance(inp["fixedMs"], bool) or not isinstance(inp["fixedMs"], int):
        raise ValueError("A recorded fixedMs clock is required; date_ms cannot be inferred")
    captures = [capture for capture in raw["captures"]
                if capture.get("pc") == 1834 and "93" in capture.get("slots", {})]
    if len(captures) != 1:
        raise ValueError("Expected exactly one complete function150 capture")
    capture = captures[0]
    slots = capture["slots"]
    if slots["14"] != inp["fixedMs"]:
        raise ValueError("Captured start time does not match the explicitly fixed clock")
    if not inp["signature"] == capture["result"] == slots["93"]:
        raise ValueError("Captured final signature observations disagree")
    before = inp["before"]
    permissions = inp["permissions"]
    dimensions = slots["75"]
    runtime = RuntimeInputs(
        navigator_user_agent=inp["userAgent"], browser_name=before["browser"],
        now_ms=inp["fixedMs"], date_ms=inp["fixedMs"],
        previous_timestamp_ms=before["previous"], call_count_before=before["counter"],
        ua_environment_bits=slots["16"], tracking_bits=slots["17"],
        environment_record=slots["37"], prefix_environment_flags=prefix_environment_flags,
        wheel_marker=slots["12"], vendor_ink=slots["22"],
        dimensions=BrowserDimensions(
            dimensions["innerWidth"], dimensions["innerHeight"],
            dimensions["outerWidth"], dimensions["outerHeight"],
            dimensions["availWidth"], dimensions["availHeight"],
            dimensions["sizeWidth"], dimensions["sizeHeight"], dimensions["platform"]),
        own_microphone_granted=permissions.get("own") == "granted",
        own_microphone_readonly=permissions.get("ownWritable") is False,
        prototype_microphone_grnated=permissions.get("proto") == "grnated",
        prototype_microphone_readonly=permissions.get("protoWritable") is False,
    )
    comparison_slots = ["18", "19", "20", "21", "26", "27", "28", "37", "76", "77",
                        "81", "82", "86", "87", "88", "89", "90", "91", "92", "93"]
    expected_slots = {key: slots[key] for key in comparison_slots}
    binary = capture.get("binarySlots", {})
    for key in ("89", "91", "92"):
        if key in binary:
            expected_slots[key] = binary[key]
    return {
        "name": raw.get("name", "browser_capture"), "source_sha256": SOURCE_SHA256,
        "query": inp["query"], "body": inp["body"], "page_id": inp["page_id"],
        "aid": inp["aid"], "version": inp["version"], "runtime": asdict(runtime),
        "random_values": inp["randomTape"], "expected_signature": inp["signature"],
        "expected_slots": expected_slots,
        "provenance": {"format": "browser_function150_capture",
                       "clock_source": "input.fixedMs explicitly fixed by collector",
                       "prefix_environment_flags_source": prefix_observation_source},
    }


class _RandomSource:
    def __init__(self, source: Callable[[], float]):
        self.source = source
        self.values: list[float] = []

    def __call__(self) -> float:
        value = self.source()
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value < 1:
            raise ValueError("Math.random observations must be finite values in [0, 1)")
        self.values.append(value)
        return value


def _browser_byte_143(runtime: RuntimeInputs, random: _RandomSource) -> int:
    offset = {"Chrome": 0, "Firefox": 40, "Safari": 81,
              "Edge": 125, "Huawei": 170}.get(runtime.browser_name, 210)
    return int32(random() * 40) + offset


def _environment_byte_144(runtime: RuntimeInputs, random: _RandomSource) -> int:
    if runtime.prefix_environment_flags & 64:
        value = int32(random() * 109)
        return value + 110 + value % 2
    value = int32(random() * 240)
    return value + value % 2 + 1 if value > 109 else value


def _property_byte_145(runtime: RuntimeInputs, random: _RandomSource) -> int:
    value = int32(random() * 255) & 77
    if runtime.own_microphone_granted:
        value |= 1 << 1
        if runtime.own_microphone_readonly:
            value |= 1 << 4
    if runtime.prototype_microphone_grnated:
        value |= 1 << 5
        if runtime.prototype_microphone_readonly:
            value |= 1 << 7
    return value


def _mix_pair_146(pair: Sequence[int], mode: int, runtime: RuntimeInputs,
                  random: _RandomSource) -> list[int]:
    value = int32(random() * 65535)
    low, high = value & 255, (value >> 8) & 255
    if mode == 1:
        high = _browser_byte_143(runtime, random)
    elif mode == 2:
        low = _environment_byte_144(runtime, random)
        high = _property_byte_145(runtime, random)
    return [(low & 170) | (pair[0] & 85),
            (low & 85) | (pair[0] & 170),
            (high & 170) | (pair[1] & 85),
            (high & 85) | (pair[1] & 170)]


def _expand_148(payload: Sequence[int], random: _RandomSource) -> list[int]:
    expanded = []
    for i in range(0, len(payload), 3):
        if i + 2 < len(payload):
            value = int32(random() * 1000) & 255
            a, b, c = payload[i:i + 3]
            expanded.extend([(value & 145) | (a & 110),
                             (value & 66) | (b & 189),
                             (value & 44) | (c & 211),
                             (a & 145) | (b & 66) | (c & 44)])
        else:
            expanded.append(payload[i])
            # This is deliberately the bundle's truthiness check, rather than
            # a length check: a zero second remainder byte is omitted.
            if i + 1 < len(payload) and payload[i + 1]:
                expanded.append(payload[i + 1])
    return expanded


def _selected_digest_byte(digest: Sequence[int], start: int, reserved: int,
                          flags: int, bit: int) -> int:
    index = start
    selected = digest[index]
    while selected == reserved:
        index += 1
        selected = digest[index] if index < len(digest) else reserved + 1
    return reserved if flags & bit else selected


def sign_current(query: str, body: str, *, page_id: int, aid: int, version: str,
                 runtime: RuntimeInputs, random: Callable[[], float]) -> SignatureResult:
    """Reconstruct function150, returning each comparison-relevant stage.

    The three legacy leading arguments and the legacy UA argument are absent
    because this function150 never reads them. Browser UA is an explicit field
    of ``runtime``. Random values are consumed in the original function order.
    """
    if not isinstance(query, str) or not isinstance(body, str):
        raise TypeError("query and normalized body must be strings")
    random = _RandomSource(random)
    s: dict[int, object] = {}
    s[12] = runtime.wheel_marker
    s[14] = runtime.now_ms
    s[16] = runtime.ua_environment_bits
    s[17] = runtime.tracking_bits
    query_hash = sm3_bytes(sm3_bytes(query + SALT))
    body_hash = sm3_bytes(sm3_bytes(body + SALT))
    # Function142: String.fromCharCode(env/256, env%256, track%256).
    ua_key = [math.trunc(runtime.ua_environment_bits / 256) & 0xFFFF,
              runtime.ua_environment_bits % 256, runtime.tracking_bits % 256]
    ua_cipher = cipher_280(ua_key, utf16_units(runtime.navigator_user_agent.strip(JS_WHITESPACE)))
    ua_encoded = encode_130(ua_cipher, ALPHABET_S3)
    ua_hash = sm3_bytes(ua_encoded)
    s[18], s[19], s[20], s[21] = query_hash, body_hash, ua_encoded, ua_hash
    s[22] = runtime.vendor_ink
    s[24] = 41
    version_numbers = [int32(part) for part in version.split(".")]
    # Missing array items become undefined, which bitwise operations map to 0.
    version_four = (version_numbers + [0] * 4)[:4]
    s[25] = version_numbers
    s[26] = int32((runtime.date_ms - 1721836800000) / 1000 / 60 / 60 / 24 / 14)
    call_count_after = runtime.call_count_before + 1
    s[27] = (3 if call_count_after > 10745 else 4 if call_count_after > 1283
             else 5 if call_count_after > 139 else 6)
    s[28] = ((runtime.now_ms - runtime.previous_timestamp_ms + 3) & 255
             if runtime.previous_timestamp_ms > 0 else 2)
    for offset in range(6):
        s[29 + offset] = (runtime.now_ms >> (offset * 8)) & 255
    s[35] = runtime.ua_environment_bits % 256 & 255
    s[36] = math.trunc(runtime.ua_environment_bits / 256) & 255
    environment = list(runtime.environment_record)
    flags = environment[4]
    s[37] = environment
    s[38], s[39] = flags & 255, (flags >> 8) & 255
    for offset in range(4):
        s[40 + offset] = environment[offset]
        s[44 + offset] = (runtime.tracking_bits >> (offset * 8)) & 255
    s[48], s[49] = query_hash[9], query_hash[18]
    s[51] = _selected_digest_byte(query_hash, 3, 11, flags, 2)
    s[52], s[53] = body_hash[10], body_hash[19]
    s[55] = _selected_digest_byte(body_hash, 4, 8, flags, 4)
    s[56], s[57] = ua_hash[11], ua_hash[21]
    s[59] = _selected_digest_byte(ua_hash, 5, 12, flags, 8)
    for offset in range(6):
        s[60 + offset] = (runtime.vendor_ink >> (offset * 8)) & 255
    s[66] = runtime.wheel_marker
    for offset in range(4):
        s[67 + offset] = (page_id >> (offset * 8)) & 255
        s[71 + offset] = (aid >> (offset * 8)) & 255
    fingerprint = runtime.dimensions.serialize()
    fingerprint_bytes = text_bytes_139(fingerprint)
    s[76], s[77] = fingerprint, fingerprint_bytes
    s[79], s[80] = len(fingerprint_bytes) & 255, len(fingerprint_bytes) >> 8 & 255
    time_text = str((runtime.now_ms + 3) & 255) + ","
    time_bytes = text_bytes_139(time_text)
    s[81], s[82] = time_text, time_bytes
    s[84], s[85] = len(time_bytes) & 255, len(time_bytes) >> 8 & 255
    version_block = (_mix_pair_146(version_four[:2], 0, runtime, random)
                     + _mix_pair_146(version_four[2:], 2, runtime, random))
    s[86] = version_block
    checksum_slots = ([24, 26, 27, 28] + list(range(29, 37)) + list(range(38, 50))
                      + [51, 52, 53, 55, 56, 57, 59] + list(range(60, 75))
                      + [79, 80, 84, 85])
    checksum = 0
    for value in version_block + [s[index] for index in checksum_slots]:
        checksum = int32(checksum ^ int32(value))
    s[87] = checksum
    field_slots = [34, 44, 56, 61, 73, 29, 70, 45, 35, 49, 38, 66, 51, 68, 28,
                   48, 64, 47, 30, 71, 26, 55, 31, 69, 59, 40, 62, 63, 27, 72,
                   41, 74, 57, 52, 42, 39, 33, 67, 53, 43, 65, 46, 36, 24, 60,
                   32, 79, 80, 84, 85]
    fields = [s[index] for index in field_slots]
    payload = fields + fingerprint_bytes + time_bytes + [checksum]
    s[88] = payload
    header = _mix_pair_146([3, 82], 1, runtime, random)
    expanded = _expand_148(payload, random)
    s[89], s[90] = header, expanded
    ciphertext = cipher_280([211], [(value & 0xFFFF) for value in version_block + expanded])
    s[91] = ciphertext
    output_units = header + ciphertext
    s[92] = output_units
    signature = encode_130(output_units, ALPHABET_S4)
    s[93] = signature
    intermediates = {
        "source_sha256": SOURCE_SHA256, "query_hash": query_hash,
        "body_hash": body_hash, "ua_key": ua_key, "ua_cipher": ua_cipher,
        "ua_encoded": ua_encoded, "ua_hash": ua_hash,
        "version_numbers": version_numbers, "version_block": version_block,
        "fingerprint": fingerprint, "fingerprint_bytes": fingerprint_bytes,
        "time_text": time_text, "time_bytes": time_bytes, "fields": fields,
        "checksum": checksum, "payload": payload, "header": header,
        "expanded": expanded, "ciphertext": ciphertext,
        "output_units": output_units,
        "vm_slots": {str(key): value for key, value in s.items()},
    }
    return SignatureResult(signature, random.values, call_count_after, intermediates)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path, help="JSON containing exact input, runtime and random_values")
    parser.add_argument("--out", type=Path, required=True,
                        help="Write signatures and intermediate values exclusively to this new local file")
    parser.add_argument("--browser-capture", action="store_true",
                        help="Normalize a raw {input,captures} record or a {fixtures:[...]} collection")
    parser.add_argument("--prefix-environment-flags", type=int,
                        help="Explicit flags from the second nr() observation")
    parser.add_argument("--prefix-observation-source",
                        help="Record where the supplied prefix flags were observed")
    args = parser.parse_args()
    try:
        if args.out.exists():
            raise FileExistsError("Output already exists")
        raw = json.loads(args.fixture.read_text(encoding="utf-8"))
        if args.browser_capture:
            fixtures = raw.get("fixtures", [raw])
            if raw.get("errors"):
                raise ValueError("The browser collector reported errors")
            fixtures = [normalize_browser_fixture(
                fixture, args.prefix_environment_flags,
                prefix_observation_source=args.prefix_observation_source) for fixture in fixtures]
        else:
            fixtures = raw.get("vectors", [raw])
        reports, summaries = [], []
        for fixture in fixtures:
            runtime = RuntimeInputs.from_dict(fixture["runtime"])
            tape = RandomTape(fixture["random_values"])
            result = sign_current(fixture["query"], fixture["body"], page_id=fixture["page_id"],
                                  aid=fixture["aid"], version=fixture["version"],
                                  runtime=runtime, random=tape)
            report = asdict(result)
            matches = (result.signature == fixture["expected_signature"]
                       if "expected_signature" in fixture else None)
            stage_matches = True
            for slot, expected in fixture.get("expected_slots", {}).items():
                if slot in {"89", "91", "92"} and isinstance(expected, str):
                    expected = utf16_units(expected)
                if result.intermediates["vm_slots"].get(slot) != expected:
                    stage_matches = False
            random_matches = tape.position == len(tape.values)
            report.update(expected_signature_matches=matches,
                          expected_stages_match=stage_matches,
                          random_tape_fully_consumed=random_matches,
                          normalized_fixture=fixture)
            reports.append(report)
            summaries.append({"equal": matches, "length": len(result.signature),
                              "stages_equal": stage_matches, "random_equal": random_matches})
        if not reports:
            raise ValueError("No fixtures provided")
        output = json.dumps(reports[0] if len(reports) == 1 else {"results": reports},
                            ensure_ascii=False, indent=2)
        with args.out.open("x", encoding="utf-8") as stream:
            stream.write(output + "\n")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        # Captured inputs may contain session material. Avoid exception values
        # (including input keys/paths) in the CLI output.
        print(json.dumps({"error": type(exc).__name__}))
        return 2
    print(json.dumps(summaries[0] if len(summaries) == 1 else {"results": summaries}))
    return 2 if any(item["equal"] is False or not item["stages_equal"]
                    or not item["random_equal"] for item in summaries) else 0


if __name__ == "__main__":
    raise SystemExit(main())
