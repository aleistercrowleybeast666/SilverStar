"""Fail-closed Arm ELF instruction boundaries used by the stack gate.

Objdump's headings include NOTYPE local labels and omit aliases. ELF FUNC
extents, not those headings, own instructions. Overlapping libgcc entries each
include their shared suffix. All cross-function branches are conservatively
charged as calls; a local non-link branch is an intra-function CFG edge.
"""
import re
from bisect import bisect_left
from collections import deque
from functools import lru_cache
from itertools import pairwise
from math import factorial

CONDITIONS = "(?:eq|ne|cs|hs|cc|lo|mi|pl|vs|vc|hi|ls|ge|lt|gt|le|al)"


@lru_cache(maxsize=4096)
def Opcode_Is(op, base):
    return re.fullmatch(re.escape(base) + "(?:" + CONDITIONS + ")?(?:\\.[nw])?", op) is not None


def BranchKind_Get(op):
    for base in ("blx", "bl", "bx", "b", "cbz", "cbnz"):
        if Opcode_Is(op, base):
            return base
    return None


def Instruction_IsIndirect(op, args):
    args = args.split("@")[0].strip()
    if Instruction_IsReturn(op, args):
        return False
    kind = BranchKind_Get(op)
    if kind in ("bx", "blx"):
        return not (kind == "bx" and args == "lr") and "<" not in args
    if re.match(r"pc\s*,", args):
        return not (Opcode_Is(op, "mov") and re.fullmatch(r"pc,\s*lr", args))
    # A stack POP/LDM return is an ABI return, not a callback registry.
    if "pc" in args and re.match(r"ldm", op) and not args.startswith("sp!"):
        return True
    return False


def Instruction_IsReturn(op, args):
    args = args.split("@")[0].strip().lower()
    return ((Opcode_Is(op, "bx") and args == "lr") or
            (Opcode_Is(op, "mov") and re.fullmatch(r"pc,\s*lr", args)) or
            (Opcode_Is(op, "pop") and re.search(r"\bpc\b", args)) or
            (re.match(r"ldm", op) and args.startswith("sp!") and re.search(r"\bpc\b", args)) or
            (Opcode_Is(op, "ldr") and re.fullmatch(r"pc,\s*\[sp\],\s*#\d+", args)))


def Instruction_IsConditional(op):
    return any(re.fullmatch(re.escape(base) + CONDITIONS + r"(?:\.[nw])?", op)
               for base in ("b", "bl", "blx", "bx", "pop", "push", "mov", "ldr", "sub", "add"))


def Registers_Count(args, width):
    registers = args[args.index("{") + 1:args.index("}")]
    count = 0
    for item in registers.split(","):
        item = item.strip()
        if "-" in item:
            first, last = item.split("-")
            count += int(re.search(r"\d+", last)[0]) - int(re.search(r"\d+", first)[0]) + 1
        else:
            count += 1
    return width * count


def StackDelta_Get(op, args):
    """Positive means allocation. Unknown SP assignments have no guessed bound."""
    args = args.split("@")[0].strip().lower()
    if Opcode_Is(op, "push") or (op.startswith("stmdb") and args.startswith("sp!")):
        return Registers_Count(args, 4)
    if Opcode_Is(op, "pop") or (op.startswith("ldmia") and args.startswith("sp!")):
        return -Registers_Count(args, 4)
    if op.startswith(("vpush", "vpop")):
        count = Registers_Count(args, 8 if "d" in args else 4)
        return -count if op.startswith("vpop") else count
    if re.match(r"(?:sub|add)", op) and re.match(r"sp,", args):
        match = re.fullmatch(r"sp,\s*(?:sp,\s*)?#(0x[0-9a-f]+|\d+)", args)
        if match:
            return int(match[1], 0) * (-1 if op.startswith("add") else 1)
        return None
    if match := re.search(r"\[sp,\s*#(-?(?:0x[0-9a-f]+|\d+))\]!", args):
        return -int(match[1], 0)
    if match := re.search(r"\[sp\],\s*#(-?(?:0x[0-9a-f]+|\d+))", args):
        return -int(match[1], 0)
    if re.search(r"\[sp[^\]]*\]!|\[sp\],", args) or re.match(r"sp,", args):
        # cmp/test/store read SP; all remaining destination-SP operations need
        # an explicit reviewed proof (including compiler frame-pointer restore).
        if not op.startswith(("cmp", "cmn", "tst", "teq", "str", "stm", "ldm")):
            return None
    if op.startswith("msr") and re.match(r"(?:msp|psp),", args):
        return None
    return 0


def ReadOnlyData_Parse(contents, section_headers):
    """Only actual allocated read-only ELF .rodata may supply absolute tables."""
    section = None
    memory = {}
    for line in contents.splitlines():
        if match := re.match(r"Contents of section (\S+):", line):
            section = match[1]
        elif section == ".rodata" and (match := re.match(r"\s*([0-9a-f]+)\s+(.+)", line)):
            raw = match[2][:35].replace(" ", "")
            if not re.fullmatch(r"[0-9a-f]+", raw) or len(raw) % 2:
                raise ValueError("Malformed linked read-only section bytes")
            address = int(match[1], 16)
            memory.update({address + offset: byte for offset, byte in enumerate(bytes.fromhex(raw))})
    if memory:
        declaration = re.search(r"^\s*\d+\s+\.rodata\s+([0-9a-f]+)\s+([0-9a-f]+)[^\n]*\n([^\n]+)",
                                section_headers, re.MULTILINE)
        if not declaration or not {"CONTENTS", "ALLOC", "LOAD", "READONLY", "DATA"}.issubset(
                set(declaration[3].strip().split(", "))):
            raise ValueError("Unproved immutable linked switch table section")
        start, size = int(declaration[2], 16), int(declaration[1], 16)
        if set(memory) != set(range(start, start + size)):
            raise ValueError("Incomplete linked read-only section bytes")
    return memory


def Assembly_Parse(disassembly, symbols, readonly_data=None):
    declarations = {}
    for line in symbols.splitlines():
        match = re.match(r"^([0-9a-f]+)\s+.*?\bF\s+(\.\S+)\s+([0-9a-f]+)\s+(?:\.hidden\s+)?(\S+)\s*$", line)
        if match:
            address, section, size, name = int(match[1], 16), match[2], int(match[3], 16), match[4]
            versions = declarations.setdefault(name, {})
            if address in versions and versions[address] != (address, size, section):
                raise ValueError("Conflicting ELF function extents: " + name)
            versions[address] = (address, size, section)
    functions = {}
    symbol_names = {}
    for name, versions in declarations.items():
        for address, value in versions.items():
            key = name if len(versions) == 1 else name + "@" + format(address, "08x")
            functions[key] = value
            symbol_names[key] = name
    if not functions:
        raise ValueError("Missing ELF FUNC symbol extents")
    rows, memory, literals = {}, dict(readonly_data or {}), {}
    section = None
    for line in disassembly.splitlines():
        if match := re.match(r"Disassembly of section (\S+):", line):
            section = match[1]
        if match := re.match(r"^\s*([0-9a-f]+):\s+((?:(?:[0-9a-f]{8}|[0-9a-f]{4}|[0-9a-f]{2})\s+)+)(\S+)\s*(.*)", line):
            address = int(match[1], 16)
            raw = b"".join(int(word, 16).to_bytes(len(word) // 2, "little") for word in match[2].split())
            if any(address + offset in memory and memory[address + offset] != value for offset, value in enumerate(raw)):
                raise ValueError("Conflicting linked instruction and table bytes")
            memory.update({address + offset: value for offset, value in enumerate(raw)})
            if match[3].startswith("."):
                literals[address] = (match[3], match[4], section)
                continue  # Mapping-symbol literal pool, not an instruction.
            value = (len(re.sub(r"\s", "", match[2])) // 2, match[3], match[4], section)
            if address in rows and rows[address] != value:
                raise ValueError("Ambiguous linked instruction address")
            rows[address] = value
    entries = {}
    addresses = sorted(rows)
    for name, (start, size, section) in functions.items():
        if start not in rows:
            raise ValueError("Missing linked function entry instruction: " + name)
        # Zero-sized assembler FUNC entries extend to the next distinct FUNC
        # entry in the same section. CFG fall-through is checked separately.
        end = start + size if size else min(
            [value[0] for value in functions.values() if value[2] == section and value[0] > start] +
            [max(address + row[0] for address, row in rows.items() if row[3] == section)])
        entries[name] = {"start": start, "end": end, "section": section, "symbol_name": symbol_names[name],
                         "rows": [(address, *rows[address][:3])
                                  for address in addresses[bisect_left(addresses, start):bisect_left(addresses, end)]
                                  if rows[address][3] == section], "memory": memory,
                         "literals": [(row[0], row[1]) for address, row in literals.items()
                                      if start <= address < end and row[2] == section]}
    return entries


def SwitchTargets_Get(index, rows, entry):
    """Recognize GCC's locally guarded Thumb byte/halfword switch table.

    Bounds and table targets come from the actual ELF. Unknown/distant guards,
    altered registers, missing table bytes or out-of-function targets reject.
    """
    address, _, op, args = rows[index]
    absolute = Opcode_Is(op, "ldr")
    width = 4 if absolute else (2 if Opcode_Is(op, "tbh") else 1)
    operands = args.split("@")[0].strip()
    base = address + 4
    guard = index - 2
    if absolute:
        match = re.fullmatch(r"pc,\s*\[(\w+),\s*(\w+),\s*lsl #2\]", operands)
        if not match or index < 3:
            raise ValueError("Unreviewed absolute Thumb switch base")
        base_register, register = match[1], match[2]
        adr_address, _, adr_op, adr_args = rows[index - 1]
        adr = re.fullmatch(re.escape(base_register) + r",\s*pc,\s*#(0x[0-9a-f]+|\d+)", adr_args.split("@")[0].strip())
        if not Opcode_Is(adr_op, "add") or not adr or base_register == register:
            raise ValueError("Unreviewed absolute Thumb switch address materialization")
        base = ((adr_address + 4) & ~3) + int(adr[1], 0)
        guard -= 1
    else:
        match = re.fullmatch(r"\[pc,\s*(\w+)(?:,\s*lsl #1)?\]", operands)
        if not match:
            raise ValueError("Unreviewed Thumb switch base")
        register = match[1]
    # The guard must be the two instructions immediately preceding the table
    # branch. No intervening load/write or bypass is admitted here.
    if guard < 0:
        raise ValueError("Missing Thumb switch bound guard")
    _, _, compare, operands = rows[guard]
    _, _, branch, destination = rows[guard + 1]
    limit = re.fullmatch(re.escape(register) + r",\s*#(0x[0-9a-f]+|\d+)", operands.split("@")[0].strip())
    if not Opcode_Is(compare, "cmp") or not limit or branch.removesuffix(".w").removesuffix(".n") not in ("bhi", "bcs", "bhs"):
        raise ValueError("Unreviewed Thumb switch bound guard")
    default = re.match(r"([0-9a-f]+)\s+<", destination)
    if not default or rows[guard][0] < int(default[1], 16) <= address:
        raise ValueError("Unreviewed Thumb switch default branch")
    count = int(limit[1], 0) + (1 if branch.startswith("bhi") else 0)
    if count <= 0 or count > 256:
        raise ValueError("Unreviewed Thumb switch table bound")
    memory = entry["memory"]
    targets = []
    for item in range(count):
        positions = [base + item * width + offset for offset in range(width)]
        if any(position not in memory for position in positions):
            raise ValueError("Missing linked Thumb switch bytes")
        offset = int.from_bytes(bytes(memory[position] for position in positions), "little")
        if absolute and not offset & 1:
            raise ValueError("Absolute Thumb switch target missing Thumb bit")
        target = (offset & ~1) if absolute else base + offset * 2
        if target not in {row[0] for row in rows}:
            raise ValueError("Thumb switch target outside function instructions")
        targets.append(target)
    return targets, [row[0] for row in rows[guard:index + 1]]


def Thumb1Guard_Get(first, register, rows):
    """Both emitted Thumb-1 forms must dominate the entire address sequence."""
    guard = first - 2
    if first >= 3 and rows[first - 1][2] in ("b", "b.n", "b.w"):
        guard = first - 3
    if guard < 0:
        raise ValueError("Missing Thumb1 switch guard")
    compare, branch = rows[guard], rows[guard + 1]
    limit = re.fullmatch(re.escape(register) + r",\s*#(0x[0-9a-f]+|\d+)",
                         compare[3].split("@")[0].strip())
    branch_op = branch[2].removesuffix(".n").removesuffix(".w")
    destination = re.match(r"([0-9a-f]+)\s+<", branch[3])
    if not Opcode_Is(compare[2], "cmp") or not limit or not destination:
        raise ValueError("Unreviewed Thumb1 switch comparison")
    if guard == first - 3:
        default = re.match(r"([0-9a-f]+)\s+<", rows[first - 1][3])
        if branch_op != "bls" or int(destination[1], 16) != rows[first][0] or not default:
            raise ValueError("Unreviewed Thumb1 switch range branch")
        default_address = int(default[1], 16)
        count = int(limit[1], 0) + 1
    else:
        if branch_op not in ("bhi", "bcs", "bhs"):
            raise ValueError("Unreviewed Thumb1 switch default branch")
        default_address = int(destination[1], 16)
        count = int(limit[1], 0) + (branch_op == "bhi")
    if count <= 0 or count > 256 or default_address not in {row[0] for row in rows}:
        raise ValueError("Invalid Thumb1 switch bound or default")
    return count, [compare[0], branch[0]], default_address


def Thumb1TableTargets_Get(base, count, width, entry, *, relative):
    memory, instructions = entry["memory"], {row[0] for row in entry["rows"]}
    targets = []
    for item in range(count):
        addresses = range(base + item * width, base + (item + 1) * width)
        if any(address not in memory for address in addresses):
            raise ValueError("Missing linked Thumb1 switch table bytes")
        value = int.from_bytes(bytes(memory[address] for address in addresses), "little")
        # MOV PC forces bit zero low; unlike BX it does not select ARM state.
        target = base + 2 * value if relative else value & ~1
        if target not in instructions:
            raise ValueError("Thumb1 switch target outside function instructions")
        targets.append(target)
    return targets


def Thumb1SwitchTargets_Get(index, rows, entry, entries):
    address, width, op, args = rows[index]
    operands = args.split("@")[0].strip()
    if Opcode_Is(op, "bl"):
        helper = entries.get("__gnu_thumb1_case_uqi")
        target = re.match(r"([0-9a-f]+)\s+<__gnu_thumb1_case_uqi>", args)
        expected = [("push", "{r1}"), ("mov", "r1, lr"), ("lsrs", "r1, r1, #1"),
                    ("lsls", "r1, r1, #1"), ("ldrb", "r1, [r1, r0]"),
                    ("lsls", "r1, r1, #1"), ("add", "lr, r1"),
                    ("pop", "{r1}"), ("bx", "lr")]
        if not helper or not target or int(target[1], 16) != helper["start"] or width != 4:
            raise ValueError("Unknown Thumb1 table helper")
        actual = [(row[2], row[3].split("@")[0].strip()) for row in helper["rows"]]
        if actual != expected or any(row[1] != 2 or row[0] != helper["start"] + 2 * i
                                     for i, row in enumerate(helper["rows"])):
            raise ValueError("Changed linked Thumb1 table helper")
        first, register, base = index, "r0", address + width
        count, guard, default = Thumb1Guard_Get(first, register, rows)
        targets = Thumb1TableTargets_Get(base, count, 1, entry, relative=True)
    else:
        match = re.fullmatch(r"pc,\s*(r[0-7])", operands)
        if not Opcode_Is(op, "mov") or not match or index < 3:
            raise ValueError("Unreviewed Thumb1 absolute switch")
        target_register = match[1]
        load = re.fullmatch(re.escape(target_register) + r",\s*\[(r[0-7]),\s*(r[0-7])\]",
                            rows[index - 1][3].split("@")[0].strip())
        if not Opcode_Is(rows[index - 1][2], "ldr") or not load or load[1] == load[2]:
            raise ValueError("Unreviewed Thumb1 indexed table load")
        base_register, index_register = load[1], load[2]
        first, parts = index - 3, rows[index - 3:index - 1]
        shifts = [row for row in parts if row[2] == "lsls"]
        loads = [row for row in parts if Opcode_Is(row[2], "ldr")]
        if len(shifts) != 1 or len(loads) != 1:
            raise ValueError("Unreviewed Thumb1 table address sequence")
        shift = re.fullmatch(re.escape(index_register) + r",\s*(r[0-7]),\s*#2",
                             shifts[0][3].split("@")[0].strip())
        literal = re.fullmatch(re.escape(base_register) + r",\s*\[pc,\s*#(0x[0-9a-f]+|\d+)\]",
                               loads[0][3].split("@")[0].strip())
        if not shift or not literal or (loads[0][0] < shifts[0][0] and base_register == shift[1]):
            raise ValueError("Changed Thumb1 switch index or base")
        location = ((loads[0][0] + 4) & ~3) + int(literal[1], 0)
        if any(location + offset not in entry["memory"] for offset in range(4)):
            raise ValueError("Missing linked Thumb1 table pointer")
        base = int.from_bytes(bytes(entry["memory"][location + offset] for offset in range(4)), "little")
        count, guard, default = Thumb1Guard_Get(first, shift[1], rows)
        targets = Thumb1TableTargets_Get(base, count, 4, entry, relative=False)
    chain = guard + [row[0] for row in rows[first:index + 1]]
    if default in chain or any(target in chain[1:] for target in targets):
        raise ValueError("Thumb1 switch bypasses its range guard")
    return targets, chain


def SavedLinkReturns_Get(rows, successors, reachable, local_calls):
    """Prove the Thumb1 split POP/BX ABI return from its saved LR stack slot.

    Like POP {pc}, this establishes control/stack shape, not arbitrary memory
    safety. No name grant, unknown SP write, ambiguous stack height, bypass or
    direct overwrite of the saved slot can earn this interpretation.
    """
    if local_calls or not rows:
        return set()
    push_index, prefix = 0, 0
    if rows[0][2] in ("sub", "sub.n", "sub.w") and rows[0][3].startswith("sp,"):
        prefix = StackDelta_Get(rows[0][2], rows[0][3])
        push_index = 1
    if prefix is None or push_index >= len(rows):
        return set()
    push = rows[push_index]
    if push[2] != "push" or not re.search(r"\blr\b", push[3]):
        return set()
    saved_depth = prefix + 4
    by_address = {row[0]: row for row in rows}
    incoming = {address: {origin for origin, values in successors.items() if address in values}
                for address in reachable}
    depths, queue = {rows[0][0]: 0}, deque([rows[0][0]])
    while queue:
        address = queue.popleft()
        row = by_address[address]
        delta = StackDelta_Get(row[2], row[3])
        if delta is None or (delta and Instruction_IsConditional(row[2])):
            return set()
        after = depths[address] + delta
        for target in successors[address]:
            if target in depths and depths[target] != after:
                return set()
            if target not in depths:
                depths[target] = after
                queue.append(target)
    if any(incoming.get(rows[i][0], set()) != {rows[i - 1][0]} for i in range(1, push_index + 1)):
        return set()
    # Direct SP stores that overlap the saved LR invalidate the return proof.
    for address in reachable:
        _, _, op, args = by_address[address]
        store = re.fullmatch(r"\w+,\s*\[sp(?:,\s*#(\d+))?\]", args.split("@")[0].strip())
        if ((op.startswith("str") and "[sp" in args and not store) or
                (op.startswith("stm") and args.startswith("sp"))):
            return set()
        if op.startswith("str") and store:
            size = 1 if op.startswith("strb") else 2 if op.startswith("strh") else 8 if op.startswith("strd") else 4
            start = int(store[1] or 0) - depths[address]
            if start < -saved_depth + 4 and start + size > -saved_depth:
                return set()
        if address != push[0] and op == "push":
            start, end = -depths[address] - Registers_Count(args, 4), -depths[address]
            if start < -saved_depth + 4 and end > -saved_depth:
                return set()
    result = set()
    for index, row in enumerate(rows):
        if row[0] not in reachable or row[2] != "bx" or not re.fullmatch(r"r[0-7]", row[3].strip()):
            continue
        first = index - 1
        if first >= 0 and rows[first][2] in ("add", "add.n", "add.w") and rows[first][3].startswith("sp,"):
            first -= 1
        if first < 0 or rows[first][2] != "pop" or rows[first][3].strip() != "{" + row[3].strip() + "}":
            continue
        chain = rows[first:index + 1]
        if (depths.get(chain[0][0]) != saved_depth or depths.get(row[0]) != 0 or
                any(incoming.get(current[0], set()) != {previous[0]} for previous, current in pairwise(chain))):
            continue
        result.add(row[0])
    return result


def Function_Analyze(name, entry, entries, no_return=()):
    rows = entry["rows"]
    by_address = {row[0]: row for row in rows}
    starts = {}
    for target, data in entries.items():
        starts.setdefault(data["start"], []).append(target)
    edges_by_address, tail_returns, unknown = {}, {}, []
    successors, weights, switches, local_calls = {}, {}, {}, {}
    for index, (address, width, op, args) in enumerate(rows):
        edge = edges_by_address.setdefault(address, set())
        tail = tail_returns.setdefault(address, set())
        kind = BranchKind_Get(op)
        target = re.match(r"(?:\w+,\s*)?([0-9a-f]+)\s+<([^>+]+)(?:\+[^>]+)?>", args)
        destination = int(target[1], 16) if target else None
        conditional = Instruction_IsConditional(op) or kind in ("cbz", "cbnz")
        next_addresses = []
        table_branch = (Opcode_Is(op, "tbb") or Opcode_Is(op, "tbh") or
                        (Opcode_Is(op, "ldr") and re.match(r"pc,\s*\[\w+,\s*\w+,\s*lsl #2\]", args)))
        thumb1_table = ((Opcode_Is(op, "bl") and target and target[2].startswith("__gnu_thumb1_case_")) or
                        (Opcode_Is(op, "mov") and re.match(r"pc,\s*r[0-7](?:\s|$)", args)))
        terminal = (Instruction_IsReturn(op, args) or Opcode_Is(op, "udf") or
                    (Instruction_IsIndirect(op, args) and kind != "blx"))
        if Instruction_IsIndirect(op, args) and not (table_branch or thumb1_table):
            unknown.append((address, op, args))
        if table_branch or thumb1_table:
            try:
                switch_targets, guard = (Thumb1SwitchTargets_Get(index, rows, entry, entries)
                                         if thumb1_table else SwitchTargets_Get(index, rows, entry))
                next_addresses.extend(switch_targets)
                switches[address] = guard
            except ValueError as error:
                unknown.append((address, "unresolved-switch", str(error)))
            terminal = True
        if kind and destination is not None:
            if kind in ("bl", "blx") and destination in by_address and destination not in starts:
                local_calls[address] = (destination, address + width, conditional)
            elif kind in ("bl", "blx") or destination not in by_address:
                candidates = starts.get(destination, [])
                if not candidates:
                    # A branch into a different function's interior requires
                    # that entire function, conservatively including its frame.
                    candidates = [key for key, value in entries.items()
                                  if value["start"] <= destination < value["end"]]
                if not candidates:
                    raise ValueError("Unresolved direct branch target: " + name + ":" + args)
                selected = target[2] if target[2] in candidates else sorted(candidates)[0]
                edge.add(selected)
                if kind not in ("bl", "blx") and selected not in no_return:
                    tail.add(selected)
                if kind in ("bl", "blx") and selected in no_return:
                    terminal = True
            elif kind not in ("bl", "blx"):
                next_addresses.append(destination)
        if not ((terminal and not conditional) or (kind == "b" and not conditional)):
            following = address + width
            if following in by_address:
                next_addresses.append(following)
            elif following in starts:
                selected = sorted(starts[following])[0]
                edge.add(selected)
                if selected not in no_return:
                    tail.add(selected)
            elif not terminal:
                # Data pools can follow an unconditional terminal only. An
                # executable fall-through into unmapped bytes is not a return.
                unknown.append((address, "unmapped-fallthrough", hex(following)))
        successors[address] = next_addresses
        delta = StackDelta_Get(op, args)
        weights[address] = max(0, delta) if delta is not None and conditional else delta
    for address, guard in switches.items():
        for previous, current in zip(guard, guard[1:]):
            incoming = {origin for origin, targets in successors.items() if current in targets}
            if incoming != {previous}:
                unknown.append((address, "unresolved-switch", "Switch guard can be bypassed"))
    # Longest weighted CFG path. A positive stack-growth cycle cannot acquire a
    # finite bound from summing each push once. Fail closed after |V| relaxations.
    initial = (entry["start"], ())
    depths = {initial: 0}
    queue, queued = deque([initial]), {initial}
    relaxations, maximum, unknown_sp = {}, 0, []
    call_count = len(local_calls)
    # An active local target may never repeat. This gives a finite call-string
    # state space without mistaking GCC libgcc's internal BL helpers for entry
    # recursion. Recursive local BL is rejected independently of SP growth.
    state_limit = len(rows) * sum(factorial(call_count) // factorial(call_count - depth)
                                 for depth in range(call_count + 1))
    while queue:
        state = queue.popleft()
        queued.remove(state)
        address, returns = state
        delta = weights[address]
        if delta is None:
            unknown_sp.append(address)
            delta = 0
        value = depths[state] + delta
        maximum = max(maximum, value)
        next_states = [(target, returns) for target in successors[address]]
        if address in local_calls:
            target, continuation, conditional = local_calls[address]
            if target in {item[0] for item in returns}:
                raise ValueError("Recursive local linked subroutine: " + name)
            next_states = [(target, (*returns, (target, continuation)))]
            if conditional:
                next_states.append((continuation, returns))
        elif returns and Instruction_IsReturn(by_address[address][2], by_address[address][3]):
            next_states.append((returns[-1][1], returns[:-1]))
        for target in next_states:
            if target[0] not in by_address:
                raise ValueError("Unresolved local link return address: " + name)
            if value > depths.get(target, -10**12):
                depths[target] = value
                relaxations[target] = relaxations.get(target, 0) + 1
                if relaxations[target] > state_limit:
                    raise ValueError("Unbounded stack-growth instruction cycle: " + name)
                if target not in queued:
                    queue.append(target)
                    queued.add(target)
    reachable = {state[0] for state in depths}
    saved_link_returns = SavedLinkReturns_Get(rows, successors, reachable, local_calls)
    return {"edges": set().union(*(edges_by_address[address] for address in reachable)),
            "indirect": [row for row in unknown if row[0] in reachable and row[0] not in saved_link_returns], "frame_bytes": maximum,
            "unknown_sp": sorted(set(unknown_sp)), "reachable_addresses": sorted(reachable),
            "successors": successors,
            "returns": [address for address, context in depths if not context and
                        (Instruction_IsReturn(by_address[address][2], by_address[address][3]) or address in saved_link_returns)],
            "tail_returns": sorted(set().union(*(tail_returns[address] for address in reachable))),
            "local_link_calls": {hex(address): {"target": hex(value[0]), "continuation": hex(value[1])}
                                 for address, value in local_calls.items() if address in reachable},
            "switches": {address: guard for address, guard in switches.items() if address in reachable},
            "saved_link_returns": sorted(saved_link_returns)}
