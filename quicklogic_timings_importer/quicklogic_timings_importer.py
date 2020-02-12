from sdf_timing import sdfparse, sdfwrite
from sdf_timing import utils as sdfutils
from pathlib import Path
import argparse
import re
import json
from pprint import pprint as pp
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
    if not ltype in LOGLEVELS[:-1]:
        return
    dat = {"INFO": (0,"green"),
           "WARNING": (1,"yellow"),
           "ERROR": (2,"red"),
           "ALL": (3, "black")}
    if dat[ltype][0] >= dat[SUPPRESSBELOW][0]:
        print(colored("{}: {}".format(ltype, message), dat[ltype][1]))


def join_duplicate_keys(ordered_pairs) -> dict:
    '''Converts multiple key-value entries in input sequence to one entry.

    The function takes all key duplicates, and form an entry with single key
    and list of values.

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


def load_timing_info_from_lib(inputfilename: str) -> (str, dict):
    '''Reads the LIB file and converts it to dictionary structure.

    Parameters
    ----------
    inputfilename: str
        The name of LIB file to process

    Returns
    -------
        (str, dict): a tuple containing string representing file header and
        dictionary containing the whole structure of the file
    '''

    # REGEX defining the dictionary name in LIB file, i.e. "pin ( QAI )",
    # "pin(FBIO[22])" or "timing()"
    structdecl = re.compile(r'^(?P<indent>\s*)(?P<type>[A-Za-z]+)\s*\(\s*\"?(?P<name>[A-Za-z0-9_]*(\[[0-9]+\])?)\"?\s*\)')  # noqa: E501

    # REGEX defining typical variable name, which is any variable starting with
    # alphabetic character, followed by [A-Za-z_0-9] characters, and not within
    # quotes
    vardecl = re.compile(r'(?P<variable>(?<!\")[a-zA-Z_][a-zA-Z_0-9]*(\[[0-9]+\])?(?![^\:]*\"))')  # noqa: E501

    # Load LIB file
    with open(inputfilename, 'r') as infile:
        libfile = infile.readlines()

    # remove empty lines
    libfile = [line.rstrip() for line in libfile if line.strip()]

    # remove comments (C/C++ style)
    fullfile = '\n'.join(libfile)
    fullfile = re.sub(r'(?:\/\*(.*?)\*\/)|(?:\/\/(.*?))', '',
                      fullfile, flags=re.DOTALL)
    libfile = fullfile.split('\n')
    fullfile = ''

    # extract file header
    header = libfile.pop(0)

    # remove PORT DELAY root name
    libfile[0] = '{'

    # replace semicolons with commas
    libfile = [line.replace(';', ',') for line in libfile]

    # remove parenthesis from struct names
    for i, line in enumerate(libfile):
        structmatch = structdecl.match(line)
        if structmatch:
            if structmatch.group("name"):
                libfile[i] = structdecl.sub(r'\g<indent>\g<name> :', line)
            else:
                libfile[i] = structdecl.sub(r'\g<indent>\g<type>\g<name> :', line)

    # wrap all text in quotes
    for i, line in enumerate(libfile):
        libfile[i] = vardecl.sub(r'"\g<variable>"', line)

    # add colons after closing braces
    for i, line in enumerate(libfile):
        libfile[i] = line.replace("}", "},")

    # remove colons before closing braces
    fullfile = '\n'.join(libfile)
    fullfile = re.sub(r',(?P<tmp>\s*})', r'\g<tmp>', fullfile, flags=re.DOTALL)
    libfile = fullfile.split('\n')
    fullfile = ''

    # remove the colon in the end of file
    libfile[-1] = re.sub(r',\s*', '', libfile[-1])

    timingdict = json.loads('\n'.join(libfile),
                            object_pairs_hook=join_duplicate_keys)


    # sanity checking and duplicate entry handling
    for key, value in timingdict.items():
        if type(value) is list:
            finalentry = dict()
            for k in sorted(list(set([key for elements in value for key in elements]))):
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
            timingdict[key] = finalentry


    return header, timingdict


def extract_delval(libentry: dict):
    """Extracts SDF delval entry from Liberty structure format.

    Parameters
    ----------
    libentry: dict
        The pin entry from Liberty file, containing fields
        intrinsic_(rise|fall)(_min|_max)?
    Returns
    -------
    (dict, dict):
        pair of dicts containing extracted agv, max, min values from intrinsic
        rise and fall entries, respectively
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


def getparsekey(entrydata, direction):
    defentrydata = defaultdict(lambda: None, entrydata)
    return (direction, defentrydata["timing_type"] is not None and defentrydata["timing_type"] != 'combinational')


def parseiopath(delval_rise, delval_fall, objectname, entrydata):
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


def parsesetuphold(delval_rise, delval_fall, objectname, entrydata):
    ptype = "setuphold"
    edgetype = 'posedge'
    delays = {"setup": delval_rise, "hold": delval_fall}
    if 'timing_type'  in entrydata:
        if entrydata['timing_type'] == 'falling_edge':
            edgetype = 'negedge'
        elif entrydata['timing_type'] == 'hold_falling':
            ptype = 'hold'
            edgetype = 'negedge'
            delays = {"nominal": delval_rise}
        elif entrydata['timing_type'] == 'hold_rising':
            ptype = 'hold'
            delays = {"nominal": delval_rise}
        elif entrydata['timing_type'] == 'setup_falling':
            ptype = 'setup'
            edgetype = 'negedge'
            delays = {"nominal": delval_rise}
        elif entrydata['timing_type'] == 'setup_rising':
            ptype = 'setup'
            delays = {"nominal": delval_rise}
        elif entrydata['timing_type'] != 'rising_edge':
            log("WARNING", "not supported timing_type: {} in {}".format(
                entrydata['timing_type'], objectname))
            return None
    else:
        log("ERROR", "timing_type not present, combinational entry")
    # if delval_rise != delval_fall:
    #     print(colored("WARNING: SETUPHOLD does not support different 0-1 and 1-0 setuphold values: {} != {}".format(delval_rise, delval_fall), "cyan"))
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


def parseport(delval_rise, delval_fall, objectname, entrydata):
    # element = sdfutils.add_port(
    #         portname={"port": objectname},
    #         paths={"rise": delval_rise, "fall": delval_fall})
    # return element
    pass


def export_sdf_from_lib_dict(header: str, voltage: float, lib_dict: dict):
    '''Converts the dictionary containing parsed timing information from LIB
    file to the SDF format.

    Parameters
    ----------
    header: str
        A header for given LIB file
    voltage: float
        A voltage for which timings apply
    lib_dict: dict
        A dictionary containing parsed LIB file
    '''

    parserhooks = {}

    parserhooks[("input", True)] = [parsesetuphold]
    parserhooks[("input", False)] = [parseiopath]
    parserhooks[("inout", True)] = [parsesetuphold]
    parserhooks[("inout", False)] = [parseiopath]
    parserhooks[("output", True)] = [parsesetuphold]
    parserhooks[("output", False)] = [parseiopath]

    # extracts cell name and design name, ignore kfactor value
    headerparser = re.compile(r'^\"?(?P<cell>[a-zA-Z_][a-zA-Z_0-9]*)\"?\s*cell\s*(?P<design>[a-zA-Z_][a-zA-Z_0-9]*).*') # noqa: E501

    # extracts pin name and value
    whenparser = re.compile("(?P<name>[a-zA-Z_][a-zA-Z_0-9]*(\[[0-9]*\])?)\s*==\s*1'b(?P<value>[0-1])(\s*&&)?") # noqa: E501

    parsedheader = headerparser.match(header)

    sdfparse.init()

    sdfparse.sdfyacc.header = {
            'date': date.today().strftime("%B %d, %Y"),
            'design': parsedheader.group('design'),
            'sdfversion': '3.0',
            'voltage': {'avg': voltage, 'max': voltage, 'min': voltage },
            }

    # name of the cell
    instancename = parsedheader.group('cell')

    cells = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))

    # for all pins in the cell
    for objectname, obj in lib_dict.items():
        direction = obj['direction']
        # for all timing configurations in the cell
        if 'timing' in obj:
            for timing in (obj['timing'] if type(obj['timing']) is list
                    else [obj['timing']]):
                cellname = instancename
                if 'when' in timing:
                    # normally, the sdf_cond field should contain the name
                    # generated by the following code, but sometimes it is not
                    # present or represented by some specific constants
                    condlist = ['{}_EQ_{}'
                            .format(entry.group('name'), entry.group('value'))
                            for entry in whenparser.finditer(timing['when'])]
                    if not condlist:
                        log("ERROR", "when entry not parsable:  {}"
                                .format(timing['when']))
                        return False
                    cellname += "_" + '_'.join(condlist)
                if 'timing_type' in timing and 'falling' in timing['timing_type']:
                    cellname += "_{}_EQ_1".format(timing['timing_type'].upper())

                rise, fall = extract_delval(timing)

                # delay_paths = {"fall": fall, "rise": rise}
                for func in parserhooks[getparsekey(timing, direction)]:
                    element = func(rise, fall, objectname, timing)
                    if element is not None:
                        if element["name"] in cells[cellname][instancename]:
                            log("INFO", "entry {}/{}/{} repeated".format(
                                cellname, instancename, element["name"]))
                        cells[cellname][instancename][element["name"]] = element

    sdfparse.sdfyacc.cells = cells
    sdfparse.sdfyacc.timings = {
            "cells": sdfparse.sdfyacc.cells,
            "header": sdfparse.sdfyacc.header}

    sdffile = sdfwrite.emit_sdf(sdfparse.sdfyacc.timings)

    return sdffile
    #                 parameternames.add((parkey, type(parval)))
    #     # for parkey, parval in obj.items():
    #     #     parameternames.add((parkey,type(parval)))
    #     #     parameters[parkey] = parval
    # pp(sorted(list(parameternames), key=lambda x: x[0]))

    # Initialize Yacc and Lex


if __name__ == "__main__":

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

    print("Processing {}".format(args.input))
    header, timingdict = load_timing_info_from_lib(args.input)

    if args.json_output:
        with open(args.json_output, 'w') as out:
            json.dump(timingdict, out, indent=4)

    result = export_sdf_from_lib_dict(header, args.voltage, timingdict)

    with open(args.output, 'w') as out:
        out.write(result)
