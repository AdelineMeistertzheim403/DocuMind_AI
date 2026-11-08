"""Read ELF64 dynamic symbols and GNU versions without executing a loader or library."""
import struct


def require(value, message):
    if not value:
        raise ValueError(message)


def inspect(data):
    require(data[:7] == b'\x7fELF\x02\x01\x01' and len(data) >= 64, 'ELF64 little endian required')

    def unpack(fmt, offset):
        require(0 <= offset <= len(data) - struct.calcsize(fmt), 'Truncated ELF table')
        return struct.unpack_from(fmt, data, offset)

    def region(offset, size):
        require(0 <= offset <= len(data) and 0 <= size <= len(data) - offset, 'ELF range outside file')
        return data[offset:offset + size]

    def string(table, offset):
        require(0 <= offset < len(table), 'Invalid ELF string offset')
        end = table.find(b'\0', offset)
        require(end >= 0, 'Unterminated ELF string')
        return table[offset:end].decode('ascii')

    kind, machine = unpack('<HH', 16)
    require(kind in (2, 3) and machine == 62, 'Expected x86_64 executable/shared object')
    phoff, shoff = unpack('<QQ', 32)
    phsize, phnum, shsize, shnum, _ = unpack('<HHHHH', 54)
    require(phsize >= 56 and shsize >= 64 and shnum > 0, 'Unavailable ELF headers')
    sections = [unpack('<IIQQQQIIQQ', shoff + i * shsize) for i in range(shnum)]
    for section in sections:
        if section[1] != 8:
            region(section[4], section[5])
    loads, dynamic, interpreter = [], [], None
    for i in range(phnum):
        ptype, _, offset, address, _, size, _, _ = unpack('<IIQQQQQQ', phoff + i * phsize)
        content = region(offset, size)
        if ptype == 1:
            loads.append((address, address + size, offset))
        elif ptype == 2:
            require(not size % 16, 'Invalid dynamic table')
            for tag, value in struct.iter_unpack('<qQ', content):
                if tag == 0:
                    break
                dynamic.append((tag, value))
        elif ptype == 3:
            require(interpreter is None, 'Duplicate PT_INTERP')
            interpreter = string(content, 0)
    pointers = [v for tag, v in dynamic if tag == 5]
    sizes = [v for tag, v in dynamic if tag == 10]
    require(len(pointers) == len(sizes) == 1, 'Dynamic strings unavailable/ambiguous')
    addresses = [offset + pointers[0] - start for start, end, offset in loads if start <= pointers[0] < end]
    require(len(addresses) == 1, 'Ambiguous dynamic string mapping')
    strings = region(addresses[0], sizes[0])

    def dynamic_names(tag):
        return [string(strings, v) for key, v in dynamic if key == tag]

    def table_strings(section):
        require(section[6] < len(sections), 'Invalid linked string table')
        linked = sections[section[6]]
        return region(linked[4], linked[5])

    imports, definitions, required_versions = {}, {}, {}
    for section in sections:
        if section[1] not in (0x6ffffffe, 0x6ffffffd):
            continue
        text = table_strings(section)
        begin, length = section[4], section[5]

        def bounded(fmt, offset):
            require(begin <= offset <= begin + length - struct.calcsize(fmt), 'GNU version bounds')
            return unpack(fmt, offset)

        cursor, seen = begin, set()
        while cursor < begin + length:
            require(cursor not in seen, 'Cyclic GNU version list')
            seen.add(cursor)
            if section[1] == 0x6ffffffe:
                version, count, filename, aux, following = bounded('<HHIII', cursor)
                require(version == 1 and count > 0, 'Unsupported verneed')
                library = string(text, filename)
                item, visited = cursor + aux, set()
                for index in range(count):
                    require(item not in visited, 'Cyclic vernaux')
                    visited.add(item)
                    _, _, number, name, next_aux = bounded('<IHHII', item)
                    pair = (library, string(text, name))
                    number &= 0x7fff
                    require(number >= 2 and (number not in imports or imports[number] == pair),
                            'Ambiguous imported version')
                    imports[number] = pair
                    required_versions.setdefault(library, set()).add(pair[1])
                    require(bool(next_aux) == (index < count - 1), 'Truncated vernaux chain')
                    item += next_aux
            else:
                version, _, number, count, _, aux, following = bounded('<HHHHIII', cursor)
                require(version == 1 and count > 0, 'Unsupported verdef')
                name, _ = bounded('<II', cursor + aux)
                value = string(text, name)
                require(number not in definitions, 'Duplicate version definition')
                definitions[number] = value
            if not following:
                break
            require(following > 0, 'Invalid GNU version offset')
            cursor += following
            require(cursor < begin + length, 'GNU version link outside section')
    dynsyms = [(i, s) for i, s in enumerate(sections) if s[1] == 11]
    require(len(dynsyms) == 1, 'Dynamic symbol table unavailable/ambiguous')
    table_index, symbols = dynsyms[0]
    require(symbols[9] == 24 and not symbols[5] % 24, 'Invalid ELF64 symbol size')
    versions = [s for s in sections if s[1] == 0x6fffffff and s[6] == table_index]
    require(len(versions) <= 1, 'Ambiguous symbol version table')
    if versions:
        require(versions[0][5] == symbols[5] // 24 * 2, 'Symbol/version count mismatch')
    text = table_strings(symbols)
    undefined, exported = [], []
    for index in range(symbols[5] // 24):
        name, info, visibility, section_index, _, _ = unpack('<IBBHQQ', symbols[4] + index * 24)
        binding, symbol_type = info >> 4, info & 15
        if not name or binding not in (1, 2, 10):
            continue
        number = unpack('<H', versions[0][4] + index * 2)[0] if versions else 1
        hidden, number = bool(number & 0x8000), number & 0x7fff
        row = {'name': string(text, name), 'type': symbol_type, 'weak': binding == 2}
        if section_index == 0:
            require(number < 2 or number in imports, 'Unknown imported version index')
            library, version = imports[number] if number >= 2 else (None, None)
            undefined.append({**row, 'library': library, 'version': version})
        elif visibility & 3 in (0, 3):
            require(number < 2 or number in definitions, 'Unknown exported version index')
            exported.append({**row, 'version': definitions.get(number) if number >= 2 else None,
                             'default': not hidden})
    return {'machine': 'x86_64', 'elf_type': kind, 'interpreter': interpreter,
            'needed': dynamic_names(1), 'soname': dynamic_names(14),
            'rpath': dynamic_names(15), 'runpath': dynamic_names(29),
            'version_requires': {k: sorted(v) for k, v in sorted(required_versions.items())},
            'version_defines': sorted(set(definitions.values())),
            'undefined_symbols': undefined, 'exported_symbols': exported,
            'gnu_ifunc_present': any(s['type'] == 10 for s in exported)}


def compare_symbols(consumer, provider, library):
    exported = {(s['name'], s['version']) for s in provider['exported_symbols']}
    required = [s for s in consumer['undefined_symbols'] if s['library'] == library]
    absent = [s for s in required if (s['name'], s['version']) not in exported]
    versions = sorted(set(consumer['version_requires'].get(library, [])) - set(provider['version_defines']))
    return {'versioned_symbols_checked': len(required), 'missing_strong': [s for s in absent if not s['weak']],
            'missing_weak': [s for s in absent if s['weak']], 'missing_versions': versions,
            'unversioned_process_scope_proven': False,
            'loader_scope_relocations_ifunc_cpu_isa_proven': False}
