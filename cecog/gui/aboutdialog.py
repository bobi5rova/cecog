"""
aboutdialog.py
"""

__author__ = 'rudolf.hoefler@gmail.com'
__copyright__ = ('The CellCognition Project'
                 'Copyright (c) 2006 - 2012'
                 'Gerlich Lab, IMBA Vienna, Austria'
                 'see AUTHORS.txt for contributions')
__licence__ = 'LGPL'
__url__ = 'www.cellcognition.org'

from PyQt4 import QtGui
from PyQt4.QtCore import Qt

from cecog import version


class CecogAboutDialog(QtGui.QDialog):

    def __init__(self, *args, **kw):
        super(CecogAboutDialog, self).__init__(*args, **kw)
        self.setBackgroundRole(QtGui.QPalette.Dark)
        self.setStyleSheet('background: #000000; '
                           'background-image: url(:cecog_about)')
        self.setWindowTitle('About CecogAnalyzer')
        self.setFixedSize(400, 300)
        layout = QtGui.QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        label1 = QtGui.QLabel(self)
        label1.setStyleSheet('background: transparent;')
        label1.setAlignment(Qt.AlignCenter)
        label1.setText('CecogAnalyzer\nVersion %s\n\n'
                       'Copyright (c) 2006 - 2011\n' %version.version)

        label2 = QtGui.QLabel(self)
        label2.setStyleSheet('background: transparent;')
        label2.setTextFormat(Qt.AutoText)
        label2.setOpenExternalLinks(True)
        label2.setAlignment(Qt.AlignCenter)

        label2.setText(('<style>a { color: green; } a:visited { color: green;'
                        ' }</style><a href="http://cellcognition.org">'
                        'cellcognition.org</a><br>'))
        layout.addWidget(label1, 1, 0)
        layout.addWidget(label2, 2, 0)
        layout.setAlignment(Qt.AlignCenter|Qt.AlignBottom)
        self.setLayout(layout)
