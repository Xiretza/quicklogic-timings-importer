from sdf_timing import sdfparse, sdfwrite
from sdf_timing import utils as sdfutils
from pathlib import Path
import argparse
import re
import json
from datetime import date
from collections import defaultdict
from .liberty_to_json import LibertyToJSONParser
from . import log_printer
from .log_printer import log


class JSONToSDFParser():

    ctypes = ['combinational', 'three_state_disable', 'three_state_enable', 'rising_edge', 'falling_edge', 'clear']

    # extracts cell name and design name, ignore kfactor value
    headerparser = re.compile(r'^\"?(?P<cell>[a-zA-Z_][a-zA-Z_0-9]*)\"?\s*cell\s*(?P<design>[a-zA-Z_][a-zA-Z_0-9]*)\s*(?:kfactor\s*(?P<kfactor>[0-9.]*))?\s*(?:instance\s*(?P<instance>[a-zA-Z_0-9]*))?.*')  # noqa: E501

    normalize_cell_names = True
    normalize_port_names = True

    @classmethod
    def extract_delval(cls, libentry: dict, kfactor: float):
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
            rise['min'] = float(libentry['intrinsic_rise_min']) * kfactor
        if 'intrinsic_rise' in libentry:
            rise['avg'] = float(libentry['intrinsic_rise']) * kfactor
        if 'intrinsic_rise_max' in libentry:
            rise['max'] = float(libentry['intrinsic_rise_max']) * kfactor

        if 'intrinsic_fall_min' in libentry:
            fall['min'] = float(libentry['intrinsic_fall_min']) * kfactor
        if 'intrinsic_fall' in libentry:
            fall['avg'] = float(libentry['intrinsic_fall']) * kfactor
        if 'intrinsic_fall_max' in libentry:
            fall['max'] = float(libentry['intrinsic_fall_max']) * kfactor

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
        tuple: key for parser hook (direction, is_sequential)
        """
        defentrydata = defaultdict(lambda: None, entrydata)
        return (
                direction,
                (defentrydata["timing_type"] is not None and
                    defentrydata["timing_type"] not in cls.ctypes))

    @classmethod
    def is_delval_empty(cls, delval):
        """Checks if delval is empty.

        Parameters
        ----------
        delval: dict
            A delval value

        Returns
        -------
        bool: True if empty, else False
        """
        for val in delval.values():
            if not(val is None or float(val) == 0):
                return False
        return True

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

        if cls.normalize_port_names:
            normalize = cls.normalize_name
        else:
            normalize = lambda x: x

        paths = {}
        paths['fast'] = delval_rise
        paths['nominal'] = delval_fall
        element = sdfutils.add_iopath(
                pfrom={
                    "port": normalize(entrydata["related_pin"]),
                    "port_edge": None,
                    },
                pto={
                    "port": normalize(objectname),
                    "port_edge": None,
                    },
                paths=paths)
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
            'hold_falling': ('hold', 'negedge'),
            'hold_rising': ('hold', 'posedge'),
            'setup_falling': ('setup', 'negedge'),
            'setup_rising': ('setup', 'posedge'),
            'removal_falling': ('removal', 'negedge'),
            'removal_rising': ('removal', 'posedge'),
            'recovery_falling': ('recovery', 'negedge'),
            'recovery_rising': ('recovery', 'posedge'),
        }

        if cls.normalize_port_names:
            normalize = cls.normalize_name
        else:
            normalize = lambda x: x

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
            else:
                delays = {
                    "nominal": (delval_fall if cls.is_delval_empty(delval_rise)
                                else delval_rise)}
            ptype, edgetype = typestoedges[timing_type]
        else:
            log("ERROR", "combinational entry in sequential timing parser")
            assert entrydata['timing_type'] not in cls.ctypes

        element = sdfutils.add_tcheck(
                type=ptype,
                pto={
                    "port": normalize(objectname),
                    "port_edge": None,
                    },
                pfrom={
                    "port": normalize(entrydata["related_pin"]),
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
    def normalize_name(cls, name):
        # remove array markers
        newname = name.replace('[','').replace(']','')
        return newname

    @classmethod
    def export_sdf_from_lib_dict(
            cls,
            voltage: float,
            parsed_data : list,
            normalize_cell_names : bool,
            normalize_port_names : bool,
            sdf_timescale : str = "1ns"):
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
        normalize_cell_names
            When True enables normalization of cell and cell instance names
        normalize_cell_names
            When True enables normalization of port names
        '''

        # setup hooks that run different parsing functions based on current
        # entry
        parserhooks = {}

        parserhooks[("input", True)] = [cls.parsesetuphold]
        parserhooks[("input", False)] = [cls.parseiopath]
        parserhooks[("inout", True)] = [cls.parsesetuphold]
        parserhooks[("inout", False)] = [cls.parseiopath]
        parserhooks[("output", False)] = [cls.parseiopath]

        cls.normalize_cell_names = normalize_cell_names
        cls.normalize_port_names = normalize_port_names

        # extracts cell name and design name, ignore kfactor value
        headerparser = cls.headerparser

        # extracts pin name and value
        whenparser = re.compile("(?P<name>[a-zA-Z_][a-zA-Z_0-9]*(\[[0-9]*\])?)\s*==\s*1'b(?P<value>[0-1])(\s*&&)?")  # noqa: E501

        # we generate a design name from the first header
        header = parsed_data[0][0]
        if header.startswith('library'):
            design = "Unknown"
        else:
            parsedheader = headerparser.match(header)
            design = parsedheader.group('design')

        sdfparse.sdfyacc.header = {
                'date': date.today().strftime("%B %d, %Y"),
                'design': design,
                'sdfversion': '3.0',
                'voltage': {'avg': voltage, 'max': voltage, 'min': voltage}
                }

        cells = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))

        for ld in parsed_data:

            header = ld[0]
            lib_dict = ld[1]

            keys = [key for key in lib_dict.keys()]

            if len(keys) != 1 or not keys[0].startswith('library'):
                log('ERROR', 'JSON does not represent Liberty library')
                return None


            if header.startswith('library'):
                kfactor = 1.0
                design = "Unknown"
                instancenames = cellnames = [key.split()[1] for key in lib_dict[keys[0]].keys() if key.startswith("cell")]
                librarycontents = [lib_dict[keys[0]][cell] for cell in lib_dict[keys[0]].keys() if cell.startswith("cell")]
            else:
                # parse header
                parsedheader = headerparser.match(header)
                kfactor = float(parsedheader.group('kfactor'))
                design = parsedheader.group('design')
                # name of the cell
                cellnames = [parsedheader.group('cell')]
                librarycontents = [lib_dict[keys[0]]]
                instance = parsedheader.group('instance')
                if instance is None:
                    instance = parsedheader.group('cell')
                instancenames = [instance]

            # initialize Yacc dictionaries holding data
            sdfparse.init()

            for instancename, cellname, librarycontent in zip(instancenames, cellnames, librarycontents):
                # for all pins in the cell
                for objectname, obj in librarycontent.items():
                    objectname = objectname.split(' ', 1)[1]
                    direction = obj['direction']
                    # for all timing configurations in the cell
                    if 'timing ' in obj:
                        elementnametotiming = defaultdict(lambda: [])
                        for timing in (obj['timing ']
                                       if type(obj['timing ']) is list
                                       else [obj['timing ']]):
                            cname = cellname
                            if 'when' in timing:
                                if timing["when"] != "":
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
                                    cname += "_" + '_'.join(condlist)

                            # when the timing is defined for falling edge, add this
                            # info to cell name
                            if 'timing_type' in timing:
                                if 'falling' in timing['timing_type']:
                                    cname += "_{}_EQ_1".format(
                                            timing['timing_type'].upper())

                            # Normalize cell and instance names
                            if cls.normalize_cell_names:
                                cname = cls.normalize_name(cname)
                                instancename = cls.normalize_name(instancename)

                            # extract intrinsic_rise and intrinsic_fall in SDF-friendly
                            # format
                            rise, fall = cls.extract_delval(timing, kfactor)

                            # if timings are completely empty, skip the entry
                            if cls.is_delval_empty(rise) and cls.is_delval_empty(fall):
                                continue

                            # run all defined hooks for given timing entry
                            parserkey = cls.getparsekey(timing, direction)
                            for func in parserhooks[parserkey]:
                                element = func(rise, fall, objectname, timing)
                                if element is not None:
                                    # Merge duplicated entries
                                    elname = element["name"]
                                    if elname in cells[cname][instancename]:
                                        element = cls.merge_delays(
                                                cells[cname][instancename][elname],
                                                element)

                                    # memorize the timing entry responsible for given
                                    # SDF entry
                                    elementnametotiming[elname].append(timing)
                                    # add SDF entry
                                    if cls.normalize_cell_names:
                                        elname = cls.normalize_name(elname)                                    
                                    cells[cname][instancename][elname] = element

        # generate SDF file from dictionaries
        sdfparse.sdfyacc.cells = cells
        sdfparse.sdfyacc.timings = {
                "cells": sdfparse.sdfyacc.cells,
                "header": sdfparse.sdfyacc.header}

        sdffile = sdfwrite.emit_sdf(sdfparse.sdfyacc.timings, timescale=sdf_timescale)

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
            "--timescale",
            help="Timescale string (def. \"1ns\") NOT A MULTIPLIER",
            default="1ns",
            type=str)
    parser.add_argument(
            "--normalize-cell-names",
            action="store_true",
            help="Don't normalize cell and instance names (remove brackets)")
    parser.add_argument(
            "--normalize-port-names",
            action="store_true",
            help="Don't normalize port names (remove brackets)")
    parser.add_argument(
            "--log-suppress-below",
            help="The mininal not suppressed log level",
            type=str,
            default="ERROR",
            choices=log_printer.LOGLEVELS)

    args = parser.parse_args()

    log_printer.SUPPRESSBELOW = args.log_suppress_below

    # Load LIB file
    with open(args.input, 'r') as infile:
        libfile = infile.readlines()

	# remove empty lines and trailing whitespaces
    libfile = [line.rstrip() for line in libfile if line.strip()]
    # remove C/C++ style comments
    libfile = [line for line in libfile if not line.startswith('/*')]

    libfiles = []
    if libfile[0].startswith('library'):
        libfiles.append({
            "header": libfile[0],
            "data": libfile[1:]
        })
    else:
        # Split the file into individual cell definitions. First identify
        # split points which are cell headers. Add the last line index in order
        # to catch the last cell in the file.
        split_points = [i for i, line in enumerate(libfile) if \
            JSONToSDFParser.headerparser.match(line) is not None]
        split_points.append(len(libfile))
        # Now split the input lib file, preserve headers
        for i in range(len(split_points)-1):
            l0 = split_points[i]
            l1 = split_points[i+1]
            libfiles.append({
                "header": libfile[l0],
                "data":   libfile[l0+1:l1]
            })

    # Parse each one
    parsed_data = []
    result = ""
    for data in libfiles:
        data["data"][0] = r'library \({}\) {}'.format(
                            data["header"].replace(' ', '_').replace('.', '_').replace('"', ''), '{')
        data["data"] = ['{\n'] + data["data"] + ['}']
        timing_dict = LibertyToJSONParser.load_timing_info_from_lib(data["data"])
        parsed_data.append((data["header"], timing_dict))

    result += JSONToSDFParser.export_sdf_from_lib_dict(
            args.voltage,
            parsed_data,
            args.normalize_cell_names,
            args.normalize_port_names,
            args.timescale,
            )

    #FIXME: reenable sanity check
	# ----------------------------------------------
    #with open("/tmp/pd.json", 'w') as fp:
    #    json.dump(parsed_data, fp, indent=4)

    #libkey = [key for key in timingdict.keys()][0]

    ## sanity checking and duplicate entry handling
    #for key, value in timingdict[libkey].items():
    #    if type(value) is list:
    #        finalentry = dict()
    #        for k in sorted(list(
    #                set([key for elements in value for key in elements]))):
    #            first = True
    #            val = None
    #            for duplicate in value:
    #                if k in duplicate:
    #                    if first:
    #                        val = duplicate[k]
    #                        first = False
    #                    assert duplicate[k] == val, \
    #                        "ERROR: entries for {} have different" \
    #                        "values for parameter {}: {} != {}".format(
    #                                key,
    #                                k,
    #                                val,
    #                                duplicate[k])
    #            finalentry[k] = val
    #        timingdict[libkey][key] = finalentry

    #args.json_output = "/tmp/dump.json"
    #if args.json_output:
    #    with open(args.json_output, 'w') as out:
    #        json.dump(parsed_data, out, indent=4)

    #result = JSONToSDFParser.export_sdf_from_lib_dict(
    #        header,
    #        args.voltage,
    #        timingdict)

    with open(args.output, 'w') as out:
        out.write(result)


if __name__ == "__main__":
    main()
