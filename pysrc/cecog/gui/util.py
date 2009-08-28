"""
                          The CellCognition Project
                  Copyright (c) 2006 - 2009 Michael Held
                   Gerlich Lab, ETH Zurich, Switzerland

           CellCognition is distributed under the LGPL License.
                     See trunk/LICENSE.txt for details.
              See trunk/AUTHORS.txt for author contributions.
"""

__author__ = 'Michael Held'
__date__ = '$Date$'
__revision__ = '$Rev$'
__source__ = '$URL::                                                          $'

__all__ = ['DEFAULT_COLORS',
           'STYLESHEET_CARBON',
           'STYLESHEET_NATIVE_MODIFIED',
           'CoordinateHolder',
           'StyledButton',
           'StyledComboBox',
           'StyledDialog',
           'StyledFrame',
           'StyledLabel',
           'StyledSideFrame',
           'numpy_to_qimage',
           ]

#-------------------------------------------------------------------------------
# standard library imports:
#
import sys
import os

#-------------------------------------------------------------------------------
# extension module imports:
#
import numpy

from PyQt4.QtGui import *
from PyQt4.QtCore import *
from PyQt4.Qt import *

#-------------------------------------------------------------------------------
# cecog imports:
#


#-------------------------------------------------------------------------------
# constants:
#

DEFAULT_COLORS = [QColor(255,0,0), QColor(0,255,0), QColor(0,0,255),
                  QColor(0,0,0), QColor(255,255,255)]

STYLESHEET_NATIVE_MODIFIED = \
"""
QToolBox::tab {
     background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                 stop: 0 #E1E1E1, stop: 0.4 #DDDDDD,
                                 stop: 0.5 #D8D8D8, stop: 1.0 #D3D3D3);
     border: 1px solid darkgrey;
     border-radius: 4px;
     color: #333333;
     padding-left: 5px;
}

QToolBox::tab:selected {
     background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                 stop: 0 #F2F2F2, stop: 0.4 #DDDDDD,
                                 stop: 0.5 #D8D8D8, stop: 1.0 #999999);
     font: bold;
     color: #000000;
}

StyledDialog {
     background: #333333;
}

StyledFrame {
     background: #000000;
}

StyledSideFrame {
     background: #DDDDDD;
     border: 1px solid darkgrey;
     border-radius: 4px;
     padding: 0px;
     margin: 0px;
 }

PositionFrame {
     background: #DDDDDD;
     border: 1px solid darkgrey;
     border-radius: 4px;
     padding: 0px;
     margin: 0px;
 }

ImageViewer {
     border: 0;
}
"""

STYLESHEET_CARBON = \
"""
MainWindow {
    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                stop: 0 #424242, stop: 0.4 #222222,
                                stop: 0.5 #282828, stop: 1.0 #111111);
    background-image: url(':background_carbon');
    color: white;
}

QTabBar::tab {
     background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                 stop: 0 #313131, stop: 0.4 #222222,
                                 stop: 0.5 #282828, stop: 1.0 #232323);
     border: 1px solid #999999;
     border-radius: 4px;
     color: #999999;
     padding: 2px;
     margin: 2px;
     min-width: 9ex;
     font: bold;
}

QTabBar::tab:selected {
     background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                 stop: 0 #424242, stop: 0.4 #222222,
                                 stop: 0.5 #282828, stop: 1.0 #111111);
     color: #FFFFFF;
     margin: 0px;
}

QToolBox::tab {
     background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                 stop: 0 #313131, stop: 0.4 #222222,
                                 stop: 0.5 #282828, stop: 1.0 #232323);
     border: 1px solid #999999;
     border-radius: 4px;
     color: #999999;
     padding-left: 5px;
     margin: 2px;
}

QToolBox::tab:selected {
     background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                 stop: 0 #424242, stop: 0.4 #222222,
                                 stop: 0.5 #282828, stop: 1.0 #111111);
     font: bold;
     color: #FFFFFF;
     margin: 0px;
}

StyledComboBox {
    border: 1px solid darkgray;
    border-radius: 3px;
    padding: 1px 1px 1px 20px;
    margin: 1px;
    alignment: center;
    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                stop: 0 #313131, stop: 0.4 #222222,
                                stop: 0.5 #282828, stop: 1.0 #232323);
    icon-size: 50px;
    selection-background-color: #444444;
    color: white;
}

StyledComboBox::drop-down {
    width: 20px;
    border-left-width: 1px;
    border-left-color: darkgray;
    border-left-style: solid;
    border-top-right-radius: 3px;
    border-bottom-right-radius: 3px;
    background: #222222;
}

StyledComboBox QAbstractItemView {
    border: 1px solid darkgray;
    background: #222222;
    spacing: 0;
}

QToolBox {
    background: transparent;
}

QSlider {
    color: blue;
}

QSlider::groove {
    color: white;
}

QSlider::handle {
    color: white;
}

StyledFrame {
    color: white;
}

StyledLabel {
    color: white;
}

StyledButton {
    color: white;
    border: 1px solid darkgray;
    border-radius: 3px;
    /*padding: 1px 1px 1px 20px;*/
    margin: 1px;
    alignment: center;
    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                stop: 0 #313131, stop: 0.4 #222222,
                                stop: 0.5 #282828, stop: 1.0 #232323);
}

StyledDialog {
     background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                 stop: 0 #323232, stop: 0.3 #222222,
                                 stop: 0.4 #111111, stop: 1.0 #000000);
     color: #000000;
}

StyledSideFrame {
    border: 1px solid darkgrey;
    border-radius: 4px;
    padding: 0px;
    margin: 0px;
    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                stop: 0 #424242, stop: 1.0 #111111);
    color: white;
}

PositionFrame {
    border: 1px solid darkgrey;
    border-radius: 4px;
    padding: 0px;
    margin: 0px;
    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                stop: 0 #424242, stop: 0.4 #222222,
                                stop: 0.5 #282828, stop: 1.0 #111111);
    color: white;
}

ImageViewer {
    border: 0;
    color: white;
}

QStatusBar {
    background-color: #333333;
    color: white;
}

"""


#-------------------------------------------------------------------------------
# functions:
#


def numpy_to_qimage(data, colors=None):
    h, w = data.shape[:2]
    print data.shape, data.ndim
    if data.dtype == numpy.uint8:
        if data.ndim == 2:
            shape = (h, numpy.ceil(w / 4.) * 4)
            if shape != data.shape:
                image = numpy.zeros(shape, numpy.uint8, 'C')
                image[:,:w] = data
            else:
                image = data
            format = QImage.Format_Indexed8
            #colors = [QColor(i,i,i) for i in range(256)]
        elif data.ndim == 3:
            shape = (h, int(numpy.ceil(w / 4.) * 4), data.shape[2])
            if data.shape[2] == 3:
                if shape != data.shape:
                    image = numpy.zeros(shape, numpy.uint8, 'C')
                    image[:,:w,:] = data[:,:,:]
                    print data
                    print image
                else:
                    image = data
                format = QImage.Format_RGB888
            elif data.shape[2] == 4:
                format = QImage.Format_RGB32

    qimage = QImage(image, w, h, format)
    if not colors is None:
        for idx, col in enumerate(colors):
            qimage.setColor(idx, col.rgb())
    return qimage

#-------------------------------------------------------------------------------
# classes:
#


class StyledLabel(QLabel):
    pass

class StyledFrame(QFrame):
    pass

class StyledDialog(QDialog):
    pass

class StyledSideFrame(QFrame):
    pass

class StyledComboBox(QComboBox):
    pass

class StyledTabWidget(QTabWidget):
    pass

class StyledButton(QPushButton):
    pass

class CoordinateHolder(object):
    position = None
    time = None
    channel = None
    zslice = None


#-------------------------------------------------------------------------------
# main:
#
