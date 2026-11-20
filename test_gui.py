"""Prueba de arranque de la interfaz en un entorno con Qt disponible."""
import os
import sys
import unittest

class GuiSmokeTests(unittest.TestCase):
    def test_launch_and_controls(self):
        from PySide6.QtWidgets import QApplication
        from app import MainWindow
        app = QApplication.instance() or QApplication(sys.argv[:1])
        window = MainWindow()
        self.assertIn('Comunicando Clips', window.windowTitle())
        self.assertEqual(window.count.value(), 15)
        self.assertEqual(window.minimum.value(), 30)
        self.assertEqual(window.maximum.value(), 90)
        self.assertTrue(window.subtitles.isChecked())
        self.assertFalse(window.approve.isEnabled())
        self.assertIsNotNone(window.restore)
        window.show()
        app.processEvents()
        window.close()

if __name__ == '__main__':
    unittest.main()
