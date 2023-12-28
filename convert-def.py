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
    'RW': 'read-write',
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

class Peripheral:
    def __init__(self):
        self.name = None
        self.group = None
        self.address = None
        self.size = None
        self.registers = {}
        self.derived = None

class AddressBlock:
    def __init__(self):
        self.address = None
        self.size = None
        self.derived = None

class Register:
    def __init__(self):
        self.name = None
        self.offset = None
        self.modifiers = None
        self.description = None
        self.bitfields = {}
        self.alternate = None

class Bitfield:
    def __init__(self):
        self.name = None
        self.start = None
        self.width = None
        self.modifier = None
        self.description = None
        self.enums = {}

class Enum:
    def __init__(self):
        self.name = None
        self.value = None
        self.description = None

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

    peripheral = Peripheral()
    peripheral.name = name
    peripheral.group = group

    return peripheral

def parse_address_block(line, original):
    line = line.strip()
    if line[0] != '=':
        raise Exception('Invalid address block: %s' % original)
    tokens = line[1:].split(',')
    if len(tokens) < 2 or len(tokens) > 3:
        raise Exception('Invalid address block: %s' % original)

    block = AddressBlock()

    if len(tokens) != 2:
        block.derived = tokens[2].strip()
        if not block.derived.isidentifier():
            raise Exception('Invalid address block: %s' % original)

    try:
        block.address = int(tokens[0], 0)
        block.size = int(tokens[1], 0)
    except:
        raise Exception('Invalid address block: %s' % original)

    return block

def parse_register(line, original):
    if not '=' in line:
        raise Exception('Invalid register definition: %s' % original)

    description = None
    i = line.find(';')
    if i > 0:
        description = line[i + 1:].strip()
        if not len(description):
            description = None
        line = line[:i].strip()

    register = Register()
    register.description = description

    tokens = line.split('=')
    if len(tokens) != 2:
        raise Exception('Invalid register definition: %s' % original)

    if ',' in tokens[1]:
        sub = tokens[1].split(',')
        sub = [s.strip() for s in sub]
        tokens[1] = sub[0]
        modifiers = sub[1:]
    else:
        modifiers = []

    register.name = tokens[0].strip()

    if not register.name.isidentifier():
        raise Exception('Invalid register definition: %s' % original)

    modifiers = [modifier.strip().upper() for modifier in modifiers]
    access_flag = False
    modify_flag = False
    size_flag = False
    alternate_flag = False
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
        elif modifier[0] == '(' and modifier[-1] == ')':
            if alternate_flag or not modifier[1:-1].isidentifier:
                raise Exception('Unexpected bitfield modifier (%s): %s' % (modifier, original))
            alternate_flag = True
        else:
            raise Exception('Invalid bitfield modifier (%s): %s' % (modifier, original))

    register.modifiers = modifiers

    try:
        register.offset = int(tokens[1], 0)
    except:
        raise Exception('Invalid register definition: %s' % original)

    return register

def parse_bitfield(line, original):
    description = None
    i = line.find(';')
    if i > 0:
        description = line[i + 1:].strip()
        if not len(description):
            description = None
        line = line[:i].strip()

    bitfield = Bitfield()
    bitfield.description = description

    tokens = line.split(',')
    if len(tokens) != 3 and len(tokens) != 4:
        raise Exception('Invalid bitfield definition: %s' % original)

    try:
        bitfield.start = int(tokens[0].strip(), 0)
        bitfield.width = int(tokens[1].strip(), 0)
    except:
        raise Exception('Invalid bitfield definition: %s' % original)

    bitfield.name = tokens[2].strip()
    if not bitfield.name.isidentifier():
        raise Exception('Invalid bitfield definition: %s' % original)

    if len(tokens) == 3:
        bitfield.modifier = None
    else:
        bitfield.modifier = tokens[3].strip().upper()
        if not bitfield.modifier in [*ACCESS_TAGS, *MODIFIED_TAGS]:
            raise Exception('Invalid bitfield access mode: %s' % original)


    return bitfield

def parse_enum(line, original):
    description = None
    i = line.find(';')
    if i > 0:
        description = line[i + 1:].strip()
        if not len(description):
            description = None
        line = line[:i]

    enum = Enum()
    enum.description = description

    tokens = line.split(',')
    if len(tokens) != 2:
        raise Exception('Invalid bitfield enum: %s' % original)

    try:
        enum.value = int(tokens[0], 0)
    except:
        raise Exception('Invalid bitfield enum: %s' % original)

    enum.name = tokens[1].strip()

    return enum

def strip_comment(line):
    i = line.find('#')
    if i >= 0:
        line = line[:i].rstrip()
    return line

def check_for_overlaps(peripherals):
    addresses = []

    for _, peripheral in sorted(peripherals.items()):
        if peripheral.address is None or peripheral.size is None:
            raise Exception('Peripheral %s does not have an address block!' % peripheral.name)

        for addr in addresses:
            tail = peripheral.address + peripheral.size - 1
            if tail < addr[0]:
                continue
            if peripheral.address < addr[0] + addr[1]:
                raise Exception('Peripheral %s overlaps with another!' % peripheral.name)

        addresses.append((peripheral.address, peripheral.size))

        reg_names = []
        reg_offsets = []

        for _, register in peripheral.registers.items():
            if register.name in reg_names or register.offset in reg_offsets:
                if register.name in reg_names and not 'ALT' in modifiers:
                    raise Exception('Register %s.%s (0x%04X) conflicts with another!' % (peripheral.name, register.name, register.offset))

            reg_names.append(register.name)
            reg_offsets.append(register.offset)

            bitset = set()
            for _, bitfield in register.bitfields.items():
                for i in range(bitfield.width):
                    bit = bitfield.start + i
                    if bit in bitset:
                        raise Exception('Bitfield %s for %s.%s (0x%04X) overlaps with another!' % (bitfield.name, peripheral.name, register.name, register.offset))
                    bitset.add(bit)

                enumset = set()
                for _, enum in bitfield.enums.items():
                    if enum.value in enumset:
                        raise Exception('Enum %d for bitfield %s at %s.%s (0x%04X)!' % (enum.value, bitfield.name, peripheral.name, register.name, register.offset))
                    enumset.add(enum)

def resolve_derived(peripherals):
    for _, peripheral in peripherals.items():
        if not peripheral.derived:
            continue
        if not peripheral.derived in peripherals:
            raise Exception('Peripheral %s requires %s but does not exist!' % (peripheral.name, peripheral.derived))

def generate_peripheral(all_peripherals, root, p_name, gen_empty):
    periph = all_peripherals[p_name]

    peripheral = xml.Element('peripheral')
    if periph.derived:
        peripheral.attrib['derivedFrom'] = periph.derived

    name = xml.Element('name')
    name.text = periph.name
    peripheral.append(name)

    if periph.group:
        group = xml.Element('groupName')
        group.text = periph.group
        peripheral.append(group)

    baseAddress = xml.Element('baseAddress')
    baseAddress.text = '0x%09X' % periph.address
    peripheral.append(baseAddress)

    addressBlock = xml.Element('addressBlock')

    offset = xml.Element('offset')
    offset.text = '0x0'
    addressBlock.append(offset)

    size = xml.Element('size')
    size.text = '0x%X' % periph.size
    addressBlock.append(size)

    usage = xml.Element('usage')
    usage.text = 'registers'
    addressBlock.append(usage)

    peripheral.append(addressBlock)

    registers = xml.Element('registers')

    for _, reg in periph.registers.items():
        register = xml.Element('register')

        name = xml.Element('name')
        name.text = reg.name
        register.append(name)

        if reg.description is not None:
            description = xml.Element('description')
            description.text = reg.description
            register.append(description)

        for modifier in reg.modifiers:
            if modifier[0] == '(':
                alternate = xml.Element('alternateRegister')
                alternate.text = modifier[1:-1]
                register.append(alternate)

        addressOffset = xml.Element('addressOffset')
        addressOffset.text = '0x%04X' % reg.offset
        register.append(addressOffset)

        for modifier in reg.modifiers:
            if modifier in ACCESS_TAGS:
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

        if len(reg.bitfields):
            fields = xml.Element('fields')
            for _, bitf in reg.bitfields.items():
                field = xml.Element('field')

                name = xml.Element('name')
                name.text = bitf.name
                field.append(name)

                if bitf.description is not None:
                    description = xml.Element('description')
                    description.text = bitf.description
                    field.append(description)

                bitOffset = xml.Element('bitOffset')
                bitOffset.text = str(bitf.start)
                field.append(bitOffset)

                bitWidth = xml.Element('bitWidth')
                bitWidth.text = str(bitf.width)
                field.append(bitWidth)

                if bitf.modifier in ACCESS_TAGS:
                    access = xml.Element('access')
                    access.text = ACCESS_TAGS[bitf.modifier]
                    field.append(access)

                if bitf.modifier in MODIFIED_TAGS:
                    modified = xml.Element('modifiedWriteValues')
                    modified.text = MODIFIED_TAGS[bitf.modifier]
                    field.append(modified)

                if len(bitf.enums):
                    enumeratedValues = xml.Element('enumeratedValues')
                    for _, e in bitf.enums.items():
                        enumeratedValue = xml.Element('enumeratedValue')

                        name = xml.Element('name')
                        name.text = e.name if e.name != '_' else ''
                        enumeratedValue.append(name)

                        if e.description is not None:
                            description = xml.Element('description')
                            description.text = e.description
                            enumeratedValue.append(description)

                        value = xml.Element('value')
                        value.text = str(e.value)
                        enumeratedValue.append(value)

                        enumeratedValues.append(enumeratedValue)

                    field.append(enumeratedValues)

                fields.append(field)
            register.append(fields)
        registers.append(register)
    if len(periph.registers) > 0:
        peripheral.append(registers)
    if len(periph.registers) > 0 or gen_empty or periph.derived:
        root.append(peripheral)
    elif not periph.derived:
        print('Peripheral %s has no registers!' % periph.name)

def generate_svd(all_peripherals, filename, gen_empty):
    device = xml.Element('device')
    device.attrib['schemaVersion'] = "1.3"
    device.attrib['xmlns:xs'] = "http://www.w3.org/2001/XMLSchema-instance"
    device.attrib['xs:noNamespaceSchemaLocation'] = "CMSIS-SVD.xsd"
    for tag in DEVICE_TAGS:
        element = xml.Element(tag[0])
        element.text = tag[1]
        device.append(element)

    derived = []
    processed = []

    peripherals = xml.Element('peripherals')
    for _, periph in sorted(all_peripherals.items()):
        if periph.derived:
            if not periph.derived in processed:
                derived.append(periph.name)
                continue
            if periph.name in derived:
                derived.remove(periph.name)

        generate_peripheral(all_peripherals, peripherals, periph.name, gen_empty)
        processed.append(periph.name)
        for d in derived:
            if all_peripherals[d].derived in processed:
                generate_peripheral(all_peripherals, peripherals, d, gen_empty)

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
            peripheral = parse_peripheral_name(line[1:], original)
            if peripheral.name in peripherals:
                raise Exception('Duplicate peripheral name at line %d: %s' % (line_num, peripheral.name))
            current_peripheral = peripheral
            peripherals[peripheral.name] = peripheral
            current_register = None
            current_bitfield = None

        elif line[0] == '@':
            address_block = parse_address_block(line[1:], original)
            if not current_peripheral:
                raise Exception('Peripheral address block without name at line %d: %s' % (line_num, original))

            if current_peripheral.address is not None or current_peripheral.size is not None:
                raise Exception('Duplicate peripheral address block at line %d: %s' % (line_num, original))

            current_peripheral.address = address_block.address
            current_peripheral.size = address_block.size
            current_peripheral.derived = address_block.derived

        elif line[0] == '>':
            bitfield = parse_bitfield(line[1:], original)

            if not current_register:
                raise Exception('Bitfield definition without register at line %d: %s' % (line_num, original))

            if bitfield.start in current_register.bitfields:
                raise Exception('Duplicate bitfield definition at line %d for %s: %s' % (line_num, current_register.name, original))

            current_register.bitfields[bitfield.start] = bitfield
            current_bitfield = bitfield

        elif line[0] == '=':
            enum = parse_enum(line[1:], original)

            if current_bitfield is None:
                raise Exception('Enum without bitfield at line %d: %s' % (line_num, original))

            enums = current_bitfield.enums

            if enum.value in enums:
                raise Exception('Duplicate enum definition at line %d for %s at %s: %s' % (line_num, current_register.name, current_bitfield, original))

            enums[enum.value] = enum

        else:
            if '=' not in line:
                raise Exception('Invalid register definition at line %d: %s' % (line_num, original))

            if not current_peripheral:
                raise Exception('Register definition without peripheral at line %d: %s' % (line_num, original))

            register = parse_register(line, original)
            if register.name in current_peripheral.registers:
                raise Exception('Duplicate register definition at line %d: %s' % (line_num, register.name))

            current_peripheral.registers[register.name] = register
            current_register = register
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
        resolve_derived(peripherals)
    except Exception as e:
        print('Error in %s: %s' % (filename, e.args))
    else:
        generate_svd(peripherals, args.o, args.empty)

