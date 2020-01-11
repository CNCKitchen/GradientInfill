# GradientInfill
![alt text](https://static1.squarespace.com/static/5d88f1f13db677155dee50fa/t/5e184edf208b5e01f31462a2/1578651390859/vlcsnap-2020-01-10-11h15m40s688.png?format=2500w)

This a Python script that post-processes existing G-Code to add gradient infill for 3D prints.

Watch my YouTube video about it: https://youtu.be/hq53gsYREHU

# Important Notes

In its current for it only works with G-Code files generated with CURA due to the comments CURA puts into the G-Code files.

It is also important to make sure that the "Walls" are printed before the "Infill" ("Infill before Walls" OFF).
For this script to work, also activate "Relative Extrusion" under "Special Modes".

Further instructions can be found on my website: http://cnckitchen.com/blog/gradient-infill-for-3d-prints