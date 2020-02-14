import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="quicklogic_timings_importer",
    version="0.0.1",
    packages=setuptools.find_packages(),
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Antmicro Ltd.",
    author_email="contact@antmicro.com",
    entry_points={
        'console_scripts': ['quicklogic_timings_importer=quicklogic_timings_importer.quicklogic_timings_importer:main']  # noqa: E501
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
    ],
)
