from sdf_timing import sdfparse, sdfwrite
from sdf_timing import utils as sdfutils
from pathlib import Path
import argparse
import re
import json
from termcolor import colored
from datetime import date
from collections import defaultdict

LOGLEVELS = ["INFO", "WARNING", "ERROR", "ALL"]
SUPPRESSBELOW = "ERROR"


def log(ltype, message):
    """Prints log messages.

    Parameters
    ----------
    ltype: str
        Log type, can be INFO, WARNING, ERROR
    message: str
        Log message
    """
    if ltype not in LOGLEVELS[:-1]:
        return
    dat = {"INFO": (0, "green"),
           "WARNING": (1, "yellow"),
           "ERROR": (2, "red"),
           "ALL": (3, "black")}
    if dat[ltype][0] >= dat[SUPPRESSBELOW][0]:
        print(colored("{}: {}".format(ltype, message), dat[ltype][1]))


class LibertyToSDFParser():

    ctypes = ['combinational', 'three_state_disable', 'three_state_enable']

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
                    d[k] = [d[k], v]
            else:
                d[k] = v
        return d

    @classmethod
    def load_timing_info_from_lib(cls, libfile: list) -> (str, dict):
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
        vardef = r'([A-Za-z_][a-zA-Z_0-9]*)'

        # REGEX defining the dictionary name in LIB file, i.e. "pin ( QAI )",
        # "pin(FBIO[22])" or "timing()"
        structdecl = re.compile(r'{inddef}(?P<type>{vardef})\s*\(\s*\"?(?P<name>{vardef}(\[[0-9]+\])?)?\"?\s*\)'.format(vardef=vardef, inddef=inddef))  # noqa: E501

        # REGEX defining global "attribute (entry);" statements
        attdecl = re.compile(r'{inddef}(?P<attrname>{vardef})\s*\(\s*\"?(?P<attrval>[^\n\"\(\)]+)\"?\s*\)\s*,'.format(vardef=vardef, inddef=inddef))  # noqa: E501

        # REGEX defining typical variable name, which is any variable starting
        # with alphabetic character, followed by [A-Za-z_0-9] characters, and
        # not within quotes
        vardecl = re.compile(r'(?P<variable>(?<!\"){vardef}(\[[0-9]+\])?(?![^\:]*\"))'.format(vardef=vardef))  # noqa: E501


        # REGEX defining Liberty `define` statements
        defdecl = re.compile(r'{inddef}define\s*\(\s*(?P<attribute_name>{vardef})\s*,\s*(?P<group_name>{vardef})\s*,\s*(?P<attribute_type>{vardef})\s*\)\s*,'.format(vardef=vardef, inddef=inddef))  # noqa: E501

        # REGEX defining lines with no ending colon
        nocommadecl = re.compile(r'(?P<content>{inddef}{vardef}\s*:\s*(\"[^\n\"\(\)]+\"|[^\n\s\"\(\),]+))\s*$'.format(inddef=inddef, vardef=vardef))  # noqa: E501

        # remove empty lines and trailing whitespaces
        libfile = [line.rstrip() for line in libfile if line.strip()]

        # join all lines into single string
        fullfile = '\n'.join(libfile)

        # remove comments (C/C++ style)
        fullfile = re.sub(r'(?:\/\*(.*?)\*\/)|(?:\/\/(.*?))', '',
                          fullfile, flags=re.DOTALL)

        # remove comments (Python style)
        fullfile = re.sub(r'#[^\n]*\n', '', fullfile, flags=re.DOTALL)

        # remove line breaks
        fullfile = re.sub(r'\\[\s\n\r\t]*', '', fullfile, flags=re.DOTALL)

        # split single string into lines
        libfile = fullfile.split('\n')
        fullfile = ''

        # replace semicolons with commas
        libfile = [line.replace(';', ',') for line in libfile]

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

            # parse attribute entries
            libfile[i] = attdecl.sub(
                    r'\g<indent>"\g<attrname>" : "\g<attrval>",',
                    libfile[i])

            # remove parenthesis from struct names
            structmatch = structdecl.match(libfile[i])
            if structmatch:
                if structmatch.group("name"):
                    libfile[i] = structdecl.sub(
                            r'\g<indent>"\g<type> \g<name>" :',
                            libfile[i])
                else:
                    libfile[i] = structdecl.sub(
                            r'\g<indent>"\g<type>" :',
                            libfile[i])



            # wrap all text in quotes
            libfile[i] = vardecl.sub(r'"\g<variable>"', libfile[i])

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

    @classmethod
    def extract_delval(cls, libentry: dict):
        """Extracts SDF delval entry from Liberty structure format.

        Parameters
        ----------
        libentry: dict
            The pin entry from Liberty file, containing fields
            intrinsic_(rise|fall)(_min|_max)?
        Returns
        -------
        (dict, dict):
            pair of dicts containing extracted agv, max, min values from
            intrinsic rise and fall entries, respectively
        """
        fall = {'avg': None, 'max': None, 'min': None}
        rise = {'avg': None, 'max': None, 'min': None}

        if 'intrinsic_rise_min' in libentry:
            rise['min'] = libentry['intrinsic_rise_min']
        if 'intrinsic_rise' in libentry:
            rise['avg'] = libentry['intrinsic_rise']
        if 'intrinsic_rise_max' in libentry:
            rise['max'] = libentry['intrinsic_rise_max']

        if 'intrinsic_fall_min' in libentry:
            fall['min'] = libentry['intrinsic_fall_min']
        if 'intrinsic_fall' in libentry:
            fall['avg'] = libentry['intrinsic_fall']
        if 'intrinsic_fall_max' in libentry:
            fall['max'] = libentry['intrinsic_fall_max']

        return rise, fall

    @classmethod
    def getparsekey(cls, entrydata, direction):
        """Generates keys for entry to corresponding parsing hook.

        Parameters
        ----------
        entrydata: dict
            Timing entry from Liberty-JSON structure to generate the key for
        direction: str
            The direction of pin, can be input, output, inout

        Returns
        -------
        tuple: key for parser hook
        """
        defentrydata = defaultdict(lambda: None, entrydata)
        return (
                direction,
                (defentrydata["timing_type"] is not None and
                    defentrydata["timing_type"] not in cls.ctypes))

    @classmethod
    def parseiopath(cls, delval_rise, delval_fall, objectname, entrydata):
        """Parses combinational entries into IOPATH.

        This hook takes combinational output entries from LIB file, and
        generates the corresponding IOPATH entry in SDF.

        Parameters
        ----------
        delval_rise: dict
            Delay values for IOPATH for 0->1 change
        delval_fall: dict
            Delay values for IOPATH for 1->0 change
        objectname: str
            The name of the cell containing given pin
        entrydata: dict
            Converted LIB struct fro given pin

        Returns
        -------
        dict: SDF entry for a given pin
        """
        element = sdfutils.add_iopath(
                pfrom={
                    "port": entrydata["related_pin"],
                    "port_edge": None,
                    },
                pto={
                    "port": objectname,
                    "port_edge": None,
                    },
                paths={'fast': delval_rise, 'nominal': delval_fall})
        element["is_absolute"] = True
        return element

    @classmethod
    def parsesetuphold(cls, delval_rise, delval_fall, objectname, entrydata):
        """Parses clock-depending entries into timingcheck entry.

        This hook takes timing information from LIB file for pins depending on
        clocks (like setup, hold, etc.), and generates the corresponding
        TIMINGCHECK entry in SDF.

        Parameters
        ----------
        delval_rise: dict
            Delay values for TIMINGCHECK
        delval_fall: dict
            Delay values for TIMINGCHECK (should not differ from delval_rise)
        objectname: str
            The name of the cell containing given pin
        entrydata: dict
            Converted LIB struct fro given pin

        Returns
        -------
        dict: SDF entry for a given pin
        """

        typestoedges = {
            'falling_edge': ('setuphold', 'negedge'),
            'rising_edge': ('setuphold', 'posedge'),
            'hold_falling': ('hold', 'negedge'),
            'hold_rising': ('hold', 'posedge'),
            'setup_falling': ('setup', 'negedge'),
            'setup_rising': ('setup', 'posedge'),
            'removal_falling': ('removal', 'negedge'),
            'removal_rising': ('removal', 'posedge'),
            'recovery_falling': ('recovery', 'negedge'),
            'recovery_rising': ('recovery', 'posedge'),
            'clear': None,
        }
        # combinational types, should not be present in this function
        if ('timing_type' in entrydata and
                entrydata['timing_type'] not in cls.ctypes):
            timing_type = entrydata['timing_type']
            if timing_type not in typestoedges:
                log("WARNING", "not supported timing_type: {} in {}".format(
                    timing_type, objectname))
                return None
            if typestoedges[timing_type] is None:
                log("INFO", 'timing type is ignored: {}'.format(timing_type))
                return None
            if timing_type in ['falling_edge', 'rising_edge']:
                delays = {"setup": delval_rise, "hold": delval_fall}
            else:
                delays = {"nominal": delval_fall}
            ptype, edgetype = typestoedges[timing_type]
        else:
            log("ERROR", "combinational entry in sequential timing parser")
            assert entrydata['timing_type'] not in cls.ctypes

        element = sdfutils.add_tcheck(
                type=ptype,
                pto={
                    "port": objectname,
                    "port_edge": None,
                    },
                pfrom={
                    "port": entrydata["related_pin"],
                    "port_edge": edgetype,
                    "cond": None,
                    "cond_equation": None,
                    },
                paths=delays)
        return element

    @classmethod
    def merge_delays(cls, oldelement, newelement):
        """Merges delays for "duplicated" entries.

        LIB format contains field `timing_sense` that describes to what changes
        between the input and output the given entry refers to
        (`positive_unate`, `negative_unate`, `non_unate`).

        SDF does not support such parameter diversity, so for now when there
        are different delay values of parameters depending on `timing_sense`
        field, then we take the worst possible timings.

        Parameters
        ----------
        oldelement: dict
            Previous pin entry for cell
        newelement: dict
            New pin entry for cell

        Returns
        -------
        dict: Merged entry
        """
        olddelays = oldelement["delay_paths"]
        newdelays = newelement["delay_paths"]
        delays = {**olddelays, **newdelays}
        for key in delays.keys():
            if key in olddelays and key in newdelays:
                old = olddelays[key]
                new = newdelays[key]
                for dkey in old:
                    if new[dkey] is None or (
                            old[dkey] is not None and old[dkey] > new[dkey]):
                        delays[key][dkey] = old[dkey]
                    else:
                        delays[key][dkey] = new[dkey]
        element = oldelement
        element["delay_paths"] = delays
        return element

    @classmethod
    def export_sdf_from_lib_dict(
            cls,
            header: str,
            voltage: float,
            lib_dict: dict):
        '''Converts the dictionary containing parsed timing information from
        LIB file to the SDF format.

        Parameters
        ----------
        header: str
            A header for given LIB file
        voltage: float
            A voltage for which timings apply
        lib_dict: dict
            A dictionary containing parsed LIB file
        '''

        # setup hooks that run different parsing functions based on current
        # entry
        parserhooks = {}

        parserhooks[("input", True)] = [cls.parsesetuphold]
        parserhooks[("input", False)] = [cls.parseiopath]
        parserhooks[("inout", True)] = [cls.parsesetuphold]
        parserhooks[("inout", False)] = [cls.parseiopath]
        parserhooks[("output", True)] = [cls.parsesetuphold]
        parserhooks[("output", False)] = [cls.parseiopath]

        # extracts cell name and design name, ignore kfactor value
        headerparser = re.compile(r'^\"?(?P<cell>[a-zA-Z_][a-zA-Z_0-9]*)\"?\s*cell\s*(?P<design>[a-zA-Z_][a-zA-Z_0-9]*).*')  # noqa: E501

        # extracts pin name and value
        whenparser = re.compile("(?P<name>[a-zA-Z_][a-zA-Z_0-9]*(\[[0-9]*\])?)\s*==\s*1'b(?P<value>[0-1])(\s*&&)?")  # noqa: E501

        # parse header
        parsedheader = headerparser.match(header)

        # initialize Yacc dictionaries holding data
        sdfparse.init()

        sdfparse.sdfyacc.header = {
                'date': date.today().strftime("%B %d, %Y"),
                'design': parsedheader.group('design'),
                'sdfversion': '3.0',
                'voltage': {'avg': voltage, 'max': voltage, 'min': voltage},
                }

        # name of the cell
        instancename = parsedheader.group('cell')

        cells = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))

        keys = [key for key in lib_dict.keys()]

        if len(keys) != 1 or not keys[0].startswith('library'):
            log('ERROR', 'JSON does not represent Liberty library')
            return None

        librarycontent = lib_dict[keys[0]]

        # for all pins in the cell
        for objectname, obj in librarycontent.items():
            direction = obj['direction']
            # for all timing configurations in the cell
            if 'timing' in obj:
                elementnametotiming = defaultdict(lambda: [])
                for timing in (obj['timing']
                               if type(obj['timing']) is list
                               else [obj['timing']]):
                    cellname = instancename
                    if 'when' in timing:
                        # normally, the sdf_cond field should contain the name
                        # generated by the following code, but sometimes it is
                        # not present or represented by some specific constants
                        condlist = ['{}_EQ_{}'
                                    .format(entry.group('name'),
                                            entry.group('value'))
                                    for entry in whenparser.finditer(
                                        timing['when'])]
                        if not condlist:
                            log("ERROR", "when entry not parsable:  {}"
                                .format(timing['when']))
                            return False
                        cellname += "_" + '_'.join(condlist)

                    # when the timing is defined for falling edge, add this
                    # info to cell name
                    if 'timing_type' in timing:
                        if 'falling' in timing['timing_type']:
                            cellname += "_{}_EQ_1".format(
                                    timing['timing_type'].upper())

                    # extract intrinsic_rise and intrinsic_fall in SDF-friendly
                    # format
                    rise, fall = cls.extract_delval(timing)

                    # run all defined hooks for given timing entry
                    parserkey = cls.getparsekey(timing, direction)
                    for func in parserhooks[parserkey]:
                        element = func(rise, fall, objectname, timing)
                        if element is not None:
                            # Merge duplicated entries
                            elname = element["name"]
                            if elname in cells[cellname][instancename]:
                                element = cls.merge_delays(
                                        cells[cellname][instancename][elname],
                                        element)

                            # memorize the timing entry responsible for given
                            # SDF entry
                            elementnametotiming[elname].append(timing)
                            # add SDF entry
                            cells[cellname][instancename][elname] = element

        # generate SDF file from dictionaries
        sdfparse.sdfyacc.cells = cells
        sdfparse.sdfyacc.timings = {
                "cells": sdfparse.sdfyacc.cells,
                "header": sdfparse.sdfyacc.header}

        sdffile = sdfwrite.emit_sdf(sdfparse.sdfyacc.timings)

        return sdffile


def main():
    global SUPPRESSBELOW

    # TODO: support missing timing_type
    # TODO: support tristate

    parser = argparse.ArgumentParser()
    parser.add_argument(
            "input",
            help="LIB file containing timings from EOS-3",
            type=Path)
    parser.add_argument(
            "output",
            help="The output SDF file containing timing",
            type=Path)
    parser.add_argument(
            "--json-output",
            help="The output JSON file containing parsed Liberty entries",
            type=Path)
    parser.add_argument(
            "--voltage",
            help="The voltage for a given timing",
            type=float)
    parser.add_argument(
            "--log-suppress-below",
            help="The mininal not suppressed log level",
            type=str,
            default="ERROR",
            choices=LOGLEVELS)

    args = parser.parse_args()

    SUPPRESSBELOW = args.log_suppress_below

    # Load LIB file
    with open(args.input, 'r') as infile:
        libfile = infile.readlines()

    # remove empty lines and trailing whitespaces
    libfile = [line.rstrip() for line in libfile if line.strip()]

    # extract file header
    header = libfile.pop(0)

    # remove PORT DELAY root name
    libfile[0] = r'library \({}\) {}'.format(
            header.replace(' ', '_').replace('.', '_').replace('"', ''), '{')
    libfile = ['{\n'] + libfile + ['}']

    print("Processing {}".format(args.input))
    timingdict = LibertyToSDFParser.load_timing_info_from_lib(libfile)

    libkey = [key for key in timingdict.keys()][0]

    # sanity checking and duplicate entry handling
    for key, value in timingdict[libkey].items():
        if type(value) is list:
            finalentry = dict()
            for k in sorted(list(
                    set([key for elements in value for key in elements]))):
                first = True
                val = None
                for duplicate in value:
                    if k in duplicate:
                        if first:
                            val = duplicate[k]
                            first = False
                        assert duplicate[k] == val, \
                            "ERROR: entries for {} have different" \
                            "values for parameter {}: {} != {}".format(
                                    key,
                                    k,
                                    val,
                                    duplicate[k])
                finalentry[k] = val
            timingdict[libkey][key] = finalentry

    if args.json_output:
        with open(args.json_output, 'w') as out:
            json.dump(timingdict, out, indent=4)

    result = LibertyToSDFParser.export_sdf_from_lib_dict(
            header,
            args.voltage,
            timingdict)

    with open(args.output, 'w') as out:
        out.write(result)


if __name__ == "__main__":
    main()
