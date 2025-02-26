# fuzzer-swen331-02-dtm5568

## Fuzzer

## Description
An exploratory testing tool used for finding weaknesses in a program by scanning its attack surface.

## Installation
.gitlab-ci.yml file defines all required installation steps. To run standalone from CI,
install requirements with `py -m pip install -r requirements.txt` in the root directory. The
main external dependency for this project is mechanicalsoup for automating programmatic page interaction.

## Usage
Used to discover and test the exploitability of page inputs given a url to explore. The discovery
will stay within the given host url domain, and attempt to find all possible sub-pages,
while the testing will perform discovery, then attempt to attack all found inputs with
a given list of attack vectors.

## Authors and acknowledgment
Author: Dylan Mulligan