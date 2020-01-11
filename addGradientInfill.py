##################################################
## Gradient Infill for 3D prints
##################################################
## MIT license
##################################################
## Author: Stefan Hermann - CNC Kitchen
## Version: 1.0
##################################################

import re
from enum import Enum


class InfillType(Enum):
    SMALL_SEGMENTS = 1  # infill with small segments like honeycomb or gyroid
    LINEAR = 2  # linear infill like rectilinear or triangles


################ EDIT this section for your creation parameters
INPUT_FILE_NAME = "cloverleaf_wHole_gyroid.gcode"
OUTPUT_FILE_NAME = "BOWDEN_cloverleaf_wHole_gyroid.gcode"

infillType = InfillType.SMALL_SEGMENTS

maxFlow = 350 #maximum extrusion flow
minFlow = 50 #minimum extrusion flow
gradientThickness = 6 #thickness of the gradient (max to min) in mm
gradientDiscretization = 4 #only applicable for linear infills; number of segments within the gradient( segmentLength=gradientThickness/gradientDiscretization); use sensible values to not overload the printer
###############################################################


class Section(Enum):
    NOTHING = 0
    INNER_WALL = 1
    INFILL = 2


def dist(x1, y1, x2, y2, x3, y3): # calculate the distance of a point to line with non-infinite length
    px = x2-x1
    py = y2-y1
    norm = px*px + py*py
    u =  ((x3 - x1) * px + (y3 - y1) * py) / float(norm)
    if u > 1:
        u = 1
    elif u < 0:
        u = 0
    x = x1 + u * px
    y = y1 + u * py
    dx = x - x3
    dy = y - y3
    dist = (dx*dx + dy*dy)**.5
    return dist


def getXY(currentLine): #Returns the X and Y value of the current line
    elementX = re.findall(r"[X]\d*\.*\d*", currentLine)[0][1:]
    elementY = re.findall(r"[Y]\d*\.*\d*", currentLine)[0][1:]
    return [float(elementX),float(elementY)]


def mapRange( a, b, s):
    (a1, a2), (b1, b2) = a, b
    return  b1 + ((s - a1) * (b2 - b1) / (a2 - a1))


def main():
    currentSection = Section.NOTHING
    lastPosition = [[-10000, -10000]]
    gradientDiscretizationLength = gradientThickness/gradientDiscretization

    with open(INPUT_FILE_NAME, "r") as gcodeFile, open(OUTPUT_FILE_NAME, "w+") as outputFile:
        for currentLine in gcodeFile:
            writtenToFile = 0
            if ";LAYER:" in currentLine:
                perimeterSegments = []
            #Look for the definition of the inner contour
            if ";TYPE:WALL-INNER" in currentLine:
                currentSection = Section.INNER_WALL
                #perimeterSegments = []
            #line with extrusion
            if (currentSection == Section.INNER_WALL
                    and "G1" in currentLine
                    and " X" in currentLine
                    and "Y" in currentLine
                    and "E" in currentLine):

                    perimeterSegments.append([getXY(currentLine), lastPosition[0]])
            #Inner wall definition end?
            if ";TYPE:WALL-OUTER" in currentLine:
                currentSection = Section.NOTHING
            #Infill segment
            if ";TYPE:FILL" in currentLine:
                currentSection = Section.INFILL
                outputFile.write(currentLine)
                continue
            if currentSection == Section.INFILL:
                if "F" in currentLine and "G1" in currentLine:
                    outputFile.write("G1 F" + re.findall(r"[F]\d*\.*\d*", currentLine)[0][1:] + "\n")
                if "E" in currentLine and "G1" in currentLine and " X" in currentLine and "Y" in currentLine:
                    currentPosition = getXY(currentLine)

                    if infillType == InfillType.LINEAR:
                        #find extrusion length
                        splitLine = currentLine.split(" ")
                        for element in splitLine:
                            if "E" in element:
                                extrusionLength = float(element[1:len(element)])
                        segmentLength = ((lastPosition[0][0]-currentPosition[0])**2+(lastPosition[0][1]-currentPosition[1])**2)**.5
                        segmentSteps = segmentLength / gradientDiscretizationLength
                        extrusionLengthPerSegment = extrusionLength / segmentSteps
                        segmentDirection = [(currentPosition[0] - lastPosition[0][0]) / segmentLength * gradientDiscretizationLength, (currentPosition[1] - lastPosition[0][1]) / segmentLength * gradientDiscretizationLength]
                        if segmentSteps >= 2:
                            for step in range(int(segmentSteps)):
                                segmentEnd = [lastPosition[0][0] + segmentDirection[0], lastPosition[0][1] + segmentDirection[1]]
                                inbetweenPoint = [lastPosition[0][0] + (segmentEnd[0] - lastPosition[0][0])/2, lastPosition[0][1] + (segmentEnd[1] - lastPosition[0][1])/2]
                                #shortest distance from any inner perimeter
                                shortestDistance = 10000
                                for perimeterSegment in perimeterSegments:
                                    distance = dist(perimeterSegment[0][0],perimeterSegment[0][1],perimeterSegment[1][0],perimeterSegment[1][1],inbetweenPoint[0], inbetweenPoint[1])
                                    if distance < shortestDistance:
                                        shortestDistance = distance
                                if shortestDistance < gradientThickness:
                                    outputFile.write("G1 X" + str(round(segmentEnd[0],3)) + " Y" + str(round(segmentEnd[1],3)) + " E" + str(round(extrusionLengthPerSegment * mapRange((0, gradientThickness), (maxFlow/100, minFlow/100), shortestDistance),5)) + "\n")
                                else:
                                    outputFile.write("G1 X" + str(round(segmentEnd[0],3)) + " Y" + str(round(segmentEnd[1],3)) + " E" + str(round(extrusionLengthPerSegment * minFlow/100,5)) + "\n" )
                                lastPosition[0] = [segmentEnd[0],segmentEnd[1]]
                            #MissingSegment
                            segmentLengthRatio = ((lastPosition[0][0]-currentPosition[0])**2+(lastPosition[0][1]-currentPosition[1])**2)**.5 / segmentLength
                            # inbetweenPoint = [lastPosition[0][0] + (currentPosition[0] - lastPosition[0][0])/2, lastPosition[0][1] + (currentPosition[1] - lastPosition[0][1])/2]
                            outputFile.write("G1 X" + str(round(currentPosition[0],3)) + " Y" + str(round(currentPosition[1],3)) + " E" + str(round(segmentLengthRatio * extrusionLength * maxFlow/100,5)) + "\n")
                        else:
                            splitLine = currentLine.split(" ")
                            outPutLine = ""
                            for element in splitLine:
                                if "E" in element:
                                    outPutLine = outPutLine + "E" + str(round(extrusionLength * maxFlow/100,5))
                                else:
                                    outPutLine = outPutLine + element + " "
                            outPutLine = outPutLine + "\n"
                            outputFile.write(outPutLine)
                        writtenToFile = 1

                    # gyroid or honeycomb
                    if infillType == InfillType.SMALL_SEGMENTS:
                        inbetweenPoint = [lastPosition[0][0] + (currentPosition[0] - lastPosition[0][0])/2, lastPosition[0][1] + (currentPosition[1] - lastPosition[0][1])/2]
                        #shortest distance from any inner perimeter
                        shortestDistance = 10000
                        for perimeterSegment in perimeterSegments:
                            distance = dist(perimeterSegment[0][0],perimeterSegment[0][1],perimeterSegment[1][0],perimeterSegment[1][1],inbetweenPoint[0], inbetweenPoint[1])
                            if distance < shortestDistance:
                                shortestDistance = distance
                        newE = 0
                        outPutLine = ""
                        if shortestDistance < gradientThickness:
                            splitLine = currentLine.split(" ")
                            for element in splitLine:
                                if "E" in element:
                                    newE = float(element[1:len(element)]) * mapRange((0, gradientThickness), (maxFlow/100, minFlow/100), shortestDistance)
                                    outPutLine = outPutLine + "E" + str(round(newE,5))
                                else:
                                    outPutLine = outPutLine + element + " "
                            outPutLine = outPutLine + "\n"
                            outputFile.write(outPutLine)
                            writtenToFile = 1
                if ";" in currentLine:
                    currentSection = Section.NOTHING


            #line with move
            if " X" in currentLine and " Y" in currentLine and ("G1" in currentLine or "G0" in currentLine):
                lastPosition[0] = getXY(currentLine)

            #write uneditedLine
            if writtenToFile == 0:
                outputFile.write(currentLine)


if __name__ == '__main__':
    main()
