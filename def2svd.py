#!/usr/bin/python3

# Copyright 2023 Dual Tachyon
# https://github.com/DualTachyon
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
#     Unless required by applicable law or agreed to in writing, software
#     distributed under the License is distributed on an "AS IS" BASIS,
#     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#     See the License for the specific language governing permissions and
#     limitations under the License.

import argparse
import sys
import xml.etree.ElementTree as xml

DEVICE_TAGS = [
    ('vendor', 'RockChip Electronics Co., Ltd.'),
    ('vendorID', 'RK'),
    ('name', 'RockChip_RK3588'),
    ('series', 'RK3588'),
    ('version', '0.1'),
    ('description', 'RockChip RK3588 System-on-Chip'),
    ('headerSystemFilename', 'rk3588'),
    ('headerDefinitionsPrefix', 'RK3588_'),
    ('addressUnitBits', '8'),
    ('width', '32'),
    ('size', '32'),
    ('access', 'read-write'),
]

ACCESS_TAGS = {
    'RO': 'read-only',
    'WO': 'write-only',
}

MODIFIED_TAGS = {
    'W1C': 'oneToClear',
    'W1S': 'oneToSet',
}

SIZE_TAGS = {
    'U8': 8,
    'U16': 16,
    'U32': 32,
}

def parse_peripheral_name(line, original):
    if line[-1] != ']':
        raise Exception('Invalid peripheral name: %s' % original)

    name = line[:-1].strip()
    group = None

    if ',' in name:
        tokens = name.split(',')
        if len(tokens) != 2:
            raise Exception('Invalid peripheral name: %s' % original)
        name = tokens[0].strip()
        group = tokens[1].strip()

    if not name.isidentifier() or (group and not group.isidentifier()):
        raise Exception('Invalid peripheral name: %s' % original)

    return (name, group)

def parse_address_block(line, original):
    line = line.strip()
    if line[0] != '=':
        raise Exception('Invalid address block: %s' % original)
    tokens = line[1:].split(',')
    if len(tokens) != 2:
        raise Exception('Invalid address block: %s' % original)
    try:
        tokens[0] = int(tokens[0], 0)
        tokens[1] = int(tokens[1], 0)
    except:
        raise Exception('Invalid address block: %s' % original)

    return tokens

def parse_register(line, original):
    if not '=' in line:
        raise Exception('Invalid register definition: %s' % original)

    description = None
    i = line.find(';')
    if i > 0:
        description = line[i + 1:].strip()
        line = line[:i].strip()

    tokens = line.split('=')
    if len(tokens) != 2:
        raise Exception('Invalid register definition: %s' % original)

    if ',' in tokens[1]:
        sub = tokens[1].split(',')
        sub = [s.strip() for s in sub]
        tokens[1] = sub[0]
        tokens.append(sub[1:])

    tokens[0] = tokens[0].strip()
    tokens[1] = tokens[1].strip()
    if len(tokens) == 2:
        tokens.append(['RW'])
    else:
        modifiers = [modifier.strip().upper() for modifier in tokens[2]]
        access_flag = False
        modify_flag = False
        size_flag = False
        for modifier in modifiers:
            if modifier in ACCESS_TAGS:
                if access_flag:
                    raise Exception('Unexpected bitfield modifier (%s): %s' % (modifier, original))
                access_flag = True
            elif modifier in MODIFIED_TAGS:
                if modify_flag:
                    raise Exception('Unexpected bitfield modifier (%s): %s' % (modifier, original))
                modify_flag = True
            elif modifier in SIZE_TAGS:
                if size_flag:
                    raise Exception('Unexpected bitfield modifier (%s): %s' % (modifier, original))
                size_flag = True
            else:
                raise Exception('Invalid bitfield modifier (%s): %s' % (modifier, original))

    try:
        tokens[1] = int(tokens[1], 0)
    except:
        raise Exception('Invalid register definition: %s' % original)

    return (*tokens, description)

def parse_bitfield(line, original):
    description = None
    i = line.find(';')
    if i > 0:
        description = line[i + 1:].strip()
        line = line[:i].strip()

    tokens = line.split(',')
    if len(tokens) != 3 and len(tokens) != 4:
        raise Exception('Invalid bitfield definition: %s' % original)

    tokens[0] = int(tokens[0].strip(), 0)
    tokens[1] = int(tokens[1].strip(), 0)
    tokens[2] = tokens[2].strip()
    if len(tokens) == 3:
        tokens.append('RW')
    else:
        tokens[3] = tokens[3].strip().upper()
        if not tokens[3] in [*ACCESS_TAGS, *MODIFIED_TAGS]:
            raise Exception('Invalid bitfield access mode: %s' % original)

    return (*tokens, description)

def parse_enum(line, original):
    description = None
    i = line.find(';')
    if i > 0:
        description = line[i + 1:].strip()
        line = line[:i]

    tokens = line.split(',')
    if len(tokens) != 2:
        raise Exception('Invalid bitfield enum: %s' % original)

    try:
        tokens[0] = int(tokens[0], 0)
    except:
        raise Exception('Invalid bitfield enum: %s' % original)

    tokens[1] = tokens[1].strip()

    return (*tokens, description)

def strip_comment(line):
    i = line.find('#')
    if i >= 0:
        line = line[:i]
    return line

def check_for_overlaps(peripherals):
    addresses = []

    for p_name, (_, p_address, p_size, p_regs) in sorted(peripherals.items()):
        if p_address is None or p_size is None:
            raise Exception('Peripheral %s does not have an address block!' % p_name)

        for addr in addresses:
            tail = p_address + p_size - 1
            if tail < addr[0]:
                continue
            if p_address < addr[0] + addr[1]:
                raise Exception('Peripheral %s overlaps with another!' % p_name)

        addresses.append((p_address, p_size))

        reg_names = []
        reg_offsets = []

        for _, (r_name, offset, _, _, bitfields) in p_regs.items():
            if r_name in reg_names or offset in reg_offsets:
                raise Exception('Register %s.%s (0x%04X) conflicts with another!' % (p_name, r_name, offset))

            reg_names.append(r_name)
            reg_offsets.append(offset)

            bitset = set()
            for bitfield_k, (start, width, b_name, _, _, enums) in bitfields.items():
                for i in range(width):
                    bit = start + i
                    if bit in bitset:
                        raise Exception('Bitfield %s for %s.%s (0x%04X) overlaps with another!' % (b_name, p_name, r_name, offset))
                    bitset.add(bit)

                enumset = set()
                for enum_k, (enum, _, _) in enums.items():
                    if enum in enumset:
                        raise Exception('Enum %d for bitfield %s at %s.%s (0x%04X)!' % (enum, b_name, p_name, r_name, offset))
                    enumset.add(enum)

def generate_svd(all_peripherals, filename, gen_empty):
    device = xml.Element('device')
    device.attrib['schemaVersion'] = "1.3"
    device.attrib['xmlns:xs'] = "http://www.w3.org/2001/XMLSchema-instance"
    device.attrib['xs:noNamespaceSchemaLocation'] = "CMSIS-SVD.xsd"
    for tag in DEVICE_TAGS:
        element = xml.Element(tag[0])
        element.text = tag[1]
        device.append(element)

    peripherals = xml.Element('peripherals')
    for p_name, (p_group, p_address, p_size, p_regs) in sorted(all_peripherals.items()):
        peripheral = xml.Element('peripheral')

        name = xml.Element('name')
        name.text = p_name
        peripheral.append(name)

        if p_group:
            group = xml.Element('groupName')
            group.text = p_group
            peripheral.append(group)

        baseAddress = xml.Element('baseAddress')
        baseAddress.text = '0x%09X' % p_address
        peripheral.append(baseAddress)

        addressBlock = xml.Element('addressBlock')

        offset = xml.Element('offset')
        offset.text = '0x0'
        addressBlock.append(offset)

        size = xml.Element('size')
        size.text = '0x%X' % p_size
        addressBlock.append(size)

        usage = xml.Element('usage')
        usage.text = 'registers'
        addressBlock.append(usage)

        peripheral.append(addressBlock)

        registers = xml.Element('registers')

        for _, (r_name, r_offset, r_modifiers, r_description, bitfields) in p_regs.items():
            register = xml.Element('register')

            name = xml.Element('name')
            name.text = r_name
            register.append(name)

            if r_description is not None:
                description = xml.Element('description')
                description.text = r_description
                register.append(description)

            addressOffset = xml.Element('addressOffset')
            addressOffset.text = '0x%04X' % r_offset
            register.append(addressOffset)

            for modifier in r_modifiers:
                if modifier != 'RW' and modifier in ACCESS_TAGS:
                    access = xml.Element('access')
                    access.text = ACCESS_TAGS[modifier]
                    register.append(access)
                elif modifier in MODIFIED_TAGS:
                    modified = xml.Element('modifiedWriteValues')
                    modified.text = MODIFIED_TAGS[modifier]
                    register.append(modified)
                elif modifier in SIZE_TAGS:
                    size = xml.Element('size')
                    size.text = str(SIZE_TAGS[modifier])
                    register.append(size)

            if len(bitfields):
                fields = xml.Element('fields')
                for bitfield_k, (offset, width, bf_name, bf_access, bf_description, enums) in bitfields.items():
                    field = xml.Element('field')

                    name = xml.Element('name')
                    name.text = bf_name
                    field.append(name)

                    if bf_description is not None:
                        description = xml.Element('description')
                        description.text = bf_description
                        field.append(description)

                    bitOffset = xml.Element('bitOffset')
                    bitOffset.text = str(offset)
                    field.append(bitOffset)

                    bitWidth = xml.Element('bitWidth')
                    bitWidth.text = str(width)
                    field.append(bitWidth)

                    if bf_access in ACCESS_TAGS:
                        access = xml.Element('access')
                        access.text = ACCESS_TAGS[bf_access]
                        field.append(access)

                    if bf_access in MODIFIED_TAGS:
                        modified = xml.Element('modifiedWriteValues')
                        modified.text = MODIFIED_TAGS[bf_access]
                        field.append(modified)

                    if len(enums):
                        enumeratedValues = xml.Element('enumeratedValues')
                        for enum_k, (enum_value, enum_name, enum_description) in enums.items():
                            enumeratedValue = xml.Element('enumeratedValue')

                            if enum_name != '_':
                                name = xml.Element('name')
                                name.text = enum_name #enum_v[1]
                                enumeratedValue.append(name)

                            if enum_description is not None:
                                description = xml.Element('description')
                                description.text = enum_description
                                enumeratedValue.append(description)

                            value = xml.Element('value')
                            value.text = str(enum_value)
                            enumeratedValue.append(value)

                            enumeratedValues.append(enumeratedValue)

                        field.append(enumeratedValues)

                    fields.append(field)
                register.append(fields)
            registers.append(register)
        if len(p_regs) > 0:
            peripheral.append(registers)
        if len(p_regs) > 0 or gen_empty:
            peripherals.append(peripheral)
        else:
            print('Peripheral %s has no registers!' % p_name)

    device.append(peripherals)
    tree = xml.ElementTree(device)
    xml.indent(tree, space = '\t', level = 0)
    f = open(filename, 'wb')
    f.write(b'<?xml version="1.0" encoding="utf-8"?>\n')
    f.write(b'\n')
    tree.write(f)

def load_definition(peripherals, filename):
    lines = open(filename, 'r').readlines()
    lines = [line.strip() for line in lines]

    current_peripheral = None
    current_register = None
    current_bitfield = None

    line_num = 0
    for original in lines:
        line_num += 1
        line = strip_comment(original)
        if not line:
            continue

        if line[0] == '[':
            (name, group) = parse_peripheral_name(line[1:], original)
            if name in peripherals:
                raise Exception('Duplicate peripheral name at line %d: %s' % (line_num, name))
            current_peripheral = [group, None, None, {}]
            peripherals[name] = current_peripheral
            current_register = None
            current_bitfield = None

        elif line[0] == '@':
            address_block = parse_address_block(line[1:], original)
            if not current_peripheral:
                raise Exception('Peripheral address block without name at line %d: %s' % (line_num, original))

            if current_peripheral[1] is not None or current_peripheral[2] is not None:
                raise Exception('Duplicate peripheral address block at line %d: %s' % (line_num, original))

            current_peripheral[1] = address_block[0]
            current_peripheral[2] = address_block[1]

        elif line[0] == '>':
            bitfield = parse_bitfield(line[1:], original)

            if not current_register:
                raise Exception('Bitfield definition without register at line %d: %s' % (line_num, original))

            register = current_peripheral[3][current_register]
            bitfields = register[4]
            if bitfield[0] in bitfields:
                raise Exception('Duplicate bitfield definition at line %d for %s: %s' % (line_num, current_register, original))

            bitfields[bitfield[0]] = (*bitfield, {})
            current_bitfield = bitfield[0]

        elif line[0] == '=':
            enum = parse_enum(line[1:], original)

            if current_bitfield is None:
                raise Exception('Enum without bitfield at line %d: %s' % (line_num, original))

            register = current_peripheral[3][current_register]
            bitfields = register[4]
            enums = bitfields[current_bitfield][5]

            if enum[0] in enums:
                raise Exception('Duplicate enum definition at line %d for %s at %s: %s' % (line_num, current_register, current_bitfield, original))

            enums[enum[0]] = enum

        else:
            if '=' not in line:
                raise Exception('Invalid register definition at line %d: %s' % (line_num, original))

            if not current_peripheral:
                raise Exception('Register definition without peripheral at line %d: %s' % (line_num, original))

            register = parse_register(line, original)
            if register[0] in current_peripheral[3]:
                raise Exception('Duplicate register definition at line %d: %s' % (line_num, register[0]))
            current_peripheral[3][register[0]] = (*register, {})
            current_register = register[0]
            current_bitfield = None

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--empty', help='Emit peripherals with no registers', action='store_true')
    parser.add_argument('-o', help='output file', type=str)
    parser.add_argument('-i', help='input files', type=str, nargs='+')
    args = parser.parse_args()

    if not args.o:
        print('Output file not specified!')
        sys.exit(1)
    if not args.i:
        print('No input files specified!')
        sys.exit(1)

    peripherals = {}

    try:
        for filename in args.i:
            load_definition(peripherals, filename)
        filename = 'consistency check'
        check_for_overlaps(peripherals)
    except Exception as e:
        print('Error in %s: %s' % (filename, e.args))
    else:
        generate_svd(peripherals, args.o, args.empty)

