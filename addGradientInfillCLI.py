#!/usr/bin/env python3
"""
CLI for Gradient Infill for 3D prints by Stefan Hermann - CNC Kitchen.

License: MIT
Version: 1.0
"""

__version__ = 1.0

import argparse
import os.path
from addGradientInfill import process_gcode, InfillType, MIN_FLOW, MAX_FLOW, GRADIENT_THICKNESS, GRADIENT_DISCRETIZATION

SCRIPT_DESCRIPTION = (
    "This script allows adding gradient infill to a gcode file produced by Cura slicer.\n"
    "\tRequires input file to have been created with the following settings:\n"
    "\t\tInfill Before Walls: OFF,\n"
    "\t\tRelative Extrusion: ON (under Special Modes)."
)

INFILL_TYPE_HELP = (
    "The infill method used to create the input gcode.\n"
    "Set 1 or \"SMALL_SEGMENTS\" for an infill method with small segments like honeycomb or gyroid.\n"
    "Set 2 or \"LINEAR\" for linear infill like rectilinear or triangles. Default: SMALL_SEGMENTS"
)

GRADIENT_DISCRETIZATION_HELP = (
    "only applicable for linear infills; number of segments within the gradient"
    "(segmentLength=gradientThickness / gradientDiscretization); use sensible values to not "
    "overload the printer. Default {0}".format(GRADIENT_DISCRETIZATION)
)


def arg_to_infill_type(arg: str) -> InfillType:
    """Check that the user-provided infill type is valid and return the corresponding Enum value.

    Args:
        arg (str): user-provided command-line argument

    Raises:
        argparse.ArgumentTypeError: when an illegal value is passed

    Returns:
        InfillType: a valid infill type
    """
    for infill_type in InfillType:
        if arg in (infill_type.name, str(infill_type.value)):
            return infill_type
    raise argparse.ArgumentTypeError("Illegal infill type: ", arg)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="GradientInfillCLI", description=SCRIPT_DESCRIPTION)
    parser.add_argument(
        "-i", "--input", type=argparse.FileType('r'), required=True, help="Path to the input gcode file"
    )
    parser.add_argument(
        "-o",
        "--output",
        type=argparse.FileType('w+'),
        required=False,
        help="Path to the output gcode file to be created",
    )
    parser.add_argument(
        "--infill_type",
        type=arg_to_infill_type,
        required=False,
        help=INFILL_TYPE_HELP,
        default=InfillType.SMALL_SEGMENTS.name,
    )
    parser.add_argument(
        "--min_flow",
        type=int,
        required=False,
        default=MIN_FLOW,
        help="minimum extrusion flow, default {0}".format(MIN_FLOW),
    )
    parser.add_argument(
        "--max_flow",
        type=int,
        required=False,
        default=MAX_FLOW,
        help="maximum extrusion flow, default {0}".format(MAX_FLOW),
    )
    parser.add_argument(
        "--thickness",
        type=int,
        required=False,
        default=GRADIENT_THICKNESS,
        help="thickness of the gradient (max to min) in mm, default {0}".format(GRADIENT_THICKNESS),
    )
    parser.add_argument(
        "--discretization", type=int, required=False, default=GRADIENT_DISCRETIZATION, help=GRADIENT_DISCRETIZATION_HELP
    )
    args = parser.parse_args()

    input_path = args.input.name

    if args.output is None:
        head, ext = os.path.splitext(input_path)
        if ext == "":
            ext = ".gcode"
        output_path = "{0}_infill_gradient{1}".format(head, ext)
    else:
        output_path = args.output.name

    process_gcode(
        input_path, output_path, args.infill_type, args.max_flow, args.min_flow, args.thickness, args.discretization
    )
