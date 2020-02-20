#!/usr/bin/env python3

import argparse
from pathlib import Path
import json
import log_printer
import pprint
import re


class JSONToLibertyWriter():

    _indtype = '  '
    _indlevel = 0
    _ind = ''

    class JSONToLibertyWriterException(Exception):
        '''Exception raised for errors in converting JSON to Liberty format.

        Attributes
        ----------
        jsonentry: tuple
            A key-value pair for which parsing failed
        message: str
            A message included with the exception
        '''
        def __init__(self, jsonentry, message):
            self.jsonentry = jsonentry
            self.message = message + '\n'
            self.message += 'key: {}\nvalue:\n'.format(jsonentry[0])
            self.message += pprint.pformat(jsonentry[1], indent=2)

    @classmethod
    def updateind(cls, diff):
        cls._indlevel += diff
        cls._ind = cls._indtype * cls._indlevel

    @classmethod
    def update(cls, lines, line):
        lines.append(cls._ind + line)

    @classmethod
    def parse_entry(cls, rootkey, rootvalue) -> list:
        '''Recursively prints the dictionary containing Liberty group.
        '''

        lines = []

        if type(rootvalue) == list:
            if 'comp_attribute ' in rootkey:
                # repeated attributes with values grouped into list
                for value in rootvalue:
                    entrylines = cls.parse_entry(rootkey, value)
                    lines.extend(entrylines)
            else:
                # we deal with list of values or i.e. timing entries
                # first we check the types of entries
                rootvaluetypes = sorted(list(set(
                    [type(el).__name__ for el in rootvalue])))

                if len(rootvaluetypes) == 1 and rootvaluetypes[0] == 'dict':
                    # these are grouped structs with same name, we need to
                    # repeat them
                    for value in rootvalue:
                        entrylines = cls.parse_entry(rootkey, value)
                        lines.extend(entrylines)
                elif (len(rootvaluetypes) == 1
                        and rootvaluetypes[0] in ['int', 'float']):
                    # these are numbers from array
                    values = ', '.join([str(val) for val in rootvalue])
                    cls.update(lines, '{} ("{}");'.format(rootkey, values))
                elif len(rootvaluetypes) == 1 and rootvaluetypes[0] == 'list':
                    # it's a two-dimensional array
                    cls.update(lines, '{} ( \\'.format(rootkey))
                    cls._ind = ' ' * (len(lines[-1]) - 2)
                    for array in rootvalue:
                        arr = '"{}", \\'.format(
                                ', '.join([str(a) for a in array]))
                        cls.update(lines, arr)
                    cls.updateind(0)
                    cls.update(lines, ");")
                else:
                    for value in rootvalue:
                        cls.update(lines, '{} ({});'.format(rootkey, value))

        elif type(rootvalue) == dict:

            # we need to process dict entries

            if ' ' in rootkey:
                keysplit = rootkey.split(' ')
                cls.update(lines, '{} ({}) {{'.format(
                    keysplit[0], keysplit[1]))
                for key, value in rootvalue.items():
                    cls.updateind(+1)
                    entrylines = cls.parse_entry(key, value)
                    cls.updateind(-1)
                    lines.extend(entrylines)
                cls.update(lines, '}')
            elif rootkey == 'define':
                cls.update(lines, '{} ({},{},{});'.format(
                    rootkey,
                    rootvalue['attribute_name'],
                    rootvalue['group_name'],
                    rootvalue['attribute_type']))
            else:
                raise cls.JSONToLibertyWriterException(
                        (rootkey, rootvalue),
                        'JSON entry not parseable 1')
        else:
            # we possibly have simple types
            if ' ' in rootkey:
                # we should have a complex attribute
                if 'comp_attribute' in rootkey:
                    attrname = rootkey.split(' ')[1]
                    cls.update(lines, '{} ({});'.format(attrname, rootvalue))
                else:
                    # there is some issue
                    raise cls.JSONToLibertyWriterException(
                            (rootkey, rootvalue),
                            'JSON entry not parseable 2')
            else:
                if ((type(rootvalue) is str)
                        and not re.match(r'^\d+\.\d+$', rootvalue)):
                    cls.update(lines, '{} : "{}";'.format(rootkey, rootvalue))
                else:
                    cls.update(lines, '{} : {};'.format(rootkey, rootvalue))
        return lines

    @classmethod
    def convert_json_to_liberty(cls, jsondict: dict, indent=2) -> list:
        '''Converts JSON-like dictionary into list of Liberty format lines.

        Parameters
        ----------
        jsondict: dict
            JSON-like dictionary containing timing content parsable by Liberty

        Returns
        -------
        list: list of string lines containing Liberty result
        '''
        lines = []
        if len(list(jsondict.keys())) != 1:
            raise cls.JSONToLibertyWriterException(
                    (None, None),
                    'JSON have multiple root objects')
        else:
            for key, value in jsondict.items():
                lines = JSONToLibertyWriter.parse_entry(key, value)
        return lines


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
            "input",
            help="JSON file containing timings",
            type=Path)
    parser.add_argument(
            "output",
            help="The output Liberty file containing JSON timings",
            type=Path)
    parser.add_argument(
            "--log-suppress-below",
            help="The mininal not suppressed log level",
            type=str,
            default="ERROR",
            choices=log_printer.LOGLEVELS)

    args = parser.parse_args()

    log_printer.SUPPRESSBELOW = args.log_suppress_below

    with open(args.input, 'r') as infile:
        jsondict = json.load(infile)

    try:
        liblines = JSONToLibertyWriter.convert_json_to_liberty(jsondict)
        if liblines:
            with open(args.output, 'w') as out:
                out.write('\n'.join(liblines))
    except JSONToLibertyWriter.JSONToLibertyWriterException as ex:
        log_printer.log('ERROR', ex.message)


if __name__ == '__main__':
    main()
