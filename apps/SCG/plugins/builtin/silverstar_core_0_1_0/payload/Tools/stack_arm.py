"""Fail-closed Arm ELF instruction boundaries used by the stack gate.

Objdump's headings include NOTYPE local labels and omit aliases. ELF FUNC
extents, not those headings, own instructions. Overlapping libgcc entries each
include their shared suffix. All cross-function branches are conservatively
charged as calls; a local non-link branch is an intra-function CFG edge.
"""
from collections import deque
from bisect import bisect_left
from functools import lru_cache
from math import factorial
import re

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


def Assembly_Parse(disassembly, symbols):
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
    rows, memory, literals = {}, {}, {}
    section = None
    for line in disassembly.splitlines():
        if match := re.match(r"Disassembly of section (\S+):", line):
            section = match[1]
        if match := re.match(r"^\s*([0-9a-f]+):\s+((?:(?:[0-9a-f]{8}|[0-9a-f]{4}|[0-9a-f]{2})\s+)+)(\S+)\s*(.*)", line):
            address = int(match[1], 16)
            raw = b"".join(int(word, 16).to_bytes(len(word) // 2, "little") for word in match[2].split())
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
        terminal = (Instruction_IsReturn(op, args) or Opcode_Is(op, "udf") or
                    (Instruction_IsIndirect(op, args) and kind != "blx"))
        if Instruction_IsIndirect(op, args) and not table_branch:
            unknown.append((address, op, args))
        if table_branch:
            try:
                switch_targets, guard = SwitchTargets_Get(index, rows, entry)
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
    return {"edges": set().union(*(edges_by_address[address] for address in reachable)),
            "indirect": [row for row in unknown if row[0] in reachable], "frame_bytes": maximum,
            "unknown_sp": sorted(set(unknown_sp)), "reachable_addresses": sorted(reachable),
            "successors": successors,
            "returns": [address for address, context in depths if not context and Instruction_IsReturn(by_address[address][2], by_address[address][3])],
            "tail_returns": sorted(set().union(*(tail_returns[address] for address in reachable))),
            "local_link_calls": {hex(address): {"target": hex(value[0]), "continuation": hex(value[1])}
                                 for address, value in local_calls.items() if address in reachable},
            "switches": {address: guard for address, guard in switches.items() if address in reachable}}
