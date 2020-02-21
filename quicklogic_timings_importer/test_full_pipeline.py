#!/usr/bin/env python3

from liberty_to_json import LibertyToJSONParser
from json_to_liberty import JSONToLibertyWriter
import json
import log_printer
from pathlib import Path
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
            "inputlist",
            help="File containing list of absolute " + \
                 "paths to test Liberty files",
            type=Path)
    parser.add_argument(
            "--output-json-root-dir",
            help="Optional directory to store generated JSON files",
            type=Path)
    parser.add_argument(
            "--output-lib-root-dir",
            help="Optional directory to store generated Liberty files",
            type=Path)
    parser.add_argument(
            "--log-suppress-below",
            help="The mininal not suppressed log level",
            type=str,
            default="ERROR",
            choices=log_printer.LOGLEVELS)

    args = parser.parse_args()

    log_printer.SUPPRESSBELOW = args.log_suppress_below

    with open(args.inputlist, 'r') as liblistfile:
       liblist = [Path(path.strip()) for path in liblistfile.readlines() if path not in ignorelist]

    liblist = sorted(liblist)

    numfailed = {
            "lib-to-json": 0,
            "json-to-lib": 0,
            "newlib-to-json": 0,
            "comparison": 0}

    numskipped = {
            "lib-to-json": 0,
            "json-to-lib": 0,
            "newlib-to-json": 0,
            "comparison": 0}

    filenum = 0
    numfiles = len(liblist)

    for libname in liblist:
        filenum += 1
        namecore = Path(str(libname.parent)[1:]) / libname.stem
        print('[{:04d}/{:04d},lj={:04d},jn={:04d},nj={:04d},jj={:04d}] Processing {}'.format(
            filenum,
            numfiles,
            numfailed['lib-to-json'],
            numfailed['json-to-lib'],
            numfailed['newlib-to-json'],
            numfailed['comparison'],
            libname))
        with open(libname, 'r') as libfile:
            inputliberty = libfile.readlines()
        inputliberty = ['{\n'] + inputliberty + ['}']
        jsondict = {}
        # try parsing LIB file
        try:
            jsondict = LibertyToJSONParser.load_timing_info_from_lib(inputliberty)
            if args.output_json_root_dir:
                targetfile = Path(str(args.output_json_root_dir / namecore) + '.json')
                targetfile.parent.mkdir(parents=True, exist_ok=True)
                with open(targetfile, 'w') as out:
                    json.dump(jsondict, out, indent=2)
            log_printer.log('INFO', ' lib-to-json: {}'.format(libname))
        except Exception as ex:
            log_printer.log('ERROR', 'lib-to-json:  {} | {}'.format(type(ex).__name__, libname))
            numfailed['lib-to-json'] += 1
            numskipped['json-to-lib'] += 1
            numskipped['newlib-to-json'] += 1
            numskipped['comparison'] += 1
            continue
        # try converting it back to LIB
        liblines = []
        try:
            liblines = JSONToLibertyWriter.convert_json_to_liberty(jsondict)
            if args.output_lib_root_dir:
                targetfile = Path(str(args.output_lib_root_dir / namecore) + '.lib')
                targetfile.parent.mkdir(parents=True, exist_ok=True)
                with open(targetfile, 'w') as out:
                    out.write('\n'.join(liblines))
            log_printer.log('INFO', ' json-to-lib: {}'.format(libname))
        except Exception as ex:
            log_printer.log('ERROR', 'json-to-lib:  {} | {}'.format(type(ex).__name__, libname))
            numfailed['json-to-lib'] += 1
            numskipped['newlib-to-json'] += 1
            numskipped['comparison'] += 1
            continue
        # convert generated LIB back to JSON and compare the results
        newjson = {}
        try:
            newjson = LibertyToJSONParser.load_timing_info_from_lib(inputliberty)
            if args.output_json_root_dir:
                targetfile = Path(str(args.output_json_root_dir / namecore) + '-new.json')
                targetfile.parent.mkdir(parents=True, exist_ok=True)
                with open(targetfile, 'w') as out:
                    json.dump(newjson, out, indent=2)
            log_printer.log('INFO', ' newlib-to-json: {}'.format(libname))
        except Exception as ex:
            log_printer.log('ERROR', 'newlib-to-json:  {} | {}'.format(type(ex).__name__, libname))
            numfailed['newlib-to-json'] += 1
            numskipped['comparison'] += 1
            continue
        if jsondict == newjson:
            log_printer.log('INFO', ' comparison: {}'.format(libname))
        else:
            log_printer.log('ERROR', 'comparison:  {} | {}'.format(type(ex).__name__, libname))
            numfailed['comparison'] += 1

    for key in numfailed.keys():
        print('{}:  {} out of {} failed ({}% succeded, out of which {} were skipped)'.format(
            key, numfailed[key], numfiles, 100.0 * (numfiles - numfailed[key]) / numfiles, numskipped[key]))

if __name__ == '__main__':
    main()
