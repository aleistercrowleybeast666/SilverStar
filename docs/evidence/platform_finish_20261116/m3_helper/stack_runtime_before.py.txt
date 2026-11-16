"""Reviewed runtime binding proofs for Cortex-M stack analysis.

These routines are only acceptance evidence after the caller has sealed the
complete selected source/compiler-input closure. They do not authorize a new
callback registry or infer freedom from arbitrary memory corruption.
"""
import hashlib
import json
import re


def Symbols_Get(nm):
    result = {}
    for line in nm.splitlines():
        words = line.split()
        if len(words) in (3, 4):
            name = words[-1]
            value = {"address": int(words[0], 16), "size": int(words[1], 16) if len(words) == 4 else 0,
                     "kind": words[-2]}
            if name in result and result[name] != value:
                continue  # Local table names may repeat; never used below.
            result[name] = value
    return result


def Literal_Read(entry, row):
    address, _, op, args = row
    match = re.fullmatch(r"\w+,\s*\[pc,\s*#(\d+)\]", args.split("@")[0].strip())
    if op not in ("ldr", "ldr.w") or not match:
        raise ValueError("Unreviewed PC-relative runtime literal load")
    pointer = ((address + 4) & ~3) + int(match[1])
    memory = entry["memory"]
    if any(pointer + offset not in memory for offset in range(4)):
        raise ValueError("Missing linked runtime literal bytes")
    return int.from_bytes(bytes(memory[pointer + offset] for offset in range(4)), "little")


def Instructions_Normalize(rows):
    result = []
    for _, _, op, args in rows:
        op = op.removesuffix(".w").removesuffix(".n")
        args = args.split("@")[0].strip().lower()
        args = re.sub(r"\s+", "", args)
        args = re.sub(r"\bsl\b", "r10", args)
        args = re.sub(r"\bfp\b", "r11", args)
        result.append(op + " " + args)
    return result


def PortStackPointers_Resolve(root, graph):
    symbols = Symbols_Get(graph["nm"])
    tcb = symbols["pxCurrentTCB"]["address"]
    top = symbols["_estack"]["address"]
    entries = graph["function_entries"]
    reset = entries["Reset_Handler"]
    reset_rows = reset["rows"]
    if (not reset_rows[0][3].startswith("sp,") or Literal_Read(reset, reset_rows[0]) != top or
            graph["assembly_proofs"]["Reset_Handler"]["unknown_sp"] != [reset_rows[0][0]]):
        raise ValueError("Reset MSP does not match linked vector stack top")
    svc = entries["SVC_Handler"]
    expected_svc = ["ldr r3,LITERAL", "ldr r1,[r3,#0]", "ldr r0,[r1,#0]",
        "ldmia r0!,{r4,r5,r6,r7,r8,r9,r10,r11,lr}", "msr psp,r0", "isb sy",
        "mov r0,#0", "msr basepri,r0", "bx lr"]
    svc_rows = Instructions_Normalize(svc["rows"])
    if Literal_Read(svc, svc["rows"][0]) != tcb:
        raise ValueError("SVC restore does not use actual pxCurrentTCB")
    svc_rows[0] = "ldr r3,LITERAL"
    if svc_rows != expected_svc:
        raise ValueError("Unreviewed linked SVC task-stack restoration")
    pend = entries["PendSV_Handler"]
    pend_rows = Instructions_Normalize(pend["rows"])
    if Literal_Read(pend, pend["rows"][2]) != tcb:
        raise ValueError("PendSV restore does not use actual pxCurrentTCB")
    pend_rows[2] = "ldr r3,LITERAL"
    call = [index for index, value in enumerate(pend_rows) if value.startswith("bl ")]
    if len(call) != 1 or not pend_rows[call[0]].endswith("<vtaskswitchcontext>"):
        raise ValueError("Unreviewed PendSV scheduler call")
    pend_rows[call[0]] = "bl vTaskSwitchContext"
    if not re.fullmatch(r"mov r0,#\d+", pend_rows[10]):
        raise ValueError("Unreviewed PendSV critical-section immediate")
    pend_rows[10] = "mov r0,PRIORITY"
    expected_pend = ["mrs r0,psp", "isb sy", "ldr r3,LITERAL", "ldr r2,[r3,#0]",
        "tst lr,#16", "it eq", "vstmdbeq r0!,{s16-s31}",
        "stmdb r0!,{r4,r5,r6,r7,r8,r9,r10,r11,lr}", "str r0,[r2,#0]", "push {r0,r3}",
        "mov r0,PRIORITY", "msr basepri,r0", "dsb sy", "isb sy", "bl vTaskSwitchContext",
        "mov r0,#0", "msr basepri,r0", "pop {r0,r3}", "ldr r1,[r3,#0]", "ldr r0,[r1,#0]",
        "ldmia r0!,{r4,r5,r6,r7,r8,r9,r10,r11,lr}", "tst lr,#16", "it eq",
        "vldmiaeq r0!,{s16-s31}", "msr psp,r0", "isb sy", "bx lr"]
    h7_pend = expected_pend[:11] + ["cpsid i"] + expected_pend[11:14] + ["cpsie i"] + expected_pend[14:]
    if pend_rows not in (expected_pend, h7_pend) or graph["frames"]["PendSV_Handler"] < 8:
        raise ValueError("Unreviewed linked PendSV PSP/MSP split")
    start = entries["prvPortStartFirstTask"]
    start_rows = Instructions_Normalize(start["rows"])
    if Literal_Read(start, start["rows"][0]) != 0xE000ED08:
        raise ValueError("Scheduler start does not read VTOR")
    start_rows[0] = "ldr r0,VTOR"
    if start_rows != ["ldr r0,VTOR", "ldr r0,[r0,#0]", "ldr r0,[r0,#0]", "msr msp,r0",
                      "mov r0,#0", "msr control,r0", "cpsie i", "cpsie f", "dsb sy", "isb sy", "svc 0", "nop "]:
        raise ValueError("Unreviewed linked scheduler MSP reset/handoff")
    ports = [path for path in graph["sources"] if path.endswith("/port.c")]
    if len(ports) != 1:
        raise ValueError("Expected one selected FreeRTOS port")
    source = (root / ports[0]).read_text(encoding="utf8")
    if not re.search(r"#define\s+portINITIAL_EXC_RETURN\s+\(\s*0xfffffffd\s*\)", source, re.IGNORECASE):
        raise ValueError("Task initial exception-return does not select PSP")
    initial = SourceFunctions_Get(source).get("pxPortInitialiseStack", "")
    if len(re.findall(r"\*pxTopOfStack\s*=\s*portINITIAL_EXC_RETURN\s*;", initial)) != 1:
        raise ValueError("Missing task exception-return initialization")
    for name in ("Reset_Handler", "SVC_Handler", "PendSV_Handler", "prvPortStartFirstTask"):
        graph["unbounded"].discard(name)
    if graph["assembly_proofs"]["prvPortStartFirstTask"]["indirect"] != [
            (start["rows"][-1][0], "unmapped-fallthrough", hex(start["rows"][-1][0] + start["rows"][-1][1]))]:
        raise ValueError("Extra scheduler handoff indirect boundary")
    graph["indirect"].discard("prvPortStartFirstTask")
    return {"port_source": ports[0], "port_sha256": hashlib.sha256((root / ports[0]).read_bytes()).hexdigest(),
            "task_context_software_bytes": 100, "PendSV_MSP_local_bytes": graph["frames"]["PendSV_Handler"],
            "scheduler_handoff": "VTOR initial MSP reset, SVC restores controlled task EXC_RETURN 0xfffffffd/PSP",
            "boot_stack_top": hex(top), "pxCurrentTCB": hex(tcb)}


def CrtCallbacks_Resolve(root, graph, prefix, table_read):
    result = []
    for name in ("deregister_tm_clones", "register_tm_clones"):
        if name not in graph["indirect"]:
            continue
        entry = graph["function_entries"][name]
        rows = entry["rows"]
        sites = graph["assembly_proofs"][name]["indirect"]
        if len(sites) != 1:
            raise ValueError("Unreviewed CRT weak callback count")
        address, op, args = sites[0]
        index = next(index for index, row in enumerate(rows) if row[0] == address)
        if index < 2 or op != "bx" or args != "r3" or Literal_Read(entry, rows[index - 2]) != 0:
            raise ValueError("CRT weak callback is not the linked NULL symbol")
        guard = rows[index - 1]
        target = re.fullmatch(r"r3,\s*([0-9a-f]+)\s+<[^>]+>", guard[3])
        if (guard[2] != "cbz" or not target or
                not any(row[0] == int(target[1], 16) and row[2:] == ("bx", "lr") for row in rows)):
            raise ValueError("Missing CRT weak NULL guard")
        successors = graph["assembly_proofs"][name]["successors"]
        for previous, current in zip(rows[index - 2:index], rows[index - 1:index + 1]):
            if {origin for origin, values in successors.items() if current[0] in values} != {previous[0]}:
                raise ValueError("CRT weak NULL guard can be bypassed")
        graph["indirect"].remove(name)
        result.append({"caller": name, "linked_weak_pointer": 0, "guard": "PC-relative NULL load, CBZ to BX LR; no guard bypass"})
    name = "__libc_init_array"
    if name not in graph["indirect"]:
        return result
    symbols = Symbols_Get(graph["nm"])
    entry = graph["function_entries"][name]
    rows = entry["rows"]
    normalized = Instructions_Normalize(rows)
    literal_indices = (1, 2, 9, 10)
    names = ("__preinit_array_end", "__preinit_array_start", "__init_array_start", "__init_array_end")
    for index, symbol in zip(literal_indices, names):
        if symbol not in symbols or Literal_Read(entry, rows[index]) != symbols[symbol]["address"]:
            raise ValueError("CRT initializer loop does not load linked array endpoints")
        normalized[index] = normalized[index].split(",", 1)[0] + "," + symbol
    for index, value in enumerate(normalized):
        if "<__libc_init_array+" in value:
            normalized[index] = value.split(" ", 1)[0] + " " + value.split("<__libc_init_array+", 1)[1].removesuffix(">")
        elif "<_init>" in value:
            normalized[index] = "bl _init"
    expected = ["push {r4,r5,r6,lr}", "ldr r3,__preinit_array_end", "ldr r5,__preinit_array_start",
        "subs r3,r3,r5", "asrs r4,r3,#2", "movs r6,#0", "cmp r6,r4", "bne 0x24", "bl _init",
        "ldr r5,__init_array_start", "ldr r3,__init_array_end", "subs r3,r3,r5", "asrs r4,r3,#2",
        "movs r6,#0", "cmp r6,r4", "bne 0x2e", "pop {r4,r5,r6,pc}",
        "ldr r3,[r5],#4", "blx r3", "adds r6,#1", "b 0xc",
        "ldr r3,[r5],#4", "blx r3", "adds r6,#1", "b 0x1e"]
    if normalized != expected:
        raise ValueError("Unreviewed linked CRT initializer loop shape")
    starts = {}
    for function, definition in graph["function_entries"].items():
        starts.setdefault(definition["start"], []).append(function)
    for label in ("__preinit_array", "__init_array"):
        start, end = symbols[label + "_start"]["address"], symbols[label + "_end"]["address"]
        if end < start or (end - start) % 4 or end - start > graph["elf"].stat().st_size:
            raise ValueError("Invalid linked CRT initializer array bounds")
        raw = table_read(root, prefix, graph["elf"], start, end - start) if end > start else b""
        targets = []
        for offset in range(0, len(raw), 4):
            pointer = int.from_bytes(raw[offset:offset + 4], "little")
            if not pointer & 1 or (pointer & ~1) not in starts:
                raise ValueError("Unresolved linked CRT initializer target")
            target = sorted(starts[pointer & ~1])[0]
            graph["edges"][name].add(target)
            targets.append(target)
        result.append({"caller": name, "array": label, "start": hex(start), "end": hex(end),
                       "entries": len(targets), "targets": targets,
                       "bytes_sha256": hashlib.sha256(raw).hexdigest()})
    graph["indirect"].remove(name)
    return result


def DwarfLocation_Read(value):
    if re.fullmatch(r"\d+", value):
        return int(value)
    expression = re.fullmatch(r"(\d+) byte block:\s*((?:[0-9a-f]{1,2}\s+)+)\(DW_OP_plus_uconst:\s*(\d+)\)", value)
    if expression:
        raw = bytes.fromhex(' '.join(word.zfill(2) for word in expression[2].split()))
        if len(raw) == int(expression[1]) and 2 <= len(raw) <= 6 and raw[0] == 0x23:
            result = 0
            for index, byte in enumerate(raw[1:]):
                result |= (byte & 0x7f) << (7 * index)
                if not byte & 0x80:
                    if index == len(raw) - 2 and result == int(expression[3]):
                        return result
                    break
    raise ValueError("Unreviewed DWARF member location")


def DwarfMembers_Get(text, names):
    """Use actual linked DWARF field offsets, rejecting inconsistent CUs."""
    structures = {name: [] for name in names}
    current, member, depth = None, None, None
    for line in text.splitlines():
        tag = re.match(r"\s*<(\d+)><[0-9a-f]+>:.*\((DW_TAG_\w+)\)", line)
        if tag:
            level, kind = int(tag[1]), tag[2]
            if current is not None and level <= depth:
                if current.get("name") in structures:
                    structures[current["name"]].append(current["members"])
                current, member = None, None
            if kind == "DW_TAG_structure_type":
                current, member, depth = {"members": {}}, None, level
            elif current is not None and kind == "DW_TAG_member" and level == depth + 1:
                member = {}
            elif current is not None:
                member = None
            continue
        if current is None:
            continue
        if "DW_AT_name " in line:
            name = line.rsplit(":", 1)[1].strip()
            if member is not None:
                member["name"] = name
            else:
                current["name"] = name
        elif member is not None and "DW_AT_data_member_location:" in line:
            value = line.split("DW_AT_data_member_location:", 1)[1].strip()
            if "name" not in member:
                raise ValueError("Unreviewed DWARF member location")
            current["members"][member["name"]] = DwarfLocation_Read(value)
    result = {}
    for name, alternatives in structures.items():
        alternatives = [value for value in alternatives if value]
        if not alternatives or any(value != alternatives[0] for value in alternatives[1:]):
            raise ValueError("Missing or inconsistent linked callback ABI: " + name)
        result[name] = alternatives[0]
    return result


def SourceFunctions_Get(text):
    # Remove strings/comments before balancing braces. No macro expansion is
    # guessed; complete source+headers+compiler flags are separately sealed.
    text = re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                  lambda match: " " * len(match[0]), text, flags=re.DOTALL)
    text = re.sub(r"(?m)^\s*#[^\n]*(?:\\\n[^\n]*)*", "", text)
    functions = {}
    cursor = 0
    while (opening := text.find("{", cursor)) >= 0:
        prefix = text[max(cursor, text.rfind(";", cursor, opening) + 1):opening]
        candidate, parenthesis = None, 0
        for token in re.finditer(r"[A-Za-z_]\w*|[()=]", prefix):
            word = token[0]
            if word == "(":
                parenthesis += 1
            elif word == ")":
                parenthesis -= 1
            elif word == "=" and parenthesis == 0:
                candidate = None
                break  # A global aggregate initializer is not a function.
            elif parenthesis == 0 and word not in ("__attribute__", "__declspec") and re.match(r"\s*\(", prefix[token.end():]):
                candidate = word
        level, end = 1, opening + 1
        while level and end < len(text):
            level += (text[end] == "{") - (text[end] == "}")
            end += 1
        if level:
            raise ValueError("Unbalanced callback source body")
        if candidate:
            if candidate in ("if", "while", "for", "switch") or candidate in functions:
                raise ValueError("Ambiguous callback source definition: " + candidate)
            functions[candidate] = text[opening + 1:end - 1]
        cursor = end
    return functions


def HalSlots_Get(graph, caller, index):
    rows = graph["function_entries"][caller]["rows"]
    register = rows[index][3].strip()
    if not re.fullmatch(r"r\d+|ip", register):
        raise ValueError("Unreviewed HAL callback register")
    successors = graph["assembly_proofs"][caller]["successors"]
    predecessors = {row[0]: set() for row in rows}
    for origin, values in successors.items():
        for target in values:
            predecessors[target].add(origin)
    by_address = {row[0]: row for row in rows}
    pending = [(origin, register) for origin in predecessors[rows[index][0]]]
    seen, slots = set(), set()
    while pending:
        address, register = pending.pop()
        if (address, register) in seen:
            continue
        seen.add((address, register))
        _, _, op, args = by_address[address]
        args = args.split("@")[0].strip()
        if op.startswith("mov") and (match := re.fullmatch(r"(\w+),\s*(\w+)", args)) and match[1] == register:
            register = match[2]
        elif op in ("ldr", "ldr.w") and (match := re.fullmatch(r"(\w+),\s*\[(\w+),\s*#(\d+)\]", args)) and match[1] == register:
            slots.add(int(match[3]))
            continue
        elif re.match(re.escape(register) + r",", args) and not op.startswith(("cmp", "cmn", "tst", "teq", "str", "cb")):
            raise ValueError("Unreviewed HAL callback register write")
        elif op.startswith(("pop", "ldm")) and re.search(r"\b" + register + r"\b", args):
            raise ValueError("HAL callback register restored from an unproved stack value")
        elif op in ("bl", "bl.w", "blx") and register in ("r0", "r1", "r2", "r3", "ip", "lr"):
            raise ValueError("HAL callback register crosses an unproved call clobber")
        if not predecessors[address]:
            raise ValueError("HAL callback load can be bypassed from function entry")
        pending.extend((origin, register) for origin in predecessors[address])
    if not slots:
        raise ValueError("HAL callback slot provenance NOT PROVEN")
    return sorted(slots)


def HalCallbacks_Resolve(root, graph, prefix, command_read, callback_slot, *, review=None, diagnostic=False):
    if not diagnostic and not review:
        raise ValueError("Missing reviewed HAL handle/object contract")
    callers = {name for name in ("HAL_DMA_IRQHandler", "HAL_DMA_Abort_IT", "HAL_UART_IRQHandler")
               if name in graph["indirect"]}
    if not callers:
        return []
    dwarf = command_read([prefix + "readelf", "--debug-dump=info", str(graph["elf"])], root)
    type_names = {"__DMA_HandleTypeDef"}
    if "RxISR" in (root / next(path for path in graph["sources"] if path.endswith("hal_uart.c"))).read_text(encoding="utf8"):
        type_names.add("__UART_HandleTypeDef")
    members = DwarfMembers_Get(dwarf, type_names)
    fields = {field for mapping in members.values() for field in mapping
              if field.startswith("Xfer") and field.endswith("Callback") or field in ("RxISR", "TxISR")}
    selected_sources = {path: (root / path).read_text(encoding="utf8") for path in graph["sources"]}
    source_definitions = {path: SourceFunctions_Get(text) for path, text in selected_sources.items()
                          if any(field in text for field in fields)}
    declared_functions = set().union(*(set(value) for value in source_definitions.values()))
    targets = {field: set() for field in fields}
    assignments = []
    null_assignments = {field: [] for field in fields}
    for path, text in selected_sources.items():
        if not any(field in text for field in fields):
            continue
        definitions = source_definitions[path]
        for function, body in definitions.items():
            for match in re.finditer(r"->\s*(" + "|".join(sorted(fields)) + r")\s*=(?!=)\s*([^;]+);", body):
                field, value = match[1], re.sub(r"\s", "", match[2])
                if value in ("NULL", "0", "0U"):
                    null_assignments[field].append({"source": path, "function": function})
                    continue
                if value not in graph["instructions"]:
                    if value in declared_functions:
                        # A retained address assignment keeps its function in
                        # the linked ELF. A constant source branch whose target
                        # was discarded by compile/link is not a runtime target.
                        # A variable callback parameter is never handled here.
                        continue
                    # Unlinked APIs with a runtime callback parameter are only
                    # absent when no selected C unit refers to that API outside
                    # its own definition. Unknown callers/aliases fail closed.
                    references = sum(len(re.findall(r"\b" + re.escape(function) + r"\b",
                        re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.DOTALL)))
                        for source in selected_sources.values())
                    if function in graph["instructions"] or references != 1:
                        raise ValueError("Unresolved runtime HAL callback assignment: " + path + ":" + function + ":" + value)
                    continue
                targets[field].add(value)
                assignments.append({"source": path, "function": function, "field": field, "target": value})
    result = []
    for caller in sorted(callers):
        mapping = dict(members["__DMA_HandleTypeDef"])
        if caller == "HAL_UART_IRQHandler" and "__UART_HandleTypeDef" in members:
            mapping.update({field: offset for field, offset in members["__UART_HandleTypeDef"].items() if field in ("RxISR", "TxISR")})
        by_offset = {offset: field for field, offset in mapping.items() if field in fields}
        if len(by_offset) != len([field for field in mapping if field in fields]):
            raise ValueError("Ambiguous HAL DMA/UART callback ABI slot")
        rows = graph["instructions"][caller]
        sites = graph["assembly_proofs"][caller]["indirect"]
        for address, op, args in sites:
            row_index = next(index for index, row in enumerate(graph["function_entries"][caller]["rows"]) if row[0] == address)
            if not re.fullmatch(r"b(?:l)?x(?:\.[nw])?", op):
                raise ValueError("Unreviewed HAL callback instruction: " + caller)
            for slot in HalSlots_Get(graph, caller, row_index):
                if slot not in by_offset:
                    raise ValueError("Unbound actual HAL callback slot: " + caller + ":" + str(slot))
                field = by_offset[slot]
                if not targets[field] and not null_assignments[field]:
                    raise ValueError("HAL callback field has no initialized target domain: " + field)
                graph["edges"][caller].update(targets[field])
                result.append({"caller": caller, "address": hex(address), "abi_slot": slot,
                               "field": field, "targets": sorted(targets[field]),
                               "null_assignments": null_assignments[field],
                               "null_only": not targets[field],
                               "assignments": [row for row in assignments if row["field"] == field]})
        graph["indirect"].remove(caller)
    if not diagnostic:
        HalObjectContract_Verify(root, graph, review, result)
    return result


def HalHandles_Get(root, graph):
    symbols = Symbols_Get(graph['nm'])
    if '_sbss' not in symbols or '_ebss' not in symbols:
        raise ValueError('Missing startup zero-initialization boundaries')
    handles = {}
    for path in graph['sources']:
        source = (root / path).read_text(encoding='utf8')
        clean = re.sub(r'/\*.*?\*/|//[^\n]*', '', source, flags=re.DOTALL)
        for match in re.finditer(r'(?m)^\s*(?:static\s+)?(DMA_HandleTypeDef|UART_HandleTypeDef)\s+(\w+)\s*;', clean):
            ctype, name = match[1], match[2]
            if name in handles:
                raise ValueError('Ambiguous HAL storage object')
            symbol = symbols.get(name)
            if (symbol is None or symbol['kind'] not in ('b', 'B') or not symbol['size'] or
                    symbol['address'] < symbols['_sbss']['address'] or
                    symbol['address'] + symbol['size'] > symbols['_ebss']['address']):
                raise ValueError('HAL handle is not in the actual startup-zeroed BSS: ' + name)
            handles[name] = {'type': ctype, 'source': path, 'address': hex(symbol['address']), 'bytes': symbol['size']}
    return handles


def HalObjectContract_Verify(root, graph, review, sites):
    """Enforce the exact manually audited object/alias domain, not a regex claim.

    A scanner's NULL assignment is never initialization/dominance evidence.
    The sealed review identifies every real handle, its BSS object and all
    callback-load object types/targets for this actual linked executable.
    """
    if review.get("schema") != "silverstar.hal-stack-objects/1":
        raise ValueError("Missing reviewed HAL handle/object contract")
    if review.get("elf_sha256") != hashlib.sha256(graph["elf"].read_bytes()).hexdigest():
        raise ValueError("Changed reviewed HAL object executable")
    expected = review.get("sites")
    actual = [{key: row[key] for key in ("caller", "address", "abi_slot", "field", "targets", "null_only")}
              for row in sites]
    if actual != expected:
        raise ValueError("Changed reviewed HAL callback object/target domain")
    handles = HalHandles_Get(root, graph)
    if not handles or handles != review.get("bss_handles"):
        raise ValueError("Changed reviewed HAL handle storage inventory")
    required = {"handle_initialization_and_parent_links", "callback_installers_and_alias_writes",
                "object_type_at_each_linked_load", "null_only_field_initialization", "no_runtime_registration"}
    audit = review.get("manual_findings", {})
    if set(audit) != required or any(not isinstance(value, str) or len(value) < 40 for value in audit.values()):
        raise ValueError("Incomplete manual HAL object/initialization/alias proof")


def ControlTask_Verify(root, graph, contract, closure_get):
    path = root / 'Generated/control_research.json'
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != contract.get('sha256'):
        raise ValueError('Changed reviewed control task contract')
    data = json.loads(raw)
    if (data.get('schema_id') != 'silverstar.control-research-runtime/1' or
            data.get('enabled') is not contract.get('enabled') or data.get('kind') != contract.get('kind')):
        raise ValueError('Unreviewed control task kind/enable state')
    cores = {'pid': 'ControlPid_Step', 'lqr': 'ControlLqr_Step'}
    if not data['enabled']:
        if any(name in graph['instructions'] for name in cores.values()):
            raise ValueError('Unexpected linked control kernel in disabled reviewed case')
        return {'enabled': False, 'required_functions': [], 'reachable': True}
    if data['kind'] not in cores or data.get('period_us') != 10000:
        raise ValueError('Unreviewed continuous control task')
    required = {'ControlResearch_Process', 'ControlResearchBackend_Step', cores[data['kind']]}
    closure = closure_get('AppTask_Flight')
    if not required <= closure:
        raise ValueError('Enabled control math kernel is not in the actual Flight task closure')
    return {'enabled': True, 'kind': data['kind'], 'required_functions': sorted(required),
            'reachable': True, 'period_us': data['period_us'], 'contract_sha256': contract['sha256']}


def WholeProgram_Build(root, graph, contract, prefix, table_read, budget_get, minimum_margin):
    """Bound reset/main and every actual vector; not a hardware measurement."""
    symbols = Symbols_Get(graph['nm'])
    vector = symbols.get('g_pfnVectors')
    if not vector or vector['kind'] not in ('r', 'R') or vector['size'] < 64 or vector['size'] % 4:
        raise ValueError('Missing complete linked exception vector table')
    raw = table_read(root, prefix, graph['elf'], vector['address'], vector['size'])
    if len(raw) != vector['size'] or hashlib.sha256(raw).hexdigest() != contract.get('vector_sha256'):
        raise ValueError('Changed reviewed exception vector table')
    entries = [int.from_bytes(raw[index:index + 4], 'little') for index in range(0, len(raw), 4)]
    if (entries[0] != symbols['_estack']['address'] or
            entries[1] != (graph['function_entries']['Reset_Handler']['start'] | 1)):
        raise ValueError('Vector initial MSP/reset entry mismatch')
    by_address = {}
    for name, entry in graph['function_entries'].items():
        by_address.setdefault(entry['start'] | 1, []).append(name)
    budgets = []
    for number, address in enumerate(entries[2:], 2):
        if address == 0:
            continue
        targets = by_address.get(address)
        if not targets:
            raise ValueError('Exception vector points outside linked function entries')
        count, chain = max((budget_get(name) for name in targets), key=lambda item: item[0])
        budgets.append({'exception_number': number, 'targets': sorted(targets),
                        'call_chain_bytes': count, 'chain': chain})
    if {2, 3} - {row['exception_number'] for row in budgets}:
        raise ValueError('Missing NMI/HardFault exception proof')
    header = root / contract.get('cmsis_device_header', '')
    if not header.is_file() or not re.search(r'#define\s+__NVIC_PRIO_BITS\s+4[Uu]?\b', header.read_text(encoding='utf8')):
        raise ValueError('Unreviewed architectural priority width')
    if contract.get('priority_bits') != 4:
        raise ValueError('Unreviewed architectural priority width')
    levels = contract.get('priority_levels')
    if levels == 4:
        if contract.get('raw_priority_domain') != [0, 5, 6, 15] or not contract.get('priority_write_review'):
            raise ValueError('Missing exact reviewed IRQ priority write domain')
    elif levels != 16:
        raise ValueError('Unreviewed IRQ nesting bound')
    reset, chain = budget_get('Reset_Handler')
    configurable = max(row['call_chain_bytes'] for row in budgets if row['exception_number'] >= 4)
    fixed = sum(row['call_chain_bytes'] for row in budgets if row['exception_number'] in (2, 3))
    exception_frame = 108  # 32 core + 72 floating-point + 4 alignment bytes.
    estimate = reset + levels * (configurable + exception_frame) + fixed + 2 * exception_frame
    allocated = symbols['_Min_Stack_Size']['address']
    return {'configured_bytes': allocated, 'main_reset_bytes': reset, 'main_reset_chain': chain,
            'priority_levels': levels, 'priority_bits': 4, 'exception_frame_bytes': exception_frame,
            'maximum_configurable_handler_bytes': configurable, 'fixed_handler_bytes': fixed,
            'worst_known_bytes': estimate, 'margin_bytes': allocated - estimate,
            'passes': allocated - estimate >= minimum_margin, 'vectors': budgets,
            'method': 'Reset/main maximum plus all configurable nesting levels, NMI and HardFault; every exception charged an extended FP frame, including first task interrupt.'}
