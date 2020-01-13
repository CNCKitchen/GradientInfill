#!/usr/bin/env python3
"""
Gradient Infill for 3D prints

License: MIT
Author: Stefan Hermann - CNC Kitchen
Version: 1.0
"""

import re
from enum import Enum
from collections import namedtuple


class InfillType(Enum):
    SMALL_SEGMENTS = 1  # infill with small segments like honeycomb or gyroid
    LINEAR = 2          # linear infill like rectilinear or triangles

    
Point2D = namedtuple('Point2D', 'x y')
Segment = namedtuple('Segment', 'point1 point2')

# EDIT this section for your creation parameters

INPUT_FILE_NAME = "cloverleaf_wHole_gyroid.gcode"
OUTPUT_FILE_NAME = "BOWDEN_cloverleaf_wHole_gyroid.gcode"

INFILL_TYPE = InfillType.SMALL_SEGMENTS

MAX_FLOW = 350               # maximum extrusion flow
MIN_FLOW = 50                # minimum extrusion flow
GRADIENT_THICKNESS = 6       # thickness of the gradient (max to min) in mm
GRADIENT_DISCRETIZATION = 4  # only applicable for linear infills; number of segments within the
                             # gradient( segmentLength=gradientThickness/gradientDiscretization);
                             # use sensible values to not overload the printer

# End edit


class Section(Enum):
    NOTHING = 0
    INNER_WALL = 1
    INFILL = 2


def dist(segment, point):
    """
    Calculate the distance from a point to a line with finite length
    """
    px = segment.point2.x - segment.point1.x
    py = segment.point2.y - segment.point1.y
    norm = px * px + py * py
    u = ((point.x - segment.point1.x) * px + (point.y - segment.point1.y) * py) / float(norm)
    if u > 1:
        u = 1
    elif u < 0:
        u = 0
    x = segment.point1.x + u * px
    y = segment.point1.y + u * py
    dx = x - point.x
    dy = y - point.y

    return (dx * dx + dy * dy) ** .5


def get_points_distance(point1, point2):
    return ((point1.x - point2.x) ** 2 + (point1.y - point2.y) ** 2) ** 0.5


def min_distance_from_segment(segment, segments):
    middlePoint = Point2D((segment.point1.x + segment.point2.x) / 2, (segment.point1.y + segment.point2.y) / 2)

    return min(dist(s, middlePoint) for s in segments)


def getXY(currentLine):
    """
    Returns the X and Y value of the current line
    """
    elementX = re.search(r"X(\d*\.?\d*)", currentLine).group(1)
    elementY = re.search(r"Y(\d*\.?\d*)", currentLine).group(1)

    return Point2D(float(elementX), float(elementY))


def mapRange(a, b, s):
    (a1, a2), (b1, b2) = a, b

    return b1 + ((s - a1) * (b2 - b1) / (a2 - a1))


def get_extrusion_command(x, y, extrusion):
    # with python 3.6+ you can write that as a format string:
    # return f"G1 X{ round(x, 3) } Y{ round(y, 3) } E{ round(extrusion, 5) }\n"
    return "G1 X{} Y{} E{}\n".format(round(x, 3), round(y, 3), round(extrusion, 5))


def is_begin_layer_line(line):
    return line.startswith(";LAYER:")


def is_begin_inner_wall_line(line):
    return line.startswith(";TYPE:WALL-INNER")


def is_end_inner_wall_line(line):
    return line.startswith(";TYPE:WALL-OUTER")


def is_extrusion_line(line):
    return "G1" in line and " X" in line and "Y" in line and "E" in line


def is_begin_infill_segment_line(line):
    return line.startswith(";TYPE:FILL")


def process_gcode(input_file_name, output_file_name, infill_type, max_flow, min_flow, gradient_thickness,
                  gradient_discretization):
    currentSection = Section.NOTHING
    lastPosition = Point2D(-10000, -10000)
    gradientDiscretizationLength = gradient_thickness / gradient_discretization

    with open(input_file_name, "r") as gcodeFile, open(output_file_name, "w+") as outputFile:
        for currentLine in gcodeFile:
            writtenToFile = 0
            if is_begin_layer_line(currentLine):
                perimeterSegments = []

            if is_begin_inner_wall_line(currentLine):
                currentSection = Section.INNER_WALL

            if currentSection == Section.INNER_WALL and is_extrusion_line(currentLine):
                perimeterSegments.append(Segment(getXY(currentLine), lastPosition))

            if is_end_inner_wall_line(currentLine):
                currentSection = Section.NOTHING

            if is_begin_infill_segment_line(currentLine):
                currentSection = Section.INFILL
                outputFile.write(currentLine)
                continue

            if currentSection == Section.INFILL:
                if "F" in currentLine and "G1" in currentLine:
                    # python3.6+ f-string variant:
                    # outputFile.write("G1 F{ re.search(r"F(\d*\.?\d*)", currentLine).group(1)) }\n"
                    outputFile.write("G1 F{}\n".format(re.search(r"F(\d*\.?\d*)", currentLine).group(1)))
                if "E" in currentLine and "G1" in currentLine and " X" in currentLine and "Y" in currentLine:
                    currentPosition = getXY(currentLine)
                    splitLine = currentLine.split(" ")

                    if infill_type == InfillType.LINEAR:
                        # find extrusion length
                        for element in splitLine:
                            if "E" in element:
                                extrusionLength = float(element[1:len(element)])
                        segmentLength = get_points_distance(lastPosition, currentPosition)
                        segmentSteps = segmentLength / gradientDiscretizationLength
                        extrusionLengthPerSegment = extrusionLength / segmentSteps
                        segmentDirection = Point2D(
                            (currentPosition.x - lastPosition.x) / segmentLength * gradientDiscretizationLength,
                            (currentPosition.y - lastPosition.y) / segmentLength * gradientDiscretizationLength
                        )
                        if segmentSteps >= 2:
                            for step in range(int(segmentSteps)):
                                segmentEnd = Point2D(
                                    lastPosition.x + segmentDirection.x,
                                    lastPosition.y + segmentDirection.y
                                )
                                shortestDistance = min_distance_from_segment(
                                    Segment(lastPosition, segmentEnd), perimeterSegments
                                )
                                if shortestDistance < gradient_thickness:
                                    segmentExtrusion = extrusionLengthPerSegment * mapRange(
                                        (0, gradient_thickness),
                                        (max_flow / 100, min_flow / 100),
                                        shortestDistance
                                    )
                                else:
                                    segmentExtrusion = extrusionLengthPerSegment * min_flow / 100

                                outputFile.write(get_extrusion_command(segmentEnd.x, segmentEnd.y, segmentExtrusion))

                                lastPosition = segmentEnd
                            # MissingSegment
                            segmentLengthRatio = get_points_distance(lastPosition, currentPosition) / segmentLength

                            outputFile.write(get_extrusion_command(
                                currentPosition.x,
                                currentPosition.y,
                                segmentLengthRatio * extrusionLength * max_flow / 100
                            ))
                        else:
                            outPutLine = ""
                            for element in splitLine:
                                if "E" in element:
                                    outPutLine = outPutLine + "E" + str(round(extrusionLength * max_flow / 100, 5))
                                else:
                                    outPutLine = outPutLine + element + " "
                            outPutLine = outPutLine + "\n"
                            outputFile.write(outPutLine)
                        writtenToFile = 1

                    # gyroid or honeycomb
                    if infill_type == InfillType.SMALL_SEGMENTS:
                        shortestDistance = min_distance_from_segment(
                            Segment(lastPosition, currentPosition),
                            perimeterSegments
                        )

                        outPutLine = ""
                        if shortestDistance < gradient_thickness:
                            for element in splitLine:
                                if "E" in element:
                                    newE = float(element[1:len(element)]) * mapRange((0, gradient_thickness), (max_flow / 100, min_flow / 100), shortestDistance)
                                    outPutLine = outPutLine + "E" + str(round(newE, 5))
                                else:
                                    outPutLine = outPutLine + element + " "
                            outPutLine = outPutLine + "\n"
                            outputFile.write(outPutLine)
                            writtenToFile = 1
                if ";" in currentLine:
                    currentSection = Section.NOTHING

            # line with move
            if " X" in currentLine and " Y" in currentLine and ("G1" in currentLine or "G0" in currentLine):
                lastPosition = getXY(currentLine)

            # write uneditedLine
            if writtenToFile == 0:
                outputFile.write(currentLine)


if __name__ == '__main__':
    process_gcode(INPUT_FILE_NAME, OUTPUT_FILE_NAME, INFILL_TYPE, MAX_FLOW, MIN_FLOW, GRADIENT_THICKNESS,
                  GRADIENT_DISCRETIZATION)
