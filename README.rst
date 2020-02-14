Importer of timing data from Quicklogic EOS-S3 to SDF
=====================================================

Files containing timing information for EOS-S3 are written in Liberty format (LIB files).
The Symbiflow accepts SDF (Standard Delay Format) format for timings.
This repository contains set of functions for processing Liberty files and converting them to SDF format.

Installation
------------

To install the `quicklogic_timings_importer`, run::

    sudo pip3 install git+https://github.com/antmicro/quicklogic-timings-importer.git

Simple usage
------------

To convert a single LIB file to SDF format, run::

    quicklogic_timings_importer input.lib output.sdf

For more settings you can check script's help::

    quicklogic_timings_importer -h
