#!/usr/bin/env python3

import argparse
from pathlib import Path
import json
import re
import log_printer


class LibertyToJSONParser():

    @classmethod
    def join_duplicate_keys(cls, ordered_pairs) -> dict:
        '''Converts multiple key-value entries in input sequence to one entry.

        The function takes all key duplicates, and form an entry with single
        key and list of values.

        Parameters
        ----------
        ordered_pairs: list
            list of pairs key-value

        Returns
        -------
        dict: dictionary, where values with same keys are grouped into list
        '''
        d = {}
        for k, v in ordered_pairs:
            if k in d:
                if type(d[k]) == list:
                    d[k].append(v)
                else:
                    if d[k] != v:
                        d[k] = [d[k], v]
            else:
                d[k] = v
        return d

    @classmethod
    def load_timing_info_from_lib(cls, libfile: list) -> (dict):
        '''Reads the LIB file and converts it to dictionary structure.

        Parameters
        ----------
        libfile: list
            The lines for input LIB file

        Returns
        -------
            dict: a dictionary containing the whole structure of the file
        '''

        # regex for indent
        inddef = r'^(?P<indent>\s*)'

        # regex for variables
        vardef = r'([A-Za-z_][a-zA-Z_0-9\-]*)'

        # regex for floating-point numbers
        numdef = r'[-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?'

        # regex for all allowed characters in struct definition name
        alloweddef = r'[^\n\"{{]+'

        # regex for arrays
        arrdef = r'(\s*\"\s*(?P<arrvalues>({numdef}(,\s*)?)+)\s*\"\s*,?)'.format(numdef=numdef)  # noqa: E501

        # REGEX defining the dictionary name in LIB file, i.e. "pin ( QAI )",
        # "pin(FBIO[22])" or "timing()"
        structdecl = re.compile(r'{inddef}(?P<type>{vardef})\s*\(\s*(\"(?P<nameq>[^\n{{]+?)?\"|(?P<name>[^\n{{]+?)?)\s*\)'.format(vardef=vardef, inddef=inddef, alloweddef=alloweddef))  # noqa: E501

        # REGEX defining global "attribute (entry);" statements
        attdecl = re.compile(r'{inddef}(?P<attrname>{vardef})\s*\(\s*(\"(?P<attrvalq>[^\n\(\)]+?)\"|(?P<attrval>[^\n\(\)]+?))\s*\)\s*,$'.format(vardef=vardef, inddef=inddef))  # noqa: E501

        # REGEX defining array for lu_table_template template breakpoints
        arrdecl = re.compile(r'{inddef}(?P<arrname>{vardef})\s*\((?P<array>{arrdef}+)\)'.format(vardef=vardef, inddef=inddef, arrdef=arrdef))  # noqa: E501

        # REGEX defining arrays
        subarrdecl = re.compile(arrdef)

        singlearr = re.compile(r'{inddef}\"(?P<arrname>{vardef})\"\s*:{arrdef}'.format(vardef=vardef, inddef=inddef, arrdef=arrdef))  # noqa: E501

        # REGEX defining Liberty `define` statements
        defdecl = re.compile(r'{inddef}define\s*\(\s*(?P<attribute_name>{vardef})\s*,\s*(?P<group_name>{vardef})\s*,\s*(?P<attribute_type>{vardef})\s*\)\s*,'.format(vardef=vardef, inddef=inddef))  # noqa: E501

        # REGEX defining lines with no ending colon
        nocommadecl = re.compile(r'(?P<content>{inddef}{vardef}\s*:\s*(\"[^\n\"\(\)]+\"|[^\n\s\"\(\),]+))\s*$'.format(inddef=inddef, vardef=vardef))  # noqa: E501

        # REGEX defining typical variable name, which is any variable starting
        # with alphabetic character, followed by [A-Za-z_0-9] characters, and
        # not within quotes
        unwrappeddecl = re.compile(r'{inddef}(\"(?P<varnameq>{vardef})\"|(?P<varname>{vardef}))\s*:\s*(\"(?P<varvalueq>[^\n\"{{]*)\"|(?P<varvalue>[^\n\"{{]*))\s*,$'.format(inddef=inddef, vardef=vardef))  # noqa: E501
        # vardecl = re.compile(r'(?P<variable>(?<!\"){vardef}(\[[0-9]+\])?(?![^\:]*\"))'.format(vardef=vardef))  # noqa: E501

        # join all lines into single string
        fullfile = '\n'.join(libfile)

        # remove comments (C/C++ style)
        
        fullfile = re.sub(r'(?:\/\*(.*?)\*\/)', '',
                          fullfile, flags=re.DOTALL)
        
        fullfile = re.sub(r'(?:\/\/(.*?)\n)', '\n',
                          fullfile, flags=re.DOTALL)

        # remove comments (Python style)
        fullfile = re.sub(r'#[^\n]*\n', '', fullfile, flags=re.DOTALL)

        # remove line breaks
        fullfile = re.sub(r'\\[\s\n\r\t]*', '', fullfile, flags=re.DOTALL)

        # replace all tabs with single space
        fullfile = fullfile.replace('\t', ' ')

        # move non-whitespace content after } to new line
        fullfile = re.sub(r'}\s*(?!\n)', '}\n', fullfile, flags=re.DOTALL)

        # split single string into lines
        libfile = fullfile.split('\n')
        fullfile = ''

        # replace semicolons with commas
        libfile = [line.replace(';', ',') for line in libfile]

        # remove empty lines and trailing whitespaces
        libfile = [line.rstrip() for line in libfile if line.strip()]

        for i in range(len(libfile)):
            # add comma if not present
            # TODO: not sure if this should be accepted or returned as error
            libfile[i] = nocommadecl.sub(r'\g<content>,', libfile[i])

            # parse `define` entries
            libfile[i] = defdecl.sub(
                    r'\g<indent>"define" : {"attribute_name": '
                    r'"\g<attribute_name>", "group_name": "\g<group_name>", '
                    r'"attribute_type": "\g<attribute_type>"}',
                    libfile[i])

            # parse array entries to make them JSON-compliant
            arrmatch = arrdecl.match(libfile[i])
            if arrmatch:
                arrays = ''

                first = True
                matches = [match for match in
                           subarrdecl.finditer(arrmatch.group("array"))]
                for match in matches:
                    if first:
                        if len(matches) == 1:
                            arrays = '{}'.format(match.group('arrvalues'))
                        else:
                            arrays = '[{}]'.format(match.group('arrvalues'))
                        first = False
                    else:
                        arrays += ', [{}]'.format(match.group('arrvalues'))

                libfile[i] = '{indent}{arrname} : [{arrays}],'.format(
                        indent=arrmatch.group('indent'),
                        arrname=arrmatch.group('arrname'),
                        arrays=arrays)

            # convert array-like attributes to arrays
            # log_printer.log('INFO', libfile[i])
            libfile[i] = singlearr.sub(
                    r'\g<indent>"\g<arrname>" : [\g<arrvalues>],',
                    libfile[i])

            # parse attribute entries
            attmatch = attdecl.match(libfile[i])
            if attmatch:
                libfile[i] = '{}"comp_attribute {}" : "{}",'.format(
                        attmatch.group("indent"),
                        attmatch.group("attrname"),
                        (attmatch.group("attrval")
                            if attmatch.group("attrval") else
                            attmatch.group("attrvalq")).replace('"', '\\"'))

            # remove parenthesis from struct names
            structmatch = structdecl.match(libfile[i])
            if structmatch:
                if structmatch.group("name") or structmatch.group("nameq"):
                    libfile[i] = '{}"{} {}" : {}'.format(
                            structmatch.group("indent"),
                            structmatch.group("type"),
                            (structmatch.group("name") if
                                structmatch.group("name") else
                                structmatch.group("nameq")).replace(
                                    '"', '\\"'),
                            '{' if libfile[i].rstrip().endswith('{') else '')
                else:
                    libfile[i] = structdecl.sub(
                            r'\g<indent>"\g<type> " :',
                            libfile[i])

            # wrap all text in quotes
            unwrappedmatch = unwrappeddecl.match(libfile[i])
            if unwrappedmatch:
                singlearrdef = r'\[?\s*(\[\s*(?P<arrvalues>({numdef}(,\s*)?)+)\s*\])+\s*\]?'.format(numdef=numdef)  # noqa: E501
                varval = (unwrappedmatch.group('varvalue')
                          if unwrappedmatch.group('varvalue')
                          else unwrappedmatch.group('varvalueq'))
                varnam = (unwrappedmatch.group('varname')
                          if unwrappedmatch.group('varname')
                          else unwrappedmatch.group('varnameq'))
                isarray = re.match(
                        singlearrdef,
                        varval)
                if isarray:
                    libfile[i] = '{}"{}" : {},'.format(
                            unwrappedmatch.group('indent'),
                            varnam,
                            varval.strip())
                else:
                    libfile[i] = '{}"{}" : "{}",'.format(
                            unwrappedmatch.group('indent'),
                            varnam,
                            varval.strip())

            # add colons after closing braces
            libfile[i] = libfile[i].replace("}", "},")

        # remove colons before closing braces
        fullfile = '\n'.join(libfile)
        fullfile = re.sub(
                r',(?P<tmp>\s*})', r'\g<tmp>',
                fullfile,
                flags=re.DOTALL)
        libfile = fullfile.split('\n')
        fullfile = ''

        # remove the colon in the end of file
        libfile[-1] = re.sub(r',\s*', '', libfile[-1])

        timingdict = json.loads('\n'.join(libfile),
                                object_pairs_hook=cls.join_duplicate_keys)

        return timingdict


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
            "input",
            help="LIB file containing timings",
            type=Path)
    parser.add_argument(
            "output",
            help="The output JSON file containing LIB timings",
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
        libfile = infile.readlines()

    libfile = ['{\n'] + libfile + ['}']

    timingdict = (LibertyToJSONParser.load_timing_info_from_lib(libfile))

    with open(args.output, 'w') as out:
        json.dump(timingdict, out, indent=4)


if __name__ == '__main__':
    main()
