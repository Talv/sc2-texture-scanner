from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
    QLabel, QWidget, QMessageBox, QFileDialog, QComboBox, QPushButton, QProgressBar, QCheckBox, QSlider
)
from PyQt5.QtCore import (
    pyqtSlot, pyqtSignal, QThread, Qt
)
import os
import sys
from scanner import T3TextureReader, readTextureList, ScriptWriter, writeImage, readSnowData
import multiprocessing


class SWorker(QThread):
    progressUpdate = pyqtSignal(object)
    finished = pyqtSignal()

    def __init__(self):
        QThread.__init__(self)
        self.mapPath = None
        self.generateImage = None
        self.t3Reader = T3TextureReader()

    def run(self):
        def progressR(pcurrent, pmax):
            self.progressUpdate.emit(pcurrent / pmax * 50)
            return True

        def progressW(pcurrent, pmax):
            self.progressUpdate.emit(50 + pcurrent / pmax * 50)
            return True

        self.t3Reader.open(os.path.join(self.mapPath, "t3TextureMasks"))
        self.t3Reader.readMap()
        wr = ScriptWriter(self.t3Reader)
        wr.writeScript(os.path.join(self.mapPath, "TextureMap.galaxy"), self.t3Reader.snowIndex, self.t3Reader.snowValue)
        if self.generateImage:
            writeImage(os.path.join(os.getcwd(), "TextureMapPreview.png"), self.t3Reader)
        self.finished.emit()


class TSWindow(QMainWindow):
    def __init__(self, parent=None):
        self.mapPath = None

        self.sworker = SWorker()
        self.sworker.finished.connect(self.onFinish)
        self.sworker.progressUpdate.connect(self.onProgress)

        QMainWindow.__init__(self, parent)
        self.resize(380, 340)
        self.setWindowTitle("Texture scanner for SC2 Ice Escapes v1.2.0")

        self.layout = QVBoxLayout()

        self.statusBar().showMessage("Map not loaded.")

        self.selectMapBtn = QPushButton('Select map directory')
        self.selectMapBtn.clicked.connect(self.chooseT3TMFile)
        # self.selectMapBtn.resize(self.selectMapBtn.sizeHint())
        # self.selectMapBtn.move(20, 20)

        self.infoLabel = QLabel("")
        # self.infoLabel.move(20, 60)

        self.generateTMBtn = QPushButton('Generate texture map')
        self.generateTMBtn.clicked.connect(self.generateTM)
        self.generateTMBtn.setEnabled(False)

        # self.progressBar = QProgressBar()
        # self.progressBar.setMinimum(1)
        # self.progressBar.setMaximum(100)

        self.snowLabel = QLabel("Select snow texture:")
        self.snowCbx = QComboBox()

        tmpLayout = QHBoxLayout()
        tmpContainer = QWidget()
        tmpContainer.setLayout(tmpLayout)
        tmpLayout.addWidget(self.snowLabel)
        tmpLayout.addWidget(self.snowCbx)

        self.layout.addWidget(self.selectMapBtn)
        self.layout.addWidget(self.infoLabel)
        self.layout.addWidget(tmpContainer)
        self.layout.addWidget(self.generateTMBtn)
        # self.layout.addWidget(self.progressBar)

        self.generateImageCh = QCheckBox()
        self.generateImageCh.setText("Generate PNG image for preview (will slow down the process)")
        self.layout.addWidget(self.generateImageCh)

        self.snowValueSld = QSlider()
        self.snowValueSld.setRange(1, 15)
        self.snowValueSld.setOrientation(Qt.Horizontal)
        self.snowValueSld.show
        self.layout.addWidget(self.snowValueSld)
        self.snowValueSld.valueChanged.connect(self.snowValueChanged)

        self.snowValueLbl = QLabel()
        self.snowValueLbl.setFixedHeight(40)
        self.layout.addWidget(self.snowValueLbl)

        # self.snowValueSld.setValue(13)

        test = QWidget()
        test.setLayout(self.layout)
        self.setCentralWidget(test)

    def showMessage(self, msg):
        msgBox = QMessageBox(self)
        msgBox.setText(msg)
        msgBox.exec_()

    @pyqtSlot()
    def chooseT3TMFile(self):
        mapPath = QFileDialog.getExistingDirectory(self, 'Choose your map', os.getcwd())
        self.snowCbx.clear()
        if not mapPath:
            return
        if not os.path.isfile(os.path.join(mapPath, "t3Terrain.xml")):
            self.showMessage("It's not a valid SC2 map directory.")
            self.generateTMBtn.setEnabled(False)
            self.statusBar().showMessage("Map not loaded.")
            self.infoLabel.setText("")
        else:
            self.mapPath = mapPath
            textureInfo = []
            for i, item in enumerate(
                    readTextureList(os.path.join(self.mapPath, "t3Terrain.xml"))
                ):
                idsc = "Slot %d - %s" % (i, item)
                textureInfo.append(idsc)
                self.snowCbx.addItem(idsc)
            self.infoLabel.setText("\n".join(textureInfo))

            if os.path.isfile(os.path.join(self.mapPath, "TextureMap.galaxy")):
                try:
                    snowInfo = readSnowData(os.path.join(self.mapPath, "TextureMap.galaxy"))
                    self.snowCbx.setCurrentIndex(snowInfo[0])
                    self.snowValueSld.setValue(snowInfo[1])
                except AttributeError:
                    pass

            self.statusBar().showMessage("ready!")
            self.generateTMBtn.setEnabled(True)

    @pyqtSlot()
    def generateTM(self):
        # self.progressBar.setValue(0)
        self.statusBar().showMessage("working..")
        self.sworker.mapPath = self.mapPath
        self.sworker.generateImage = self.generateImageCh.isChecked()
        self.sworker.t3Reader.snowIndex = self.snowCbx.currentIndex()
        self.sworker.t3Reader.snowValue = self.snowValueSld.value()
        self.sworker.start()

    @pyqtSlot(int)
    def snowValueChanged(self, val):
        self.snowValueLbl.setText("Snow detection threshold: %d%% \n(the higher value, the more opaque snow has to be for its registration)" % int(val / 15 * 100))

    def onFinish(self):
        # self.progressBar.setValue(0)
        self.statusBar().showMessage("ready!")
        self.showMessage("Generating texture map has been completed!")
        # self.progressBar.setValue(0)

    def onProgress(self, pcurrent):
        # self.progressBar.setValue(pcurrent)
        pass


# Workaround for issue regarding *multiprocessing* on windows
# Module multiprocessing is organized differently in Python 3.4+
try:
    # Python 3.4+
    if sys.platform.startswith('win'):
        import multiprocessing.popen_spawn_win32 as forking
    else:
        import multiprocessing.popen_fork as forking
except ImportError:
    import multiprocessing.forking as forking

if sys.platform.startswith('win'):
    # First define a modified version of Popen.
    class _Popen(forking.Popen):
        def __init__(self, *args, **kw):
            if hasattr(sys, 'frozen'):
                # We have to set original _MEIPASS2 value from sys._MEIPASS
                # to get --onefile mode working.
                os.putenv('_MEIPASS2', sys._MEIPASS)
            try:
                super(_Popen, self).__init__(*args, **kw)
            finally:
                if hasattr(sys, 'frozen'):
                    # On some platforms (e.g. AIX) 'os.unsetenv()' is not
                    # available. In those cases we cannot delete the variable
                    # but only set it to the empty string. The bootloader
                    # can handle this case.
                    if hasattr(os, 'unsetenv'):
                        os.unsetenv('_MEIPASS2')
                    else:
                        os.putenv('_MEIPASS2', '')

    # Second override 'Popen' class with our modified version.
    forking.Popen = _Popen

if __name__ == '__main__':
    multiprocessing.freeze_support()
    app = QApplication(sys.argv)
    wnd = TSWindow()
    wnd.show()
    sys.exit(app.exec_())
