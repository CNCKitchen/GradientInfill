# GradientInfill
"""
Gradient Infill for 3D prints.

License: MIT
Author: Stefan Hermann - CNC Kitchen
Version: 1.0

5axes modification : 19/01/2020  -> Transform into a Cura Postprocessing PlugIn Script
5axes modification : 21/01/2020  -> Connect Infill Lines mode not supported
5axes modification : 22/01/2020  -> Add dedicate flow for short distance
5axes modification : 22/01/2020  -> Add gradiant speed
5axes modification : 23/01/2020  -> Test param infill_before_walls to false
5axes modification : 23/01/2020  -> Option to test with Inner Wall or Outer Wall  

"""

from ..Script import Script
from UM.Logger import Logger
from UM.Application import Application
import re #To perform the search
from cura.Settings.ExtruderManager import ExtruderManager
from collections import namedtuple
from enum import Enum
from typing import List, Tuple
from UM.Message import Message
from UM.i18n import i18nCatalog
catalog = i18nCatalog("cura")

__version__ = '1.5'


Point2D = namedtuple('Point2D', 'x y')
Segment = namedtuple('Segment', 'point1 point2')


# MAX_FLOW = 350.0  # maximum extrusion flow
# MIN_FLOW = 50.0  # minimum extrusion flow
# GRADIENT_THICKNESS = 6.0  # thickness of the gradient (max to min) in mm
# GRADIENT_DISCRETIZATION = 4.0  # only applicable for linear infills; number of segments within the
# gradient(segmentLength=gradientThickness / gradientDiscretization); use sensible values to not overload the printer


class Infill(Enum):
    """Enum for infill type."""

    SMALL_SEGMENTS = 1  # infill with small segments like gyroid
    LINEAR = 2  # linear infill like rectilinear or triangles

class Section(Enum):
    """Enum for section type."""

    NOTHING = 0
    INNER_WALL = 1
    OUTER_WALL = 2
    INFILL = 3


def dist(segment: Segment, point: Point2D) -> float:
    """Calculate the distance from a point to a line with finite length.

    Args:
        segment (Segment): line used for distance calculation
        point (Point2D): point used for distance calculation

    Returns:
        float: distance between ``segment`` and ``point``
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

    return (dx * dx + dy * dy) ** 0.5


def get_points_distance(point1: Point2D, point2: Point2D) -> float:
    """Calculate the euclidean distance between two points.

    Args:
        point1 (Point2D): first point
        point2 (Point2D): second point

    Returns:
        float: euclidean distance between the points
    """
    return ((point1.x - point2.x) ** 2 + (point1.y - point2.y) ** 2) ** 0.5


def min_distance_from_segment(segment: Segment, segments: List[Segment]) -> float:
    """Calculate the minimum distance from the midpoint of ``segment`` to the nearest segment in ``segments``.

    Args:
        segment (Segment): segment to use for midpoint calculation
        segments (List[Segment]): segments list

    Returns:
        float: the smallest distance from the midpoint of ``segment`` to the nearest segment in the list
    """
    middlePoint = Point2D((segment.point1.x + segment.point2.x) / 2, (segment.point1.y + segment.point2.y) / 2)

    return min(dist(s, middlePoint) for s in segments)


def getXY(currentLine: str) -> Point2D:
    """Create a ``Point2D`` object from a gcode line.

    Args:
        currentLine (str): gcode line

    Raises:
        SyntaxError: when the regular expressions cannot find the relevant coordinates in the gcode

    Returns:
        Point2D: the parsed coordinates
    """
    searchX = re.search(r"X(\d*\.?\d*)", currentLine)
    searchY = re.search(r"Y(\d*\.?\d*)", currentLine)
    if searchX and searchY:
        elementX = searchX.group(1)
        elementY = searchY.group(1)
    else:
        raise SyntaxError('Gcode file parsing error for line {currentLine}')

    return Point2D(float(elementX), float(elementY))


def mapRange(a: Tuple[float, float], b: Tuple[float, float], s: float) -> float:
    """Calculate a multiplier for the extrusion value from the distance to the perimeter.

    Args:
        a (Tuple[float, float]): a tuple containing:
            - a1 (float): the minimum distance to the perimeter (always zero at the moment)
            - a2 (float): the maximum distance to the perimeter where the interpolation is performed
        b (Tuple[float, float]): a tuple containing:
            - b1 (float): the maximum flow as a fraction
            - b2 (float): the minimum flow as a fraction
        s (float): the euclidean distance from the middle of a segment to the nearest perimeter

    Returns:
        float: a multiplier for the modified extrusion value
    """
    (a1, a2), (b1, b2) = a, b

    return b1 + ((s - a1) * (b2 - b1) / (a2 - a1))


def get_extrusion_command(x: float, y: float, extrusion: float) -> str:
    """Format a gcode string from the X, Y coordinates and extrusion value.

    Args:
        x (float): X coordinate
        y (float): Y coordinate
        extrusion (float): Extrusion value

    Returns:
        str: Gcode line
    """
    return "G1 X{} Y{} E{}".format(round(x, 3), round(y, 3), round(extrusion, 5))


def is_begin_layer_line(line: str) -> bool:
    """Check if current line is the start of a layer section.

    Args:
        line (str): Gcode line

    Returns:
        bool: True if the line is the start of a layer section
    """
    return line.startswith(";LAYER:")


def is_begin_inner_wall_line(line: str) -> bool:
    """Check if current line is the start of an inner wall section.

    Args:
        line (str): Gcode line

    Returns:
        bool: True if the line is the start of an inner wall section
    """
    return line.startswith(";TYPE:WALL-INNER")


def is_begin_outer_wall_line(line: str) -> bool:
    """Check if current line is the start of an outer wall section.

    Args:
        line (str): Gcode line

    Returns:
        bool: True if the line is the start of an outer wall section
    """
    return line.startswith(";TYPE:WALL-OUTER")


def is_extrusion_line(line: str) -> bool:
    """Check if current line is a standard printing segment.

    Args:
        line (str): Gcode line

    Returns:
        bool: True if the line is a standard printing segment
    """
    return "G1" in line and " X" in line and "Y" in line and "E" in line


def is_begin_infill_segment_line(line: str) -> bool:
    """Check if current line is the start of an infill.

    Args:
        line (str): Gcode line

    Returns:
        bool: True if the line is the start of an infill section
    """
    return line.startswith(";TYPE:FILL")


def mfill_mode(Mode):
    """Definie the type of Infill pattern

       linear infill like rectilinear or triangles = 2
       infill with small segments like gyroid = 1

    Args:
        line (Mode): Infill Pattern

    Returns:
        Int: the Type of infill pattern
    """
    iMode=0
    if Mode == 'grid':
        iMode=2
    if Mode == 'lines':
        iMode=2
    if Mode == 'triangles':
        iMode=2
    if Mode == 'trihexagon':
        iMode=2
    if Mode == 'cubic':
        iMode=2
    if Mode == 'cubicsubdiv':
        iMode=0
    if Mode == 'tetrahedral':
        iMode=2
    if Mode == 'quarter_cubic':
        iMode=2
    if Mode == 'concentric':
        iMode=0
    if Mode == 'zigzag':
        iMode=0
    if Mode == 'cross':
        iMode=1
    if Mode == 'cross_3d':
        iMode=1
    if Mode == 'gyroid':
        iMode=1

    return iMode
        
class GradientInfill(Script):
    def getSettingDataString(self):
        return """{
            "name": "Gradient Infill",
            "key": "GradientInfill",
            "metadata": {},
            "version": 2,
            "settings":
            {
                "gradientthickness":
                {
                    "label": "Gradient Distance",
                    "description": "Distance of the gradient (max to min) in mm",
                    "unit": "mm",
                    "type": "float",
                    "default_value": 6.0,
                    "minimum_value": 1.0,
                    "minimum_value_warning": 2.0
                },
                "gradientdiscretization":
                {
                    "label": "Gradient Discretization",
                    "description": "Only applicable for linear infills; number of segments within the gradient(segmentLength=gradientThickness / gradientDiscretization); use sensible values to not overload",
                    "type": "int",
                    "default_value": 4,
                    "minimum_value": 1,
                    "minimum_value_warning": 2
                },
                "maxflow":
                {
                    "label": "Max flow",
                    "description": "Maximum extrusion flow",
                    "unit": "%",
                    "type": "int",
                    "default_value": 350,
                    "minimum_value": 100
                },
                "minflow":
                {
                    "label": "Min flow",
                    "description": "Minimum extrusion flow",
                    "unit": "%",
                    "type": "int",
                    "default_value": 50,
                    "minimum_value": 0,
                    "maximum_value": 100,
                    "minimum_value_warning": 10,
                    "maximum_value_warning": 90
                },
                "shortdistflow":
                {
                    "label": "Short distance flow",
                    "description": "Extrusion flow for short distance < 2x Gradient distance",
                    "unit": "%",
                    "type": "int",
                    "value": "math.floor(maxflow)", 
                    "minimum_value": 100
                },
                "gradualspeed":
                {
                    "label": "Gradual speed",
                    "description": "Activate also Gradual Speed linked to the gradual flow",
                    "type": "bool",
                    "default_value": false
                },
                "maxoverspeed":
                {
                    "label": "Max over speed",
                    "description": "Maximum over speed factor",
                    "unit": "%",
                    "type": "int",
                    "default_value": 200,
                    "enabled": "gradualspeed"
                },
                "minoverspeed":
                {
                    "label": "Min over speed",
                    "description": "Minimum over speed factor",
                    "unit": "%",
                    "type": "int",
                    "default_value": 60,
                    "enabled": "gradualspeed"
                }, 
                "extruder_nb":
                {
                    "label": "Extruder Id",
                    "description": "Define extruder Id in case of multi extruders",
                    "unit": "",
                    "type": "int",
                    "default_value": 1
                },
                "testouterwall":
                {
                    "label": "Test with outer wall",
                    "description": "Test the gradiant with the outer wall segments",
                    "type": "bool",
                    "default_value": false
                }
            }
        }"""


## -----------------------------------------------------------------------------
#
#  Main Prog
#
## -----------------------------------------------------------------------------

    def execute(self, data):

        gradient_discretization = float(self.getSettingValueByKey("gradientdiscretization"))
        max_flow = float(self.getSettingValueByKey("maxflow"))
        min_flow = float(self.getSettingValueByKey("minflow"))
        link_flow = float(self.getSettingValueByKey("shortdistflow"))
        gradient_thickness = float(self.getSettingValueByKey("gradientthickness"))
        extruder_id  = self.getSettingValueByKey("extruder_nb")
        extruder_id = extruder_id -1
        gradual_speed= bool(self.getSettingValueByKey("gradualspeed"))
        max_over_speed_factor = float(self.getSettingValueByKey("maxoverspeed"))
        max_over_speed_factor = max_over_speed_factor /100
        min_over_speed_factor = float(self.getSettingValueByKey("minoverspeed"))
        min_over_speed_factor = min_over_speed_factor /100

        test_outer_wall= bool(self.getSettingValueByKey("testouterwall"))
        

        
        
        #   machine_extruder_count
        extruder_count=Application.getInstance().getGlobalContainerStack().getProperty("machine_extruder_count", "value")
        extruder_count = extruder_count-1
        if extruder_id>extruder_count :
            extruder_id=extruder_count

        # Deprecation function
        # extrud = list(Application.getInstance().getGlobalContainerStack().extruders.values())
        extrud = Application.getInstance().getGlobalContainerStack().extruderList
 
        infillpattern = extrud[extruder_id].getProperty("infill_pattern", "value")
        connectinfill = extrud[extruder_id].getProperty("zig_zaggify_infill", "value")
        
        relativeextrusion = extrud[extruder_id].getProperty("relative_extrusion", "value")
        link = extrud[extruder_id].getProperty("relative_extrusion", "value")
        if relativeextrusion == False:
            #
            Logger.log('d', 'Gcode must be generate in relative extrusion mode')
            Message('Gcode must be generate in relative extrusion mode', title = catalog.i18nc("@info:title", "Post Processing")).show()
            return None

        # Note : Walls are used to define the boundary of the infill segment and detect if the point are in the 'Gradiant' area
        infillbeforewalls = extrud[extruder_id].getProperty("infill_before_walls", "value")
        if infillbeforewalls == True:
            #
            Logger.log('d', 'Gcode must be generate with the mode infill_before_walls to off')
            Message('It is important to make sure that the Walls are printed before the Infill (Infill before Walls must be set to  OFF)', title = catalog.i18nc("@info:title", "Post Processing")).show()
            return None
        
        """Parse Gcode and modify infill portions with an extrusion width gradient."""
        currentSection = Section.NOTHING
        lastPosition = Point2D(-10000, -10000)
        gradientDiscretizationLength = gradient_thickness / gradient_discretization

        infill_type=mfill_mode(infillpattern)
        if infill_type == 0:
            #
            Logger.log('d', 'Infill Pattern not supported : ' + infillpattern)
            Message('Infill Pattern not supported : ' + infillpattern , title = catalog.i18nc("@info:title", "Post Processing")).show()

            return None

        if connectinfill == True:
            #
            Logger.log('d', 'Connect Infill Lines no supported')
            Message('Gcode must be generate without Connect Infill Lines mode activated' , title = catalog.i18nc("@info:title", "Post Processing")).show()
            return None      

        Logger.log('d',  "GradientFill Param : " + str(gradientDiscretizationLength) + "/" + str(max_flow) + "/" + str(min_flow) + "/" + str(gradient_discretization)+ "/" + str(gradient_thickness) )
        Logger.log('d',  "Pattern Param : " + infillpattern + "/" + str(infill_type) )

        for layer in data:
            layer_index = data.index(layer)
            lines = layer.split("\n")
            for currentLine in lines:
                new_Line=""
                stringFeed = ""
                line_index = lines.index(currentLine)
                
                if is_begin_layer_line(currentLine):
                    perimeterSegments = []
                    
                if is_begin_inner_wall_line(currentLine):
                    currentSection = Section.INNER_WALL
                    # Logger.log('d', 'is_begin_inner_wall_line'  )

                if is_begin_outer_wall_line(currentLine):
                    currentSection = Section.OUTER_WALL
                    # Logger.log('d', 'is_begin_outer_wall_line' )

                if currentSection == Section.INNER_WALL and test_outer_wall == False:
                    if is_extrusion_line(currentLine):
                        perimeterSegments.append(Segment(getXY(currentLine), lastPosition))

                if currentSection == Section.OUTER_WALL and test_outer_wall == True:
                    if is_extrusion_line(currentLine):
                        perimeterSegments.append(Segment(getXY(currentLine), lastPosition))

                if is_begin_infill_segment_line(currentLine):
                    # Log Size of perimeterSegments for debuging
                    Logger.log('d', 'PerimeterSegments seg : {}'.format(len(perimeterSegments)))
                    currentSection = Section.INFILL
                    # ! Important 
                    continue

                if currentSection == Section.INFILL:
                    if "F" in currentLine and "G1" in currentLine:
                        searchSpeed = re.search(r"F(\d*\.?\d*)", currentLine)
                        
                        if searchSpeed:
                            current_feed=float(searchSpeed.group(1))
                            new_Line="G1 F{}\n".format(current_feed)
                        else:
                            Logger.log('d', 'Gcode file parsing error for line : ' + currentLine )

                    if "E" in currentLine and "G1" in currentLine and "X" in currentLine and "Y" in currentLine:
                        currentPosition = getXY(currentLine)
                        splitLine = currentLine.split(" ")
                        
                        # if infill_type == Infill.LINEAR:  
                        if infill_type == 2:
                            # find extrusion length
                            for element in splitLine:
                                if "E" in element:
                                    extrusionLength = float(element[1:])

                            segmentLength = get_points_distance(lastPosition, currentPosition)
                            segmentSteps = segmentLength / gradientDiscretizationLength
                            extrusionLengthPerSegment = extrusionLength / segmentSteps
                            segmentDirection = Point2D((currentPosition.x - lastPosition.x) / segmentLength * gradientDiscretizationLength,(currentPosition.y - lastPosition.y) / segmentLength * gradientDiscretizationLength)
 
                            if segmentSteps >= 2:
                                # new_Line=new_Line+"; GradientInfill segmentSteps >= 2\n"
                                for step in range(int(segmentSteps)):
                                    segmentEnd = Point2D(lastPosition.x + segmentDirection.x, lastPosition.y + segmentDirection.y)
                                    shortestDistance = min_distance_from_segment(Segment(lastPosition, segmentEnd), perimeterSegments)
                                    if shortestDistance < gradient_thickness:
                                        segmentExtrusion = extrusionLengthPerSegment * mapRange((0, gradient_thickness), (max_flow / 100, min_flow / 100), shortestDistance)
                                        segmentFeed = current_feed / mapRange((0, gradient_thickness), (max_flow / 100, min_flow / 100), shortestDistance)
    
                                        if gradual_speed:
                                            if segmentFeed > (current_feed * max_over_speed_factor):
                                                segmentFeed = current_feed * max_over_speed_factor
                                            if segmentFeed < (current_feed * min_over_speed_factor):
                                                segmentFeed = current_feed * min_over_speed_factor
                                            stringFeed = " F{}".format(int(segmentFeed))

                                    else:
                                        segmentExtrusion = extrusionLengthPerSegment * min_flow / 100
                                        if min_flow>0:
                                            segmentFeed = current_feed / (min_flow / 100)
                                        else:
                                            segmentFeed = current_feed * max_over_speed_factor
                                            
                                            
                                        if gradual_speed:
                                            if segmentFeed > (current_feed * max_over_speed_factor):
                                                segmentFeed = current_feed * max_over_speed_factor
                                            if segmentFeed < (current_feed * min_over_speed_factor):
                                                segmentFeed = current_feed * min_over_speed_factor
                                            stringFeed = " F{}".format(int(segmentFeed))

                                    new_Line=new_Line + get_extrusion_command(segmentEnd.x, segmentEnd.y, segmentExtrusion) + stringFeed + "\n"
                                    lastPosition = segmentEnd

                                # MissingSegment
                                segmentLengthRatio = get_points_distance(lastPosition, currentPosition) / segmentLength
                                segmentFeed = current_feed / ( max_flow / 100 )
                                if segmentFeed < (current_feed * min_over_speed_factor):
                                    segmentFeed = current_feed * min_over_speed_factor
                                if gradual_speed:
                                    stringFeed = " F{}".format(int(segmentFeed))
                    
                                new_Line=new_Line+get_extrusion_command(currentPosition.x,currentPosition.y,segmentLengthRatio * extrusionLength * max_flow / 100) + stringFeed # + " ; Last line"
                                
                                lines[line_index] = new_Line
                                
                            else :
                                outPutLine = ""
                                # outPutLine = "; GradientInfill segmentSteps < 2\n"
                               
                                for element in splitLine:
                                    if "E" in element:
                                        outPutLine = outPutLine + "E" + str(round(extrusionLength * link_flow / 100, 5))
                                    else:
                                        outPutLine = outPutLine + element + " "
                                outPutLine = outPutLine # + "\n"
                                lines[line_index] = outPutLine
                                
                            # writtenToFile = 1
                            
                        # gyroid or honeycomb
                        # if infill_type == Infill.SMALL_SEGMENTS:
                        if infill_type == 1:
                            shortestDistance = min_distance_from_segment(Segment(lastPosition, currentPosition), perimeterSegments)

                            outPutLine = new_Line
                            if shortestDistance < gradient_thickness:
                                for element in splitLine:
                                    if "E" in element:
                                        newE = float(element[1:]) * mapRange((0, gradient_thickness), (max_flow / 100, min_flow / 100), shortestDistance)
                                        segmentFeed = current_feed / mapRange((0, gradient_thickness), (max_flow / 100, min_flow / 100), shortestDistance)
                                        if gradual_speed:
                                            if segmentFeed > (current_feed * max_over_speed_factor):
                                                segmentFeed = current_feed * max_over_speed_factor
                                            if segmentFeed < (current_feed * min_over_speed_factor):
                                                segmentFeed = current_feed * min_over_speed_factor
                                            stringFeed = " F{}".format(int(segmentFeed))

                                        outPutLine = outPutLine + "E" + str(round(newE, 5))
                                        # test if F already define in line
                                        if not " F" in outPutLine and gradual_speed:
                                            outPutLine = outPutLine + stringFeed
                                    else:
                                        outPutLine = outPutLine + element + " "

                                outPutLine = outPutLine # + "\n"
                                lines[line_index] = outPutLine
                    #
                    # comment like ;MESH:NONMESH 
                    #
                    if ";" in currentLine:
                        currentSection = Section.NOTHING
                        lines[line_index] = currentLine # other Comment 
                #
                # line with move
                #
                if "X" in currentLine and "Y" in currentLine and ("G1" in currentLine or "G0" in currentLine):
                    lastPosition = getXY(currentLine)

            final_lines = "\n".join(lines)
            data[layer_index] = final_lines
        return data
