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
import os
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

READ_TAGS = {
    'R2C': 'clear',
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
        self.refcount = 0
        self.struct = None

class AddressBlock:
    def __init__(self):
        self.address = None
        self.size = None
        self.derived = None

class Register:
    def __init__(self):
        self.name = None
        self.offset = None
        self.size = None
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

def replace_index(string, index):
    return string.replace('$', '%d' % index)

def remove_index(string):
    return string.replace('$', '')

def parse_peripheral(line, original):
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

    if not name.isidentifier(): # or (group and not group.isidentifier()):
        raise Exception('Invalid peripheral name: %s' % original)

    peripheral = Peripheral()
    peripheral.name = name
    peripheral.group = group

    return peripheral

def parse_address_block(line, original):
    line = line.strip()
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

def parse_struct_name(line, original):
    line = line.strip()
    if line[0] != '=':
        raise Exception('Invalid structure name: %s' % original)

    name = line[1:].lstrip()

    if not name.isidentifier():
        raise Exception('Invalid structure name: %s' % original)

    return name

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
    register.size = 32

    if not remove_index(register.name).isidentifier():
        raise Exception('Invalid register definition: %s' % original)

    modifiers = [modifier.strip().upper() for modifier in modifiers]
    access_flag = False
    modify_flag = False
    size_flag = False
    alternate_flag = False
    read_flag = False
    array_flag = False
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
            register.size = int(modifier[1:], 0)
            size_flag = True
        elif modifier[0] == '(' and modifier[-1] == ')':
            if alternate_flag or not modifier[1:-1].isidentifier:
                raise Exception('Unexpected bitfield modifier (%s): %s' % (modifier, original))
            alternate_flag = True
        elif modifier in READ_TAGS:
            if read_flag:
                raise Exception('Unexpected bitfield modifier (%s): %s' % (modifier, original))
            read_flag = True
        elif modifier.startswith('@'):
            if array_flag:
                raise Exception('Unexpected bitfield modifier (%s): %s' % (modifier, original))
            if not '$' in register.name:
                raise Exception('Array modifier without $ in register name: %s' % original)

            array_flag = True
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
    if not remove_index(bitfield.name).isidentifier():
        raise Exception('Invalid bitfield definition: %s' % original)

    if len(tokens) == 3:
        bitfield.modifier = None
    else:
        bitfield.modifier = tokens[3].strip().upper()
        if not bitfield.modifier in [*ACCESS_TAGS, *MODIFIED_TAGS, *READ_TAGS]:
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
    if len(tokens) != 2 or ' ' in tokens[1].strip() or tokens[1] == '':
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

def check_for_inconsistencies(peripherals):
    blocks = []

    for peripheral in peripherals.values():
        if peripheral.address is None or peripheral.size is None:
            raise Exception('Peripheral %s does not have an address block!' % peripheral.name)

        if peripheral.derived:
            peripherals[peripheral.derived].refcount += 1
            if peripherals[peripheral.derived].struct is None:
                raise Exception('Peripheral %s does not have a structure name!' % peripheral.derived)

        for block in blocks:
            tail = peripheral.address + peripheral.size - 1
            if tail < block.address:
                continue
            if peripheral.address < block.address + block.size:
                raise Exception('Peripheral %s overlaps with another!' % peripheral.name)

        block = AddressBlock()
        block.address = peripheral.address
        block.size = peripheral.size
        blocks.append(block)

        reg_names = []
        reg_offsets = []

        for register in peripheral.registers.values():
            if register.name in reg_names or register.offset in reg_offsets:
                if register.name in reg_names and not 'ALT' in modifiers:
                    raise Exception('Register %s.%s (0x%04X) conflicts with another!' % (peripheral.name, register.name, register.offset))

            reg_names.append(register.name)
            reg_offsets.append(register.offset)

            bitset = set()
            bf_names = []
            for bitfield in register.bitfields.values():
                if bitfield.name in bf_names:
                        raise Exception('Bitfield %s for %s.%s (0x%04X) overlaps with another!' % (bitfield.name, peripheral.name, register.name, register.offset))
                bf_names.append(bitfield.name)

                for i in range(bitfield.width):
                    bit = bitfield.start + i
                    if bit in bitset:
                        raise Exception('Bitfield %s for %s.%s (0x%04X) overlaps with another!' % (bitfield.name, peripheral.name, register.name, register.offset))
                    bitset.add(bit)

                enumset = set()
                enum_names = []
                for enum in bitfield.enums.values():
                    if enum.value in enumset:
                        raise Exception('Enum %d for bitfield %s at %s.%s (0x%04X)!' % (enum.value, bitfield.name, peripheral.name, register.name, register.offset))
                    if enum.name in enum_names:
                        raise Exception('Enum %d for bitfield %s at %s.%s (0x%04X)!' % (enum.value, bitfield.name, peripheral.name, register.name, register.offset))
                    enumset.add(enum)
                    enum_names.append(enum.name)

def resolve_derived(peripherals, duplicate=False):
    for peripheral in peripherals.values():
        if not peripheral.derived:
            continue
        if not peripheral.derived in peripherals:
            raise Exception('Peripheral %s requires %s but does not exist!' % (peripheral.name, peripheral.derived))

        if duplicate:
            peripheral.registers = peripherals[peripheral.derived].registers

def generate_enum(parent, enum, index):
    xml_enumeratedValue = xml.Element('enumeratedValue')

    xml_name = xml.Element('name')
    xml_name.text = replace_index(enum.name, index)
    xml_enumeratedValue.append(xml_name)

    if enum.description is not None:
        xml_description = xml.Element('description')
        xml_description.text = replace_index(enum.description, index)
        xml_enumeratedValue.append(xml_description)

    xml_value = xml.Element('value')
    xml_value.text = str(enum.value)
    xml_enumeratedValue.append(xml_value)

    parent.append(xml_enumeratedValue)

def generate_enums(parent, enums, index):
    xml_enumeratedValues = xml.Element('enumeratedValues')
    for enum in enums:
        generate_enum(xml_enumeratedValues, enum, index)

    parent.append(xml_enumeratedValues)

def generate_bitfield(parent, bitfield, index):
    xml_field = xml.Element('field')

    xml_name = xml.Element('name')
    xml_name.text = replace_index(bitfield.name, index)
    xml_field.append(xml_name)

    if bitfield.description is not None:
        xml_description = xml.Element('description')
        xml_description.text = replace_index(bitfield.description, index)
        xml_field.append(xml_description)

    xml_bitOffset = xml.Element('bitOffset')
    xml_bitOffset.text = str(bitfield.start)
    xml_field.append(xml_bitOffset)

    xml_bitWidth = xml.Element('bitWidth')
    xml_bitWidth.text = str(bitfield.width)
    xml_field.append(xml_bitWidth)

    if bitfield.modifier in ACCESS_TAGS:
        xml_access = xml.Element('access')
        xml_access.text = ACCESS_TAGS[bitfield.modifier]
        xml_field.append(xml_access)

    if bitfield.modifier in MODIFIED_TAGS:
        xml_modified = xml.Element('modifiedWriteValues')
        xml_modified.text = MODIFIED_TAGS[bitfield.modifier]
        xml_field.append(xml_modified)

    if bitfield.modifier in READ_TAGS:
        xml_read = xml.Element('readAction')
        xml_read.text = READ_TAGS[bitfield.modifier]
        xml_field.append(xml_read)

    if len(bitfield.enums):
        generate_enums(xml_field, bitfield.enums.values(), index)

    parent.append(xml_field)

def generate_bitfields(parent, bitfields, index):
    xml_fields = xml.Element('fields')
    for bitfield in bitfields:
        generate_bitfield(xml_fields, bitfield, index)

    parent.append(xml_fields)

def generate_register(parent, register, index):
    xml_register = xml.Element('register')

    xml_name = xml.Element('name')
    xml_name.text = replace_index(register.name, index)
    xml_register.append(xml_name)

    if register.description is not None:
        xml_description = xml.Element('description')
        xml_description.text = replace_index(register.description, index)
        xml_register.append(xml_description)

    for modifier in register.modifiers:
        if modifier[0] == '(':
            xml_alternate = xml.Element('alternateRegister')
            xml_alternate.text = modifier[1:-1]
            xml_register.append(xml_alternate)
            break

    xml_addressOffset = xml.Element('addressOffset')
    xml_addressOffset.text = '0x%04X' % (register.offset + (index * (register.size // 8)))
    xml_register.append(xml_addressOffset)

    if register.size != 32:
        xml_size = xml.Element('size')
        xml_size.text = str(register.size)
        xml_register.append(xml_size)

    for modifier in register.modifiers:
        if modifier in ACCESS_TAGS:
            xml_access = xml.Element('access')
            xml_access.text = ACCESS_TAGS[modifier]
            xml_register.append(xml_access)
        elif modifier in MODIFIED_TAGS:
            xml_modified = xml.Element('modifiedWriteValues')
            xml_modified.text = MODIFIED_TAGS[modifier]
            xml_register.append(xml_modified)
        elif modifier in READ_TAGS:
            xml_read = xml.Element('readAction')
            xml_read.text = READ_TAGS[modifier]
            xml_register.append(xml_read)

    if len(register.bitfields):
        generate_bitfields(xml_register, register.bitfields.values(), index)

    parent.append(xml_register)

def generate_peripheral(peripherals, root, p_name, gen_empty):
    peripheral = peripherals[p_name]

    xml_peripheral = xml.Element('peripheral')
    if peripheral.derived:
        if not len(peripherals[peripheral.derived].registers):
            return
        xml_peripheral.attrib['derivedFrom'] = peripheral.derived

    xml_name = xml.Element('name')
    xml_name.text = peripheral.name
    xml_peripheral.append(xml_name)

    #if peripheral.group:
        #xml_group = xml.Element('groupName')
        #xml_group.text = peripheral.group
        #xml_peripheral.append(xml_group)

    xml_baseAddress = xml.Element('baseAddress')
    xml_baseAddress.text = '0x%09X' % peripheral.address
    xml_peripheral.append(xml_baseAddress)

    xml_addressBlock = xml.Element('addressBlock')

    xml_offset = xml.Element('offset')
    xml_offset.text = '0x0'
    xml_addressBlock.append(xml_offset)

    xml_size = xml.Element('size')
    xml_size.text = '0x%X' % peripheral.size
    xml_addressBlock.append(xml_size)

    xml_usage = xml.Element('usage')
    xml_usage.text = 'registers'
    xml_addressBlock.append(xml_usage)

    xml_peripheral.append(xml_addressBlock)

    xml_registers = xml.Element('registers')

    for register in peripheral.registers.values():
        # Expand arrays manually because ADS doesn't display items in proper order
        count = 1
        for modifier in register.modifiers:
            if modifier.startswith('@'):
                count = int(modifier[1:], 0)
                break

        if count > 1:
            # Skip SRAM blocks due to too many entries
            if register.name == 'SRAM$':
                continue

        for i in range(count):
            generate_register(xml_registers, register, i)

    if len(peripheral.registers) > 0:
        xml_peripheral.append(xml_registers)
    if len(peripheral.registers) > 0 or gen_empty or peripheral.derived:
        root.append(xml_peripheral)
    elif not peripheral.derived:
        print('Peripheral %s has no registers!' % peripheral.name)

def generate_svd(peripherals, filename, gen_empty):
    xml_device = xml.Element('device')
    xml_device.attrib['schemaVersion'] = "1.3"
    xml_device.attrib['xmlns:xs'] = "http://www.w3.org/2001/XMLSchema-instance"
    xml_device.attrib['xs:noNamespaceSchemaLocation'] = "CMSIS-SVD.xsd"
    for tag in DEVICE_TAGS:
        xml_element = xml.Element(tag[0])
        xml_element.text = tag[1]
        xml_device.append(xml_element)

    derived = []
    processed = []

    p_sorted = sorted([name for name in peripherals.keys()])

    xml_peripherals = xml.Element('peripherals')
    for p_name in p_sorted:
        peripheral = peripherals[p_name]
        if peripheral.derived:
            if not peripheral.derived in processed:
                derived.append(peripheral.derived)
                continue
            if peripheral.name in derived:
                derived.remove(peripheral.name)

        generate_peripheral(peripherals, xml_peripherals, peripheral.name, gen_empty)
        processed.append(peripheral.name)
        for name in derived:
            if peripherals[name].derived in processed:
                generate_peripheral(peripherals, xml_peripherals, name, gen_empty)

    xml_device.append(xml_peripherals)
    xml_tree = xml.ElementTree(xml_device)
    xml.indent(xml_tree, space = '\t', level = 0)

    f = open(filename, 'wb')
    f.write(b'<?xml version="1.0" encoding="utf-8"?>\n')
    f.write(b'\n')
    xml_tree.write(f)

def calculate_max_indent(peripheral):
    max_length = 0

    # #define peripheral
    p_length = 8 + len(peripheral.name)
    # #define peripheral_BASE
    max_length = max(max_length, 5 + p_length)

    if len(peripheral.registers) > 0:
        # #define peripheral_ENUM_BITS_VALUE_WM(r, b, v)
        max_length = max(max_length, 28 + p_length)

    for register in peripheral.registers.values():
        # #define peripheral_register
        r_length = 1 + p_length + len(remove_index(register.name))
        # #define peripheral_register_ADDR
        max_length = max(max_length, 5 + r_length)

        for bitfield in register.bitfields.values():
            # #define peripheral_register_bitfield
            b_length = 1 + r_length + len(remove_index(bitfield.name))
            # #define peripheral_register_GET_bitfield(v)
            max_length = max(max_length, 7 + b_length)

            for enum in bitfield.enums.values():
                # #define peripheral_register_bitfield_enum
                e_length = 1 + b_length + len(remove_index(enum.name))
                # #define peripheral_register_bitfield_VALUE_enum
                max_length = max(max_length, 6 + e_length)

    # add in space for separation
    return max_length + 1

def insert_indent(a, b, indent):
    return a + (' ' * (indent - len(a))) + b

def get_include_filename(path, peripheral):
    if peripheral.group:
        group = peripheral.group + os.sep
    else:
        group = ''

    return path + os.sep + group + peripheral.name.lower() + '.h'

def get_derived_filename(path, peripheral, struct):
    return path + os.sep + 'internal' + os.sep + '%s.h' % struct.lower()

def generate_boilerplate(f, peripheral):
    f.write('// Automatically generated by https://github.com/DualTachyon/rk3588-svd\n')
    f.write('\n')
    f.write('/* Copyright 2024 Dual Tachyon\n')
    f.write(' * https://github.com/DualTachyon\n')
    f.write(' *\n')
    f.write(' * Licensed under the Apache License, Version 2.0 (the "License");\n')
    f.write(' * you may not use this file except in compliance with the License.\n')
    f.write(' * You may obtain a copy of the License at\n')
    f.write(' *\n')
    f.write(' *     http://www.apache.org/licenses/LICENSE-2.0\n')
    f.write(' *\n')
    f.write(' *     Unless required by applicable law or agreed to in writing, software\n')
    f.write(' *     distributed under the License is distributed on an "AS IS" BASIS,\n')
    f.write(' *     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.\n')
    f.write(' *     See the License for the specific language governing permissions and\n')
    f.write(' *     limitations under the License.\n')
    f.write(' */\n')
    f.write('\n')
    f.write('#ifndef RK3588_%s_H\n' % peripheral)
    f.write('#define RK3588_%s_H\n' % peripheral)
    f.write('\n')
    f.write('#include <stdint.h>\n')
    f.write('\n')

def generate_base(f, struct, peripheral, indent):
    suffix = 'LL' if peripheral.address >= 0x100000000 else ''
    f.write(insert_indent('#define %s_BASE' % peripheral.name, '0x%09XU%s\n' % (peripheral.address, suffix), indent))
    suffix = 'LL' if peripheral.size >= 0x100000000 else ''
    f.write(insert_indent('#define %s_SIZE' % peripheral.name, '0x%09XU%s\n' % (peripheral.size, suffix), indent))
    if len(peripheral.registers) > 0:
        f.write(insert_indent('#define %s' % peripheral.name, '((%s_t *)%s_BASE)\n' % (struct, peripheral.name), indent))
    f.write('\n')

def generate_access_macros(f, struct, name, indent):
    get_macro = '%s_##r##_GET_##b' % struct
    set_macro = '%s_##r##_SET_##b' % struct
    mask_macro = '%s_##r##_##b##_MASK' % struct

    f.write("// Reads register 'r' and checks if bitfield 'b' is equal to 'e'.\n")
    f.write(insert_indent('#define %s_ENUM_EQUALS(r, b, e)' % name,           '(%s(%s->r) == %s_##r##_##b##_VALUE_##e)\n' % (get_macro, name, struct), indent))

    f.write("// Returns the encoding of enum 'e' for bitfield 'b' of register 'r'.\n")
    f.write(insert_indent('#define %s_ENUM_BITS(r, b, e)' % name,             '(%s(%s_##r##_##b##_VALUE_##e))\n' % (set_macro, struct), indent))

    f.write("// Same as %s_ENUM_BITS but applies the corresponding RockChip write mask.\n" % name)
    f.write(insert_indent('#define %s_ENUM_BITS_WM(r, b, e)' % name,          '(%s(%s_##r##_##b##_VALUE_##e) | (%s << 16))\n' % (set_macro, struct, mask_macro), indent))

    f.write("// Returns the encoding of value 'v' for bitfield 'b' of register 'r'.\n")
    f.write(insert_indent('#define %s_ENUM_BITS_VALUE(r, b, v)' % name,       '(%s(v))\n' % set_macro, indent))

    f.write("// Same as %s_ENUM_BITS_VALUE but applies the corresponding RockChip write mask.\n" % name)
    f.write(insert_indent('#define %s_ENUM_BITS_VALUE_WM(r, b, v)' % name,    '(%s(v) | (%s_##r##_##b##_MASK << 16))\n' % (set_macro, struct), indent))

    f.write("// Returns the value of bitfield 'b' of register 'r' from value 'v'.\n")
    f.write(insert_indent('#define %s_ENUM_GET(v, r, b)' % name,              '(%s(v))\n' % get_macro, indent))

    f.write("// Returns the integer value of the enum 'e' for bitfield 'b' of register 'r'.\n")
    f.write(insert_indent('#define %s_ENUM_VALUE(r, b, e)' % name,            '(%s_##r##_##b##_VALUE_##e)\n'% struct, indent))

    f.write("// Given an input 'i', returns it with bitfield 'b' of register 'r' replaced with enum 'e'.\n")
    f.write(insert_indent('#define %s_ENUM_REPLACE(i, r, b, e)' % name,       '(((i) & ~%s) | %s(%s_##r##_##b##_VALUE_##e))\n'% (mask_macro, set_macro, struct), indent))

    f.write("// Given an input 'i', returns it with bitfield 'b' of register 'r' replaced with value 'v'.\n")
    f.write(insert_indent('#define %s_ENUM_REPLACE_VALUE(i, r, b, v)' % name, '(((i) & ~%s) | %s(v))\n'% (mask_macro, set_macro), indent))

    f.write('\n')

def generate_register_macros(f, peripheral, p_prefix, indent):
    for register in peripheral.registers.values():
        prefix = '%s_%s' % (p_prefix, remove_index(register.name))

        for bitfield in register.bitfields.values():
            if not bitfield.start and bitfield.width == register.size and not len(bitfield.enums):
                continue

            bf_name = remove_index(bitfield.name)
            shift = '%s_%s_SHIFT' % (prefix, bf_name)
            width = '%s_%s_WIDTH' % (prefix, bf_name)
            mask = '%s_%s_MASK' % (prefix, bf_name)
            f.write(insert_indent('#define %s' % shift, '%dU\n' % bitfield.start, indent))
            f.write(insert_indent('#define %s' % width, '%dU\n' % bitfield.width, indent))
            f.write(insert_indent('#define %s' % mask, '(((1U << %s) - 1U) << %s)\n' % (width, shift), indent))
            is_ro = (register.modifiers and 'RO' in register.modifiers) or (bitfield.modifier and 'RO' in bitfield.modifier)
            is_wo = (register.modifiers and 'WO' in register.modifiers) or (bitfield.modifier and 'WO' in bitfield.modifier)
            if bitfield.width == register.size:
                if not is_wo:
                    f.write(insert_indent('#define %s_GET_%s(v)' % (prefix, bf_name), '((uint%d_t)(v))\n' % bitfield.width, indent))
                if not is_ro:
                    f.write(insert_indent('#define %s_SET_%s(v)' % (prefix, bf_name), '((uint%d_t)(v))\n' % bitfield.width, indent))
            else:
                if not is_wo:
                    f.write(insert_indent('#define %s_GET_%s(v)' % (prefix, bf_name), '(((v) & %s) >> %s)\n' % (mask, shift), indent))
                if not is_ro:
                    f.write(insert_indent('#define %s_SET_%s(v)' % (prefix, bf_name), '(((uint32_t)(v) << %s) & %s)\n' % (shift, mask), indent))

            for enum in bitfield.enums.values():
                f.write(insert_indent('#define %s_%s_VALUE_%s' % (prefix, bf_name, remove_index(enum.name)), '0x%XU\n' % enum.value, indent))

            f.write('\n')

def generate_structure(f, peripheral):
    if peripheral.refcount > 0:
        struct = peripheral.struct
    else:
        struct = peripheral.name
    registers = peripheral.registers.values()
    offsets = {r.offset:[s for s in registers if s.offset == r.offset] for r in registers}
    base = 0

    if not len(offsets.items()):
        return

    f.write('#pragma pack(push)\n')
    f.write('#pragma pack(1)\n')
    f.write('\n')

    f.write('typedef volatile struct {\n')
    for offset, registers in sorted(offsets.items()):
        if base < offset:
            if offset - base == 1:
                f.write('\tuint8_t Reserved_%04X;\n' % base)
            else:
                f.write('\tuint8_t Reserved_%04X[%d];\n' % (base, offset - base))
        elif base > offset:
            raise Exception('WTF')
        if len(registers) > 1:
            f.write('\tunion {\n')
            for register in registers:
                f.write('\t\tuint%d_t %s;\n' % (register.size, remove_index(register.name)))
            f.write('\t};\n')
        else:
            register = registers[0]
            reg_name = remove_index(register.name)
            count = 1
            for modifier in register.modifiers:
                if modifier.startswith('@'):
                    count = int(modifier[1:], 0)
                    break

            readonly = 'const ' if 'RO' in register.modifiers else ''

            if count > 1:
                if register.size == 8:
                    f.write('\t%suint%d_t %s[%d];\n' % (readonly, register.size, reg_name, count))
                else:
                    f.write('\t%sunion {\n' % readonly)
                    f.write('\t\tuint8_t %s_BASE[%d];\n' % (reg_name, count * (register.size // 8)))
                    f.write('\t\tuint%d_t %s[%d];\n' % (register.size, reg_name, count))
                    f.write('\t};\n')
                offset += (register.size // 8) * (count - 1)
            else:
                f.write('\t%suint%d_t %s;\n' % (readonly, register.size, reg_name))
        base = offset + (register.size // 8)
    f.write('} %s_t;\n' % struct)
    f.write('\n')
    f.write('#pragma pack(pop)\n')
    f.write('\n')

def generate_headers(peripherals, path):
    if path:
        path += os.sep + 'rk3588'
        try:
            os.mkdir(path, mode = 0o755)
            os.mkdir(path + os.sep + 'internal', mode = 0o755)
        except FileExistsError:
            pass
        except Exception as e:
            print('Cannot create output folder!: %s' % e)
            return
    else:
        path = 'rk3588'

    for peripheral in peripherals.values():
        fullpath = get_include_filename(path, peripheral)

        i = fullpath.rfind('/')
        if i > 0:
            try:
                os.makedirs(fullpath[:i], mode=0o755, exist_ok=True)
            except Exception as e:
                print('Cannot create output folder!: %s' % e)
                continue

        f = open(fullpath, 'w')

        generate_boilerplate(f, peripheral.name)

        indent = calculate_max_indent(peripheral)
        short_indent = 37 + len(peripheral.name)

        if peripheral.group:
            prefix = peripheral.group + '/'
        else:
            prefix = ''

        if peripheral.refcount > 0:
            struct = peripheral.struct
        elif peripheral.derived:
            struct = peripherals[peripheral.derived].struct
        else:
            struct = peripheral.name

        if peripheral.refcount or peripheral.derived:
            f.write('#include <rk3588/internal/%s.h>\n' % struct.lower())
            f.write('\n')
            generate_base(f, struct, peripheral, short_indent)
        else:
            generate_base(f, struct, peripheral, indent)

        if len(peripheral.registers) > 0 and not peripheral.refcount and not peripheral.derived:
            for register in peripheral.registers.values():
                if len(register.bitfields) > 0:
                    generate_access_macros(f, struct, peripheral.name, indent)
                    break
            generate_register_macros(f, peripheral, peripheral.name, indent)
            generate_structure(f, peripheral)
        elif peripheral.derived:
            if len(peripherals[peripheral.derived].registers) > 0:
                generate_access_macros(f, struct, peripheral.name, short_indent)
        elif peripheral.struct:
            if len(peripheral.registers) > 0:
                generate_access_macros(f, struct, peripheral.name, short_indent)

            f.write('#endif\n\n')
            f.close()

            fullpath = get_derived_filename(path, peripheral, struct)
            f = open(fullpath, 'w')
            generate_boilerplate(f, struct)
            generate_register_macros(f, peripheral, struct, indent)
            generate_structure(f, peripheral)

        f.write('#endif\n\n')
        f.close()

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
            peripheral = parse_peripheral(line[1:], original)
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

        elif line[0] == '+':
            name = parse_struct_name(line[1:], original)
            if not current_peripheral:
                raise Exception('Structure name without peripheral at line %d: %s' % (line_num, original))
            if current_peripheral.struct is not None:
                raise Exception('Duplicate structure name at line %d: %s' % (line_num, original))

            current_peripheral.struct = name

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

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--svd', help='Generate a .svd file', action='store_true')
    group.add_argument('--headers', help='Generate header files', action='store_true')

    parser.add_argument('--empty', help='Emit peripherals with no registers', action='store_true')
    parser.add_argument('-o', help='output path', type=str, required=True)
    parser.add_argument('-i', help='input files', type=str, required=True, nargs='+')
    args = parser.parse_args()

    if args.svd and not args.o:
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
        check_for_inconsistencies(peripherals)
        resolve_derived(peripherals, args.headers)
    except Exception as e:
        print('Error in %s: %s' % (filename, e.args))
        sys.exit(1)
    else:
        if args.svd:
            generate_svd(peripherals, args.o, args.empty)
        if args.headers:
            generate_headers(peripherals, args.o)

